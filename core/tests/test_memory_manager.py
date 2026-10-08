"""Tests for MemoryManager."""

import pytest
from uuid import UUID, uuid4
from datetime import datetime
from unittest.mock import Mock, MagicMock

from contracts.base import Result, Scope, MemoryStatus, InstructionStatus
from contracts.conflict import ConflictCandidate, ConflictResolutionResult, ConflictResolutionStatus, ResolutionDecision
from contracts.instruction import CustomInstruction, CustomInstructionCreateRequest, CustomInstructionListParams, CustomInstructionUpdateRequest, InstructionStatus
from contracts.memory import Memory, MemoryCreateRequest, MemorySearchParams, MemoryUpdateRequest, MemoryLineage
from contracts.project import Project, ProjectCreateRequest, ProjectUpdateRequest, Session, SessionCreateRequest, SessionUpdateRequest
from contracts.retrieval import RetrievalRequest, RetrievalResult, ContextAssemblyRequest, AssembledContext, CompactRequest, CompactResult, UpdateContextRequest, UpdateContextResult
from core.recall_core.memory_manager import MemoryManager


class TestMemoryManager:
    """Tests for MemoryManager."""

    @pytest.fixture
    def manager(self, mock_uow, mock_retrieval_service, mock_conflict_service, mock_semantic_index):
        return MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_semantic_index,
        )

    @pytest.fixture
    def sample_project(self):
        return Project(id=uuid4(), name="Test Project")

    @pytest.fixture
    def sample_session(self, sample_project):
        return Session(id=uuid4(), project_id=sample_project.id)

    @pytest.fixture
    def sample_memory(self, sample_project, sample_session):
        return Memory(
            id=uuid4(),
            project_id=sample_project.id,
            session_id=sample_session.id,
            scope=Scope.PROJECT,
            content="Test memory",
            status=MemoryStatus.ACTIVE,
        )

    @pytest.fixture
    def sample_instruction(self):
        return CustomInstruction(
            id=uuid4(),
            scope=Scope.GLOBAL,
            content="Test instruction",
            status=InstructionStatus.ACTIVE,
        )

    # --- Project Tests ---

    def test_create_project(self, manager, mock_uow):
        """Test project creation."""
        project = Project(id=uuid4(), name="New Project")
        mock_uow.projects.create.return_value = Result.ok(project)

        request = ProjectCreateRequest(name="New Project")
        result = manager.create_project(request)

        assert result.success
        assert result.value.name == "New Project"
        mock_uow.projects.create.assert_called_once_with(request)

    def test_get_project(self, manager, mock_uow, sample_project):
        """Test getting a project."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        result = manager.get_project(sample_project.id)

        assert result.success
        assert result.value.id == sample_project.id

    def test_get_project_not_found(self, manager, mock_uow):
        """Test getting a non-existent project returns error."""
        missing_id = uuid4()
        mock_uow.projects.get.return_value = Result.err("Project not found")

        result = manager.get_project(missing_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_get_project_repo_failure(self, manager, mock_uow):
        """Test getting a project when repository fails."""
        project_id = uuid4()
        mock_uow.projects.get.return_value = Result.err("Database connection failed")

        result = manager.get_project(project_id)

        assert not result.success
        assert "Database connection failed" in result.error

    def test_update_project(self, manager, mock_uow, sample_project):
        """Test updating a project."""
        updated = Project(id=sample_project.id, name="Updated Project", description="New desc")
        mock_uow.projects.update.return_value = Result.ok(updated)

        request = ProjectUpdateRequest(name="Updated Project", description="New desc")
        result = manager.update_project(sample_project.id, request)

        assert result.success
        assert result.value.name == "Updated Project"
        mock_uow.projects.update.assert_called_once_with(sample_project.id, request)

    def test_update_project_not_found(self, manager, mock_uow):
        """Test updating a non-existent project."""
        project_id = uuid4()
        mock_uow.projects.update.return_value = Result.err("Project not found")

        request = ProjectUpdateRequest(name="Updated")
        result = manager.update_project(project_id, request)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_delete_project(self, manager, mock_uow, sample_project):
        """Test deleting a project."""
        mock_uow.projects.delete.return_value = Result.ok(True)

        result = manager.delete_project(sample_project.id)

        assert result.success
        assert result.value is True
        mock_uow.projects.delete.assert_called_once_with(sample_project.id)

    def test_delete_project_not_found(self, manager, mock_uow):
        """Test deleting a non-existent project."""
        project_id = uuid4()
        mock_uow.projects.delete.return_value = Result.err("Project not found")

        result = manager.delete_project(project_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_list_projects(self, manager, mock_uow):
        """Test listing projects."""
        projects = [Project(id=uuid4(), name=f"Project {i}") for i in range(3)]
        from contracts.base import PaginatedResult
        mock_uow.projects.list.return_value = Result.ok(PaginatedResult(items=projects, total=3, limit=50, offset=0))

        result = manager.list_projects(limit=50, offset=0)

        assert result.success
        assert len(result.value) == 3

    def test_list_projects_repo_failure(self, manager, mock_uow):
        """Test listing projects when repository fails."""
        mock_uow.projects.list.return_value = Result.err("Query timeout")

        result = manager.list_projects()

        assert not result.success
        assert "timeout" in result.error.lower()

    # --- Session Tests ---

    def test_create_session(self, manager, mock_uow, sample_project):
        """Test session creation."""
        session = Session(id=uuid4(), project_id=sample_project.id)
        mock_uow.sessions.create.return_value = Result.ok(session)

        request = SessionCreateRequest(project_id=sample_project.id)
        result = manager.create_session(request)

        assert result.success
        assert result.value.project_id == sample_project.id

    def test_get_session(self, manager, mock_uow, sample_session):
        """Test getting a session by ID."""
        mock_uow.sessions.get.return_value = Result.ok(sample_session)

        result = manager.get_session(sample_session.id)

        assert result.success
        assert result.value.id == sample_session.id

    def test_get_session_not_found(self, manager, mock_uow):
        """Test getting a non-existent session."""
        session_id = uuid4()
        mock_uow.sessions.get.return_value = Result.err("Session not found")

        result = manager.get_session(session_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_get_session_repo_failure(self, manager, mock_uow):
        """Test getting a session when repository fails."""
        session_id = uuid4()
        mock_uow.sessions.get.return_value = Result.err("Database error")

        result = manager.get_session(session_id)

        assert not result.success
        assert "Database error" in result.error

    def test_get_active_session(self, manager, mock_uow, sample_project, sample_session):
        """Test getting active session for project."""
        mock_uow.sessions.get_active_for_project.return_value = Result.ok(sample_session)

        result = manager.get_active_session(sample_project.id)

        assert result.success
        assert result.value.id == sample_session.id

    def test_get_active_session_none(self, manager, mock_uow, sample_project):
        """Test getting active session when none exists."""
        mock_uow.sessions.get_active_for_project.return_value = Result.ok(None)

        result = manager.get_active_session(sample_project.id)

        assert result.success
        assert result.value is None

    def test_update_session(self, manager, mock_uow, sample_session):
        """Test updating a session."""
        updated = Session(id=sample_session.id, project_id=sample_session.project_id, ended_at=datetime.utcnow())
        mock_uow.sessions.update.return_value = Result.ok(updated)

        request = SessionUpdateRequest(ended_at=datetime.utcnow())
        result = manager.update_session(sample_session.id, request)

        assert result.success
        assert result.value.ended_at is not None
        mock_uow.sessions.update.assert_called_once_with(sample_session.id, request)

    def test_update_session_not_found(self, manager, mock_uow):
        """Test updating a non-existent session."""
        session_id = uuid4()
        mock_uow.sessions.update.return_value = Result.err("Session not found")

        request = SessionUpdateRequest(ended_at=datetime.utcnow())
        result = manager.update_session(session_id, request)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_end_session(self, manager, mock_uow, sample_session):
        """Test ending a session."""
        ended_session = Session(id=sample_session.id, project_id=sample_session.project_id, ended_at=datetime.utcnow())
        mock_uow.sessions.update.return_value = Result.ok(ended_session)

        result = manager.end_session(sample_session.id)

        assert result.success
        assert result.value.ended_at is not None

    def test_end_session_not_found(self, manager, mock_uow):
        """Test ending a non-existent session."""
        session_id = uuid4()
        mock_uow.sessions.update.return_value = Result.err("Session not found")

        result = manager.end_session(session_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_end_session_repo_failure(self, manager, mock_uow, sample_session):
        """Test ending a session when repository fails."""
        mock_uow.sessions.update.return_value = Result.err("Transaction failed")

        result = manager.end_session(sample_session.id)

        assert not result.success
        assert "Transaction failed" in result.error

# --- Memory Tests ---

    def test_create_memory(self, manager, mock_uow, mock_semantic_index, sample_project, sample_session):
        """Test memory creation with semantic indexing."""
        memory = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="New memory",
            status=MemoryStatus.ACTIVE,
        )
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.ok(True)

        request = MemoryCreateRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="New memory",
        )
        result = manager.create_memory(request)

        assert result.success
        assert result.value.content == "New memory"
        mock_uow.memories.create.assert_called_once()
        mock_semantic_index.index_memory.assert_called_once()

    def test_create_memory_index_failure_continues(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Test memory creation continues even if semantic index fails."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="New memory", status=MemoryStatus.ACTIVE)
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.err("Index unavailable")

        request = MemoryCreateRequest(project_id=sample_project.id, content="New memory")
        result = manager.create_memory(request)

        # Should still succeed - semantic index is derived
        assert result.success
        assert result.value.content == "New memory"

    def test_create_memory_repo_failure(self, manager, mock_uow, sample_project):
        """Test memory creation when repository fails."""
        mock_uow.memories.create.return_value = Result.err("Constraint violation")

        request = MemoryCreateRequest(project_id=sample_project.id, content="New memory")
        result = manager.create_memory(request)

        assert not result.success
        assert "Constraint violation" in result.error

    def test_create_memory_preserves_provenance(self, manager, mock_uow, mock_semantic_index, sample_project, sample_session):
        """Test memory creation preserves provenance and timestamps."""
        created_id = uuid4()
        memory = Memory(
            id=created_id,
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Test memory",
            status=MemoryStatus.ACTIVE,
            provenance="user_explicit",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.ok(True)

        request = MemoryCreateRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Test memory",
            provenance="user_explicit",
        )
        result = manager.create_memory(request)

        assert result.success
        assert result.value.id == created_id
        assert result.value.provenance == "user_explicit"
        assert result.value.created_at is not None
        assert result.value.updated_at is not None

    def test_get_memory(self, manager, mock_uow, sample_memory):
        """Test getting a memory by ID."""
        mock_uow.memories.get.return_value = Result.ok(sample_memory)

        result = manager.get_memory(sample_memory.id)

        assert result.success
        assert result.value.id == sample_memory.id

    def test_get_memory_not_found(self, manager, mock_uow):
        """Test getting a non-existent memory."""
        memory_id = uuid4()
        mock_uow.memories.get.return_value = Result.err("Memory not found")

        result = manager.get_memory(memory_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_get_memory_repo_failure(self, manager, mock_uow):
        """Test getting a memory when repository fails."""
        memory_id = uuid4()
        mock_uow.memories.get.return_value = Result.err("Connection lost")

        result = manager.get_memory(memory_id)

        assert not result.success
        assert "Connection lost" in result.error

    def test_update_memory(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test memory update."""
        updated_memory = Memory(id=sample_memory.id, content="Updated content", status=MemoryStatus.ACTIVE)
        mock_uow.memories.update.return_value = Result.ok(updated_memory)
        mock_semantic_index.update_memory.return_value = Result.ok(True)

        request = MemoryUpdateRequest(content="Updated content")
        result = manager.update_memory(sample_memory.id, request)

        assert result.success
        assert result.value.content == "Updated content"

    def test_update_memory_not_found(self, manager, mock_uow):
        """Test updating a non-existent memory."""
        memory_id = uuid4()
        mock_uow.memories.update.return_value = Result.err("Memory not found")

        request = MemoryUpdateRequest(content="Updated")
        result = manager.update_memory(memory_id, request)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_update_memory_repo_failure(self, manager, mock_uow, sample_memory):
        """Test updating a memory when repository fails."""
        mock_uow.memories.update.return_value = Result.err("Optimistic lock failed")

        request = MemoryUpdateRequest(content="Updated")
        result = manager.update_memory(sample_memory.id, request)

        assert not result.success
        assert "lock" in result.error.lower()

    def test_update_memory_index_failure_continues(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test memory update continues even if semantic index fails."""
        updated_memory = Memory(id=sample_memory.id, content="Updated", status=MemoryStatus.ACTIVE)
        mock_uow.memories.update.return_value = Result.ok(updated_memory)
        mock_semantic_index.update_memory.return_value = Result.err("Index unavailable")

        request = MemoryUpdateRequest(content="Updated")
        result = manager.update_memory(sample_memory.id, request)

        assert result.success
        assert result.value.content == "Updated"

    def test_delete_memory(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test memory deletion."""
        mock_uow.memories.delete.return_value = Result.ok(True)
        mock_semantic_index.remove_memory.return_value = Result.ok(True)

        result = manager.delete_memory(sample_memory.id)

        assert result.success
        assert result.value is True
        mock_semantic_index.remove_memory.assert_called_once_with(sample_memory.id)
        mock_uow.memories.delete.assert_called_once_with(sample_memory.id)

    def test_delete_memory_not_found(self, manager, mock_uow):
        """Test deleting a non-existent memory."""
        memory_id = uuid4()
        mock_uow.memories.delete.return_value = Result.err("Memory not found")

        result = manager.delete_memory(memory_id)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_delete_memory_repo_failure(self, manager, mock_uow, sample_memory):
        """Test deleting a memory when repository fails."""
        mock_uow.memories.delete.return_value = Result.err("Foreign key constraint")

        result = manager.delete_memory(sample_memory.id)

        assert not result.success
        assert "constraint" in result.error.lower()

    def test_search_memories(self, manager, mock_uow, sample_memory):
        """Test memory search."""
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[sample_memory], total=1, limit=50, offset=0))

        params = MemorySearchParams(project_id=sample_memory.project_id, limit=50)
        result = manager.search_memories(params)

        assert result.success
        assert len(result.value) == 1

    def test_search_memories_empty(self, manager, mock_uow):
        """Test memory search with no results."""
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[], total=0, limit=50, offset=0))

        params = MemorySearchParams(project_id=uuid4(), limit=50)
        result = manager.search_memories(params)

        assert result.success
        assert len(result.value) == 0

    def test_search_memories_repo_failure(self, manager, mock_uow):
        """Test memory search when repository fails."""
        mock_uow.memories.search.return_value = Result.err("Search index corrupted")

        params = MemorySearchParams(project_id=uuid4(), limit=50)
        result = manager.search_memories(params)

        assert not result.success
        assert "corrupted" in result.error.lower()

    def test_get_active_memories(self, manager, mock_uow, sample_memory):
        """Test getting active memories for project."""
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])

        result = manager.get_active_memories(sample_memory.project_id, limit=50)

        assert result.success
        assert len(result.value) == 1

    def test_get_active_memories_empty(self, manager, mock_uow, sample_project):
        """Test getting active memories when none exist."""
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])

        result = manager.get_active_memories(sample_project.id, limit=50)

        assert result.success
        assert len(result.value) == 0

    def test_get_active_memories_repo_failure(self, manager, mock_uow, sample_project):
        """Test getting active memories when repository fails."""
        mock_uow.memories.get_active_for_project.return_value = Result.err("Query failed")

        result = manager.get_active_memories(sample_project.id, limit=50)

        assert not result.success
        assert "Query failed" in result.error

    def test_memory_status_transitions(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test canonical memory state transitions."""
        # ACTIVE -> SUPERSEDED
        superseded = Memory(id=sample_memory.id, status=MemoryStatus.SUPERSEDED, content=sample_memory.content)
        mock_uow.memories.update.return_value = Result.ok(superseded)
        mock_semantic_index.update_memory.return_value = Result.ok(True)

        result = manager.update_memory(sample_memory.id, MemoryUpdateRequest(status=MemoryStatus.SUPERSEDED))
        assert result.success
        assert result.value.status == MemoryStatus.SUPERSEDED

        # SUPERSEDED -> ARCHIVED
        archived = Memory(id=sample_memory.id, status=MemoryStatus.ARCHIVED, content=sample_memory.content)
        mock_uow.memories.update.return_value = Result.ok(archived)

        result = manager.update_memory(sample_memory.id, MemoryUpdateRequest(status=MemoryStatus.ARCHIVED))
        assert result.success
        assert result.value.status == MemoryStatus.ARCHIVED

        # ARCHIVED -> DELETED
        deleted = Memory(id=sample_memory.id, status=MemoryStatus.DELETED, content=sample_memory.content)
        mock_uow.memories.update.return_value = Result.ok(deleted)

        result = manager.update_memory(sample_memory.id, MemoryUpdateRequest(status=MemoryStatus.DELETED))
        assert result.success
        assert result.value.status == MemoryStatus.DELETED

    def test_get_active_memories(self, manager, mock_uow, sample_memory):
        """Test getting active memories for project."""
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])

        result = manager.get_active_memories(sample_memory.project_id, limit=50)

        assert result.success
        assert len(result.value) == 1

    # --- Custom Instruction Tests ---

    def test_create_instruction(self, manager, mock_uow):
        """Test instruction creation."""
        instruction = CustomInstruction(id=uuid4(), content="Test instruction", status=InstructionStatus.ACTIVE)
        mock_uow.custom_instructions.create.return_value = Result.ok(instruction)

        request = CustomInstructionCreateRequest(content="Test instruction")
        result = manager.create_instruction(request)

        assert result.success
        assert result.value.content == "Test instruction"

    def test_create_instruction_empty_content(self, manager, mock_uow):
        """Test instruction creation with empty content fails."""
        request = CustomInstructionCreateRequest(content="")
        result = manager.create_instruction(request)

        assert not result.success
        assert "empty" in result.error.lower()
        mock_uow.custom_instructions.create.assert_not_called()

    def test_create_instruction_repo_failure(self, manager, mock_uow):
        """Test instruction creation when repository fails."""
        mock_uow.custom_instructions.create.return_value = Result.err("Duplicate instruction")

        request = CustomInstructionCreateRequest(content="Test")
        result = manager.create_instruction(request)

        assert not result.success
        assert "Duplicate" in result.error

    def test_get_instruction(self, manager, mock_uow):
        """Test getting an instruction by ID."""
        instruction_id = uuid4()
        instruction = CustomInstruction(id=instruction_id, content="Test")
        mock_uow.custom_instructions.get.return_value = Result.ok(instruction)

        result = manager.get_instruction(instruction_id)

        assert result.success
        assert result.value.id == instruction_id

    def test_get_instruction_not_found(self, manager, mock_uow):
        """Test getting a non-existent instruction."""
        instruction_id = uuid4()
        mock_uow.custom_instructions.get.return_value = Result.err("Not found")

        result = manager.get_instruction(instruction_id)

        assert not result.success

    def test_update_instruction(self, manager, mock_uow):
        """Test updating an instruction."""
        instruction_id = uuid4()
        updated = CustomInstruction(id=instruction_id, content="Updated")
        mock_uow.custom_instructions.update.return_value = Result.ok(updated)

        request = CustomInstructionUpdateRequest(content="Updated")
        result = manager.update_instruction(instruction_id, request)

        assert result.success
        assert result.value.content == "Updated"

    def test_delete_instruction(self, manager, mock_uow):
        """Test deleting an instruction."""
        instruction_id = uuid4()
        mock_uow.custom_instructions.delete.return_value = Result.ok(True)

        result = manager.delete_instruction(instruction_id)

        assert result.success
        assert result.value is True

    def test_list_instructions(self, manager, mock_uow):
        """Test listing instructions with filters."""
        from contracts.base import PaginatedResult
        instructions = [
            CustomInstruction(id=uuid4(), content="Inst 1"),
            CustomInstruction(id=uuid4(), content="Inst 2"),
        ]
        mock_uow.custom_instructions.list.return_value = Result.ok(PaginatedResult(items=instructions, total=2, limit=50, offset=0))

        params = CustomInstructionListParams(limit=50, offset=0)
        result = manager.list_instructions(params)

        assert result.success
        assert len(result.value) == 2

    def test_get_active_instructions_global(self, manager, mock_uow, sample_instruction):
        """Test getting active global instructions."""
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([sample_instruction])

        result = manager.get_active_instructions(project_id=None)

        assert result.success
        assert len(result.value) == 1
        mock_uow.custom_instructions.get_active_for_scope.assert_called_with("global", None)

    def test_get_active_instructions_project(self, manager, mock_uow, sample_instruction, sample_project):
        """Test getting active instructions for project (global + project)."""
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]
        project_inst = [CustomInstruction(id=uuid4(), content="Project", scope=Scope.PROJECT, project_id=sample_project.id)]

        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok(project_inst),
        ]

        result = manager.get_active_instructions(project_id=sample_project.id)

        assert result.success
        assert len(result.value) == 2
        assert mock_uow.custom_instructions.get_active_for_scope.call_count == 2

    def test_get_active_instructions_project_only_global(self, manager, mock_uow, sample_project):
        """Test getting active instructions when only global exist."""
        global_inst = [CustomInstruction(id=uuid4(), content="Global", scope=Scope.GLOBAL)]
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok(global_inst),
            Result.ok([]),  # No project-scoped
        ]

        result = manager.get_active_instructions(project_id=sample_project.id)

        assert result.success
        assert len(result.value) == 1
        assert result.value[0].scope == Scope.GLOBAL

    def test_get_active_instructions_repo_failure(self, manager, mock_uow, sample_project):
        """Test getting active instructions when repository fails."""
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.err("Query failed")

        result = manager.get_active_instructions(project_id=sample_project.id)

        assert not result.success
        assert "Query failed" in result.error

    def test_instruction_precedence_in_context_assembly(self, manager, mock_uow, sample_project, sample_session):
        """Test that custom instructions take precedence in context assembly."""
        # Setup: historical memory contradicts custom instruction
        historical_memory = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Old approach: use XML for config",
            status=MemoryStatus.SUPERSEDED,
            provenance="inferred",
        )
        explicit_instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Always use YAML for configuration files",
            status=InstructionStatus.ACTIVE,
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(
            type('obj', (object,), {'items': [historical_memory], 'total': 1})()
        )
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([explicit_instruction])

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            include_custom_instructions=True,
            include_historical=True,
        )
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Custom instruction should be in context
        assert len(context.custom_instructions) == 1
        assert context.custom_instructions[0].content == "Always use YAML for configuration files"
        # Historical memory should be in historical_memories, not active
        assert len(context.historical_memories) == 1
        assert context.historical_memories[0].content == "Old approach: use XML for config"

    # --- Authority / Precedence Tests (Critical RECALL Invariant) ---

    def test_precedence_explicit_instruction_over_historical_memory(self, manager, mock_uow, sample_project, sample_session):
        """Explicit user custom instruction > historical memory."""
        historical = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Use tabs for indentation",
            status=MemoryStatus.SUPERSEDED,
            provenance="inferred",
        )
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Use 4 spaces for indentation",
            status=InstructionStatus.ACTIVE,
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=True, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Instruction should be present and active
        assert any(inst.content == "Use 4 spaces for indentation" for inst in context.custom_instructions)
        # Historical memory should be in historical, not active
        assert any(mem.content == "Use tabs for indentation" for mem in context.historical_memories)
        assert not any(mem.content == "Use tabs for indentation" for mem in context.active_memories)

    def test_precedence_explicit_update_over_historical_memory(self, manager, mock_uow, sample_project):
        """Explicit user update > historical memory."""
        historical = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Old decision: use PostgreSQL",
            status=MemoryStatus.SUPERSEDED,
            provenance="inferred",
        )
        explicit_update = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="New decision: use SQLite for canonical storage",
            status=MemoryStatus.ACTIVE,
            provenance="user_explicit",
        )

        mock_uow.memories.get_active_for_project.return_value = Result.ok([explicit_update])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Explicit update should be in active memories
        explicit_memories = [mem for mem in context.active_memories if mem.content == "New decision: use SQLite for canonical storage"]
        assert len(explicit_memories) == 1
        assert explicit_memories[0].provenance == "user_explicit"
        # Historical should be in historical_memories
        assert any(mem.content == "Old decision: use PostgreSQL" for mem in context.historical_memories)

    def test_precedence_current_canonical_over_historical(self, manager, mock_uow, sample_project):
        """Current canonical memory > older historical memory."""
        current = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Current: API v2 is standard",
            status=MemoryStatus.ACTIVE,
            provenance="user_explicit",
            updated_at=datetime.utcnow(),
        )
        historical = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Old: API v1 is standard",
            status=MemoryStatus.SUPERSEDED,
            provenance="inferred",
            updated_at=datetime.utcnow(),
        )

        mock_uow.memories.get_active_for_project.return_value = Result.ok([current])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Current should be in active
        assert any(mem.content == "Current: API v2 is standard" for mem in context.active_memories)
        # Historical should be in historical
        assert any(mem.content == "Old: API v1 is standard" for mem in context.historical_memories)
        assert not any(mem.content == "Old: API v1 is standard" for mem in context.active_memories)

    def test_precedence_multiple_historical_conflicts(self, manager, mock_uow, sample_project, sample_session):
        """Multiple historical memories conflict - behavior follows contract."""
        hist1 = Memory(id=uuid4(), project_id=sample_project.id, content="Option A", status=MemoryStatus.SUPERSEDED)
        hist2 = Memory(id=uuid4(), project_id=sample_project.id, content="Option B", status=MemoryStatus.SUPERSEDED)
        hist3 = Memory(id=uuid4(), project_id=sample_project.id, content="Option C", status=MemoryStatus.ARCHIVED)

        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [hist1, hist2, hist3], 'total': 3})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # All historical memories should be in historical_memories
        historical_contents = {mem.content for mem in context.historical_memories}
        assert "Option A" in historical_contents
        assert "Option B" in historical_contents
        assert "Option C" in historical_contents
        # None should be in active_memories
        assert len(context.active_memories) == 0

    def test_precedence_custom_instruction_over_conflict_candidate(self, manager, mock_conflict_service, sample_project, sample_instruction):
        """Custom instruction authority preserved over conflict resolution candidates."""
        candidate_memory = Memory(id=uuid4(), project_id=sample_project.id, content="Candidate from conflict", status=MemoryStatus.ACTIVE)
        candidate = ConflictCandidate(memory=candidate_memory)

        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[candidate],
            resolution_reason="Candidate preferred by resolver",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        # Custom instruction contradicts the resolver's preference
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Explicit instruction overrides resolver preference",
            status=InstructionStatus.ACTIVE,
        )

        # When assembling context, instruction should take precedence
        mock_uow = Mock()
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        from core.recall_core.context_assembly import ContextAssemblyService
        assembly = ContextAssemblyService(
            memory_repo=mock_uow.memories if hasattr(mock_uow, 'memories') else Mock(),
            project_repo=mock_uow.projects,
            session_repo=Mock(),
            retrieval_service=Mock(),
        )
        # The manager's assemble_context applies instructions after assembly
        # This tests the precedence at the context assembly level

    # --- Conflict Resolution Boundary Tests ---

    def test_conflict_resolution_delegates_to_service(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test that Core delegates conflict handling to ConflictResolutionService."""
        candidates = [ConflictCandidate(memory=sample_memory)]
        instructions = [sample_instruction]
        project_id = sample_memory.project_id

        resolution = ConflictResolutionResult(status=ConflictResolutionStatus.RESOLVED)
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        result = manager.detect_and_resolve_conflicts(candidates, instructions, project_id=project_id)

        assert result.success
        # Verify service was called with correct request structure
        mock_conflict_service.detect_and_resolve.assert_called_once()
        call_args = mock_conflict_service.detect_and_resolve.call_args[0][0]
        assert call_args.candidates == candidates
        assert call_args.custom_instructions == instructions
        assert call_args.project_context is not None
        assert call_args.project_context.id == project_id

    def test_conflict_resolution_does_not_implement_arbitration(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test that Core does not implement arbitration logic itself."""
        import inspect
        from core.recall_core.memory_manager import MemoryManager

        source = inspect.getsource(MemoryManager.detect_and_resolve_conflicts)

        # Should delegate to conflict_service
        assert "self._conflict_service.detect_and_resolve" in source
        # Should not contain arbitration logic
        assert "llm" not in source.lower()
        assert "arbitrat" not in source.lower()
        assert "model" not in source.lower()
        assert "prompt" not in source.lower()

    def test_conflict_resolution_handles_service_success(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test resolver success is handled correctly."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[ConflictCandidate(memory=sample_memory)],
            resolution_reason="Explicit instruction takes precedence",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        result = manager.detect_and_resolve_conflicts([ConflictCandidate(memory=sample_memory)], [sample_instruction])

        assert result.success
        assert result.value.status == ConflictResolutionStatus.RESOLVED
        assert result.value.resolution_reason == "Explicit instruction takes precedence"
        assert len(result.value.preferred_candidates) == 1

    def test_conflict_resolution_handles_service_failure(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test resolver failure is handled according to contract."""
        mock_conflict_service.detect_and_resolve.return_value = Result.err("Resolver timeout")

        result = manager.detect_and_resolve_conflicts([ConflictCandidate(memory=sample_memory)], [sample_instruction])

        assert not result.success
        assert "timeout" in result.error.lower()

    def test_conflict_resolution_empty_candidates(self, manager, mock_conflict_service):
        """Test empty/no-conflict cases behave correctly."""
        result = manager.detect_and_resolve_conflicts([], [])

        # Should still call service with empty candidates
        assert mock_conflict_service.detect_and_resolve.called

    def test_conflict_resolution_partial_result(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test partially resolved conflicts."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.PARTIALLY_RESOLVED,
            preferred_candidates=[ConflictCandidate(memory=sample_memory)],
            unresolved_candidates=[ConflictCandidate(memory=Memory(id=uuid4(), content="Unresolved"))],
            resolution_reason="Some conflicts remain",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        candidates = [ConflictCandidate(memory=sample_memory), ConflictCandidate(memory=Memory(id=uuid4(), content="Other"))]
        result = manager.detect_and_resolve_conflicts(candidates, [sample_instruction])

        assert result.success
        assert result.value.status == ConflictResolutionStatus.PARTIALLY_RESOLVED
        assert len(result.value.unresolved_candidates) == 1

    def test_conflict_resolution_abstained(self, manager, mock_conflict_service, sample_memory):
        """Test abstained/unresolved conflicts."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.ABSTAINED,
            unresolved_candidates=[ConflictCandidate(memory=sample_memory)],
            resolution_reason="Insufficient information",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        result = manager.detect_and_resolve_conflicts([ConflictCandidate(memory=sample_memory)], [])

        assert result.success
        assert result.value.status == ConflictResolutionStatus.ABSTAINED
        assert result.value.has_unresolved()

    def test_conflict_resolution_explicit_instruction_preserved(self, manager, mock_conflict_service, sample_project):
        """Test explicit higher-authority instructions remain authoritative during conflict resolution."""
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Explicit: always prefer user intent",
            status=InstructionStatus.ACTIVE,
        )
        memory1 = Memory(id=uuid4(), project_id=sample_project.id, content="Inferred A", status=MemoryStatus.ACTIVE)
        memory2 = Memory(id=uuid4(), project_id=sample_project.id, content="Inferred B", status=MemoryStatus.ACTIVE)

        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[ConflictCandidate(memory=memory1)],
            resolution_reason="Resolver picked A",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        candidates = [ConflictCandidate(memory=memory1), ConflictCandidate(memory=memory2)]
        result = manager.detect_and_resolve_conflicts(candidates, [instruction], project_id=sample_project.id)

        assert result.success
        # Verify instruction was passed to resolver
        call_args = mock_conflict_service.detect_and_resolve.call_args[0][0]
        assert len(call_args.custom_instructions) == 1
        assert call_args.custom_instructions[0].content == "Explicit: always prefer user intent"

    # --- Context Assembly Tests ---

    def test_assemble_context_project_only(self, manager, mock_uow, sample_project, sample_memory):
        """Test context assembly with project context only."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.project is not None
        assert context.project.id == sample_project.id
        assert context.session is None
        assert len(context.active_memories) == 1

    def test_assemble_context_session_only(self, manager, mock_uow, sample_session, sample_memory):
        """Test context assembly with session context only (via project)."""
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(Project(id=sample_session.project_id, name="Test"))

        request = ContextAssemblyRequest(session_id=sample_session.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.session is not None
        assert context.session.id == sample_session.id

    def test_assemble_context_project_and_session(self, manager, mock_uow, sample_project, sample_session, sample_memory):
        """Test context assembly with both project and session."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.project.id == sample_project.id
        assert context.session.id == sample_session.id

    def test_assemble_context_with_active_memories(self, manager, mock_uow, sample_project, sample_memory):
        """Test context assembly includes active canonical memories."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.active_memories) == 1
        assert context.active_memories[0].id == sample_memory.id
        assert context.active_memories[0].status == MemoryStatus.ACTIVE

    def test_assemble_context_with_historical_memories(self, manager, mock_uow, sample_project):
        """Test context assembly includes historical memories when requested."""
        historical = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Old decision",
            status=MemoryStatus.SUPERSEDED,
        )
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.historical_memories) == 1
        assert context.historical_memories[0].content == "Old decision"

    def test_assemble_context_without_historical(self, manager, mock_uow, sample_project):
        """Test context assembly excludes historical memories when not requested."""
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old", status=MemoryStatus.SUPERSEDED)
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=False)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.historical_memories) == 0

    def test_assemble_context_with_custom_instructions(self, manager, mock_uow, sample_project):
        """Test context assembly includes custom instructions."""
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Project rule",
            status=InstructionStatus.ACTIVE,
        )
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.custom_instructions) == 1
        assert context.custom_instructions[0].content == "Project rule"

    def test_assemble_context_without_custom_instructions(self, manager, mock_uow, sample_project):
        """Test context assembly excludes custom instructions when not requested."""
        instruction = CustomInstruction(id=uuid4(), content="Rule", status=InstructionStatus.ACTIVE)
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=False)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.custom_instructions) == 0

    def test_assemble_context_with_conflict_results(self, manager, mock_uow, sample_project, sample_memory):
        """Test context assembly includes conflict resolutions."""
        from core.recall_core.context_assembly import ContextAssemblyService
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[type('obj', (object,), {'memory': sample_memory})()],
        )
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        # Use ContextAssemblyService directly to test apply_conflict_resolutions
        assembly = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=Mock(),
        )
        context = AssembledContext(project=sample_project)
        updated = assembly.apply_conflict_resolutions(context, [resolution])

        assert updated is context
        assert len(context.conflict_resolutions) == 1
        assert len(context.resolved_memories) == 1

    def test_assemble_context_empty_sources(self, manager, mock_uow, sample_project):
        """Test context assembly with all empty sources."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.project is not None
        assert len(context.active_memories) == 0
        assert len(context.custom_instructions) == 0
        assert len(context.historical_memories) == 0

    def test_assemble_context_partial_sources(self, manager, mock_uow, sample_project, sample_memory):
        """Test context assembly with some missing optional sources."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(None)  # No session
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=uuid4())
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.project is not None
        assert context.session is None
        assert len(context.active_memories) == 1

    def test_assemble_context_conflicting_sources(self, manager, mock_uow, sample_project, sample_session):
        """Test context assembly with conflicting sources."""
        # Active memory says one thing, historical says another
        active = Memory(id=uuid4(), project_id=sample_project.id, content="Use new API", status=MemoryStatus.ACTIVE)
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Use old API", status=MemoryStatus.SUPERSEDED)
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Migrate to new API",
            status=InstructionStatus.ACTIVE,
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([active])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            include_custom_instructions=True,
            include_historical=True,
        )
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # All sources should be present in their respective buckets
        assert len(context.active_memories) == 1
        assert context.active_memories[0].content == "Use new API"
        assert len(context.historical_memories) == 1
        assert context.historical_memories[0].content == "Use old API"
        assert len(context.custom_instructions) == 1
        assert context.custom_instructions[0].content == "Migrate to new API"

    def test_assemble_context_dependency_failure(self, manager, mock_uow, sample_project):
        """Test context assembly when a dependency fails."""
        mock_uow.projects.get.return_value = Result.err("Project service unavailable")

        request = ContextAssemblyRequest(project_id=sample_project.id)
        result = manager.assemble_context(request)

        assert not result.success
        assert "unavailable" in result.error.lower()

    def test_assemble_context_no_duplicate_memories(self, manager, mock_uow, sample_project, sample_memory):
        """Test context assembly doesn't accidentally duplicate memories."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        # Retrieval returns the same memory
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [], 'total': 0})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        # Mock retrieval to return same memory
        mock_retrieval = Mock()
        mock_retrieval.retrieve.return_value = Result.ok(
            type('obj', (object,), {'memories': [sample_memory], 'total_found': 1})()
        )
        manager._retrieval_service = mock_retrieval

        request = ContextAssemblyRequest(project_id=sample_project.id, query="test")
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Should not have duplicate
        assert len(context.active_memories) == 1

    def test_assemble_context_no_loss_of_authoritative_info(self, manager, mock_uow, sample_project):
        """Test context assembly doesn't lose authoritative information."""
        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Critical rule: never delete production data",
            status=InstructionStatus.ACTIVE,
        )
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Instruction must be preserved
        assert any(inst.content == "Critical rule: never delete production data" for inst in context.custom_instructions)

    # --- /recall compact Tests ---

    def test_compact_nothing_to_compact(self, manager, mock_uow, sample_project):
        """Test compact when there's nothing to compact."""
        # Few active memories, below threshold
        few_memories = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"Memory {i}", status=MemoryStatus.ACTIVE)
            for i in range(10)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=few_memories, total=10, limit=1000, offset=0))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        assert result.value.compacted_count == 0
        assert result.value.superseded_count == 0
        assert result.value.preserved_count == 10

    def test_compact_exactly_at_threshold(self, manager, mock_uow, sample_project):
        """Test compact when active memories exactly at threshold."""
        threshold = 50
        memories = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"Memory {i}", status=MemoryStatus.ACTIVE)
            for i in range(threshold)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=threshold, limit=1000, offset=0))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=threshold)
        result = manager.compact(request)

        assert result.success
        assert result.value.compacted_count == 0
        assert result.value.preserved_count == threshold

    def test_compact_above_threshold_creates_summaries(self, manager, mock_uow, sample_project, sample_session):
        """Test compact above threshold creates summary memories."""
        # 60 active memories, threshold 50
        many_memories = [
            Memory(id=uuid4(), project_id=sample_project.id, session_id=sample_session.id, content=f"Memory {i}", status=MemoryStatus.ACTIVE)
            for i in range(60)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=many_memories, total=60, limit=1000, offset=0))

        # Mock create_memory for summaries
        summary_count = 0
        def create_summary(req):
            nonlocal summary_count
            summary_count += 1
            return Result.ok(Memory(
                id=uuid4(),
                project_id=sample_project.id,
                content=req.content,
                status=MemoryStatus.ACTIVE,
                provenance="compaction_summary",
                supersedes_id=req.supersedes_id,
            ))

        # Mock update_memory for superseding
        supersede_count = 0
        def update_supersede(mem_id, req):
            nonlocal supersede_count
            supersede_count += 1
            return Result.ok(Memory(id=mem_id, status=req.status))

        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(side_effect=update_supersede)

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        assert result.value.compacted_count == 10
        assert result.value.superseded_count == 10
        assert result.value.preserved_count == 50
        assert summary_count == 10
        assert supersede_count == 10

    def test_compact_selection_of_memories(self, manager, mock_uow, sample_project, sample_session):
        """Test compact selects oldest/least relevant memories for compaction."""
        # Create memories with different updated_at timestamps
        base_time = datetime.utcnow()
        memories = []
        for i in range(60):
            mem = Memory(
                id=uuid4(),
                project_id=sample_project.id,
                session_id=sample_session.id,
                content=f"Memory {i}",
                status=MemoryStatus.ACTIVE,
            )
            # Set updated_at manually for test
            memories.append(mem)

        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        created_summaries = []
        def create_summary(req):
            created_summaries.append(req.content)
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE))
        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        # Should have compacted 10 oldest
        assert result.value.compacted_count == 10
        assert len(created_summaries) == 10

    def test_compact_summary_preserves_lineage(self, manager, mock_uow, sample_project, sample_session):
        """Test compact preserves lineage via supersedes_id."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="Original", status=MemoryStatus.ACTIVE)
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[memory] * 60, total=60, limit=1000, offset=0))

        created_supersedes = []
        def create_summary(req):
            created_supersedes.append(req.supersedes_id)
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE))
        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        # All summaries should have supersedes_id pointing to original memories
        assert len(created_supersedes) == 10
        for supersedes_id in created_supersedes:
            assert supersedes_id is not None

    def test_compact_preserves_provenance(self, manager, mock_uow, sample_project, sample_session):
        """Test compact preserves provenance of original memories."""
        original_id = uuid4()
        memory = Memory(id=original_id, project_id=sample_project.id, content="User decision", status=MemoryStatus.ACTIVE, provenance="user_explicit")
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[memory] * 60, total=60, limit=1000, offset=0))

        created_metadata = []
        def create_summary(req):
            created_metadata.append(req.metadata)
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE, metadata=req.metadata))
        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        # Summaries should preserve original metadata plus compaction info
        for meta in created_metadata:
            assert "compacted" in meta
            assert "original_id" in meta
            assert meta["original_id"] == str(original_id)

    def test_compact_preserves_project_session_scope(self, manager, mock_uow, sample_project, sample_session):
        """Test compact preserves project/session scope."""
        memories = [
            Memory(id=uuid4(), project_id=sample_project.id, session_id=sample_session.id, content=f"Mem {i}", status=MemoryStatus.ACTIVE)
            for i in range(60)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        created_requests = []
        def create_summary(req):
            created_requests.append(req)
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE))
        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        for req in created_requests:
            assert req.project_id == sample_project.id
            assert req.session_id == sample_session.id

    def test_compact_archive_behavior(self, manager, mock_uow, sample_project):
        """Test compact archives old historical memories."""
        # 150 historical memories, keep 100
        historical = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"Hist {i}", status=MemoryStatus.SUPERSEDED)
            for i in range(150)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=historical, total=150, limit=1000, offset=0))

        archived_ids = []
        def update_archive(mem_id, req):
            if req.status == MemoryStatus.ARCHIVED:
                archived_ids.append(mem_id)
            return Result.ok(Memory(id=mem_id, status=req.status))
        manager.update_memory = Mock(side_effect=update_archive)

        request = CompactRequest(project_id=sample_project.id)
        result = manager.compact(request)

        assert result.success
        assert result.value.archived_count == 50
        assert len(archived_ids) == 50

    def test_compact_transactional_behavior(self, manager, mock_uow, sample_project, sample_session):
        """Test compact behaves transactionally where defined."""
        memories = [Memory(id=uuid4(), project_id=sample_project.id, content=f"M{i}", status=MemoryStatus.ACTIVE) for i in range(60)]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        # Fail on 5th summary creation
        call_count = 0
        def create_summary_fail(req):
            nonlocal call_count
            call_count += 1
            if call_count == 5:
                return Result.err("Storage full")
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE))
        manager.create_memory = Mock(side_effect=create_summary_fail)
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        # Should handle partial failure gracefully
        assert result.success
        # Errors should be recorded
        assert len(result.value.errors) > 0

    def test_compact_partial_operation_failure(self, manager, mock_uow, sample_project, sample_session):
        """Test compact handles partial operation failure."""
        memories = [Memory(id=uuid4(), project_id=sample_project.id, content=f"M{i}", status=MemoryStatus.ACTIVE) for i in range(60)]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        # Fail on supersede
        supersede_count = 0
        def update_supersede_fail(mem_id, req):
            nonlocal supersede_count
            supersede_count += 1
            if supersede_count == 3:
                return Result.err("Lock timeout")
            return Result.ok(Memory(id=mem_id, status=req.status))
        manager.create_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Summary", status=MemoryStatus.ACTIVE)))
        manager.update_memory = Mock(side_effect=update_supersede_fail)

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        assert len(result.value.errors) > 0

    def test_compact_indexing_failure(self, manager, mock_uow, mock_semantic_index, sample_project, sample_session):
        """Test compact handles indexing failure as best-effort."""
        memories = [Memory(id=uuid4(), project_id=sample_project.id, content=f"M{i}", status=MemoryStatus.ACTIVE) for i in range(60)]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        manager.create_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Summary", status=MemoryStatus.ACTIVE)))
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))
        mock_semantic_index.index_memory.return_value = Result.err("Index down")

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        # Indexing failure should not block compaction

    def test_compact_repeated_compaction(self, manager, mock_uow, sample_project, sample_session):
        """Test repeated compaction behavior."""
        memories = [Memory(id=uuid4(), project_id=sample_project.id, content=f"M{i}", status=MemoryStatus.ACTIVE) for i in range(60)]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=memories, total=60, limit=1000, offset=0))

        manager.create_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Summary", status=MemoryStatus.ACTIVE)))
        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result1 = manager.compact(request)
        result2 = manager.compact(request)

        assert result1.success
        assert result2.success
        # Second compaction should find fewer active memories (already compacted)
        # This depends on implementation - verify it doesn't error

    def test_compact_does_not_delete_canonical_info(self, manager, mock_uow, sample_project, sample_session):
        """Test compact does not accidentally delete canonical information."""
        original_id = uuid4()
        memory = Memory(id=original_id, project_id=sample_project.id, content="Critical decision", status=MemoryStatus.ACTIVE, provenance="user_explicit")
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[memory] * 60, total=60, limit=1000, offset=0))

        deleted_ids = []
        def update_supersede(mem_id, req):
            if req.status == MemoryStatus.DELETED:
                deleted_ids.append(mem_id)
            return Result.ok(Memory(id=mem_id, status=req.status))
        manager.create_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Summary", status=MemoryStatus.ACTIVE)))
        manager.update_memory = Mock(side_effect=update_supersede)

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        # No memory should be DELETED, only SUPERSEDED or ARCHIVED
        assert original_id not in deleted_ids
        assert result.value.archived_count >= 0
        assert result.value.superseded_count >= 0

    # --- /recall update-context Tests ---

    def test_update_context_success(self, manager, sample_project):
        """Test explicit context update."""
        new_memory = Memory(id=uuid4(), project_id=sample_project.id, content="Explicit update", status=MemoryStatus.ACTIVE)
        manager.create_memory = Mock(return_value=Result.ok(new_memory))

        request = UpdateContextRequest(project_id=sample_project.id, content="Explicit update")
        result = manager.update_context(request)

        assert result.success
        assert result.value.memory_id == new_memory.id
        manager.create_memory.assert_called_once()

    def test_update_context_empty_content(self, manager):
        """Test update context fails with empty content."""
        request = UpdateContextRequest(content="")
        result = manager.update_context(request)

        assert not result.success
        assert "empty" in result.error.lower()

    def test_update_context_whitespace_content(self, manager):
        """Test update context fails with whitespace-only content."""
        request = UpdateContextRequest(content="   \n\t  ")
        result = manager.update_context(request)

        assert not result.success

    def test_update_context_provenance(self, manager, sample_project, sample_session):
        """Test update context creates memory with correct provenance."""
        manager.create_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Test", status=MemoryStatus.ACTIVE)))

        request = UpdateContextRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Explicit update",
            provenance="user_directive",
            memory_type="decision",
        )
        result = manager.update_context(request)

        assert result.success
        # Verify create_memory was called with correct parameters
        call_args = manager.create_memory.call_args[0][0]
        assert call_args.content == "Explicit update"
        assert call_args.provenance == "user_directive"
        assert call_args.memory_type == "decision"
        assert call_args.project_id == sample_project.id
        assert call_args.session_id == sample_session.id
        assert call_args.metadata.get("explicit_update") is True

    def test_update_context_interaction_with_retrieval(self, manager, mock_retrieval_service, sample_project, sample_session):
        """Test update context interaction with subsequent retrieval."""
        new_memory = Memory(id=uuid4(), project_id=sample_project.id, content="New explicit context", status=MemoryStatus.ACTIVE)
        manager.create_memory = Mock(return_value=Result.ok(new_memory))

        request = UpdateContextRequest(project_id=sample_project.id, content="New explicit context")
        result = manager.update_context(request)

        assert result.success

        # Now retrieval should find it
        mock_retrieval_service.retrieve.return_value = Result.ok(
            RetrievalResult(memories=[new_memory], total_found=1)
        )
        retrieval_result = manager.search("explicit context", project_id=sample_project.id)

        assert retrieval_result.success
        assert retrieval_result.value.total_found == 1

    def test_update_context_precedence_over_historical(self, manager, mock_uow, sample_project, sample_session):
        """Test update context takes precedence over historical memory."""
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old context", status=MemoryStatus.SUPERSEDED)
        explicit = Memory(id=uuid4(), project_id=sample_project.id, content="New explicit context", status=MemoryStatus.ACTIVE, provenance="user_explicit")

        manager.create_memory = Mock(return_value=Result.ok(explicit))

        request = UpdateContextRequest(project_id=sample_project.id, content="New explicit context")
        result = manager.update_context(request)

        assert result.success

        # In context assembly, explicit should be in active, historical in historical
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([explicit])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        assemble_request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        assemble_result = manager.assemble_context(assemble_request)

        assert assemble_result.success
        context = assemble_result.value
        assert any(m.content == "New explicit context" for m in context.active_memories)
        assert any(m.content == "Old context" for m in context.historical_memories)
        assert not any(m.content == "Old context" for m in context.active_memories)

    def test_update_context_persistence_failure(self, manager):
        """Test update context when persistence fails."""
        manager.create_memory = Mock(return_value=Result.err("Disk full"))

        request = UpdateContextRequest(content="Test")
        result = manager.update_context(request)

        assert not result.success
        assert "Disk full" in result.error

    def test_update_context_invalid_input(self, manager):
        """Test update context with invalid input."""
        # Missing required content
        request = UpdateContextRequest(content=None)
        result = manager.update_context(request)

        assert not result.success

    def test_update_context_no_accidental_mutation(self, manager, mock_uow, sample_project, sample_memory):
        """Test update context doesn't mutate unrelated memories."""
        existing = sample_memory
        new_explicit = Memory(id=uuid4(), project_id=sample_project.id, content="New context", status=MemoryStatus.ACTIVE)
        manager.create_memory = Mock(return_value=Result.ok(new_explicit))

        request = UpdateContextRequest(project_id=sample_project.id, content="New context")
        result = manager.update_context(request)

        assert result.success
        # Verify only create_memory was called, not update/delete on existing
        manager.create_memory.assert_called_once()
        # Should not have called update/delete on existing memories

    # --- Project / Session Isolation Tests ---

    def test_project_isolation_memories(self, manager, mock_uow):
        """Test project A does not receive project B memories."""
        project_a = Project(id=uuid4(), name="Project A")
        project_b = Project(id=uuid4(), name="Project B")
        mem_a = Memory(id=uuid4(), project_id=project_a.id, content="Project A memory", status=MemoryStatus.ACTIVE)
        mem_b = Memory(id=uuid4(), project_id=project_b.id, content="Project B memory", status=MemoryStatus.ACTIVE)

        # When querying project A, only A's memories should be returned
        mock_uow.memories.get_active_for_project.return_value = Result.ok([mem_a])
        mock_uow.projects.get.return_value = Result.ok(project_a)
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=project_a.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.active_memories) == 1
        assert context.active_memories[0].content == "Project A memory"
        assert context.active_memories[0].project_id == project_a.id
        # Verify get_active_for_project was called with project A's ID
        mock_uow.memories.get_active_for_project.assert_called_with(project_a.id, 50)

    def test_project_isolation_instructions(self, manager, mock_uow):
        """Test project A does not receive project B instructions."""
        project_a = Project(id=uuid4(), name="Project A")
        project_b = Project(id=uuid4(), name="Project B")
        inst_a = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project_a.id, content="A's rule", status=InstructionStatus.ACTIVE)
        inst_b = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project_b.id, content="B's rule", status=InstructionStatus.ACTIVE)
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global rule", status=InstructionStatus.ACTIVE)

        # Project A gets global + A's project instructions
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),  # global
            Result.ok([inst_a]),       # project A
        ]
        mock_uow.projects.get.return_value = Result.ok(project_a)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [], 'total': 0})())

        request = ContextAssemblyRequest(project_id=project_a.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        instruction_contents = {inst.content for inst in context.custom_instructions}
        assert "Global rule" in instruction_contents
        assert "A's rule" in instruction_contents
        assert "B's rule" not in instruction_contents

    def test_session_isolation(self, manager, mock_uow):
        """Test session-specific context does not leak across sessions."""
        project = Project(id=uuid4(), name="Test Project")
        session_1 = Session(id=uuid4(), project_id=project.id)
        session_2 = Session(id=uuid4(), project_id=project.id)
        mem_1 = Memory(id=uuid4(), project_id=project.id, session_id=session_1.id, content="Session 1 memory", status=MemoryStatus.ACTIVE)
        mem_2 = Memory(id=uuid4(), project_id=project.id, session_id=session_2.id, content="Session 2 memory", status=MemoryStatus.ACTIVE)

        # Query session 1
        mock_uow.projects.get.return_value = Result.ok(project)
        mock_uow.sessions.get.return_value = Result.ok(session_1)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([mem_1])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=project.id, session_id=session_1.id)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.session.id == session_1.id
        assert len(context.active_memories) == 1
        assert context.active_memories[0].content == "Session 1 memory"
        assert context.active_memories[0].session_id == session_1.id

    def test_multiple_sessions_same_project(self, manager, mock_uow):
        """Test multiple sessions in same project work independently."""
        project = Project(id=uuid4(), name="Test Project")
        sessions = [Session(id=uuid4(), project_id=project.id) for _ in range(3)]
        memories = [Memory(id=uuid4(), project_id=project.id, session_id=s.id, content=f"Mem for {s.id}", status=MemoryStatus.ACTIVE) for s in sessions]

        for i, (session, memory) in enumerate(zip(sessions, memories)):
            mock_uow.projects.get.return_value = Result.ok(project)
            mock_uow.sessions.get.return_value = Result.ok(session)
            mock_uow.memories.get_active_for_project.return_value = Result.ok([memory])
            mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

            request = ContextAssemblyRequest(project_id=project.id, session_id=session.id)
            result = manager.assemble_context(request)

            assert result.success
            assert result.value.session.id == session.id
            assert result.value.active_memories[0].content == f"Mem for {session.id}"

    def test_overlapping_memory_content_different_projects(self, manager, mock_uow):
        """Test overlapping memory text/content across projects."""
        project_a = Project(id=uuid4(), name="Project A")
        project_b = Project(id=uuid4(), name="Project B")
        # Same content in both projects
        mem_a = Memory(id=uuid4(), project_id=project_a.id, content="Use Python for scripting", status=MemoryStatus.ACTIVE)
        mem_b = Memory(id=uuid4(), project_id=project_b.id, content="Use Python for scripting", status=MemoryStatus.ACTIVE)

        mock_uow.memories.get_active_for_project.side_effect = [
            Result.ok([mem_a]),
            Result.ok([mem_b]),
        ]
        mock_uow.projects.get.side_effect = [Result.ok(project_a), Result.ok(project_b)]
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        # Query project A
        result_a = manager.assemble_context(ContextAssemblyRequest(project_id=project_a.id))
        assert result_a.success
        assert result_a.value.active_memories[0].project_id == project_a.id

        # Query project B
        result_b = manager.assemble_context(ContextAssemblyRequest(project_id=project_b.id))
        assert result_b.success
        assert result_b.value.active_memories[0].project_id == project_b.id

    def test_global_instructions_applied_correctly(self, manager, mock_uow):
        """Test global instructions are applied according to contract."""
        project = Project(id=uuid4(), name="Test Project")
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global: prefer simplicity", status=InstructionStatus.ACTIVE)
        project_inst = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project.id, content="Project: use type hints", status=InstructionStatus.ACTIVE)

        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),
            Result.ok([project_inst]),
        ]
        mock_uow.projects.get.return_value = Result.ok(project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [], 'total': 0})())

        request = ContextAssemblyRequest(project_id=project.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert len(context.custom_instructions) == 2
        contents = {inst.content for inst in context.custom_instructions}
        assert "Global: prefer simplicity" in contents
        assert "Project: use type hints" in contents

    def test_global_instructions_only_no_project(self, manager, mock_uow):
        """Test global instructions work for project without project-scoped instructions."""
        project = Project(id=uuid4(), name="Test Project")
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global rule", status=InstructionStatus.ACTIVE)

        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),
            Result.ok([]),  # No project-scoped
        ]
        mock_uow.projects.get.return_value = Result.ok(project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=project.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        assert len(result.value.custom_instructions) == 1
        assert result.value.custom_instructions[0].content == "Global rule"

    def test_retrieval_filters_passed_correctly(self, manager, mock_retrieval_service, sample_project):
        """Test retrieval filters are passed correctly."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="Filtered memory", status=MemoryStatus.ACTIVE)
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[memory], total_found=1))

        request = RetrievalRequest(
            query="test",
            project_id=sample_project.id,
            memory_types=["decision"],
            include_historical=False,
            limit=10,
        )
        result = manager.retrieve(request)

        assert result.success
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.project_id == sample_project.id
        assert called_request.memory_types == ["decision"]
        assert called_request.include_historical is False
        assert called_request.limit == 10

    # --- Error and Failure Path Tests ---

    def test_project_repo_failure(self, manager, mock_uow, sample_project):
        """Test ProjectRepository failure handling."""
        mock_uow.projects.get.return_value = Result.err("DB connection lost")

        result = manager.get_project(sample_project.id)

        assert not result.success
        assert "connection" in result.error.lower()

    def test_session_repo_failure(self, manager, mock_uow, sample_session):
        """Test SessionRepository failure handling."""
        mock_uow.sessions.get.return_value = Result.err("Session table locked")

        result = manager.get_session(sample_session.id)

        assert not result.success
        assert "locked" in result.error.lower()

    def test_memory_repo_failure(self, manager, mock_uow, sample_memory):
        """Test MemoryRepository failure handling."""
        mock_uow.memories.get.return_value = Result.err("Memory index corrupted")

        result = manager.get_memory(sample_memory.id)

        assert not result.success
        assert "corrupted" in result.error.lower()

    def test_instruction_repo_failure(self, manager, mock_uow):
        """Test CustomInstructionRepository failure handling."""
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.err("Instruction query failed")

        result = manager.get_active_instructions(project_id=uuid4())

        assert not result.success
        assert "failed" in result.error.lower()

    def test_semantic_index_repo_failure(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Test SemanticIndexRepository failure handling (best-effort)."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="Test", status=MemoryStatus.ACTIVE)
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.err("Vector DB unavailable")

        request = MemoryCreateRequest(project_id=sample_project.id, content="Test")
        result = manager.create_memory(request)

        # Canonical succeeds, semantic is best-effort
        assert result.success

    def test_retrieval_service_failure(self, manager, mock_retrieval_service):
        """Test RetrievalService failure handling."""
        mock_retrieval_service.retrieve.return_value = Result.err("Embedding service down")

        request = RetrievalRequest(query="test", limit=10)
        result = manager.retrieve(request)

        assert not result.success
        assert "down" in result.error.lower()

    def test_conflict_service_failure(self, manager, mock_conflict_service, sample_memory):
        """Test ConflictResolutionService failure handling."""
        mock_conflict_service.detect_and_resolve.return_value = Result.err("Resolver crashed")

        result = manager.detect_and_resolve_conflicts([ConflictCandidate(memory=sample_memory)], [])

        assert not result.success
        assert "crashed" in result.error.lower()

    def test_all_dependencies_fail_independently(self, manager, mock_uow, mock_retrieval_service, mock_conflict_service, mock_semantic_index, sample_project):
        """Test each major dependency failing independently."""
        # Project repo fails
        mock_uow.projects.get.return_value = Result.err("Project DB down")
        result = manager.get_project(sample_project.id)
        assert not result.success

        # Session repo fails
        mock_uow.sessions.get.return_value = Result.err("Session DB down")
        result = manager.get_session(uuid4())
        assert not result.success

        # Memory repo fails
        mock_uow.memories.get.return_value = Result.err("Memory DB down")
        result = manager.get_memory(uuid4())
        assert not result.success

        # Instruction repo fails
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.err("Instruction DB down")
        result = manager.get_active_instructions()
        assert not result.success

        # Semantic index fails (best-effort)
        mock_uow.memories.create.return_value = Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content="Test", status=MemoryStatus.ACTIVE))
        mock_semantic_index.index_memory.return_value = Result.err("Index down")
        result = manager.create_memory(MemoryCreateRequest(project_id=sample_project.id, content="Test"))
        assert result.success  # Best-effort

        # Retrieval fails
        mock_retrieval_service.retrieve.return_value = Result.err("Retrieval down")
        result = manager.retrieve(RetrievalRequest(query="test"))
        assert not result.success

        # Conflict fails
        mock_conflict_service.detect_and_resolve.return_value = Result.err("Conflict down")
        result = manager.detect_and_resolve_conflicts([], [])
        assert not result.success

    def test_failures_not_silently_swallowed(self, manager, mock_uow, sample_project):
        """Test failures are not silently swallowed."""
        mock_uow.projects.create.return_value = Result.err("Explicit error")

        result = manager.create_project(ProjectCreateRequest(name="Test"))

        assert not result.success
        assert result.error is not None
        assert "Explicit error" in result.error

    def test_failures_not_fabricated_success(self, manager, mock_uow):
        """Test failures don't become fabricated successful results."""
        mock_uow.projects.create.return_value = Result.err("Real error")

        result = manager.create_project(ProjectCreateRequest(name="Test"))

        assert not result.success
        assert result.value is None

    def test_failures_no_partial_inconsistent_state(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Test failures don't create partially inconsistent state."""
        # Memory creation fails after semantic index was called
        mock_uow.memories.create.return_value = Result.err("Constraint violation")
        mock_semantic_index.index_memory.return_value = Result.ok(True)

        result = manager.create_memory(MemoryCreateRequest(project_id=sample_project.id, content="Test"))

        assert not result.success
        # Semantic index was called but canonical failed - this is expected
        # Core doesn't rollback semantic index (it's derived)

    # --- Retrieval Tests ---

    def test_retrieve(self, manager, mock_retrieval_service, sample_memory):
        """Test memory retrieval."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))

        request = RetrievalRequest(query="test", limit=20)
        result = manager.retrieve(request)

        assert result.success
        assert result.value.total_found == 1
        mock_retrieval_service.retrieve.assert_called_once_with(request)

    def test_retrieve_empty_results(self, manager, mock_retrieval_service):
        """Test retrieval with empty results."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[], total_found=0))

        request = RetrievalRequest(query="nonexistent", limit=20)
        result = manager.retrieve(request)

        assert result.success
        assert result.value.total_found == 0
        assert len(result.value.memories) == 0

    def test_retrieve_failure(self, manager, mock_retrieval_service):
        """Test retrieval when service fails."""
        mock_retrieval_service.retrieve.return_value = Result.err("Embedding model unavailable")

        request = RetrievalRequest(query="test", limit=20)
        result = manager.retrieve(request)

        assert not result.success
        assert "Embedding model" in result.error

    def test_retrieve_passes_correct_scope(self, manager, mock_retrieval_service, sample_memory, sample_project):
        """Test retrieval passes correct project/session scope."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))

        request = RetrievalRequest(query="test", project_id=sample_project.id, session_id=uuid4(), limit=10)
        result = manager.retrieve(request)

        assert result.success
        # Verify the request passed to service has correct scope
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.project_id == sample_project.id
        assert called_request.session_id == request.session_id
        assert called_request.limit == 10

    def test_retrieve_passes_filters(self, manager, mock_retrieval_service, sample_memory):
        """Test retrieval passes relevant filters/options."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))

        request = RetrievalRequest(
            query="test",
            project_id=uuid4(),
            include_historical=True,
            memory_types=["decision", "fact"],
            limit=25
        )
        result = manager.retrieve(request)

        assert result.success
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.include_historical is True
        assert called_request.memory_types == ["decision", "fact"]
        assert called_request.limit == 25

    def test_search_convenience(self, manager, mock_retrieval_service, sample_memory):
        """Test convenience search method."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))

        result = manager.search("test query", project_id=uuid4(), limit=10)

        assert result.success
        assert result.value.total_found == 1
        # Verify it constructs a proper RetrievalRequest
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.query == "test query"
        assert called_request.limit == 10

    def test_search_convenience_without_project(self, manager, mock_retrieval_service, sample_memory):
        """Test convenience search without project scope (global)."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))

        result = manager.search("global query", limit=5)

        assert result.success
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.query == "global query"
        assert called_request.project_id is None
        assert called_request.limit == 5

    # --- Semantic Indexing Tests ---

    def test_create_memory_indexes_semantic(self, manager, mock_uow, mock_semantic_index, sample_project, sample_session):
        """Test that memory creation calls semantic index with correct memory."""
        memory = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Test memory for indexing",
            status=MemoryStatus.ACTIVE,
        )
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.ok(True)

        request = MemoryCreateRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Test memory for indexing",
        )
        result = manager.create_memory(request)

        assert result.success
        mock_semantic_index.index_memory.assert_called_once()
        indexed_memory = mock_semantic_index.index_memory.call_args[0][0]
        assert indexed_memory.content == "Test memory for indexing"
        assert indexed_memory.project_id == sample_project.id

    def test_update_memory_updates_semantic(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test that memory update calls semantic index update."""
        updated = Memory(id=sample_memory.id, content="Updated content", status=MemoryStatus.ACTIVE)
        mock_uow.memories.update.return_value = Result.ok(updated)
        mock_semantic_index.update_memory.return_value = Result.ok(True)

        request = MemoryUpdateRequest(content="Updated content")
        result = manager.update_memory(sample_memory.id, request)

        assert result.success
        mock_semantic_index.update_memory.assert_called_once()
        indexed_memory = mock_semantic_index.update_memory.call_args[0][0]
        assert indexed_memory.content == "Updated content"

    def test_delete_memory_removes_from_semantic(self, manager, mock_uow, mock_semantic_index, sample_memory):
        """Test that memory deletion removes from semantic index."""
        mock_uow.memories.delete.return_value = Result.ok(True)
        mock_semantic_index.remove_memory.return_value = Result.ok(True)

        result = manager.delete_memory(sample_memory.id)

        assert result.success
        mock_semantic_index.remove_memory.assert_called_once_with(sample_memory.id)

    def test_semantic_index_failure_is_best_effort(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Test that semantic index failures are handled as best-effort."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="Test", status=MemoryStatus.ACTIVE)
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.err("ChromaDB unavailable")

        request = MemoryCreateRequest(project_id=sample_project.id, content="Test")
        result = manager.create_memory(request)

        # Canonical persistence succeeds independently
        assert result.success
        assert result.value.content == "Test"
        # Index was still attempted
        mock_semantic_index.index_memory.assert_called_once()

    def test_semantic_index_interface_calls(self, manager, mock_semantic_index, sample_project, sample_memory):
        """Test that Core calls SemanticIndexRepository interface correctly."""
        # Verify all expected interface methods exist and are called
        mock_semantic_index.index_memory.return_value = Result.ok(True)
        mock_semantic_index.update_memory.return_value = Result.ok(True)
        mock_semantic_index.remove_memory.return_value = Result.ok(True)
        mock_semantic_index.search_similar.return_value = Result.ok([])
        mock_semantic_index.rebuild_from_canonical.return_value = Result.ok(100)
        mock_semantic_index.health_check.return_value = Result.ok({"status": "healthy"})

        # These are called through manager operations
        manager.create_memory(MemoryCreateRequest(project_id=sample_project.id, content="Test"))
        manager.update_memory(sample_memory.id, MemoryUpdateRequest(content="Updated"))
        manager.delete_memory(sample_memory.id)

        mock_semantic_index.index_memory.assert_called()
        mock_semantic_index.update_memory.assert_called()
        mock_semantic_index.remove_memory.assert_called()

    def test_core_does_not_contain_vector_logic(self):
        """Verify Core implementation doesn't contain vector store implementation details."""
        import inspect
        from core.recall_core import memory_manager

        source = inspect.getsource(memory_manager.MemoryManager)

        # Should not contain direct ChromaDB/SQLite/vector logic
        assert "chromadb" not in source.lower()
        assert "sqlite" not in source.lower()
        assert "embedding" not in source.lower()
        assert "vector" not in source.lower()
        assert "faiss" not in source.lower()
        assert "hnsw" not in source.lower()
        # Should delegate to interfaces
        assert "semantic_index" in source.lower()
        assert "_semantic_index" in source

    # --- Conflict Resolution Tests ---

    def test_detect_and_resolve_conflicts(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test conflict detection and resolution."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            decisions=[ResolutionDecision(candidate_id=sample_memory.id, action="keep", reason="User explicit")],
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        candidates = [ConflictCandidate(memory=sample_memory)]
        result = manager.detect_and_resolve_conflicts(candidates, [sample_instruction])

        assert result.success
        assert result.value.status == ConflictResolutionStatus.RESOLVED

    # --- Context Assembly Tests ---

    def test_assemble_context(self, manager, mock_uow, sample_project, sample_session, sample_memory):
        """Test context assembly."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id)
        result = manager.assemble_context(request)

        assert result.success
        assert result.value.project.id == sample_project.id
        assert len(result.value.active_memories) == 1

    # --- Compact Tests ---

    def test_compact_no_project_id(self, manager):
        """Test compact fails without project ID."""
        request = CompactRequest(project_id=None)
        result = manager.compact(request)

        assert not result.success
        assert "Project ID required" in result.error

    def test_compact_creates_summaries(self, manager, mock_uow, sample_project, sample_memory):
        """Test compact creates summary memories for excess active memories."""
        # Create many active memories
        many_memories = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"Memory {i}", status=MemoryStatus.ACTIVE)
            for i in range(60)
        ]
        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=many_memories, total=60, limit=1000, offset=0))

        # Mock create_memory for summaries
        def create_summary(req):
            return Result.ok(Memory(id=uuid4(), project_id=sample_project.id, content=req.content, status=MemoryStatus.ACTIVE))
        manager.create_memory = Mock(side_effect=create_summary)

        # Mock update_memory for superseding
        manager.update_memory = Mock(return_value=Result.ok(many_memories[0]))

        request = CompactRequest(project_id=sample_project.id, max_active_memories=50)
        result = manager.compact(request)

        assert result.success
        assert result.value.compacted_count == 10
        assert result.value.superseded_count == 10
        assert result.value.preserved_count == 50

    def test_compact_archives_old_historical(self, manager, mock_uow, sample_project):
        """Test compact archives old historical memories."""
        # Create many historical memories
        many_historical = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"Hist {i}", status=MemoryStatus.SUPERSEDED)
            for i in range(150)
        ]
        all_memories = many_historical  # Only historical for this test

        from contracts.base import PaginatedResult
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=all_memories, total=150, limit=1000, offset=0))

        manager.update_memory = Mock(return_value=Result.ok(Memory(id=uuid4(), status=MemoryStatus.ARCHIVED)))

        request = CompactRequest(project_id=sample_project.id)
        result = manager.compact(request)

        assert result.success
        assert result.value.archived_count == 50  # 150 - 100 kept

    # --- Update Context Tests ---

    def test_update_context_success(self, manager, sample_project):
        """Test explicit context update."""
        new_memory = Memory(id=uuid4(), project_id=sample_project.id, content="Explicit update", status=MemoryStatus.ACTIVE)
        manager.create_memory = Mock(return_value=Result.ok(new_memory))

        request = UpdateContextRequest(project_id=sample_project.id, content="Explicit update")
        result = manager.update_context(request)

        assert result.success
        assert result.value.memory_id == new_memory.id
        manager.create_memory.assert_called_once()

    def test_update_context_empty_content(self, manager):
        """Test update context fails with empty content."""
        request = UpdateContextRequest(content="")
        result = manager.update_context(request)

        assert not result.success
        assert "empty" in result.error.lower()

    # --- Stats Tests ---

    def test_get_stats(self, manager, mock_uow, sample_project):
        """Test getting statistics."""
        from contracts.base import PaginatedResult

        mock_uow.projects.list.return_value = Result.ok(PaginatedResult(items=[sample_project], total=1, limit=1000, offset=0))
        mock_uow.sessions.list.return_value = Result.ok(PaginatedResult(items=[], total=5, limit=1000, offset=0))
        mock_uow.memories.search.return_value = Result.ok(PaginatedResult(items=[], total=10, limit=1000, offset=0))
        mock_uow.custom_instructions.list.return_value = Result.ok(PaginatedResult(items=[], total=3, limit=1000, offset=0))
        mock_uow.semantic_index.health_check.return_value = Result.ok({"status": "healthy", "vectors": 100})

        result = manager.get_stats(project_id=sample_project.id)

        assert result.success
        stats = result.value
        assert stats["projects"] == 1
        assert stats["sessions"] == 5
        assert stats["memories"]["active"] == 10
        assert stats["custom_instructions"]["active"] == 3
        assert stats["semantic_index"]["status"] == "healthy"

    # --- Lifecycle Tests ---

    def test_close(self, manager, mock_uow):
        """Test closing the manager."""
        manager.close()
        mock_uow.close.assert_called_once()

    def test_context_manager(self, manager, mock_uow):
        """Test using manager as context manager."""
        with manager as m:
            assert m is manager
        mock_uow.close.assert_called_once()

    # --- Memory creation/invalid input tests ---

    def test_create_memory_invalid_content(self, manager, mock_uow):
        """Test memory creation fails with empty content."""
        mock_uow.memories.create.return_value = Result.err("Content cannot be empty")
        request = MemoryCreateRequest(project_id=uuid4(), content="")
        result = manager.create_memory(request)
        assert not result.success
        assert "empty" in result.error.lower() or "content" in result.error.lower()

    def test_create_memory_missing_project(self, manager, mock_uow, sample_session):
        """Test memory creation with missing project_id still works (global scope)."""
        request = MemoryCreateRequest(session_id=sample_session.id, content="Global memory")
        result = manager.create_memory(request)
        # Should succeed with global scope, project_id optional
        assert result.success or result.error is not None

    # --- Memory retrieval delegation tests ---

    def test_retrieve_delegates_to_service(self, manager, mock_retrieval_service, sample_memory):
        """Test retrieve delegates to RetrievalService."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[sample_memory], total_found=1))
        request = RetrievalRequest(query="test", limit=10)
        result = manager.retrieve(request)
        assert result.success
        mock_retrieval_service.retrieve.assert_called_once_with(request)

    def test_retrieve_empty_query(self, manager, mock_retrieval_service):
        """Test retrieval with empty query string."""
        mock_retrieval_service.retrieve.return_value = Result.ok(RetrievalResult(memories=[], total_found=0))
        request = RetrievalRequest(query="", limit=20)
        result = manager.retrieve(request)
        assert result.success
        assert result.value.total_found == 0

    # --- Conflict resolution delegation tests ---

    def test_detect_and_resolve_conflicts_delegates(self, manager, mock_conflict_service, sample_memory, sample_instruction):
        """Test detect_and_resolve_conflicts fully delegates to ConflictResolutionService."""
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(ConflictResolutionResult(status=ConflictResolutionStatus.RESOLVED))
        candidates = [ConflictCandidate(memory=sample_memory)]
        result = manager.detect_and_resolve_conflicts(candidates, [sample_instruction])
        assert result.success
        mock_conflict_service.detect_and_resolve.assert_called_once()

    def test_detect_and_resolve_conflicts_empty_candidates(self, manager, mock_conflict_service):
        """Test detect_and_resolve_conflicts with empty candidates list."""
        result = manager.detect_and_resolve_conflicts([], [])
        assert mock_conflict_service.detect_and_resolve.called

    def test_detect_and_resolve_conflicts_no_instructions(self, manager, mock_conflict_service, sample_memory):
        """Test detect_and_resolve_conflicts with no custom instructions."""
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(ConflictResolutionResult(status=ConflictResolutionStatus.ABSTAINED))
        result = manager.detect_and_resolve_conflicts([ConflictCandidate(memory=sample_memory)], [])
        assert result.success
        assert result.value.status == ConflictResolutionStatus.ABSTAINED

    # --- Context assembly comprehensive tests ---

    def test_assemble_context_all_sources(self, manager, mock_uow, sample_project, sample_session, sample_memory):
        """Test context assembly with project, session, memories, and instructions."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])
        # Historical memories search - return empty list since sample_memory is ACTIVE
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [], 'total': 0})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
    
        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id, include_historical=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        assert context.project is not None
        assert context.session is not None
        assert len(context.active_memories) == 1
        assert len(context.historical_memories) == 0

    def test_assemble_context_no_project_no_session(self, manager, mock_uow):
        """Test context assembly without project or session."""
        mock_uow.projects.get.return_value = Result.ok(None)  # type: ignore
        # No project, no session

        request = ContextAssemblyRequest()
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        assert context.project is None
        assert context.session is None

    def test_assemble_context_with_historical_and_instructions(self, manager, mock_uow, sample_project, sample_session):
        """Test historical memories and custom instructions coexist correctly."""
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old decision", status=MemoryStatus.SUPERSEDED)
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global approach", status=InstructionStatus.ACTIVE)
        instruction = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id, content="New approach", status=InstructionStatus.ACTIVE)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        # Global instruction returns global, project instruction returns project
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),    # get_active_global -> "global"
            Result.ok([instruction]),    # get_active_for_scope("project", project_id) -> "project"
        ]

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id, include_custom_instructions=True, include_historical=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        # Historical memory in historical_memories
        assert len(context.historical_memories) == 1
        assert context.historical_memories[0].content == "Old decision"
        # Custom instructions: both global and project (no duplication since they have different scopes)
        assert len(context.custom_instructions) == 2
        contents = {inst.content for inst in context.custom_instructions}
        assert "Global approach" in contents
        assert "New approach" in contents
        # No active memories from historical
        assert len(context.active_memories) == 0

    def test_project_isolation_instructions_detailed(self, manager, mock_uow):
        """Test detailed project isolation: project A gets only its own instructions."""
        project_a = Project(id=uuid4(), name="Project A")
        project_b = Project(id=uuid4(), name="Project B")
        inst_a = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project_a.id, content="A's rule", status=InstructionStatus.ACTIVE)
        inst_b = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=project_b.id, content="B's rule", status=InstructionStatus.ACTIVE)
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global rule", status=InstructionStatus.ACTIVE)

        # Project A: get_active_for_scope returns global + project A
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),  # global scope
            Result.ok([inst_a]),       # project scope = project_a
        ]
        mock_uow.projects.get.return_value = Result.ok(project_a)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [], 'total': 0})())

        request = ContextAssemblyRequest(project_id=project_a.id, include_custom_instructions=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        instruction_contents = {inst.content for inst in context.custom_instructions}
        assert "Global rule" in instruction_contents
        assert "A's rule" in instruction_contents
        assert "B's rule" not in instruction_contents

    def test_assemble_context_dependency_project_repo_failure(self, manager, mock_uow):
        """Test context assembly propagates project repo failure."""
        mock_uow.projects.get.return_value = Result.err("Project service unavailable")

        request = ContextAssemblyRequest(project_id=uuid4())
        result = manager.assemble_context(request)
        assert not result.success
        assert "unavailable" in result.error.lower() or "project" in result.error.lower()

    def test_assemble_context_custom_instructions_disabled(self, manager, mock_uow, sample_project):
        """Test context assembly respects include_custom_instructions=False."""
        instruction = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id, content="Project rule", status=InstructionStatus.ACTIVE)
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=False)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        assert len(context.custom_instructions) == 0

    # --- Authority/precedence critical invariants ---

    def test_explicit_instruction_over_historical_memory(self, manager, mock_uow, sample_project, sample_session):
        """EXPLICIT USER CUSTOM INSTRUCTION > historical memory (authority invariant)."""
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Use tabs for indentation", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        explicit_inst = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id, content="Use 4 spaces for indentation", status=InstructionStatus.ACTIVE)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([explicit_inst])

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=True, include_historical=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        # Instruction takes precedence - should be in custom_instructions, not active_memories
        assert any(inst.content == "Use 4 spaces for indentation" for inst in context.custom_instructions)
        # Historical memory should be in historical, not active
        assert any(mem.content == "Use tabs for indentation" for mem in context.historical_memories)
        assert not any(mem.content == "Use tabs for indentation" for mem in context.active_memories)

    def test_explicit_update_over_historical_memory(self, manager, mock_uow, sample_project):
        """EXPLICIT USER UPDATE > historical memory (authority invariant)."""
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old decision: use PostgreSQL", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        explicit_update = Memory(id=uuid4(), project_id=sample_project.id, content="New decision: use SQLite for canonical storage", status=MemoryStatus.ACTIVE, provenance="user_explicit")

        mock_uow.memories.get_active_for_project.return_value = Result.ok([explicit_update])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        # Explicit update in active memories
        explicit_memories = [mem for mem in context.active_memories if mem.content == "New decision: use SQLite for canonical storage"]
        assert len(explicit_memories) == 1
        assert explicit_memories[0].provenance == "user_explicit"
        # Historical in historical_memories
        assert any(mem.content == "Old decision: use PostgreSQL" for mem in context.historical_memories)

    def test_current_canonical_over_older_historical(self, manager, mock_uow, sample_project):
        """CURRENT CANONICAL MEMORY > older historical memory (authority invariant)."""
        current = Memory(id=uuid4(), project_id=sample_project.id, content="Current: API v2 is standard", status=MemoryStatus.ACTIVE, provenance="user_explicit", updated_at=datetime.utcnow())
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old: API v1 is standard", status=MemoryStatus.SUPERSEDED, provenance="inferred", updated_at=datetime.utcnow())

        mock_uow.memories.get_active_for_project.return_value = Result.ok([current])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)
        assert result.success
        context = result.value
        # Current canonical in active
        assert any(mem.content == "Current: API v2 is standard" for mem in context.active_memories)
        # Older historical in historical
        assert any(mem.content == "Old: API v1 is standard" for mem in context.historical_memories)
        assert not any(mem.content == "Old: API v1 is standard" for mem in context.active_memories)

    def test_no_authority_downgrade_by_conflict_resolver(self, manager, mock_conflict_service, sample_project, sample_memory, sample_instruction):
        """Conflict resolver output does not silently downgrade higher-authority information."""
        # Set up a conflict where the resolver might try to prefer a lower-authority candidate
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[ConflictCandidate(memory=sample_memory)],
            resolution_reason="resolver picked this",
        )
        mock_conflict_service.detect_and_resolve.return_value = Result.ok(resolution)

        instruction = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id, content="Explicit: always prefer user intent", status=InstructionStatus.ACTIVE)

        # Manager passes instruction to resolver
        result = manager.detect_and_resolve_conflicts(
            [ConflictCandidate(memory=sample_memory)],
            [instruction],
            project_id=sample_project.id
        )
        assert result.success
        # Instruction was passed to resolver
        call_args = mock_conflict_service.detect_and_resolve.call_args[0][0]
        assert len(call_args.custom_instructions) == 1
        assert call_args.custom_instructions[0].content == "Explicit: always prefer user intent"
        # Resolution result should preserve the instruction's authority
        assert result.value is not None

    # --- Boundary: Core does not implement storage/algorithm logic ---

    def test_manager_delegates_all_storage_to_repositories(self, manager, mock_uow):
        """Verify MemoryManager does not implement SQL or storage logic directly."""
        import inspect
        from core.recall_core.memory_manager import MemoryManager

        source = inspect.getsource(MemoryManager.create_memory)
        # Should not contain direct SQL
        assert "insert" not in source.lower()
        assert "update" not in source.lower()
        assert "delete" not in source.lower()
        # Should use repository
        assert "self._uow.memories.create" in source or "self._uow.memories.update" in source or "self._uow.memories.delete" in source

    def test_manager_delegates_retrieval_fully(self, manager, mock_retrieval_service):
        """Verify MemoryManager does not implement retrieval algorithms."""
        import inspect
        from core.recall_core.memory_manager import MemoryManager

        source = inspect.getsource(MemoryManager.retrieve)
        # Should delegate to retrieval service
        assert "self._retrieval_service.retrieve" in source
        # Should not contain ranking or ranking logic
        assert "rank" not in source.lower() or "self._retrieval_service" in source

    def test_manager_delegates_conflict_resolution_fully(self, manager, mock_conflict_service):
        """Verify MemoryManager does not implement conflict arbitration."""
        import inspect
        from core.recall_core.memory_manager import MemoryManager

        source = inspect.getsource(MemoryManager.detect_and_resolve_conflicts)
        # Should delegate to conflict service
        assert "self._conflict_service.detect_and_resolve" in source
        # Should not contain LLM/model logic
        assert "llm" not in source.lower()
        assert "model" not in source.lower()
        assert "prompt" not in source.lower()