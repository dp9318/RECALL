"""Main Memory Manager orchestration for RECALL Core."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from contracts.base import Result, PaginationParams
from contracts.conflict import ConflictResolutionRequest, ConflictResolutionResult
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
    InstructionStatus,
)
from contracts.memory import Memory, MemoryCreateRequest, MemorySearchParams, MemoryStatus, MemoryUpdateRequest
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
            try:
                index_result = self._semantic_index.index_memory(memory)
                if not index_result.success:
                    return Result.ok(
                        memory,
                        metadata={"semantic_index_error": index_result.error or "Indexing failed"},
                    )
            except Exception as index_error:
                return Result.ok(memory, metadata={"semantic_index_error": str(index_error)})

            return Result.ok(memory)

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

    def search_memories(self, params: MemorySearchParams) -> Result[list[Memory]]:
        """Search memories with filters."""
        result = self._uow.memories.search(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Search failed")

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
            from contracts.project import Project, Session

            # Package candidates
            conflict_candidates = []
            for c in candidates:
                if isinstance(c, ConflictCandidate):
                    conflict_candidates.append(c)
                elif isinstance(c, Memory):
                    conflict_candidates.append(ConflictCandidate(memory=c))

            # Get project/session context
            project = None
            session = None
            if project_id:
                proj_result = self._uow.projects.get(project_id)
                if proj_result.success:
                    project = proj_result.value
            if session_id:
                sess_result = self._uow.sessions.get(session_id)
                if sess_result.success:
                    session = sess_result.value

            request = ConflictResolutionRequest(
                candidates=conflict_candidates,
                custom_instructions=custom_instructions,
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

        This operation:
        1. Identifies memories eligible for compaction (old, superseded, low relevance)
        2. Creates supersession relationships where appropriate
        3. Archives old memories instead of deleting
        4. Preserves lineage metadata
        """
        try:
            compacted = 0
            superseded = 0
            archived = 0
            preserved = 0
            errors = []

            if not request.project_id:
                return Result.err("Project ID required for compaction")

            # Get all memories for the project
            search_params = MemorySearchParams(
                project_id=request.project_id,
                include_historical=True,
                limit=1000,
            )
            search_result = self._uow.memories.search(search_params)
            if not search_result.success or not search_result.value:
                return Result.ok(CompactResult(errors=["No memories found"]))

            all_memories = search_result.value.items
            active_memories = [m for m in all_memories if m.status == MemoryStatus.ACTIVE]

            # If we have too many active memories, compact the oldest/least relevant
            if len(active_memories) > request.max_active_memories:
                # Sort by updated_at (oldest first) and relevance
                active_memories.sort(key=lambda m: m.updated_at)

                to_compact = active_memories[:-request.max_active_memories]
                to_preserve = active_memories[-request.max_active_memories:]

                for memory in to_compact:
                    try:
                        # Create a summary/superseding memory
                        summary_content = f"[Compacted] {memory.content[:500]}"
                        summary_request = MemoryCreateRequest(
                            project_id=memory.project_id,
                            session_id=memory.session_id,
                            scope=memory.scope,
                            memory_type="compaction_summary",
                            content=summary_content,
                            provenance=f"compacted_from_{memory.id}",
                            supersedes_id=memory.id,
                            metadata={"compacted": True, "original_id": str(memory.id)},
                        )

                        summary_result = self.create_memory(summary_request)
                        if summary_result.success and summary_result.value:
                            # Mark original as superseded
                            update_result = self.update_memory(memory.id, MemoryUpdateRequest(
                                status=MemoryStatus.SUPERSEDED,
                                metadata={**memory.metadata, "compacted_at": datetime.now(timezone.utc).isoformat()},
                            ))
                            if update_result.success:
                                superseded += 1
                                compacted += 1
                            else:
                                errors.append(f"Failed to supersede {memory.id}: {update_result.error}")
                        else:
                            errors.append(f"Failed to create summary for {memory.id}: {summary_result.error}")

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

            preserved = len(to_preserve) if 'to_preserve' in locals() else len(active_memories)

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
                scope=request.project_id and "project" or "global",
                memory_type=request.memory_type,
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

            if project_id:
                # Session count for project
                sess_result = self._uow.sessions.list(PaginationParams(limit=1000), project_id)
                if sess_result.success and sess_result.value:
                    stats["sessions"] = sess_result.value.total

                # Memory counts
                for status in [MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED, MemoryStatus.DELETED]:
                    mem_params = MemorySearchParams(project_id=project_id, status=status, limit=1000)
                    mem_result = self._uow.memories.search(mem_params)
                    if mem_result.success and mem_result.value:
                        stats["memories"][status.value] = mem_result.value.total

                # Instruction counts
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