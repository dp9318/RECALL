"""Test configuration and fixtures for RECALL Core tests."""

import sys
from pathlib import Path

# Add the project root to path so we can import contracts, database, intelligence, core.recall_core
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import pytest and standard library modules first
import pytest
from unittest.mock import Mock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

# Import core modules via a helper function to avoid top-level import issues
def _import_core_modules():
    from contracts.base import Result, PaginationParams, PaginatedResult, Scope, MemoryStatus, InstructionStatus
    from contracts.conflict import ConflictCandidate, ConflictResolutionResult, ConflictResolutionStatus, ResolutionDecision
    from contracts.instruction import CustomInstruction, CustomInstructionCreateRequest, CustomInstructionListParams, CustomInstructionUpdateRequest
    from contracts.memory import Memory, MemoryCreateRequest, MemorySearchParams, MemoryUpdateRequest, MemoryLineage
    from contracts.project import Project, ProjectCreateRequest, ProjectUpdateRequest, Session, SessionCreateRequest, SessionUpdateRequest
    from contracts.retrieval import RetrievalRequest, RetrievalResult, ContextAssemblyRequest, AssembledContext, CompactRequest, CompactResult, UpdateContextRequest, UpdateContextResult
    from database.repositories import (
        ProjectRepository, SessionRepository, MemoryRepository,
        CustomInstructionRepository, SemanticIndexRepository, UnitOfWork
    )
    from intelligence.retrieval import RetrievalService
    from intelligence.conflict import ConflictResolutionService
    from core.recall_core import MemoryManager, CustomInstructionService, ContextAssemblyService
    return {
        'Result': Result, 'PaginationParams': PaginationParams, 'PaginatedResult': PaginatedResult,
        'Scope': Scope, 'MemoryStatus': MemoryStatus, 'InstructionStatus': InstructionStatus,
        'ConflictCandidate': ConflictCandidate, 'ConflictResolutionResult': ConflictResolutionResult,
        'ConflictResolutionStatus': ConflictResolutionStatus, 'ResolutionDecision': ResolutionDecision,
        'CustomInstruction': CustomInstruction, 'CustomInstructionCreateRequest': CustomInstructionCreateRequest,
        'CustomInstructionListParams': CustomInstructionListParams, 'CustomInstructionUpdateRequest': CustomInstructionUpdateRequest,
        'Memory': Memory, 'MemoryCreateRequest': MemoryCreateRequest, 'MemorySearchParams': MemorySearchParams,
        'MemoryUpdateRequest': MemoryUpdateRequest, 'MemoryLineage': MemoryLineage,
        'Project': Project, 'ProjectCreateRequest': ProjectCreateRequest, 'ProjectUpdateRequest': ProjectUpdateRequest,
        'Session': Session, 'SessionCreateRequest': SessionCreateRequest, 'SessionUpdateRequest': SessionUpdateRequest,
        'RetrievalRequest': RetrievalRequest, 'RetrievalResult': RetrievalResult,
        'ContextAssemblyRequest': ContextAssemblyRequest, 'AssembledContext': AssembledContext,
        'CompactRequest': CompactRequest, 'CompactResult': CompactResult,
        'UpdateContextRequest': UpdateContextRequest, 'UpdateContextResult': UpdateContextResult,
        'ProjectRepository': ProjectRepository, 'SessionRepository': SessionRepository,
        'MemoryRepository': MemoryRepository, 'CustomInstructionRepository': CustomInstructionRepository,
        'SemanticIndexRepository': SemanticIndexRepository, 'UnitOfWork': UnitOfWork,
        'RetrievalService': RetrievalService, 'ConflictResolutionService': ConflictResolutionService,
        'MemoryManager': MemoryManager, 'CustomInstructionService': CustomInstructionService, 'ContextAssemblyService': ContextAssemblyService,
    }

# Import core modules and make them available as module globals
_core_modules = _import_core_modules()
globals().update(_core_modules)


@pytest.fixture
def mock_project_repo():
    repo = Mock(spec=ProjectRepository)
    repo.create = Mock()
    repo.get = Mock()
    repo.update = Mock()
    repo.delete = Mock()
    repo.list = Mock()
    return repo


@pytest.fixture
def mock_session_repo():
    repo = Mock(spec=SessionRepository)
    repo.create = Mock()
    repo.get = Mock()
    repo.get_active_for_project = Mock()
    repo.update = Mock()
    repo.list = Mock()
    return repo


@pytest.fixture
def mock_memory_repo():
    repo = Mock(spec=MemoryRepository)
    repo.create = Mock()
    repo.get = Mock()
    repo.update = Mock()
    repo.delete = Mock()
    repo.search = Mock()
    repo.search.return_value = Result.ok(
        PaginatedResult(items=[], total=0, limit=50, offset=0)
    )
    repo.get_active_for_project = Mock()
    repo.get_by_ids = Mock()
    repo.create_lineage = Mock()
    repo.get_lineage = Mock()
    return repo


@pytest.fixture
def mock_instruction_repo():
    repo = Mock(spec=CustomInstructionRepository)
    repo.create = Mock()
    repo.get = Mock()
    repo.update = Mock()
    repo.delete = Mock()
    repo.list = Mock()
    repo.get_active_for_scope = Mock()
    return repo


@pytest.fixture
def mock_semantic_index():
    repo = Mock(spec=SemanticIndexRepository)
    repo.index_memory = Mock()
    repo.update_memory = Mock()
    repo.remove_memory = Mock()
    repo.search_similar = Mock()
    repo.rebuild_from_canonical = Mock()
    repo.health_check = Mock()
    return repo


@pytest.fixture
def mock_uow(mock_project_repo, mock_session_repo, mock_memory_repo, mock_instruction_repo, mock_semantic_index):
    uow = Mock(spec=UnitOfWork)
    uow.projects = mock_project_repo
    uow.sessions = mock_session_repo
    uow.memories = mock_memory_repo
    uow.custom_instructions = mock_instruction_repo
    uow.semantic_index = mock_semantic_index
    uow.begin = Mock()
    uow.commit = Mock()
    uow.rollback = Mock()
    uow.close = Mock()
    return uow


@pytest.fixture
def mock_retrieval_service():
    service = Mock(spec=RetrievalService)
    service.retrieve = Mock()
    service.search_structured = Mock()
    service.search_semantic = Mock()
    service.rank_results = Mock()
    service.detect_conflicts = Mock()
    return service


@pytest.fixture
def mock_conflict_service():
    service = Mock(spec=ConflictResolutionService)
    service.detect_and_resolve = Mock()
    service.detector = Mock()
    service.resolver = Mock()
    return service


@pytest.fixture
def sample_project():
    return Project(
        id=uuid4(),
        name="Test Project",
        description="A test project",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_session(sample_project):
    return Session(
        id=uuid4(),
        project_id=sample_project.id,
        started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_memory(sample_project, sample_session):
    return Memory(
        id=uuid4(),
        project_id=sample_project.id,
        session_id=sample_session.id,
        scope=Scope.PROJECT,
        memory_type="decision",
        content="Use SQLite for canonical storage",
        status=MemoryStatus.ACTIVE,
        provenance="user_explicit",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_instruction():
    return CustomInstruction(
        id=uuid4(),
        scope=Scope.GLOBAL,
        content="Always prefer explicit user instructions over inferred memories",
        status=InstructionStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )