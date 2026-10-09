"""Context assembly service for RECALL Core."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from contracts.base import Result
from contracts.conflict import ConflictResolutionResult
from contracts.instruction import CustomInstruction
from contracts.memory import Memory, MemorySearchParams, MemoryStatus
from contracts.project import Project, Session
from contracts.retrieval import AssembledContext, ContextAssemblyRequest, RetrievalRequest, RetrievalResult
from database.repositories import MemoryRepository, ProjectRepository, SessionRepository
from intelligence.retrieval import RetrievalService


class ContextAssemblyService:
    """Service for assembling context from multiple sources."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        project_repo: ProjectRepository,
        session_repo: SessionRepository,
        retrieval_service: RetrievalService,
    ):
        self._memory_repo = memory_repo
        self._project_repo = project_repo
        self._session_repo = session_repo
        self._retrieval_service = retrieval_service

    def assemble(self, request: ContextAssemblyRequest) -> Result[AssembledContext]:
        """Assemble context from all sources."""
        try:
            project = None
            session = None

            if request.project_id:
                project_result = self._project_repo.get(request.project_id)
                if project_result.success:
                    project = project_result.value
                else:
                    return project_result

            if request.session_id:
                session_result = self._session_repo.get(request.session_id)
                if not session_result.success:
                    return Result.err(session_result.error or "Failed to load requested session")
                session = session_result.value
            elif request.project_id:
                session_result = self._session_repo.get_active_for_project(request.project_id)
                if not session_result.success:
                    return Result.err(session_result.error or "Failed to load active session")
                session = session_result.value

            # Get active custom instructions
            custom_instructions = []
            if request.include_custom_instructions and request.project_id:
                # This would be fetched via CustomInstructionService
                # For now, return empty - the orchestrator will populate this
                pass

            # Get active memories
            active_memories = []
            if request.project_id:
                active_result = self._memory_repo.get_active_for_project(request.project_id, request.retrieval_limit)
                if not active_result.success:
                    return Result.err(active_result.error or "Failed to load active memories")
                active_memories = active_result.value or []

            # Get resolved memories (memories that were part of conflict resolutions)
            resolved_memories = []
            # This would come from conflict resolution results

            # Get historical memories if requested
            historical_memories = []
            if request.include_historical and request.project_id:
                hist_params = MemorySearchParams(
                    project_id=request.project_id,
                    status=MemoryStatus.SUPERSEDED,
                    limit=request.retrieval_limit,
                    include_historical=True,
                )
                hist_result = self._memory_repo.search(hist_params)
                if not hist_result.success:
                    return Result.err(hist_result.error or "Failed to load historical memories")
                if hist_result.value:
                    historical_memories = hist_result.value.items

            # Perform retrieval if query provided
            conflict_resolutions = []
            if request.query:
                retrieval_request = RetrievalRequest(
                    query=request.query,
                    project_id=request.project_id,
                    session_id=request.session_id,
                    limit=request.retrieval_limit,
                    include_historical=request.include_historical,
                )
                retrieval_result = self._retrieval_service.retrieve(retrieval_request)
                if not retrieval_result.success:
                    return Result.err(retrieval_result.error or "Memory retrieval failed")
                if retrieval_result.value:
                    # Merge retrieved memories with active memories
                    for mem in retrieval_result.value.memories:
                        if mem not in active_memories and mem.status == MemoryStatus.ACTIVE:
                            active_memories.append(mem)

            context = AssembledContext(
                project=project,
                session=session,
                custom_instructions=custom_instructions,
                active_memories=active_memories,
                resolved_memories=resolved_memories,
                historical_memories=historical_memories,
                conflict_resolutions=conflict_resolutions,
                query=request.query,
                assembled_at=datetime.now(timezone.utc).isoformat(),
            )

            return Result.ok(context)

        except Exception as e:
            return Result.err(f"Context assembly failed: {str(e)}")

    def apply_custom_instructions(self, context: AssembledContext, instructions: list[CustomInstruction]) -> AssembledContext:
        """Apply custom instructions to assembled context (precedence handling)."""
        context.custom_instructions = instructions
        return context

    def apply_conflict_resolutions(self, context: AssembledContext, resolutions: list[ConflictResolutionResult]) -> AssembledContext:
        """Apply conflict resolutions to assembled context."""
        context.conflict_resolutions = resolutions

        # Add resolved memories to the context
        for resolution in resolutions:
            for candidate in resolution.preferred_candidates:
                if candidate.memory not in context.resolved_memories:
                    context.resolved_memories.append(candidate.memory)
            for candidate in resolution.superseded_candidates:
                if candidate.memory not in context.historical_memories:
                    context.historical_memories.append(candidate.memory)

        return context