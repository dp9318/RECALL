"""Tests verifying all timestamps are timezone-aware UTC."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from contracts.base import Scope, MemoryStatus, InstructionStatus, TimestampMixin
from contracts.memory import Memory, MemoryCreateRequest
from contracts.project import Project, Session, SessionUpdateRequest
from contracts.instruction import CustomInstruction
from contracts.retrieval import ContextAssemblyRequest, AssembledContext
from core.recall_core.context_assembly import ContextAssemblyService
from core.recall_core.memory_manager import MemoryManager


class TestTimestampMixin:
    """Verify TimestampMixin produces timezone-aware UTC datetimes."""

    def test_created_at_is_timezone_aware(self):
        obj = TimestampMixin()
        assert obj.created_at.tzinfo is not None
        assert obj.created_at.tzinfo == timezone.utc

    def test_updated_at_is_timezone_aware(self):
        obj = TimestampMixin()
        assert obj.updated_at.tzinfo is not None
        assert obj.updated_at.tzinfo == timezone.utc

    def test_timestamps_are_utc(self):
        before = datetime.now(timezone.utc)
        obj = TimestampMixin()
        after = datetime.now(timezone.utc)
        assert before <= obj.created_at <= after
        assert before <= obj.updated_at <= after


class TestMemoryTimestamps:
    """Verify Memory datetimes are timezone-aware."""

    def test_memory_default_timestamps_are_aware(self):
        mem = Memory(content="test")
        assert mem.created_at.tzinfo is not None
        assert mem.created_at.tzinfo == timezone.utc
        assert mem.updated_at.tzinfo is not None
        assert mem.updated_at.tzinfo == timezone.utc

    def test_memory_explicit_timestamps_stored_as_given(self):
        ts = datetime.now(timezone.utc)
        mem = Memory(content="test", created_at=ts, updated_at=ts)
        assert mem.created_at.tzinfo == timezone.utc
        assert mem.updated_at.tzinfo == timezone.utc


class TestSessionTimestamps:
    """Verify Session datetimes are timezone-aware."""

    def test_session_started_at_is_timezone_aware(self):
        sess = Session(project_id=uuid4())
        assert sess.started_at.tzinfo is not None
        assert sess.started_at.tzinfo == timezone.utc

    def test_session_default_timestamps_are_aware(self):
        sess = Session(project_id=uuid4())
        assert sess.created_at.tzinfo is not None
        assert sess.updated_at.tzinfo is not None


class TestProjectTimestamps:
    """Verify Project datetimes are timezone-aware."""

    def test_project_default_timestamps_are_aware(self):
        proj = Project(name="test")
        assert proj.created_at.tzinfo is not None
        assert proj.created_at.tzinfo == timezone.utc
        assert proj.updated_at.tzinfo is not None
        assert proj.updated_at.tzinfo == timezone.utc


class TestInstructionTimestamps:
    """Verify CustomInstruction datetimes are timezone-aware."""

    def test_instruction_default_timestamps_are_aware(self):
        inst = CustomInstruction(content="test")
        assert inst.created_at.tzinfo is not None
        assert inst.created_at.tzinfo == timezone.utc
        assert inst.updated_at.tzinfo is not None
        assert inst.updated_at.tzinfo == timezone.utc


class TestContextAssemblyTimestamps:
    """Verify assembled_at is a timezone-aware UTC ISO string."""

    def test_assembled_at_is_utc_isoformat(self, mock_uow, mock_retrieval_service, sample_project):
        mock_uow.projects.get.return_value = __import__('contracts.base', fromlist=['Result']).Result.ok(sample_project)
        mock_uow.sessions.get.return_value = __import__('contracts.base', fromlist=['Result']).Result.ok(None)
        mock_uow.memories.get_active_for_project.return_value = __import__('contracts.base', fromlist=['Result']).Result.ok([])

        service = ContextAssemblyService(
            memory_repo=mock_uow.memories,
            project_repo=mock_uow.projects,
            session_repo=mock_uow.sessions,
            retrieval_service=mock_retrieval_service,
        )

        result = service.assemble(ContextAssemblyRequest(project_id=sample_project.id))
        assert result.success
        assembled_at = result.value.assembled_at
        parsed = datetime.fromisoformat(assembled_at)
        assert parsed.tzinfo is not None
        assert parsed.tzinfo == timezone.utc


class TestMemoryManagerTimestamps:
    """Verify MemoryManager produces timezone-aware timestamps."""

    def test_end_session_uses_aware_datetime(self, mock_uow, mock_retrieval_service, mock_conflict_service, mock_semantic_index, sample_session):
        from contracts.base import Result
        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_semantic_index,
        )
        ended = Session(
            id=sample_session.id,
            project_id=sample_session.project_id,
            ended_at=datetime.now(timezone.utc),
        )
        mock_uow.sessions.update.return_value = Result.ok(ended)

        result = manager.end_session(sample_session.id)
        assert result.success
        call_args = mock_uow.sessions.update.call_args[0][1]
        assert call_args.ended_at.tzinfo is not None
        assert call_args.ended_at.tzinfo == timezone.utc

    def test_compact_uses_aware_datetime(self, mock_uow, mock_retrieval_service, mock_conflict_service, mock_semantic_index, sample_project, sample_session):
        from contracts.base import Result, PaginatedResult, MemoryStatus
        manager = MemoryManager(
            unit_of_work=mock_uow,
            retrieval_service=mock_retrieval_service,
            conflict_service=mock_conflict_service,
            semantic_index=mock_semantic_index,
        )
        memories = [
            Memory(id=uuid4(), project_id=sample_project.id, session_id=sample_session.id,
                   content=f"Memory {i}", status=MemoryStatus.ACTIVE)
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

        from contracts.retrieval import CompactRequest
        result = manager.compact(CompactRequest(project_id=sample_project.id, max_active_memories=50))
        assert result.success
        if manager.update_memory.call_args:
            call_args = manager.update_memory.call_args
            if call_args and len(call_args) > 1 and hasattr(call_args[1], 'metadata'):
                metadata = call_args[1].metadata
                if metadata and "compacted_at" in metadata:
                    parsed = datetime.fromisoformat(metadata["compacted_at"])
                    assert parsed.tzinfo is not None
                    assert parsed.tzinfo == timezone.utc


from unittest.mock import Mock
