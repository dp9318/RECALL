"""Integration tests for Core flows with mocked dependencies.

These tests verify complete request/response cycles through MemoryManager,
exercising the coordination of multiple services. They do NOT test concrete
storage/retrieval implementations (which do not yet exist).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, call

from contracts.base import Result, Scope, MemoryStatus, InstructionStatus, PaginatedResult
from contracts.conflict import ConflictResolutionResult, ConflictResolutionStatus
from contracts.instruction import CustomInstruction, CustomInstructionCreateRequest, CustomInstructionListParams
from contracts.memory import Memory, MemoryCreateRequest, MemorySearchParams, MemoryUpdateRequest
from contracts.project import Project, ProjectCreateRequest, Session, SessionCreateRequest, SessionUpdateRequest
from contracts.retrieval import (
    RetrievalRequest, RetrievalResult, ContextAssemblyRequest,
    AssembledContext, CompactRequest, CompactResult, UpdateContextRequest, UpdateContextResult,
)
from core.recall_core.memory_manager import MemoryManager


@pytest.fixture
def manager(mock_uow, mock_retrieval_service, mock_conflict_service, mock_semantic_index):
    return MemoryManager(
        unit_of_work=mock_uow,
        retrieval_service=mock_retrieval_service,
        conflict_service=mock_conflict_service,
        semantic_index=mock_semantic_index,
    )


class TestMemoryLifecycleIntegration:
    """Full memory lifecycle through MemoryManager."""

    def test_create_get_update_delete_memory(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Verify complete memory lifecycle."""
        mem_id = uuid4()
        created = Memory(id=mem_id, project_id=sample_project.id, content="Original", status=MemoryStatus.ACTIVE)
        mock_uow.memories.create.return_value = Result.ok(created)
        mock_semantic_index.index_memory.return_value = Result.ok(True)

        create_result = manager.create_memory(MemoryCreateRequest(
            project_id=sample_project.id, content="Original"
        ))
        assert create_result.success
        assert create_result.value.id == mem_id

        mock_uow.memories.get.return_value = Result.ok(created)
        get_result = manager.get_memory(mem_id)
        assert get_result.success
        assert get_result.value.content == "Original"

        updated = Memory(id=mem_id, project_id=sample_project.id, content="Updated", status=MemoryStatus.ACTIVE)
        mock_uow.memories.update.return_value = Result.ok(updated)
        mock_semantic_index.update_memory.return_value = Result.ok(True)

        update_result = manager.update_memory(mem_id, MemoryUpdateRequest(content="Updated"))
        assert update_result.success
        assert update_result.value.content == "Updated"

        mock_uow.memories.delete.return_value = Result.ok(True)
        mock_semantic_index.remove_memory.return_value = Result.ok(True)

        delete_result = manager.delete_memory(mem_id)
        assert delete_result.success
        assert delete_result.value is True

        mock_uow.memories.create.assert_called_once()
        mock_uow.memories.get.assert_called_once_with(mem_id)
        mock_uow.memories.update.assert_called_once()
        mock_uow.memories.delete.assert_called_once_with(mem_id)

    def test_create_memory_with_semantic_index_failure_still_succeeds(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Canonical write succeeds even if semantic index fails."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, content="Test", status=MemoryStatus.ACTIVE)
        mock_uow.memories.create.return_value = Result.ok(memory)
        mock_semantic_index.index_memory.return_value = Result.err("Index unavailable")

        result = manager.create_memory(MemoryCreateRequest(project_id=sample_project.id, content="Test"))

        assert result.success
        assert result.value.id == memory.id
        assert "semantic_index_error" in result.metadata

    def test_delete_memory_does_not_touch_index_when_canonical_fails(self, manager, mock_uow, mock_semantic_index):
        """When canonical delete fails, semantic index must not be touched."""
        mock_uow.memories.delete.return_value = Result.err("Canonical store unavailable")

        result = manager.delete_memory(uuid4())

        assert not result.success
        mock_semantic_index.remove_memory.assert_not_called()


class TestSessionLifecycleIntegration:
    """Full session lifecycle through MemoryManager."""

    def test_create_get_end_session(self, manager, mock_uow, sample_project):
        """Verify complete session lifecycle."""
        session_id = uuid4()
        created_session = Session(id=session_id, project_id=sample_project.id)
        mock_uow.sessions.create.return_value = Result.ok(created_session)

        create_result = manager.create_session(SessionCreateRequest(project_id=sample_project.id))
        assert create_result.success
        assert create_result.value.id == session_id

        mock_uow.sessions.get.return_value = Result.ok(created_session)
        get_result = manager.get_session(session_id)
        assert get_result.success
        assert get_result.value.id == session_id

        ended_session = Session(
            id=session_id, project_id=sample_project.id,
            ended_at=datetime.now(timezone.utc),
        )
        mock_uow.sessions.update.return_value = Result.ok(ended_session)

        end_result = manager.end_session(session_id)
        assert end_result.success
        assert end_result.value.ended_at is not None

        mock_uow.sessions.create.assert_called_once()
        mock_uow.sessions.get.assert_called_once_with(session_id)
        mock_uow.sessions.update.assert_called_once()


class TestContextAssemblyIntegration:
    """Full context assembly with all sources."""

    def test_assemble_context_all_sources(self, manager, mock_uow, sample_project, sample_session):
        """Verify context assembly with project, session, memories, and instructions."""
        memory = Memory(id=uuid4(), project_id=sample_project.id, session_id=sample_session.id,
                        content="Active memory", status=MemoryStatus.ACTIVE)
        instruction = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL,
                                        content="Global rule", status=InstructionStatus.ACTIVE)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([memory])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            include_custom_instructions=True,
        )
        result = manager.assemble_context(request)

        assert result.success
        context = result.value
        assert context.project.id == sample_project.id
        assert context.session.id == sample_session.id
        assert len(context.active_memories) == 1
        assert len(context.custom_instructions) == 1
        assert context.assembled_at != ""

    def test_assemble_context_with_historical(self, manager, mock_uow, sample_project):
        """Verify historical memories are included when requested."""
        historical = Memory(id=uuid4(), project_id=sample_project.id,
                            content="Old decision", status=MemoryStatus.SUPERSEDED)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get_active_for_project.return_value = Result.ok(None)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(
            type('obj', (object,), {'items': [historical], 'total': 1})()
        )
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        request = ContextAssemblyRequest(
            project_id=sample_project.id,
            include_historical=True,
        )
        result = manager.assemble_context(request)

        assert result.success
        assert len(result.value.historical_memories) == 1
        assert result.value.historical_memories[0].content == "Old decision"

    def test_assemble_context_with_query_triggers_retrieval(self, manager, mock_uow, mock_retrieval_service, sample_project):
        """Verify query triggers retrieval service."""
        retrieved = Memory(id=uuid4(), project_id=sample_project.id,
                           content="Retrieved", status=MemoryStatus.ACTIVE)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get_active_for_project.return_value = Result.ok(None)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_retrieval_service.retrieve.return_value = Result.ok(
            RetrievalResult(memories=[retrieved], total_found=1)
        )

        request = ContextAssemblyRequest(project_id=sample_project.id, query="test query")
        result = manager.assemble_context(request)

        assert result.success
        mock_retrieval_service.retrieve.assert_called_once()
        assert len(result.value.active_memories) == 1


class TestCompactIntegration:
    """Full compact operation through MemoryManager."""

    def test_compact_creates_summaries_and_supersedes(self, manager, mock_uow, sample_project, sample_session):
        """Verify compact creates summary memories and supersedes originals."""
        memories = [
            Memory(id=uuid4(), project_id=sample_project.id, session_id=sample_session.id,
                   content=f"Memory {i}", status=MemoryStatus.ACTIVE)
            for i in range(60)
        ]
        mock_uow.memories.search.return_value = Result.ok(
            PaginatedResult(items=memories, total=60, limit=1000, offset=0)
        )

        def create_summary(req):
            return Result.ok(Memory(
                id=uuid4(), project_id=sample_project.id,
                content=req.content, status=MemoryStatus.ACTIVE,
                provenance=req.provenance, supersedes_id=req.supersedes_id,
            ))
        manager.create_memory = Mock(side_effect=create_summary)
        manager.update_memory = Mock(return_value=Result.ok(
            Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)
        ))

        result = manager.compact(CompactRequest(project_id=sample_project.id, max_active_memories=50))

        assert result.success
        assert result.value.compacted_count == 11
        assert result.value.superseded_count == 11
        assert result.value.preserved_count == 50

    def test_compact_with_index_failure_still_succeeds(self, manager, mock_uow, mock_semantic_index, sample_project):
        """Compact succeeds even if semantic index fails during re-indexing."""
        memories = [
            Memory(id=uuid4(), project_id=sample_project.id, content=f"M{i}", status=MemoryStatus.ACTIVE)
            for i in range(60)
        ]
        mock_uow.memories.search.return_value = Result.ok(
            PaginatedResult(items=memories, total=60, limit=1000, offset=0)
        )
        manager.create_memory = Mock(return_value=Result.ok(
            Memory(id=uuid4(), project_id=sample_project.id, content="summary", status=MemoryStatus.ACTIVE)
        ))
        manager.update_memory = Mock(return_value=Result.ok(
            Memory(id=uuid4(), status=MemoryStatus.SUPERSEDED)
        ))
        mock_semantic_index.index_memory.return_value = Result.err("Index down")

        result = manager.compact(CompactRequest(project_id=sample_project.id, max_active_memories=50))

        assert result.success


class TestUpdateContextIntegration:
    """Full update-context flow through MemoryManager."""

    def test_update_context_creates_explicit_memory(self, manager, sample_project, sample_session):
        """Verify update-context creates a memory with explicit provenance."""
        new_memory = Memory(id=uuid4(), project_id=sample_project.id, content="Explicit update",
                            status=MemoryStatus.ACTIVE, provenance="user_explicit")
        manager.create_memory = Mock(return_value=Result.ok(new_memory))

        result = manager.update_context(UpdateContextRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            content="Explicit update",
        ))

        assert result.success
        assert result.value.memory_id == new_memory.id

        call_args = manager.create_memory.call_args[0][0]
        assert call_args.provenance == "user_explicit"
        assert call_args.metadata.get("explicit_update") is True


class TestAuthorityPrecedenceIntegration:
    """End-to-end authority precedence verification."""

    def test_explicit_instruction_beats_historical_in_full_flow(self, manager, mock_uow, sample_project, sample_session):
        """Explicit custom instruction > historical memory in complete context assembly."""
        historical = Memory(id=uuid4(), project_id=sample_project.id,
                            content="Use tabs", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        instruction = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id,
                                        content="Use 4 spaces", status=InstructionStatus.ACTIVE)

        mock_uow.projects.get.return_value = Result.ok(sample_project)
        mock_uow.sessions.get.return_value = Result.ok(sample_session)
        mock_uow.memories.get_active_for_project.return_value = Result.ok([])
        mock_uow.memories.search.return_value = Result.ok(
            type('obj', (object,), {'items': [historical], 'total': 1})()
        )
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([instruction])

        result = manager.assemble_context(ContextAssemblyRequest(
            project_id=sample_project.id,
            session_id=sample_session.id,
            include_custom_instructions=True,
            include_historical=True,
        ))

        assert result.success
        context = result.value
        assert any(i.content == "Use 4 spaces" for i in context.custom_instructions)
        assert any(m.content == "Use tabs" for m in context.historical_memories)
        assert not any(m.content == "Use tabs" for m in context.active_memories)

    def test_explicit_update_beats_historical_in_full_flow(self, manager, mock_uow, sample_project):
        """Explicit user update > historical memory in complete context assembly."""
        historical = Memory(id=uuid4(), project_id=sample_project.id,
                            content="Old: PostgreSQL", status=MemoryStatus.SUPERSEDED, provenance="inferred")
        explicit = Memory(id=uuid4(), project_id=sample_project.id,
                          content="New: SQLite", status=MemoryStatus.ACTIVE, provenance="user_explicit")

        mock_uow.memories.get_active_for_project.return_value = Result.ok([explicit])
        mock_uow.memories.search.return_value = Result.ok(
            type('obj', (object,), {'items': [historical], 'total': 1})()
        )
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])
        mock_uow.projects.get.return_value = Result.ok(sample_project)

        result = manager.assemble_context(ContextAssemblyRequest(
            project_id=sample_project.id,
            include_historical=True,
        ))

        assert result.success
        context = result.value
        assert any(m.content == "New: SQLite" for m in context.active_memories)
        assert any(m.content == "Old: PostgreSQL" for m in context.historical_memories)


class TestProjectIsolationIntegration:
    """Project isolation in complete flows."""

    def test_project_a_does_not_see_project_b_memories(self, manager, mock_uow):
        """Verify project isolation in context assembly."""
        project_a = Project(id=uuid4(), name="A")
        project_b = Project(id=uuid4(), name="B")
        mem_a = Memory(id=uuid4(), project_id=project_a.id, content="A memory", status=MemoryStatus.ACTIVE)
        mem_b = Memory(id=uuid4(), project_id=project_b.id, content="B memory", status=MemoryStatus.ACTIVE)

        mock_uow.memories.get_active_for_project.return_value = Result.ok([mem_a])
        mock_uow.projects.get.return_value = Result.ok(project_a)
        mock_uow.custom_instructions.get_active_for_scope.return_value = Result.ok([])

        result = manager.assemble_context(ContextAssemblyRequest(project_id=project_a.id))

        assert result.success
        assert len(result.value.active_memories) == 1
        assert result.value.active_memories[0].project_id == project_a.id
        mock_uow.memories.get_active_for_project.assert_called_with(project_a.id, 20)


class TestCustomInstructionLifecycleIntegration:
    """Full custom instruction lifecycle through MemoryManager."""

    def test_create_get_update_delete_instruction(self, manager, mock_uow):
        """Verify complete instruction lifecycle."""
        inst_id = uuid4()
        created = CustomInstruction(id=inst_id, content="Test", status=InstructionStatus.ACTIVE)
        mock_uow.custom_instructions.create.return_value = Result.ok(created)

        create_result = manager.create_instruction(CustomInstructionCreateRequest(content="Test"))
        assert create_result.success
        assert create_result.value.id == inst_id

        mock_uow.custom_instructions.get.return_value = Result.ok(created)
        get_result = manager.get_instruction(inst_id)
        assert get_result.success
        assert get_result.value.content == "Test"

        updated = CustomInstruction(id=inst_id, content="Updated", status=InstructionStatus.ACTIVE)
        mock_uow.custom_instructions.update.return_value = Result.ok(updated)

        from contracts.instruction import CustomInstructionUpdateRequest
        update_result = manager.update_instruction(inst_id, CustomInstructionUpdateRequest(content="Updated"))
        assert update_result.success
        assert update_result.value.content == "Updated"

        mock_uow.custom_instructions.delete.return_value = Result.ok(True)
        delete_result = manager.delete_instruction(inst_id)
        assert delete_result.success
        assert delete_result.value is True

        mock_uow.custom_instructions.create.assert_called_once()
        mock_uow.custom_instructions.get.assert_called_once_with(inst_id)
        mock_uow.custom_instructions.update.assert_called_once()
        mock_uow.custom_instructions.delete.assert_called_once_with(inst_id)

    def test_get_active_instructions_combines_global_and_project(self, manager, mock_uow, sample_project):
        """Verify get_active_instructions combines global and project-scoped."""
        global_inst = CustomInstruction(id=uuid4(), scope=Scope.GLOBAL, content="Global", status=InstructionStatus.ACTIVE)
        project_inst = CustomInstruction(id=uuid4(), scope=Scope.PROJECT, project_id=sample_project.id,
                                         content="Project", status=InstructionStatus.ACTIVE)

        mock_uow.custom_instructions.get_active_for_scope.side_effect = [
            Result.ok([global_inst]),
            Result.ok([project_inst]),
        ]

        result = manager.get_active_instructions(project_id=sample_project.id)

        assert result.success
        assert len(result.value) == 2
        scopes = {i.scope for i in result.value}
        assert Scope.GLOBAL in scopes
        assert Scope.PROJECT in scopes
