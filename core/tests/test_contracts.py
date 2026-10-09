"""Tests for contracts."""

import pytest
from uuid import UUID, uuid4
from datetime import datetime, timezone
from unittest.mock import Mock

from contracts.base import Result, Scope, MemoryStatus, InstructionStatus, PaginationParams, PaginatedResult
from contracts.instruction import CustomInstruction, CustomInstructionCreateRequest, CustomInstructionUpdateRequest
from contracts.memory import Memory, MemoryCreateRequest, MemoryUpdateRequest, MemorySearchParams
from contracts.project import Project, ProjectCreateRequest, Session, SessionCreateRequest
from contracts.conflict import ConflictCandidate, ConflictResolutionResult, ConflictResolutionStatus, ResolutionDecision
from contracts.retrieval import RetrievalRequest, RetrievalResult, ContextAssemblyRequest, AssembledContext


class TestContracts:
    """Tests for contract DTOs."""

    def test_result_ok(self):
        """Test Result.ok factory."""
        result = Result.ok("success value", metadata={"key": "value"})
        assert result.success
        assert result.value == "success value"
        assert result.metadata["key"] == "value"
        assert result.error is None

    def test_result_err(self):
        """Test Result.err factory."""
        result = Result.err("error message", metadata={"code": 500})
        assert not result.success
        assert result.error == "error message"
        assert result.metadata["code"] == 500
        assert result.value is None

    def test_pagination_params_defaults(self):
        """Test PaginationParams defaults."""
        params = PaginationParams()
        assert params.limit == 50
        assert params.offset == 0

    def test_pagination_params_clamping(self):
        """Test PaginationParams clamps values."""
        params = PaginationParams(limit=500, offset=-10)
        assert params.limit == 200  # Max clamped
        assert params.offset == 0   # Min clamped

    def test_paginated_result_has_more(self):
        """Test PaginatedResult.has_more property."""
        result = PaginatedResult(items=[1, 2, 3], total=100, limit=10, offset=0)
        assert result.has_more

        result = PaginatedResult(items=[1, 2, 3], total=5, limit=10, offset=0)
        assert not result.has_more

    def test_scope_enum(self):
        """Test Scope enum values."""
        assert Scope.GLOBAL == "global"
        assert Scope.PROJECT == "project"

    def test_memory_status_enum(self):
        """Test MemoryStatus enum values."""
        assert MemoryStatus.ACTIVE == "active"
        assert MemoryStatus.SUPERSEDED == "superseded"
        assert MemoryStatus.ARCHIVED == "archived"
        assert MemoryStatus.DELETED == "deleted"

    def test_instruction_status_enum(self):
        """Test InstructionStatus enum values."""
        assert InstructionStatus.ACTIVE == "active"
        assert InstructionStatus.INACTIVE == "inactive"
        assert InstructionStatus.DELETED == "deleted"

    def test_memory_is_active(self):
        """Test Memory.is_active method."""
        memory = Memory(status=MemoryStatus.ACTIVE)
        assert memory.is_active()

        memory.status = MemoryStatus.SUPERSEDED
        assert not memory.is_active()

    def test_memory_is_historical(self):
        """Test Memory.is_historical method."""
        memory = Memory(status=MemoryStatus.SUPERSEDED)
        assert memory.is_historical()

        memory.status = MemoryStatus.ARCHIVED
        assert memory.is_historical()

        memory.status = MemoryStatus.ACTIVE
        assert not memory.is_historical()

    def test_custom_instruction_is_active(self):
        """Test CustomInstruction.is_active method."""
        inst = CustomInstruction(status=InstructionStatus.ACTIVE)
        assert inst.is_active()

        inst.status = InstructionStatus.INACTIVE
        assert not inst.is_active()

    def test_custom_instruction_scope_matches(self):
        """Test CustomInstruction.scope_matches method."""
        project_id = uuid4()

        global_inst = CustomInstruction(scope=Scope.GLOBAL)
        assert global_inst.scope_matches(project_id)  # Global matches all
        assert global_inst.scope_matches(None)  # Global matches no project

        project_inst = CustomInstruction(scope=Scope.PROJECT, project_id=project_id)
        assert project_inst.scope_matches(project_id)
        assert not project_inst.scope_matches(uuid4())
        assert not project_inst.scope_matches(None)

    def test_conflict_resolution_result_is_resolved(self):
        """Test ConflictResolutionResult.is_resolved."""
        result = ConflictResolutionResult(status=ConflictResolutionStatus.RESOLVED)
        assert result.is_resolved()

        result.status = ConflictResolutionStatus.PARTIALLY_RESOLVED
        assert not result.is_resolved()

    def test_conflict_resolution_result_has_unresolved(self):
        """Test ConflictResolutionResult.has_unresolved."""
        result = ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED)
        assert result.has_unresolved()

        result.status = ConflictResolutionStatus.ABSTAINED
        assert result.has_unresolved()

        result.status = ConflictResolutionStatus.RESOLVED
        result.unresolved_candidates = [Mock()]
        assert result.has_unresolved()

    def test_session_is_active(self):
        """Test Session.is_active method."""
        session = Session(ended_at=None)
        assert session.is_active()

        session.ended_at = datetime.now(timezone.utc)
        assert not session.is_active()


class TestMemoryContract:
    """Tests for memory contract DTOs."""

    def test_memory_create_request(self):
        """Test MemoryCreateRequest."""
        project_id = uuid4()
        request = MemoryCreateRequest(
            project_id=project_id,
            content="Test memory",
            memory_type="decision",
        )
        assert request.project_id == project_id
        assert request.content == "Test memory"
        assert request.memory_type == "decision"

    def test_memory_update_request(self):
        """Test MemoryUpdateRequest."""
        request = MemoryUpdateRequest(content="Updated", status=MemoryStatus.ARCHIVED)
        assert request.content == "Updated"
        assert request.status == MemoryStatus.ARCHIVED

    def test_memory_search_params(self):
        """Test MemorySearchParams."""
        params = MemorySearchParams(query="test", limit=20)
        assert params.query == "test"
        assert params.limit == 20


class TestInstructionContract:
    """Tests for instruction contract DTOs."""

    def test_custom_instruction_create_request(self):
        """Test CustomInstructionCreateRequest."""
        request = CustomInstructionCreateRequest(
            scope=Scope.PROJECT,
            project_id=uuid4(),
            content="Project instruction",
        )
        assert request.scope == Scope.PROJECT
        assert request.content == "Project instruction"

    def test_custom_instruction_update_request(self):
        """Test CustomInstructionUpdateRequest."""
        request = CustomInstructionUpdateRequest(
            content="Updated",
            status=InstructionStatus.INACTIVE,
        )
        assert request.content == "Updated"
        assert request.status == InstructionStatus.INACTIVE


class TestProjectContract:
    """Tests for project contract DTOs."""

    def test_project_create_request(self):
        """Test ProjectCreateRequest."""
        request = ProjectCreateRequest(name="Test Project", description="Desc")
        assert request.name == "Test Project"
        assert request.description == "Desc"

    def test_session_create_request(self):
        """Test SessionCreateRequest."""
        project_id = uuid4()
        request = SessionCreateRequest(project_id=project_id)
        assert request.project_id == project_id


class TestRetrievalContract:
    """Tests for retrieval contract DTOs."""

    def test_retrieval_request(self):
        """Test RetrievalRequest."""
        request = RetrievalRequest(query="test", project_id=uuid4(), limit=10)
        assert request.query == "test"
        assert request.limit == 10

    def test_context_assembly_request(self):
        """Test ContextAssemblyRequest."""
        request = ContextAssemblyRequest(project_id=uuid4(), query="test")
        assert request.project_id is not None
        assert request.query == "test"
        assert request.include_custom_instructions is True


class TestConflictContract:
    """Tests for conflict contract DTOs."""

    def test_resolution_decision(self):
        """Test ResolutionDecision."""
        decision = ResolutionDecision(
            candidate_id=uuid4(),
            action="keep",
            reason="Explicit user instruction",
            confidence=0.9,
        )
        assert decision.action == "keep"
        assert decision.confidence == 0.9

    def test_conflict_resolution_result(self):
        """Test ConflictResolutionResult."""
        result = ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            resolution_reason="User explicit takes precedence",
        )
        assert result.is_resolved()
        assert result.resolution_reason == "User explicit takes precedence"