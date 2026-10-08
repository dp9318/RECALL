"""Tests for ContextAssemblyService."""

import pytest
from uuid import UUID, uuid4
from datetime import datetime
from unittest.mock import Mock

from contracts.base import Result, Scope, MemoryStatus
from contracts.conflict import ConflictResolutionResult, ConflictResolutionStatus
from contracts.instruction import CustomInstruction, InstructionStatus
from contracts.memory import Memory, MemorySearchParams
from contracts.project import Project, Session
from contracts.retrieval import RetrievalRequest, RetrievalResult, ContextAssemblyRequest, AssembledContext
from core.recall_core.context_assembly import ContextAssemblyService


class TestContextAssemblyService:
    """Tests for ContextAssemblyService."""

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

    def test_assemble_context_basic(self, mock_uow, mock_retrieval_service, sample_project, sample_session, sample_memory):
        """Test basic context assembly."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        request = ContextAssemblyRequest(project_id=sample_project.id, session_id=sample_session.id)
        result = service.assemble(request)

        assert result.success
        context = result.value
        assert context.project is not None
        assert context.project.id == sample_project.id
        assert context.session is not None
        assert context.session.id == sample_session.id
        assert len(context.active_memories) == 1
        assert context.active_memories[0].id == sample_memory.id

    def test_assemble_context_with_query(self, mock_uow, mock_retrieval_service, sample_project, sample_session, sample_memory):
        """Test context assembly with retrieval query."""
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([sample_memory])

        retrieval_memory = Memory(
            id=uuid4(),
            project_id=sample_project.id,
            content="Retrieved memory",
            status=MemoryStatus.ACTIVE,
        )
        mock_retrieval_service.retrieve.return_value = Result.ok(
            RetrievalResult(memories=[retrieval_memory], total_found=1)
        )

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            query="test query",
        )
        result = service.assemble(request)

        assert result.success
        context = result.value
        assert context.query == "test query"
        assert len(context.active_memories) == 2  # original + retrieved
        mock_retrieval_service.retrieve.assert_called_once()

    def test_apply_custom_instructions(self, mock_uow, mock_retrieval_service, sample_project):
        """Test applying custom instructions to context."""
        instructions = [
            CustomInstruction(id=uuid4(), content="Global instruction", scope=Scope.GLOBAL),
            CustomInstruction(id=uuid4(), content="Project instruction", scope=Scope.PROJECT, project_id=sample_project.id),
        ]

        context = AssembledContext(project=sample_project)

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        updated_context = service.apply_custom_instructions(context, instructions)

        assert updated_context is context  # Same object
        assert len(context.custom_instructions) == 2
        assert context.custom_instructions[0].content == "Global instruction"

    def test_apply_conflict_resolutions(self, mock_uow, mock_retrieval_service, sample_project, sample_memory):
        """Test applying conflict resolutions to context."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[
                type('obj', (object,), {'memory': sample_memory})()
            ],
            superseded_candidates=[],
            unresolved_candidates=[],
        )

        context = AssembledContext(project=sample_project)

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        updated_context = service.apply_conflict_resolutions(context, [resolution])

        assert updated_context is context
        assert len(context.conflict_resolutions) == 1
        assert len(context.resolved_memories) == 1
        assert context.resolved_memories[0].id == sample_memory.id

    def test_assemble_context_dependency_project_repo_failure(self, mock_uow):
        """Test context assembly propagates project repo failure."""
        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=Mock(),
        )

        mock_uow.projects.get.return_value = Result.err("Project service unavailable")

        request = ContextAssemblyRequest(project_id=uuid4())
        result = service.assemble(request)

        assert not result.success
        assert result.error is not None

    def test_assemble_context_empty_request(self, mock_uow, mock_retrieval_service):
        """Test context assembly with no project or session."""
        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        request = ContextAssemblyRequest()
        result = service.assemble(request)

        assert result.success
        context = result.value
        assert context.project is None
        assert context.session is None
        assert context.active_memories == []
        assert context.custom_instructions == []

    def test_assemble_context_with_conflict_resolutions(self, mock_uow, mock_retrieval_service, sample_project, sample_memory):
        """Test context assembly with conflict resolutions flag."""
        resolution = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            preferred_candidates=[
                type('obj', (object,), {'memory': sample_memory})()
            ],
            superseded_candidates=[],
            unresolved_candidates=[],
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        request = ContextAssemblyRequest(project_id=sample_project.id, include_resolved_conflicts=True)
        result = service.assemble(request)

        assert result.success
        context = result.value
        # Conflict resolutions are included when flag is set and query is provided
        assert context.query is None  # No query, so no retrieval
        # conflict_resolutions will be empty without a query
        assert len(context.conflict_resolutions) == 0

    def test_assemble_context_applies_custom_instructions_via_manager(self, mock_uow, sample_project, sample_session):
        """Test that manager's assemble_context applies custom instructions correctly without duplication."""
        from core.recall_core.memory_manager import MemoryManager
        from unittest.mock import Mock

        # Create manager with mocked dependencies
        mock_retrieval_service = Mock(spec=['retrieve'])
        mock_conflict_service = Mock(spec=['detect_and_resolve'])

        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_uow.semantic_index,
        )

        instruction = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Project rule",
            status=InstructionStatus.ACTIVE,
        )
        # Use DIFFERENT instructions for global and project to avoid duplication
        global_inst = CustomInstruction(
            id=uuid4(),
            scope=Scope.GLOBAL,
            content="Global rule",
            status=InstructionStatus.ACTIVE,
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        # Setup: global instruction returns one result, project returns different one
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),    # get_active_global -> "global"
            Result.ok([instruction]),    # get_active_for_scope("project", project_id) -> "project"
        ]

        request = ContextAssemblyRequest(project_id=sample_project.id, include_custom_instructions=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Should have exactly 2 instructions: global + project (no duplication)
        assert len(context.custom_instructions) == 2
        contents = {inst.content for inst in context.custom_instructions}
        assert "Global rule" in contents
        assert "Project rule" in contents

    def test_assemble_context_authority_precedence_explicit_instruction(self, mock_uow, sample_project, sample_session):
        """Test explicit custom instruction takes precedence over historical memory in context assembly."""
        from core.recall_core.memory_manager import MemoryManager
        from unittest.mock import Mock

        mock_retrieval_service = Mock(spec=['retrieve'])
        mock_conflict_service = Mock(spec=['detect_and_resolve'])
        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_uow.semantic_index,
        )

        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old approach: use XML", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        explicit_inst = CustomInstruction(
            id=uuid4(),
            scope=Scope.PROJECT,
            project_id=sample_project.id,
            content="Always use YAML for configuration",
            status=InstructionStatus.ACTIVE,
        )

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        # Return empty for global, project instruction for project scope
        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([]),                    # get_active_global -> no global instructions
            Result.ok([explicit_inst]),       # get_active_for_scope("project", project_id) -> project instruction
        ]
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([explicit_inst])

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            include_custom_instructions=True,
            include_historical=True,
        )
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Custom instruction should be present (project scope only, not duplicated from global)
        assert len(context.custom_instructions) == 1
        assert context.custom_instructions[0].content == "Always use YAML for configuration"
        # Historical memory should be in historical_memories, not active
        assert len(context.historical_memories) == 1
        assert context.historical_memories[0].content == "Old approach: use XML"
        # Historical should NOT be in active_memories
        assert not any(mem.content == "Old approach: use XML" for mem in context.active_memories)

    def test_assemble_context_authority_precedence_explicit_update(self, mock_uow, sample_project):
        """Test explicit user update takes precedence over historical memory."""
        from core.recall_core.memory_manager import MemoryManager
        from unittest.mock import Mock

        mock_retrieval_service = Mock(spec=['retrieve'])
        mock_conflict_service = Mock(spec=['detect_and_resolve'])
        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_uow.semantic_index,
        )

        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old decision: use PostgreSQL", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        explicit_update = Memory(id=uuid4(), project_id=sample_project.id, content="New decision: use SQLite", status=MemoryStatus.ACTIVE, provenance="user_explicit")

        mock_uow.memories.get_active_for_project.return_value = Result.ok([explicit_update])
        mock_uow.memories.search.return_value = Result.ok(type('obj', (object,), {'items': [historical], 'total': 1})())
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        request = ContextAssemblyRequest(project_id=sample_project.id, include_historical=True)
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        # Explicit update in active
        explicit_memories = [mem for mem in context.active_memories if mem.content == "New decision: use SQLite"]
        assert len(explicit_memories) == 1
        assert explicit_memories[0].provenance == "user_explicit"
        # Historical in historical_memories
        assert any(mem.content == "Old decision: use PostgreSQL" for mem in context.historical_memories)

    def test_assemble_context_authority_precedence_current_canonical(self, mock_uow, sample_project):
        """Test current canonical memory takes precedence over older historical memory."""
        from core.recall_core.memory_manager import MemoryManager
        from unittest.mock import Mock

        mock_retrieval_service = Mock(spec=['retrieve'])
        mock_conflict_service = Mock(spec=['detect_and_resolve'])
        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_uow.semantic_index,
        )

        current = Memory(id=uuid4(), project_id=sample_project.id, content="Current: API v2 is standard", status=MemoryStatus.ACTIVE, provenance="user_explicit", updated_at=datetime.utcnow().isoformat())
        historical = Memory(id=uuid4(), project_id=sample_project.id, content="Old: API v1 is standard", status=MemoryStatus.SUPERSEDED, provenance="inferred", updated_at=datetime.utcnow().isoformat())

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
        # Older historical in historical_memories
        assert any(mem.content == "Old: API v1 is standard" for mem in context.historical_memories)
        assert not any(mem.content == "Old: API v1 is standard" for mem in context.active_memories)

def test_assemble_context_propagates_session_repository_failure(self, mock_uow, mock_retrieval_service, sample_project):
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get_active_for_project.return_value = Result.err("Session store unavailable")

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )
        result = service.assemble(ContextAssemblyRequest(project_id=sample_project.id))

        assert not result.success
        assert "Session store unavailable" in result.error

    def test_assemble_context_propagates_retrieval_failure(self, mock_uow, mock_retrieval_service, sample_project):
        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_retrieval_service.retrieve.return_value = Result.err("Retrieval unavailable")

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )
        result = service.assemble(ContextAssemblyRequest(project_id=sample_project.id, query="test"))

        assert not result.success
        assert "Retrieval unavailable" in result.error
