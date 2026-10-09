"""Custom instruction service for RECALL Core."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from contracts.base import Result
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from database.repositories import CustomInstructionRepository


class CustomInstructionService:
    """Service for managing custom instructions."""

    def __init__(self, repository: CustomInstructionRepository):
        self._repository = repository

    def create(self, request: CustomInstructionCreateRequest) -> Result[CustomInstruction]:
        """Create a new custom instruction."""
        if not request.content or not request.content.strip():
            return Result.err("Instruction content cannot be empty")

        return self._repository.create(request)

    def get(self, instruction_id: UUID) -> Result[Optional[CustomInstruction]]:
        """Get a custom instruction by ID."""
        return self._repository.get(instruction_id)

    def update(self, instruction_id: UUID, request: CustomInstructionUpdateRequest) -> Result[Optional[CustomInstruction]]:
        """Update a custom instruction."""
        return self._repository.update(instruction_id, request)

    def delete(self, instruction_id: UUID) -> Result[bool]:
        """Delete (deactivate) a custom instruction."""
        return self._repository.delete(instruction_id)

    def list(self, params: CustomInstructionListParams) -> Result[list[CustomInstruction]]:
        """List custom instructions with filters."""
        result = self._repository.list(params)
        if result.success and result.value:
            return Result.ok(result.value.items)
        return Result.err(result.error or "Failed to list instructions")

    def get_active_for_scope(self, scope: str, project_id: Optional[UUID] = None) -> Result[list[CustomInstruction]]:
        """Get active instructions for a scope (global or project)."""
        return self._repository.get_active_for_scope(scope, project_id)

    def get_active_global(self) -> Result[list[CustomInstruction]]:
        """Get all active global instructions."""
        return self.get_active_for_scope("global")

    def get_active_for_project(self, project_id: UUID) -> Result[list[CustomInstruction]]:
        """Get active instructions for a project (global + project-scoped)."""
        global_result = self.get_active_global()
        if not global_result.success:
            return global_result

        project_result = self.get_active_for_scope("project", project_id)
        if not project_result.success:
            return project_result

        # Repositories should scope their results correctly, but deduplicate
        # defensively in case an adapter returns an instruction in both lists.
        combined = []
        seen_ids = set()
        for instruction in (global_result.value or []) + (project_result.value or []):
            if instruction.id in seen_ids:
                continue
            seen_ids.add(instruction.id)
            combined.append(instruction)

        return Result.ok(combined)