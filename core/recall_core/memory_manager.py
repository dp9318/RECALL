"""Main Memory Manager orchestration for RECALL Core."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from contracts.base import Result, PaginatedResult, PaginationParams, Scope
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

    # --- Project Operations ---

    def create_project(self, request: ProjectCreateRequest) -> Result[Project]:
        """Create a new project."""
        return self._uow.projects.create(request)

    def get_project(self, project_id: UUID) -> Result[Optional[Project]]:
        """Get a project by ID."""
        return self._uow.projects.get(project_id)

    def update_project(self, project_id: UUID, request: ProjectUpdateRequest) -> Result[Optional[Project]]:
        """Update a project."""
        return self._uow.projects.update(project_id, request)

    def delete_project(self, project_id: UUID) -> Result[bool]:
        """Delete a project."""
        return self._uow.projects.delete(project_id)

    def list_projects(self, limit: int = 50, offset: int = 0) -> Result[list[Project]]:
        """List projects."""
        from contracts.base import PaginationParams
        params = PaginationParams(limit=limit, offset=offset)
        result = self._uow.projects.list(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Failed to list projects")

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

    # --- Memory Operations ---

    def create_memory(self, request: MemoryCreateRequest) -> Result[Memory]:
        """Create a new memory with semantic indexing."""
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
        """Get a memory by ID."""
        return self._uow.memories.get(memory_id)

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
        """Delete (deactivate) a memory."""
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
        """Re-embed all active canonical memories into the derived index."""
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
        """Search memories with filters."""
        result = self._uow.memories.search(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Search failed")

    def search_memories_paginated(self, params: MemorySearchParams) -> Result[PaginatedResult[Memory]]:
        """Search memories with filters returning full pagination metadata."""
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
                canonical = {
                    memory.id: memory
                    for memory in (canonical_result.value or [])
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
                context = self._context_assembly.apply_custom_instructions(
                    context, instr_result.value or []
                )

            return Result.ok(context)

        except Exception as e:
            return Result.err(f"Context assembly failed: {str(e)}")

    # --- /recall compact ---

    def compact(self, request: CompactRequest) -> Result[CompactResult]:
        """
        Compact eligible context while preserving canonical history and lineage.

        The oldest active memories above the configured cap are replaced by
        one active summary; source records remain canonical and superseded.
        Compaction lineage is mandatory.
        """
        try:
            compacted = 0
            superseded = 0
            archived = 0
            preserved = 0
            errors = []

            if not request.project_id:
                return Result.err("Project ID required for compaction")
            if request.preserve_lineage is not True:
                return Result.err(
                    "Lineage preservation is mandatory for compaction"
                )
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

            # Get all memories for the project
            search_params = MemorySearchParams(
                project_id=request.project_id,
                include_historical=True,
                limit=1000,
            )
            search_result = self._uow.memories.search(search_params)
            if not search_result.success:
                return Result.err(search_result.error or "Failed to load memories for compaction")
            if not search_result.value or not search_result.value.items:
                return Result.ok(CompactResult())

            all_memories = search_result.value.items
            active_memories = [m for m in all_memories if m.status == MemoryStatus.ACTIVE]

            summary_created = False

            # Replace the selected source memories with one compact summary.
            if len(active_memories) > request.max_active_memories:
                active_memories.sort(key=lambda m: m.updated_at)

                compact_count = len(active_memories) - request.max_active_memories + 1
                to_compact = active_memories[:compact_count]
                summary_content = "\n".join(
                    f"[{memory.id}] {memory.content[:500]}" for memory in to_compact
                )
                source_sessions = {memory.session_id for memory in to_compact}
                summary_session_id = (
                    next(iter(source_sessions)) if len(source_sessions) == 1 else None
                )
                summary_request = MemoryCreateRequest(
                    project_id=request.project_id,
                    session_id=summary_session_id,
                    scope=Scope.PROJECT,
                    memory_type="compaction_summary",
                    content=f"[Compacted]\n{summary_content}",
                    provenance="compaction_summary",
                    metadata={
                        "compacted": True,
                        "original_ids": [str(memory.id) for memory in to_compact],
                    },
                )

                try:
                    summary_result = self.create_memory(summary_request)
                except Exception as e:
                    return Result.err(f"Compaction failed while creating summary: {e}")
                if not summary_result.success or summary_result.value is None:
                    return Result.err(
                        summary_result.error or "Failed to create compaction summary"
                    )

                summary_created = True
                summary = summary_result.value
                for memory in to_compact:
                    try:
                        lineage_result = self._uow.memories.create_lineage(
                            MemoryLineage(
                                parent_id=memory.id,
                                child_id=summary.id,
                                relationship="supersedes",
                                reason="compaction_summary",
                            )
                        )
                        if not lineage_result.success:
                            errors.append(
                                f"Failed to preserve lineage for {memory.id}: "
                                f"{lineage_result.error}"
                            )
                            continue

                        update_result = self.update_memory(
                            memory.id,
                            MemoryUpdateRequest(
                                status=MemoryStatus.SUPERSEDED,
                                metadata={
                                    **memory.metadata,
                                    "compacted_at": datetime.now(timezone.utc).isoformat(),
                                },
                            ),
                        )
                        if update_result.success and update_result.value is not None:
                            superseded += 1
                            compacted += 1
                        else:
                            errors.append(
                                f"Failed to supersede {memory.id}: {update_result.error}"
                            )
                    except Exception as e:
                        errors.append(f"Error compacting {memory.id}: {str(e)}")

            # Archive old superseded memories beyond a threshold
            historical_memories = [m for m in all_memories if m.status in (MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED)]
            historical_memories.sort(key=lambda m: m.updated_at, reverse=True)

            # Keep last 100 historical, archive the rest
            if len(historical_memories) > 100:
                for memory in historical_memories[100:]:
                    try:
                        update_result = self.update_memory(memory.id, MemoryUpdateRequest(
                            status=MemoryStatus.ARCHIVED,
                        ))
                        if update_result.success:
                            archived += 1
                    except Exception as e:
                        errors.append(f"Error archiving {memory.id}: {str(e)}")

            preserved = len(active_memories) - compacted + int(summary_created)

            return Result.ok(CompactResult(
                compacted_count=compacted,
                superseded_count=superseded,
                archived_count=archived,
                preserved_count=preserved,
                errors=errors,
            ))

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
            proj_result = self.list_projects(limit=1000)
            if proj_result.success:
                stats["projects"] = len(proj_result.value)

            # Session count (scoped or system-wide)
            sess_result = self._uow.sessions.list(PaginationParams(limit=1000), project_id)
            if sess_result.success and sess_result.value:
                stats["sessions"] = sess_result.value.total

            # Memory counts (scoped or system-wide)
            for status in [MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED, MemoryStatus.DELETED]:
                mem_params = MemorySearchParams(
                    project_id=project_id,
                    status=status,
                    limit=1000,
                    include_historical=(status == MemoryStatus.DELETED),
                )
                mem_result = self._uow.memories.search(mem_params)
                if mem_result.success and mem_result.value:
                    stats["memories"][status.value] = mem_result.value.total

            # Instruction counts (scoped or system-wide)
            for status_val in [InstructionStatus.ACTIVE, InstructionStatus.INACTIVE]:
                instr_params = CustomInstructionListParams(project_id=project_id, status=status_val, limit=1000)
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