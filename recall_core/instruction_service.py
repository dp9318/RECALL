"""Custom instruction service for RECALL Core."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from contracts.base import InstructionStatus, Result
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from database.repositories import CustomInstructionRepository

_VALID_INSTRUCTION_TRANSITIONS: dict[InstructionStatus, set[InstructionStatus]] = {
    InstructionStatus.ACTIVE: {
        InstructionStatus.ACTIVE,
        InstructionStatus.INACTIVE,
        InstructionStatus.DELETED,
    },
    InstructionStatus.INACTIVE: {
        InstructionStatus.ACTIVE,
        InstructionStatus.INACTIVE,
        InstructionStatus.DELETED,
    },
    InstructionStatus.DELETED: set(),
}


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
        """Update a custom instruction with content and state-transition validation."""
        if request.content is not None and not request.content.strip():
            return Result.err("Instruction content cannot be empty")

        if request.status is not None:
            existing = self._repository.get(instruction_id)
            if isinstance(existing, Result):
                if not existing.success:
                    return Result.err(existing.error or "Failed to load instruction for update")
                if existing.value is None:
                    return Result.ok(None)
                if isinstance(existing.value, CustomInstruction):
                    current_status = existing.value.status
                    if current_status == InstructionStatus.DELETED:
                        return Result.err("Invalid instruction status transition: cannot update a deleted instruction")
                    if request.status not in _VALID_INSTRUCTION_TRANSITIONS.get(current_status, set()):
                        return Result.err(
                            f"Invalid instruction status transition: {current_status.value} -> {request.status.value}"
                        )

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
        """Get active instructions for a project (project-scoped precedence over global)."""
        global_result = self.get_active_global()
        if not global_result.success:
            return global_result

        project_result = self.get_active_for_scope("project", project_id)
        if not project_result.success:
            return project_result

        # Project-scoped instructions take precedence over global instructions.
        project_items = project_result.value if isinstance(project_result.value, list) else []
        global_items = global_result.value if isinstance(global_result.value, list) else []
        combined = []
        seen_ids = set()
        for instruction in project_items + global_items:
            if instruction.id in seen_ids:
                continue
            seen_ids.add(instruction.id)
            combined.append(instruction)

        return Result.ok(combined)
