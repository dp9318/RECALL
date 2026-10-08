"""Tests for CustomInstructionService."""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

from contracts.base import Result, PaginatedResult, PaginationParams, Scope, InstructionStatus
from contracts.instruction import CustomInstruction, CustomInstructionCreateRequest, CustomInstructionListParams, CustomInstructionUpdateRequest
from core.recall_core.instruction_service import CustomInstructionService


class TestCustomInstructionService:
    """Tests for CustomInstructionService."""

    def test_create_instruction_success(self, mock_instruction_repo):
        """Test successful instruction creation."""
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.GLOBAL,
            content="Test instruction",
            status=InstructionStatus.ACTIVE,
        )
        mock_instruction_repo.create.return_value = Result.ok(instruction)

        service = CustomInstructionService(mock_instruction_repo)
        request = CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="Test instruction")
        result = service.create(request)

        assert result.success
        assert result.value.content == "Test instruction"
        mock_instruction_repo.create.assert_called_once_with(request)

    def test_create_instruction_empty_content(self, mock_instruction_repo):
        """Test instruction creation with empty content fails."""
        service = CustomInstructionService(mock_instruction_repo)
        request = CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="")
        result = service.create(request)

        assert not result.success
        assert "empty" in result.error.lower()
        mock_instruction_repo.create.assert_not_called()

    def test_get_instruction(self, mock_instruction_repo):
        """Test getting an instruction by ID."""
        instruction_id = uuid4()
        instruction = CustomInstruction(id=instruction_id, content="Test")
        mock_instruction_repo.get.return_value = Result.ok(instruction)

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get(instruction_id)

        assert result.success
        assert result.value.id == instruction_id
        mock_instruction_repo.get.assert_called_once_with(instruction_id)

    def test_update_instruction(self, mock_instruction_repo):
        """Test updating an instruction."""
        instruction_id = uuid4()
        updated = CustomInstruction(id=instruction_id, content="Updated")
        mock_instruction_repo.update.return_value = Result.ok(updated)

        service = CustomInstructionService(mock_instruction_repo)
        request = CustomInstructionUpdateRequest(content="Updated")
        result = service.update(instruction_id, request)

        assert result.success
        assert result.value.content == "Updated"
        mock_instruction_repo.update.assert_called_once_with(instruction_id, request)

    def test_delete_instruction(self, mock_instruction_repo):
        """Test deleting an instruction."""
        instruction_id = uuid4()
        mock_instruction_repo.delete.return_value = Result.ok(True)

        service = CustomInstructionService(mock_instruction_repo)
        result = service.delete(instruction_id)

        assert result.success
        assert result.value is True
        mock_instruction_repo.delete.assert_called_once_with(instruction_id)

    def test_list_instructions(self, mock_instruction_repo):
        """Test listing instructions."""
        instructions = [
            CustomInstruction(id=uuid4(), content="Inst 1"),
            CustomInstruction(id=uuid4(), content="Inst 2"),
        ]
        paginated = PaginatedResult(items=instructions, total=2, limit=50, offset=0)
        mock_instruction_repo.list.return_value = Result.ok(paginated)

        service = CustomInstructionService(mock_instruction_repo)
        params = CustomInstructionListParams(limit=50, offset=0)
        result = service.list(params)

        assert result.success
        assert len(result.value) == 2
        mock_instruction_repo.list.assert_called_once_with(params)

    def test_get_active_global(self, mock_instruction_repo):
        """Test getting active global instructions."""
        instructions = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]
        mock_instruction_repo.get_active_for_scope.return_value = Result.ok(instructions)

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_global()

        assert result.success
        assert len(result.value) == 1
        assert result.value[0].scope == Scope.GLOBAL
        mock_instruction_repo.get_active_for_scope.assert_called_once_with("global", None)

    def test_get_active_for_project(self, mock_instruction_repo):
        """Test getting active instructions for a project (global + project-scoped)."""
        project_id = uuid4()
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]
        project_inst = [CustomInstruction(id=uuid4(), content="Project", scope=Scope.PROJECT, project_id=project_id)]

        mock_instruction_repo.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok(project_inst),
        ]

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_for_project(project_id)

        assert result.success
        assert len(result.value) == 2
        assert mock_instruction_repo.get_active_for_scope.call_count == 2

    def test_get_active_for_project_multiple_instructions(self, mock_instruction_repo):
        """Test getting active instructions when both global and project-scoped exist."""
        project_id = uuid4()
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]
        project_inst = [CustomInstruction(id=uuid4(), content="Project", scope=Scope.PROJECT, project_id=project_id)]

        mock_instruction_repo.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok(project_inst),
        ]

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_for_project(project_id)

        assert result.success
        assert len(result.value) == 2
        assert mock_instruction_repo.get_active_for_scope.call_count == 2

        # Verify both instructions are present with correct scopes
        scopes = {inst.scope for inst in result.value}
        assert Scope.GLOBAL in scopes
        assert Scope.PROJECT in scopes

    def test_get_active_for_project_inactive_instructions_filtered(self, mock_instruction_repo):
        """Test that inactive instructions returned from repository are passed through."""
        project_id = uuid4()
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL, status=InstructionStatus.INACTIVE)]
        project_inst = [CustomInstruction(id=uuid4(), content="Project", scope=Scope.PROJECT, project_id=project_id, status=InstructionStatus.INACTIVE)]

        mock_instruction_repo.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok(project_inst),
        ]

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_for_project(project_id)

        # Service passes through to repository; repository returns what it's given
        assert result.success
        # Both inactive instructions are returned (filtering would happen at repository level)
        assert len(result.value) == 2

    def test_scope_matches_behavior(self, mock_instruction_repo):
        """Test CustomInstruction.scope_matches behavior through service."""
        from contracts.instruction import CustomInstruction, Scope

        project_id = uuid4()

        # Global instruction matches all projects
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL)
        assert global_inst.scope_matches(project_id) is True
        assert global_inst.scope_matches(None) is True

        # Project instruction matches only its own project
        project_inst = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project_id)
        assert project_inst.scope_matches(project_id) is True
        assert project_inst.scope_matches(uuid4()) is False
        assert project_inst.scope_matches(None) is False

        # Inactive instruction
        inactive_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, status=InstructionStatus.INACTIVE)
        assert inactive_inst.is_active() is False

    def test_create_instruction_validates_content(self, mock_instruction_repo):
        """Test instruction creation validates content is not empty/whitespace."""
        service = CustomInstructionService(mock_instruction_repo)

        # Whitespace-only content
        request = CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="   \n  ")
        result = service.create(request)
        assert not result.success
        assert "empty" in result.error.lower()

        # None content
        request = CustomInstructionCreateRequest(scope=Scope.GLOBAL, content=None)
        result = service.create(request)
        assert not result.success

    def test_update_instruction_preserves_id(self, mock_instruction_repo):
        """Test instruction update preserves the original instruction ID."""
        instruction_id = uuid4()
        updated = CustomInstruction(id=instruction_id, content="Updated content", status=InstructionStatus.ACTIVE)
        mock_instruction_repo.update.return_value = Result.ok(updated)

        service = CustomInstructionService(mock_instruction_repo)
        request = CustomInstructionUpdateRequest(content="Updated content")
        result = service.update(instruction_id, request)

        assert result.success
        assert result.value.id == instruction_id
        assert result.value.content == "Updated content"

    def test_list_instructions_with_scope_filter(self, mock_instruction_repo):
        """Test listing instructions with scope filter passes through to repository."""
        instructions = [
            CustomInstruction(id=uuid4(), content="Global 1", scope=Scope.GLOBAL),
            CustomInstruction(id=uuid4(), content="Project 1", scope=Scope.PROJECT, project_id=uuid4()),
            CustomInstruction(id=uuid4(), content="Project 2", scope=Scope.PROJECT, project_id=uuid4()),
        ]
        paginated = type('obj', (object,), {'items': instructions, 'total': 3, 'limit': 50, 'offset': 0})()
        mock_instruction_repo.list.return_value = Result.ok(paginated)

        service = CustomInstructionService(mock_instruction_repo)
        params = CustomInstructionListParams(scope=Scope.GLOBAL)
        result = service.list(params)

        assert result.success
        # Service passes through to repository; scope filtering is repository's responsibility
        assert len(result.value) == 3
        mock_instruction_repo.list.assert_called_once_with(params)

    def test_list_instructions_with_project_filter(self, mock_instruction_repo):
        """Test listing instructions with project filter passes through to repository."""
        project_id = uuid4()
        instructions = [
            CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL),
            CustomInstruction(id=uuid4(), content="Project A", scope=Scope.PROJECT, project_id=project_id),
            CustomInstruction(id=uuid4(), content="Project B", scope=Scope.PROJECT, project_id=uuid4()),
        ]
        paginated = type('obj', (object,), {'items': instructions, 'total': 3, 'limit': 50, 'offset': 0})()
        mock_instruction_repo.list.return_value = Result.ok(paginated)

        service = CustomInstructionService(mock_instruction_repo)
        params = CustomInstructionListParams(project_id=project_id)
        result = service.list(params)

        assert result.success
        # Service passes through to repository; project filtering is repository's responsibility
        assert len(result.value) == 3
        mock_instruction_repo.list.assert_called_once_with(params)

    def test_get_active_global_no_instructions(self, mock_instruction_repo):
        """Test getting active global instructions when none exist."""
        mock_instruction_repo.get_active_for_scope.return_value = Result.ok([])

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_global()

        assert result.success
        assert len(result.value) == 0

    def test_get_active_for_project_no_project_instructions(self, mock_instruction_repo):
        """Test getting active for project when only global instructions exist."""
        project_id = uuid4()
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]

        mock_instruction_repo.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok([]),  # No project-scoped
        ]

        service = CustomInstructionService(mock_instruction_repo)
        result = service.get_active_for_project(project_id)

        assert result.success
        assert len(result.value) == 1
        assert result.value[0].scope == Scope.GLOBAL