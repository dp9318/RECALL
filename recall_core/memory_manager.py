"""Main Memory Manager orchestration for RECALL Core."""

from __future__ import annotations

import contextlib
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from contracts.base import ConflictResolutionStatus, Result, PaginatedResult, PaginationParams, Scope
from contracts.conflict import ConflictResolutionRequest, ConflictResolutionResult
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
    InstructionStatus,
)
from contracts.memory import Memory, MemoryCreateRequest, MemoryLineage, MemorySearchParams, MemoryStatus, MemoryUpdateRequest
from contracts.project import Project, ProjectCreateRequest, ProjectUpdateRequest, Session, SessionCreateRequest, SessionUpdateRequest
from contracts.retrieval import (
    AssembledContext,
    CompactRequest,
    CompactResult,
    ContextAssemblyRequest,
    RetrievalRequest,
    RetrievalResult,
    UpdateContextRequest,
    UpdateContextResult,
)
from contracts.capture import CaptureEventRequest, CaptureEventResponse
from .capture_service import CaptureService
from .context_assembly import ContextAssemblyService
from .exceptions import (
    ConflictResolutionError,
    InstructionNotFoundError,
    MemoryNotFoundError,
    PersistenceError,
    ProjectNotFoundError,
    RetrievalError,
    SessionNotFoundError,
    ValidationError,
)
from .instruction_service import CustomInstructionService
from database.repositories import (
    CustomInstructionRepository,
    MemoryRepository,
    ProjectRepository,
    SemanticIndexRepository,
    SessionRepository,
    UnitOfWork,
)
from intelligence.conflict import ConflictResolutionService
from intelligence.retrieval import RetrievalService


class MemoryManager:
    """
    Central orchestration layer for RECALL memory operations.

    Coordinates persistence, retrieval, conflict resolution, custom instructions,
    and context assembly. Does not implement storage, retrieval algorithms,
    or conflict resolution logic directly - delegates to specialized services.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWork,
        retrieval_service: RetrievalService,
        conflict_service: ConflictResolutionService,
        semantic_index: SemanticIndexRepository,
    ):
        self._uow = unit_of_work
        self._retrieval_service = retrieval_service
        self._conflict_service = conflict_service
        self._semantic_index = semantic_index

        # Initialize sub-services
        self._instruction_service = CustomInstructionService(unit_of_work.custom_instructions)
        self._context_assembly = ContextAssemblyService(
            memory_repo=unit_of_work.memories,
            project_repo=unit_of_work.projects,
            session_repo=unit_of_work.sessions,
            retrieval_service=retrieval_service,
        )
        self._capture_service = CaptureService(unit_of_work, self)

    def capture_memory(self, request: CaptureEventRequest) -> Result[CaptureEventResponse]:
        """Capture an eligible event through the conservative automatic capture pipeline."""
        return self._capture_service.capture(request)


    # --- Project Operations ---

    def create_project(self, request: ProjectCreateRequest) -> Result[Project]:
        """Create a new project."""
        return self._uow.projects.create(request)

    def get_project(self, project_id: UUID) -> Result[Optional[Project]]:
        """Get a project by ID."""
        return self._uow.projects.get(project_id)

    def get_project_by_name(self, name: str) -> Result[Optional[Project]]:
        """Get a project by name."""
        return self._uow.projects.get_by_name(name)

    def resolve_or_create_project(
        self,
        name: str,
        description: Optional[str] = None,
        project_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Result[Project]:
        """Atomically resolve an existing project or create a new one under a write transaction.

        Serializes across concurrent processes sharing canonical storage
        using UnitOfWork.begin() before looking up by name.
        Preserves canonical project identity, normalized-name lookup, and conflict handling.
        """
        try:
            with self._uow.begin():
                if project_id is not None:
                    existing = self._uow.projects.get(project_id)
                    if existing.success and existing.value is not None:
                        proj = existing.value
                        if proj.name.strip().lower() != name.strip().lower():
                            return Result.err(
                                f"Project '{project_id}' already exists with name '{proj.name}', "
                                f"which conflicts with requested name '{name}'"
                            )
                        return Result.ok(proj)

                    by_name = self._uow.projects.get_by_name(name)
                    if by_name.success and by_name.value is not None:
                        if by_name.value.id != project_id:
                            return Result.err(
                                f"A project named '{name}' already exists with ID '{by_name.value.id}', "
                                f"which conflicts with requested ID '{project_id}'"
                            )

                    req = ProjectCreateRequest(
                        id=project_id,
                        name=name,
                        description=description,
                        metadata=metadata or {},
                    )
                    return self._uow.projects.create(req)

                by_name = self._uow.projects.get_by_name(name)
                if by_name.success and by_name.value is not None:
                    return Result.ok(by_name.value)

                req = ProjectCreateRequest(
                    name=name,
                    description=description,
                    metadata=metadata or {},
                )
                return self._uow.projects.create(req)
        except Exception as exc:
            return Result.err(f"Failed to resolve or create project: {exc}")

    def update_project(self, project_id: UUID, request: ProjectUpdateRequest) -> Result[Optional[Project]]:
        """Update a project."""
        return self._uow.projects.update(project_id, request)

    def delete_project(self, project_id: UUID) -> Result[bool]:
        """Delete a project and clean up related semantic index entries."""
        try:
            # 1. Verify project exists
            project_res = self._uow.projects.get(project_id)
            if not project_res.success:
                return Result.err(project_res.error or "Failed to check project existence")
            if not project_res.value:
                return Result.err("Project not found")

            # 2. Collect project memory IDs before canonical deletion cascades
            memory_ids: list[UUID] = []
            try:
                memories_res = self._uow.memories.search(
                    MemorySearchParams(project_id=project_id, limit=10000)
                )
                if memories_res.success and memories_res.value:
                    memory_ids = [m.id for m in memories_res.value.items]
            except Exception:
                pass

            # 3. Canonical deletion in canonical storage (cascades sessions, memories, instructions via foreign keys)
            delete_res = self._uow.projects.delete(project_id)
            if not delete_res.success or not delete_res.value:
                return delete_res

            # 4. Clean up derived semantic index (best effort, canonical deletion succeeded)
            if hasattr(self._semantic_index, "remove_by_project"):
                try:
                    self._semantic_index.remove_by_project(project_id)
                except Exception:
                    pass
            elif hasattr(self._semantic_index, "remove_memory"):
                for m_id in memory_ids:
                    try:
                        self._semantic_index.remove_memory(m_id)
                    except Exception:
                        pass

            return Result.ok(True)
        except Exception as exc:
            return Result.err(f"Project deletion failed: {exc}")

    def list_projects(self, limit: int = 50, offset: int = 0) -> Result[list[Project]]:
        """List projects."""
        params = PaginationParams(limit=limit, offset=offset)
        result = self._uow.projects.list(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Failed to list projects")

    def list_projects_paginated(self, limit: int = 50, offset: int = 0) -> Result[PaginatedResult[Project]]:
        """List projects with full pagination metadata."""
        params = PaginationParams(limit=limit, offset=offset)
        return self._uow.projects.list(params)

    def get_project_memory_count(
        self,
        project_id: UUID,
        status: Optional[MemoryStatus] = MemoryStatus.ACTIVE,
    ) -> Result[int]:
        """Get the count of memories for a project filtered by status."""
        try:
            if hasattr(self._uow.memories, "count"):
                c_res = self._uow.memories.count(project_id=project_id, status=status)
                if c_res.success and c_res.value is not None:
                    return Result.ok(c_res.value)
                if not c_res.success:
                    return Result.err(c_res.error or "Failed to count project memories")

            search_res = self._uow.memories.search(
                MemorySearchParams(project_id=project_id, status=status, limit=1)
            )
            if search_res.success and search_res.value:
                return Result.ok(search_res.value.total)
            return Result.err(search_res.error or "Failed to count project memories")
        except Exception as exc:
            return Result.err(f"Failed to count project memories: {exc}")

    def get_project_session_count(self, project_id: UUID) -> Result[int]:
        """Get the count of sessions registered for a project."""
        try:
            sess_res = self._uow.sessions.list(PaginationParams(limit=1), project_id=project_id)
            if sess_res.success and sess_res.value:
                return Result.ok(sess_res.value.total)
            return Result.err(sess_res.error or "Failed to count project sessions")
        except Exception as exc:
            return Result.err(f"Failed to count project sessions: {exc}")

    # --- Session Operations ---

    def create_session(self, request: SessionCreateRequest) -> Result[Session]:
        """Create a new session."""
        return self._uow.sessions.create(request)

    def get_session(self, session_id: UUID) -> Result[Optional[Session]]:
        """Get a session by ID."""
        return self._uow.sessions.get(session_id)

    def get_active_session(self, project_id: UUID) -> Result[Optional[Session]]:
        """Get the active session for a project."""
        return self._uow.sessions.get_active_for_project(project_id)

    def update_session(self, session_id: UUID, request: SessionUpdateRequest) -> Result[Optional[Session]]:
        """Update a session."""
        return self._uow.sessions.update(session_id, request)

    def end_session(self, session_id: UUID) -> Result[Optional[Session]]:
        """End a session."""
        return self._uow.sessions.update(session_id, SessionUpdateRequest(ended_at=datetime.now(timezone.utc)))

    def list_sessions_paginated(
        self,
        project_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[PaginatedResult[Session]]:
        """List sessions with full pagination metadata, optionally scoped to a project."""
        params = PaginationParams(limit=limit, offset=offset)
        return self._uow.sessions.list(params, project_id=project_id)

    def get_session_memory_count(
        self,
        session_id: UUID,
        include_historical: bool = True,
    ) -> Result[int]:
        """Get the count of memories captured during a specific session."""
        try:
            mem_res = self._uow.memories.search(
                MemorySearchParams(session_id=session_id, limit=1, include_historical=include_historical)
            )
            if mem_res.success and mem_res.value:
                return Result.ok(mem_res.value.total)
            return Result.err(mem_res.error or "Failed to count session memories")
        except Exception as exc:
            return Result.err(f"Failed to count session memories: {exc}")

    # --- Memory Operations ---

    def create_memory(self, request: MemoryCreateRequest) -> Result[Memory]:
        """Create a new memory in canonical storage and index into semantic index.

        Args:
            request: MemoryCreateRequest containing content, scope, project_id,
                session_id, memory_type, provenance, and optional supersedes_id.

        Returns:
            Result[Memory]: Success with the created canonical Memory DTO (and any
            semantic index metadata in result.metadata), or Result.err on failure.

        Side Effects:
            1. Writes record to canonical storage with status='active'.
            2. If supersedes_id is provided, removes superseded item from semantic index.
            3. Upserts representation of the new memory into semantic index.
            4. If semantic indexing fails, canonical creation still succeeds (best effort).
        """
        try:
            # Create in canonical storage
            result = self._uow.memories.create(request)
            if not result.success or not result.value:
                return Result.err(result.error or "Failed to create memory")

            memory = result.value

            # Index in semantic store (best effort). Canonical persistence has
            # succeeded, so a derived-index outage must not report creation as
            # failed and encourage callers to retry a write that already exists.
            index_metadata = {}
            if memory.supersedes_id is not None:
                try:
                    cleanup_result = self._semantic_index.remove_memory(
                        memory.supersedes_id
                    )
                    if not cleanup_result.success:
                        index_metadata["semantic_index_cleanup_error"] = (
                            cleanup_result.error or "Superseded memory cleanup failed"
                        )
                except Exception as cleanup_error:
                    index_metadata["semantic_index_cleanup_error"] = str(cleanup_error)
            try:
                index_result = self._semantic_index.index_memory(memory)
                if not index_result.success:
                    index_metadata["semantic_index_error"] = (
                        index_result.error or "Indexing failed"
                    )
            except Exception as index_error:
                index_metadata["semantic_index_error"] = str(index_error)

            return Result.ok(memory, metadata=index_metadata)

        except Exception as e:
            return Result.err(f"Memory creation failed: {str(e)}")

    def get_memory(self, memory_id: UUID) -> Result[Optional[Memory]]:
        """Get a memory by ID from canonical storage."""
        return self._uow.memories.get(memory_id)

    def get_memory_lineage(self, memory_id: UUID) -> Result[list[MemoryLineage]]:
        """Retrieve lineage graph relationships for a memory.

        Args:
            memory_id: UUID of the memory to query.

        Returns:
            Result[list[MemoryLineage]]: List of MemoryLineage records where the memory
            acts as either parent or child, supporting DAG exploration in API and UI.
        """
        if not isinstance(memory_id, UUID):
            try:
                memory_id = UUID(str(memory_id))
            except (ValueError, TypeError) as exc:
                return Result.err(f"Invalid memory ID: {exc}")
        return self._uow.memories.get_lineage(memory_id)

    def update_memory(self, memory_id: UUID, request: MemoryUpdateRequest) -> Result[Optional[Memory]]:
        """Update a memory."""
        try:
            result = self._uow.memories.update(memory_id, request)
            if not result.success or not result.value:
                return Result.err(result.error or "Failed to update memory")

            memory = result.value

            # Updating canonical state is authoritative; index maintenance is
            # best effort and can be reconciled by rebuilding the derived index.
            try:
                index_result = self._semantic_index.update_memory(memory)
                if not index_result.success:
                    return Result.ok(
                        memory,
                        metadata={"semantic_index_error": index_result.error or "Index update failed"},
                    )
            except Exception as index_error:
                return Result.ok(memory, metadata={"semantic_index_error": str(index_error)})

            return Result.ok(memory)

        except Exception as e:
            return Result.err(f"Memory update failed: {str(e)}")

    def delete_memory(self, memory_id: UUID) -> Result[bool]:
        """Soft-delete a memory in canonical storage and purge from semantic index.

        Args:
            memory_id: UUID of the memory to deactivate.

        Returns:
            Result[bool]: Result.ok(True) if the record was deactivated,
            Result.ok(False) if not found, or Result.err on failure.

        Side Effects:
            1. Updates canonical row status to 'deleted'.
            2. Best-effort removes the item from semantic index.
            3. Semantic index cleanup failures do not rollback canonical deletion.
        """
        try:
            # Canonical storage is the source of truth. Never remove a memory
            # from the derived index unless the canonical operation succeeded.
            delete_result = self._uow.memories.delete(memory_id)
            if not delete_result.success or not delete_result.value:
                return delete_result

            # The semantic index is derived and can be rebuilt. Cleanup failure
            # must not turn a successful canonical deletion into a false failure.
            try:
                index_result = self._semantic_index.remove_memory(memory_id)
                if not index_result.success:
                    return Result.ok(
                        delete_result.value,
                        metadata={"semantic_index_cleanup_error": index_result.error or "Index cleanup failed"},
                    )
            except Exception as index_error:
                return Result.ok(
                    delete_result.value,
                    metadata={"semantic_index_cleanup_error": str(index_error)},
                )

            return delete_result

        except Exception as e:
            return Result.err(f"Memory deletion failed: {str(e)}")

    def rebuild_semantic_index(self) -> Result[int]:
        """Re-index all active canonical memories into the derived semantic index.

        Paginates through all memories with status='active' in canonical storage
        and repopulates the semantic index.

        Returns:
            Result[int]: Count of re-indexed memories on success.
        """
        try:
            page_size = 200
            offset = 0
            memories: list[Memory] = []
            while True:
                result = self._uow.memories.search(
                    MemorySearchParams(
                        status=MemoryStatus.ACTIVE,
                        limit=page_size,
                        offset=offset,
                    )
                )
                if not result.success:
                    return Result.err(
                        result.error or "Failed to load canonical memories for rebuild"
                    )
                page = result.value.items if result.value else []
                memories.extend(page)
                if not result.value or len(page) < page_size:
                    break
                offset += len(page)
            return self._semantic_index.rebuild_from_canonical(memories)
        except Exception as exc:
            return Result.err(f"Failed to rebuild semantic index: {exc}")

    def search_memories(self, params: MemorySearchParams) -> Result[list[Memory]]:
        """Search memories with filters, returning a plain list of items."""
        result = self._uow.memories.search(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Search failed")

    def search_memories_paginated(self, params: MemorySearchParams) -> Result[PaginatedResult[Memory]]:
        """Search memories with filters, returning full pagination metadata (total, limit, offset)."""
        return self._uow.memories.search(params)

    def get_active_memories(self, project_id: UUID, limit: int = 50) -> Result[list[Memory]]:
        """Get active memories for a project."""
        return self._uow.memories.get_active_for_project(project_id, limit)

    # --- Custom Instruction Operations ---

    def create_instruction(self, request: CustomInstructionCreateRequest) -> Result[CustomInstruction]:
        """Create a custom instruction."""
        return self._instruction_service.create(request)

    def get_instruction(self, instruction_id: UUID) -> Result[Optional[CustomInstruction]]:
        """Get a custom instruction by ID."""
        return self._instruction_service.get(instruction_id)

    def update_instruction(self, instruction_id: UUID, request: CustomInstructionUpdateRequest) -> Result[Optional[CustomInstruction]]:
        """Update a custom instruction."""
        return self._instruction_service.update(instruction_id, request)

    def delete_instruction(self, instruction_id: UUID) -> Result[bool]:
        """Delete a custom instruction."""
        try:
            # Note: semantic index cleanup for instructions would be handled separately
            return self._instruction_service.delete(instruction_id)
        except Exception as e:
            return Result.err(f"Instruction deletion failed: {str(e)}")

    def list_instructions(self, params: CustomInstructionListParams) -> Result[list[CustomInstruction]]:
        """List custom instructions."""
        return self._instruction_service.list(params)

    def get_active_instructions(self, project_id: Optional[UUID] = None) -> Result[list[CustomInstruction]]:
        """Get active instructions for a project (global + project-scoped)."""
        if project_id:
            return self._instruction_service.get_active_for_project(project_id)
        return self._instruction_service.get_active_global()

    # --- Retrieval Operations ---

    def retrieve(self, request: RetrievalRequest) -> Result[RetrievalResult]:
        """Retrieve memories for a query."""
        try:
            return self._retrieval_service.retrieve(request)
        except Exception as e:
            return Result.err(f"Retrieval failed: {str(e)}")

    def search(self, query: str, project_id: Optional[UUID] = None, limit: int = 20) -> Result[RetrievalResult]:
        """Convenience method for simple search."""
        request = RetrievalRequest(query=query, project_id=project_id, limit=limit)
        return self.retrieve(request)

    def warmup(self) -> Result[bool]:
        """Pre-initialize retrieval services and index caches for fast first query execution."""
        if self._semantic_index is not None and hasattr(self._semantic_index, "warmup"):
            return self._semantic_index.warmup()
        return Result.ok(True)

    # --- Conflict Resolution ---

    def detect_and_resolve_conflicts(
        self,
        candidates: list,
        custom_instructions: list[CustomInstruction],
        project_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
    ) -> Result[ConflictResolutionResult]:
        """Detect and resolve conflicts among memory candidates."""
        try:
            from contracts.conflict import ConflictCandidate

            supplied_candidates: list[ConflictCandidate] = []
            for c in candidates:
                if isinstance(c, ConflictCandidate):
                    if c.memory is not None:
                        supplied_candidates.append(c)
                elif isinstance(c, Memory):
                    supplied_candidates.append(
                        ConflictCandidate(id=c.id, memory=c)
                    )

            project = None
            session = None
            if project_id:
                proj_result = self._uow.projects.get(project_id)
                if not proj_result.success or proj_result.value is None:
                    return Result.err(
                        proj_result.error or "The requested project was not found"
                    )
                project = proj_result.value
            if session_id:
                sess_result = self._uow.sessions.get(session_id)
                if not sess_result.success or sess_result.value is None:
                    return Result.err(
                        sess_result.error or "The requested session was not found"
                    )
                session = sess_result.value
                if project_id is not None and session.project_id != project_id:
                    return Result.err("The requested session does not belong to project")

            canonical_candidates: list[ConflictCandidate] = []
            if supplied_candidates:
                requested_ids = list(
                    dict.fromkeys(
                        candidate.memory.id
                        for candidate in supplied_candidates
                        if candidate.memory is not None
                    )
                )
                canonical_result = self._uow.memories.get_by_ids(requested_ids)
                if not canonical_result.success:
                    return Result.err(
                        canonical_result.error
                        or "Failed to validate conflict candidates against canonical memory"
                    )
                canonical_items = canonical_result.value if isinstance(canonical_result.value, list) else []
                canonical = {
                    memory.id: memory
                    for memory in canonical_items
                }
                for candidate in supplied_candidates:
                    if candidate.memory is None:
                        continue
                    memory = canonical.get(candidate.memory.id)
                    if memory is None or not memory.is_active():
                        continue
                    if project_id is not None and (
                        memory.project_id != project_id
                        and not (
                            memory.project_id is None
                            and memory.scope == Scope.GLOBAL
                        )
                    ):
                        continue
                    if session_id is not None and (
                        memory.session_id not in {None, session_id}
                    ):
                        continue
                    canonical_candidates.append(
                        ConflictCandidate(
                            id=memory.id,
                            memory=memory,
                            relevance_score=candidate.relevance_score,
                            conflict_type=candidate.conflict_type,
                            evidence=list(candidate.evidence),
                        )
                    )

            eligible_instructions = [
                instruction
                for instruction in custom_instructions
                if instruction.is_active()
                and (
                    instruction.scope == Scope.GLOBAL
                    or (
                        project_id is not None
                        and instruction.scope == Scope.PROJECT
                        and instruction.project_id == project_id
                    )
                )
            ]

            request = ConflictResolutionRequest(
                candidates=canonical_candidates,
                custom_instructions=eligible_instructions,
                project_context=project,
                session_context=session,
            )

            return self._conflict_service.detect_and_resolve(request)

        except Exception as e:
            return Result.err(f"Conflict resolution failed: {str(e)}")

    def get_conflicts(
        self,
        project_id: Optional[UUID] = None,
        limit: int = 200,
    ) -> Result[Optional[ConflictResolutionResult]]:
        """Detect and resolve conflicts among active memories for a project or system-wide."""
        try:
            mem_res = self._uow.memories.search(
                MemorySearchParams(project_id=project_id, status=MemoryStatus.ACTIVE, limit=limit)
            )
            if not mem_res.success:
                return Result.err(mem_res.error or "Unable to query memories for conflict check")
            memories = list(mem_res.value.items if mem_res.value is not None else [])
            if project_id is not None:
                global_res = self._uow.memories.search(
                    MemorySearchParams(scope=Scope.GLOBAL, status=MemoryStatus.ACTIVE, limit=limit)
                )
                if not global_res.success:
                    return Result.err(global_res.error or "Unable to query global memories for conflict check")
                if global_res.value is not None and isinstance(global_res.value.items, list):
                    seen_ids = {m.id for m in memories}
                    memories.extend(
                        m for m in global_res.value.items
                        if m.project_id is None and m.id not in seen_ids
                    )
            if len(memories) < 2:
                return Result.ok(None)
            from contracts.conflict import ConflictCandidate
            candidates = [
                ConflictCandidate(id=m.id, memory=m, relevance_score=1.0)
                for m in memories
            ]
            instr_res = self.get_active_instructions(project_id)
            if not instr_res.success:
                return Result.err(instr_res.error or "Failed to load active custom instructions for conflict check")
            active_instructions = instr_res.value or []
            return self.detect_and_resolve_conflicts(
                candidates, active_instructions, project_id=project_id
            )
        except Exception as exc:
            return Result.err(f"Conflict detection failed: {exc}")

    # --- Context Assembly ---

    def assemble_context(self, request: ContextAssemblyRequest) -> Result[AssembledContext]:
        """Assemble complete context for a project/session/query."""
        try:
            context_result = self._context_assembly.assemble(request)
            if not context_result.success:
                return context_result
            context = context_result.value

            # Apply custom instructions (highest precedence). Global instructions
            # must also be available when no project has been selected.
            if request.include_custom_instructions:
                instr_result = self.get_active_instructions(request.project_id)
                if not instr_result.success:
                    return Result.err(
                        instr_result.error or "Failed to load required custom instructions"
                    )
                instructions = instr_result.value or []
                if not getattr(request, "include_global", True) and request.project_id is not None:
                    instructions = [
                        inst for inst in instructions
                        if inst.scope == Scope.PROJECT and inst.project_id == request.project_id
                    ]
                context = self._context_assembly.apply_custom_instructions(
                    context, instructions
                )

            if len(context.active_memories) >= 2:
                from contracts.conflict import ConflictCandidate
                candidates = [
                    ConflictCandidate(id=m.id, memory=m, relevance_score=1.0)
                    for m in context.active_memories
                ]
                conflict_res = self.detect_and_resolve_conflicts(
                    candidates,
                    context.custom_instructions,
                    project_id=request.project_id,
                )
                if not conflict_res.success:
                    return Result.err(
                        conflict_res.error or "Conflict resolution failed during context assembly"
                    )
                if conflict_res.value is not None:
                    res_val = conflict_res.value
                    if res_val.decisions or res_val.preferred_candidates or res_val.unresolved_candidates:
                        context = self._context_assembly.apply_conflict_resolutions(
                            context, [res_val]
                        )

            return Result.ok(context)

        except Exception as e:
            return Result.err(f"Context assembly failed: {str(e)}")

    # --- /recall compact ---

    @staticmethod
    def _is_compaction_eligible(memory: Memory, conflicted_ids: set[UUID]) -> bool:
        """Return True if an active memory may be compacted without losing authority or conflict state."""
        if memory.status != MemoryStatus.ACTIVE:
            return False
        if memory.id in conflicted_ids:
            return False
        if memory.metadata.get("unresolved") is True:
            return False
        if memory.metadata.get("conflict_status") in {"unresolved", "abstained"}:
            return False
        if memory.metadata.get("pinned") is True or memory.metadata.get("authoritative") is True:
            return False
        if memory.provenance == "explicit_user_update":
            return False
        return True

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @contextlib.contextmanager
    def _transaction_context(self):
        tx = self._uow.begin()
        if hasattr(tx, "__enter__") and hasattr(tx, "__exit__"):
            with tx:
                yield
        else:
            yield

    def _load_all_memories(self, project_id: Optional[UUID] = None) -> Result[list[Memory]]:
        """Load all canonical memories (including historical) via pagination."""
        all_items: list[Memory] = []
        offset = 0
        page_size = 200
        while True:
            res = self._uow.memories.search(
                MemorySearchParams(
                    project_id=project_id,
                    include_historical=True,
                    limit=page_size,
                    offset=offset,
                )
            )
            if not res.success:
                return Result.err(res.error or "Failed to load memories")
            page = res.value.items if res.value is not None else []
            all_items.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return Result.ok(all_items)

    def flush_pending_semantic_sync(self, project_id: Optional[UUID] = None) -> Result[int]:
        """Replay durable canonical-backed pending semantic index sync operations."""
        if self._semantic_index is None:
            return Result.ok(0)
        try:
            load_res = self._load_all_memories(project_id=project_id)
            if not load_res.success:
                return Result.err(load_res.error or "Failed to load pending semantic sync items")
            items = load_res.value or []
            synced_ids: list[UUID] = []
            for memory in items:
                pending = memory.metadata.get("pending_semantic_sync")
                if pending not in {"upsert", "remove"}:
                    continue
                if pending == "upsert" and memory.status == MemoryStatus.ACTIVE:
                    idx_res = self._semantic_index.index_memory(memory)
                else:
                    idx_res = self._semantic_index.remove_memory(memory.id)
                if not idx_res.success:
                    if synced_ids:
                        with self._transaction_context():
                            for mid in synced_ids:
                                self._uow.memories.update(
                                    mid,
                                    MemoryUpdateRequest(metadata={"pending_semantic_sync": None}),
                                )
                    return Result.err(idx_res.error or f"Semantic sync failed for {memory.id}")
                synced_ids.append(memory.id)

            if synced_ids:
                with self._transaction_context():
                    for mid in synced_ids:
                        upd_res = self._uow.memories.update(
                            mid,
                            MemoryUpdateRequest(metadata={"pending_semantic_sync": None}),
                        )
                        if not upd_res.success:
                            return Result.err(upd_res.error or f"Failed to clear sync outbox for {mid}")
            return Result.ok(len(synced_ids))
        except Exception as exc:
            return Result.err(f"Pending semantic sync failed: {exc}")

    def traverse_lineage(self, memory_id: UUID | str, max_depth: int = 20) -> Result[dict[str, list[UUID]]]:
        """Traverse ancestor and descendant memory IDs across multi-round compaction DAGs."""
        try:
            root_id = memory_id if isinstance(memory_id, UUID) else UUID(str(memory_id))
            ancestors: list[UUID] = []
            descendants: list[UUID] = []

            for direction in ("ancestors", "descendants"):
                visited: set[UUID] = {root_id}
                queue: deque[tuple[UUID, int]] = deque([(root_id, 0)])
                while queue:
                    current_id, depth = queue.popleft()
                    if depth >= max_depth:
                        continue
                    lineage_res = self._uow.memories.get_lineage(current_id)
                    if not lineage_res.success:
                        return Result.err(lineage_res.error or "Failed to traverse lineage")
                    for edge in lineage_res.value or []:
                        nxt = edge.parent_id if (direction == "ancestors" and edge.child_id == current_id) else (
                            edge.child_id if (direction == "descendants" and edge.parent_id == current_id) else None
                        )
                        if nxt is not None and nxt not in visited:
                            visited.add(nxt)
                            if direction == "ancestors":
                                ancestors.append(nxt)
                            else:
                                descendants.append(nxt)
                            queue.append((nxt, depth + 1))

            return Result.ok({"ancestors": ancestors, "descendants": descendants})
        except Exception as exc:
            return Result.err(f"Lineage traversal failed: {exc}")

    def compact(self, request: CompactRequest) -> Result[CompactResult]:
        """
        Compact eligible context atomically while preserving canonical history and lineage.

        Runs summary creation, lineage insertion, source supersession, version allocation,
        and durable outbox marking inside one BEGIN IMMEDIATE canonical transaction.
        """
        try:
            compacted = 0
            superseded = 0
            archived = 0
            preserved = 0
            errors: list[str] = []

            if not request.project_id:
                return Result.err("Project ID required for compaction")
            if request.preserve_lineage is not True:
                return Result.err("Lineage preservation is mandatory for compaction")
            if (
                isinstance(request.max_active_memories, bool)
                or not isinstance(request.max_active_memories, int)
                or request.max_active_memories < 1
            ):
                return Result.err("max_active_memories must be a positive integer")

            project_result = self.get_project(request.project_id)
            if not project_result.success or project_result.value is None:
                return Result.err(project_result.error or "Project not found")
            if request.session_id is not None:
                session_result = self.get_session(request.session_id)
                if not session_result.success or session_result.value is None:
                    return Result.err(session_result.error or "Session not found")
                if session_result.value.project_id != request.project_id:
                    return Result.err("Session does not belong to the requested project")

            conflicted_ids: set[UUID] = set()
            conflicts_res = self.get_conflicts(project_id=request.project_id, limit=1000)
            if not conflicts_res.success:
                return Result.err(conflicts_res.error or "Conflict check failed before compaction")
            if conflicts_res.value is not None:
                if isinstance(conflicts_res.value.unresolved_candidates, list):
                    for cand in conflicts_res.value.unresolved_candidates:
                        if cand.memory is not None:
                            conflicted_ids.add(cand.memory.id)
                if isinstance(conflicts_res.value.decisions, list):
                    for dec in conflicts_res.value.decisions:
                        if dec.action == "unresolved":
                            conflicted_ids.add(dec.candidate_id)

            summary_id: Optional[UUID] = None
            compaction_version: Optional[int] = None
            idempotent_replay = False
            replay_result: Optional[CompactResult] = None

            class _LineageRollbackError(RuntimeError):
                pass

            try:
                with self._transaction_context():
                    load_result = self._load_all_memories(project_id=request.project_id)
                    if not load_result.success:
                        raise RuntimeError(load_result.error or "Failed to load memories for compaction")
                    all_memories = load_result.value or []
                    if not all_memories:
                        return Result.ok(CompactResult())

                    active_memories = [m for m in all_memories if m.status == MemoryStatus.ACTIVE]

                    if request.idempotency_key:
                        for existing in all_memories:
                            if (
                                existing.memory_type == "compaction_summary"
                                and existing.metadata.get("idempotency_key") == request.idempotency_key
                            ):
                                orig_session = existing.metadata.get("compaction_session_id")
                                orig_cap = existing.metadata.get("compaction_max_active")
                                req_session = str(request.session_id) if request.session_id is not None else None
                                if (
                                    (orig_session is not None or "compaction_session_id" in existing.metadata)
                                    and orig_session != req_session
                                ) or (
                                    orig_cap is not None and orig_cap != request.max_active_memories
                                ):
                                    return Result.err(
                                        "idempotency_key already used with different compaction parameters"
                                    )
                                replay_result = CompactResult(
                                    compacted_count=0,
                                    superseded_count=0,
                                    archived_count=0,
                                    preserved_count=len(active_memories),
                                    summary_id=existing.id,
                                    compaction_version=self._safe_int(
                                        existing.metadata.get("compaction_version"), default=0
                                    ) or None,
                                    idempotent_replay=True,
                                )
                                break

                    if replay_result is None:
                        scoped_active = [
                            m for m in active_memories
                            if request.session_id is None or m.session_id == request.session_id
                        ]
                        eligible_active = [
                            m for m in scoped_active
                            if self._is_compaction_eligible(m, conflicted_ids)
                        ]

                        summary_created = False
                        newly_superseded: list[Memory] = []
                        if len(eligible_active) > request.max_active_memories:
                            eligible_active.sort(
                                key=lambda m: m.updated_at.timestamp() if isinstance(m.updated_at, datetime) else 0.0
                            )
                            compact_count = len(eligible_active) - request.max_active_memories + 1
                            to_compact = eligible_active[:compact_count]

                            max_version = max(
                                (
                                    self._safe_int(m.metadata.get("compaction_version"), default=0)
                                    for m in all_memories
                                    if m.memory_type == "compaction_summary"
                                ),
                                default=0,
                            )
                            compaction_version = max_version + 1
                            compaction_op_id = str(uuid4())
                            now_iso = datetime.now(timezone.utc).isoformat()

                            summary_content = "\n".join(
                                f"[{memory.id}] {memory.content[:500]}" for memory in to_compact
                            )
                            source_sessions = {memory.session_id for memory in to_compact}
                            summary_session_id = (
                                request.session_id
                                if request.session_id is not None
                                else (next(iter(source_sessions)) if len(source_sessions) == 1 else None)
                            )
                            summary_metadata: dict[str, Any] = {
                                "compacted": True,
                                "compaction_version": compaction_version,
                                "compaction_op_id": compaction_op_id,
                                "compacted_at": now_iso,
                                "compaction_session_id": str(request.session_id) if request.session_id is not None else None,
                                "compaction_max_active": request.max_active_memories,
                                "original_ids": [str(memory.id) for memory in to_compact],
                                "pending_semantic_sync": "upsert",
                            }
                            if request.idempotency_key:
                                summary_metadata["idempotency_key"] = request.idempotency_key

                            summary_request = MemoryCreateRequest(
                                project_id=request.project_id,
                                session_id=summary_session_id,
                                scope=Scope.PROJECT,
                                memory_type="compaction_summary",
                                content=f"[Compacted v{compaction_version}]\n{summary_content}",
                                provenance="compaction_summary",
                                metadata=summary_metadata,
                            )
                            create_fn = self.create_memory if "create_memory" in self.__dict__ else self._uow.memories.create
                            update_fn = self.update_memory if "update_memory" in self.__dict__ else self._uow.memories.update

                            summary_result = create_fn(summary_request)
                            if not summary_result.success or summary_result.value is None:
                                raise RuntimeError(summary_result.error or "Failed to create compaction summary")

                            summary = summary_result.value
                            summary_id = summary.id
                            summary_created = True

                            for memory in to_compact:
                                lineage_result = self._uow.memories.create_lineage(
                                    MemoryLineage(
                                        parent_id=memory.id,
                                        child_id=summary.id,
                                        relationship="supersedes",
                                        reason="compaction_summary",
                                    )
                                )
                                if not lineage_result.success:
                                    raise _LineageRollbackError(
                                        f"Failed to preserve lineage for {memory.id}: {lineage_result.error}"
                                    )

                                update_result = update_fn(
                                    memory.id,
                                    MemoryUpdateRequest(
                                        status=MemoryStatus.SUPERSEDED,
                                        metadata={
                                            **memory.metadata,
                                            "compacted_at": now_iso,
                                            "compaction_summary_id": str(summary.id),
                                            "compaction_op_id": compaction_op_id,
                                            "pending_semantic_sync": "remove",
                                        },
                                    ),
                                )
                                if not update_result.success or update_result.value is None:
                                    raise _LineageRollbackError(
                                        f"Failed to supersede {memory.id}: {update_result.error}"
                                    )
                                newly_superseded.append(update_result.value)
                                superseded += 1
                                compacted += 1

                        # Recoverable archival policy: mark SUPERSEDED tail > 100 as ARCHIVED without deleting rows/lineage.
                        update_fn = self.update_memory if "update_memory" in self.__dict__ else self._uow.memories.update
                        historical_memories = [
                            m for m in all_memories if m.status == MemoryStatus.SUPERSEDED
                        ] + newly_superseded
                        historical_memories.sort(
                            key=lambda m: m.updated_at.timestamp() if isinstance(m.updated_at, datetime) else 0.0,
                            reverse=True,
                        )
                        if len(historical_memories) > 100:
                            archival_time = datetime.now(timezone.utc).isoformat()
                            for memory in historical_memories[100:]:
                                upd_res = update_fn(
                                    memory.id,
                                    MemoryUpdateRequest(
                                        status=MemoryStatus.ARCHIVED,
                                        metadata={
                                            **memory.metadata,
                                            "archived_at": archival_time,
                                            "pending_semantic_sync": "remove",
                                        },
                                    ),
                                )
                                if not upd_res.success:
                                    raise RuntimeError(f"Failed to archive {memory.id}: {upd_res.error}")
                                archived += 1

                        preserved = len(active_memories) - compacted + int(summary_created)
            except _LineageRollbackError as lineage_exc:
                return Result.ok(
                    CompactResult(
                        compacted_count=0,
                        superseded_count=0,
                        archived_count=0,
                        preserved_count=len(active_memories),
                        errors=[str(lineage_exc)],
                    )
                )

            # Post-commit derived semantic index sync (outbox replay; canonical storage remains intact if this fails).
            sync_res = self.flush_pending_semantic_sync(request.project_id)
            if not sync_res.success and sync_res.error:
                errors.append(sync_res.error)

            if replay_result is not None:
                replay_result.errors = errors
                return Result.ok(replay_result)

            return Result.ok(
                CompactResult(
                    compacted_count=compacted,
                    superseded_count=superseded,
                    archived_count=archived,
                    preserved_count=preserved,
                    errors=errors,
                    summary_id=summary_id,
                    compaction_version=compaction_version,
                    idempotent_replay=idempotent_replay,
                )
            )

        except Exception as e:
            return Result.err(f"Compaction failed: {str(e)}")

    # --- /recall update-context ---

    def update_context(self, request: UpdateContextRequest) -> Result[UpdateContextResult]:
        """
        Persist an explicit durable context update.

        This creates a new memory with explicit user provenance,
        which takes precedence over inferred historical memories.
        """
        try:
            if not request.content or not request.content.strip():
                return Result.err("Context content cannot be empty")

            memory_request = MemoryCreateRequest(
                project_id=request.project_id,
                session_id=request.session_id,
                scope=Scope.PROJECT if request.project_id else Scope.GLOBAL,
                memory_type=(request.memory_type or "context_update").strip() or "context_update",
                content=request.content,
                provenance=request.provenance,
                metadata={"explicit_update": True},
            )

            result = self.create_memory(memory_request)
            if not result.success or not result.value:
                return Result.err(result.error or "Failed to create context update memory")

            return Result.ok(UpdateContextResult(memory_id=result.value.id))

        except Exception as e:
            return Result.err(f"Context update failed: {str(e)}")

    # --- Stats ---

    def get_stats(self, project_id: Optional[UUID] = None) -> Result[dict]:
        """Get memory statistics."""
        try:
            stats = {
                "projects": 0,
                "sessions": 0,
                "memories": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
                "custom_instructions": {"active": 0, "inactive": 0},
                "semantic_index": {},
            }

            # Project count
            proj_result = self._uow.projects.list(PaginationParams(limit=1))
            if proj_result.success and proj_result.value:
                stats["projects"] = proj_result.value.total

            # Session count (scoped or system-wide)
            sess_result = self._uow.sessions.list(PaginationParams(limit=1), project_id)
            if sess_result.success and sess_result.value:
                stats["sessions"] = sess_result.value.total

            # Memory counts (scoped or system-wide)
            counted = False
            if hasattr(self._uow.memories, "count_by_status"):
                status_res = self._uow.memories.count_by_status(project_id)
                if status_res.success and isinstance(status_res.value, dict):
                    stats["memories"].update(status_res.value)
                    counted = True

            if not counted:
                for status in [MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED, MemoryStatus.DELETED]:
                    mem_params = MemorySearchParams(
                        project_id=project_id,
                        status=status,
                        limit=1,
                        include_historical=(status == MemoryStatus.DELETED),
                    )
                    mem_result = self._uow.memories.search(mem_params)
                    if mem_result.success and mem_result.value:
                        stats["memories"][status.value] = mem_result.value.total

            if hasattr(self._uow.memories, "count"):
                total_res = self._uow.memories.count(project_id)
                if total_res.success and isinstance(total_res.value, int):
                    stats["total_memories"] = total_res.value
                else:
                    stats["total_memories"] = sum(stats["memories"].values())
            else:
                stats["total_memories"] = sum(stats["memories"].values())

            # Instruction counts (scoped or system-wide)
            for status_val in [InstructionStatus.ACTIVE, InstructionStatus.INACTIVE]:
                instr_params = CustomInstructionListParams(project_id=project_id, status=status_val, limit=1)
                instr_result = self._uow.custom_instructions.list(instr_params)
                if instr_result.success and instr_result.value:
                    stats["custom_instructions"][status_val.value] = instr_result.value.total

            # Semantic index health
            index_health = self._semantic_index.health_check()
            if index_health.success:
                stats["semantic_index"] = index_health.value

            return Result.ok(stats)

        except Exception as e:
            return Result.err(f"Stats retrieval failed: {str(e)}")

    # --- Lifecycle ---

    def close(self) -> None:
        """Close the memory manager and underlying resources."""
        self._uow.close()

    def __enter__(self) -> MemoryManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
