"""Tests for database repositories and Unit of Work."""

import tempfile
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime, timezone

from database.config import DatabaseConfig
from database.connection import initialize_database, get_connection
from database.repositories import (
    SQLiteProjectRepository,
    SQLiteSessionRepository,
    SQLiteMemoryRepository,
    SQLiteCustomInstructionRepository,
    SQLiteUnitOfWork,
)
from contracts.project import ProjectCreateRequest, ProjectUpdateRequest, SessionCreateRequest, SessionUpdateRequest
from contracts.memory import MemoryCreateRequest, MemorySearchParams, MemoryUpdateRequest, MemoryStatus, MemoryLineage
from contracts.instruction import CustomInstructionCreateRequest, CustomInstructionUpdateRequest, InstructionStatus
from contracts.base import Scope, PaginationParams
from database.repositories.base import uuid_to_str


def test_project_repository():
    """Test ProjectRepository CRUD operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            repo = SQLiteProjectRepository(conn)

            # Create
            request = ProjectCreateRequest(name="Test Project", description="A test project")
            result = repo.create(request)
            assert result.success, f"Create failed: {result.error}"
            project = result.value
            assert project.name == "Test Project"
            assert project.description == "A test project"
            project_id = project.id

            # Get
            result = repo.get(project_id)
            assert result.success
            assert result.value is not None
            assert result.value.name == "Test Project"

            # Update
            update_request = ProjectUpdateRequest(name="Updated Project", description="Updated description")
            result = repo.update(project_id, update_request)
            assert result.success
            assert result.value.name == "Updated Project"

            # List
            result = repo.list(PaginationParams(limit=10, offset=0))
            assert result.success
            assert len(result.value.items) == 1

            # Delete
            result = repo.delete(project_id)
            assert result.success
            assert result.value is True

            # Verify deleted
            result = repo.get(project_id)
            assert result.success
            assert result.value is None


def test_session_repository():
    """Test SessionRepository CRUD operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            project_repo = SQLiteProjectRepository(conn)
            session_repo = SQLiteSessionRepository(conn)

            # Create project first
            project_request = ProjectCreateRequest(name="Test Project")
            project_result = project_repo.create(project_request)
            assert project_result.success
            project_id = project_result.value.id

            # Create session
            request = SessionCreateRequest(project_id=project_id)
            result = session_repo.create(request)
            assert result.success
            session = result.value
            assert session.project_id == project_id
            assert session.is_active()
            session_id = session.id

            # Get
            result = session_repo.get(session_id)
            assert result.success
            assert result.value is not None

            # Get active for project
            result = session_repo.get_active_for_project(project_id)
            assert result.success
            assert result.value is not None
            assert result.value.id == session_id

            # End session
            update_request = SessionUpdateRequest(ended_at=datetime.now(timezone.utc))
            result = session_repo.update(session_id, update_request)
            assert result.success
            assert result.value is not None
            assert not result.value.is_active()

            # List by project
            result = session_repo.list(PaginationParams(limit=10, offset=0), project_id=project_id)
            assert result.success
            assert len(result.value.items) == 1


def test_memory_repository():
    """Test MemoryRepository CRUD and search operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            project_repo = SQLiteProjectRepository(conn)
            session_repo = SQLiteSessionRepository(conn)
            memory_repo = SQLiteMemoryRepository(conn)

            # Create project and session
            project = SQLiteProjectRepository(conn).create(ProjectCreateRequest(name="Test")).value
            session = SQLiteSessionRepository(conn).create(SessionCreateRequest(project_id=project.id)).value

            # Create memory
            request = MemoryCreateRequest(
                project_id=project.id,
                session_id=session.id,
                scope=Scope.PROJECT,
                memory_type="fact",
                content="Test memory content",
                provenance="test",
            )
            result = memory_repo.create(request)
            if not result.success:
                print(f"Memory creation failed: {result.error}")
            assert result.success
            memory = result.value
            assert memory.content == "Test memory content"
            assert memory.status == MemoryStatus.ACTIVE
            memory_id = memory.id

            # Get
            result = memory_repo.get(memory_id)
            assert result.success
            assert result.value.content == "Test memory content"

            # Update
            update_request = MemoryUpdateRequest(content="Updated content")
            result = memory_repo.update(memory_id, update_request)
            assert result.success

            # Search
            search_params = MemorySearchParams(project_id=project.id, limit=10)
            result = memory_repo.search(search_params)
            assert result.success
            assert len(result.value.items) == 1

            # Get active for project
            result = memory_repo.get_active_for_project(project.id, limit=10)
            if not result.success:
                print(f"get_active_for_project failed: {result.error}")
            assert result.success
            assert len(result.value) == 1

            # Test supersession/lineage
            new_memory_request = MemoryCreateRequest(
                project_id=project.id,
                session_id=session.id,
                scope=Scope.PROJECT,
                memory_type="fact",
                content="Superseding memory",
                provenance="test",
                supersedes_id=memory_id,
            )
            result = memory_repo.create(new_memory_request)
            assert result.success
            new_memory = result.value
            assert new_memory.supersedes_id == memory_id

            # Check original memory is superseded
            result = memory_repo.get(memory_id)
            assert result.success
            assert result.value.status == MemoryStatus.SUPERSEDED

            # Check lineage
            result = memory_repo.get_lineage(memory_id)
            if not result.success:
                print(f"get_lineage failed: {result.error}")
            assert result.success
            assert len(result.value) == 1


def test_custom_instruction_repository():
    """Test CustomInstructionRepository CRUD and uniqueness."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            project_repo = SQLiteProjectRepository(conn)
            instr_repo = SQLiteCustomInstructionRepository(conn)

            # Create project
            project = project_repo.create(ProjectCreateRequest(name="Test Project")).value

            # Create global instruction
            global_request = CustomInstructionCreateRequest(
                scope=Scope.GLOBAL,
                content="Global instruction",
            )
            result = instr_repo.create(global_request)
            assert result.success
            global_instr = result.value

            # Create project-scoped instruction
            project_request = CustomInstructionCreateRequest(
                scope=Scope.PROJECT,
                project_id=project.id,
                content="Project instruction",
            )
            result = instr_repo.create(project_request)
            assert result.success
            project_instr = result.value

            # Try to create another active project-scoped instruction for same project - should fail
            duplicate_request = CustomInstructionCreateRequest(
                scope=Scope.PROJECT,
                project_id=project.id,
                content="Duplicate instruction",
            )
            result = instr_repo.create(duplicate_request)
            assert not result.success
            assert "already exists" in result.error.lower()

            # Get active for project (should include project-scoped)
            result = instr_repo.get_active_for_scope("project", project.id)
            if not result.success:
                print(f"get_active_for_scope failed: {result.error}")
            assert result.success
            assert len(result.value) == 1  # Only project-scoped

            # Get active global
            result = instr_repo.get_active_for_scope("global")
            if not result.success:
                print(f"get_active_for_scope global failed: {result.error}")
            assert result.success
            assert len(result.value) == 1

            # Get active for project via service (global + project)
            from recall_core.instruction_service import CustomInstructionService
            instr_service = CustomInstructionService(instr_repo)
            result = instr_service.get_active_for_project(project.id)
            assert result.success
            assert len(result.value) == 2

            # Deactivate project instruction
            update_request = CustomInstructionUpdateRequest(status=InstructionStatus.INACTIVE)
            result = instr_repo.update(project_instr.id, update_request)
            assert result.success

            # Now creating another should succeed
            result = instr_repo.create(duplicate_request)
            assert result.success


def test_unit_of_work():
    """Test UnitOfWork transaction handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with SQLiteUnitOfWork(config) as uow:
            # Test successful transaction
            with uow.begin() as tx:
                project = uow.projects.create(ProjectCreateRequest(name="UoW Project")).value
                session = uow.sessions.create(SessionCreateRequest(project_id=project.id)).value
                memory = uow.memories.create(MemoryCreateRequest(
                    project_id=project.id,
                    session_id=session.id,
                    scope=Scope.PROJECT,
                    content="UoW memory",
                )).value

            # Verify committed
            assert uow.projects.get(project.id).value is not None
            assert uow.sessions.get(session.id).value is not None
            assert uow.memories.get(memory.id).value is not None

            # Test rollback on exception
            try:
                with uow.begin() as tx:
                    project2 = uow.projects.create(ProjectCreateRequest(name="Rollback Project")).value
                    raise ValueError("Force rollback")
            except ValueError:
                pass

            # Verify rolled back
            result = uow.projects.get(project2.id)
            assert result.value is None


def test_cascade_delete():
    """Test cascade delete behavior."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            project_repo = SQLiteProjectRepository(conn)
            session_repo = SQLiteSessionRepository(conn)
            memory_repo = SQLiteMemoryRepository(conn)

            # Create project with session and memories
            project = project_repo.create(ProjectCreateRequest(name="Cascade Test")).value
            session = session_repo.create(SessionCreateRequest(project_id=project.id)).value
            memory = memory_repo.create(MemoryCreateRequest(
                project_id=project.id,
                session_id=session.id,
                scope=Scope.PROJECT,
                content="Project memory",
            )).value

            # Global memory (no project_id)
            global_memory = memory_repo.create(MemoryCreateRequest(
                session_id=session.id,
                scope=Scope.GLOBAL,
                content="Global memory",
            )).value

            instr_repo = SQLiteCustomInstructionRepository(conn)
            project_instr = instr_repo.create(CustomInstructionCreateRequest(
                scope=Scope.PROJECT,
                project_id=project.id,
                content="Project scoped instruction",
            )).value

            # Delete project - should cascade delete session, project-scoped memory, and project instruction
            project_repo.delete(project.id)

            # Verify session is deleted (cascade)
            assert session_repo.get(session.id).value is None

            # Verify project-scoped memory is deleted (cascade)
            assert memory_repo.get(memory.id).value is None

            # Verify project instruction is deleted (cascade)
            assert instr_repo.get(project_instr.id).value is None

            # Verify global memory still exists (session_id set to NULL)
            result = memory_repo.get(global_memory.id)
            assert result.success
            assert result.value is not None
            assert result.value.session_id is None


def test_custom_instruction_and_memory_deletion():
    """Test soft-delete semantics and filtering for instructions and memories."""
    from contracts.instruction import CustomInstructionListParams
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        with get_connection(config) as conn:
            instr_repo = SQLiteCustomInstructionRepository(conn)
            memory_repo = SQLiteMemoryRepository(conn)

            # 1. Custom Instruction soft-delete
            instr = instr_repo.create(CustomInstructionCreateRequest(
                scope=Scope.GLOBAL,
                content="Test instruction to delete",
            )).value

            # Initial list includes it
            list_res = instr_repo.list(CustomInstructionListParams())
            assert list_res.success
            assert any(i.id == instr.id for i in list_res.value.items)

            # First delete succeeds
            del_res = instr_repo.delete(instr.id)
            assert del_res.success
            assert del_res.value is True

            # Second delete on same ID returns False (already deleted)
            del_res_again = instr_repo.delete(instr.id)
            assert del_res_again.success
            assert del_res_again.value is False

            # Normal list excludes it
            list_after_del = instr_repo.list(CustomInstructionListParams())
            assert list_after_del.success
            assert all(i.id != instr.id for i in list_after_del.value.items)

            # Query with status=deleted includes it
            list_deleted = instr_repo.list(CustomInstructionListParams(status=InstructionStatus.DELETED))
            assert list_deleted.success
            assert any(i.id == instr.id for i in list_deleted.value.items)

            # Update on deleted instruction fails / returns None
            update_res = instr_repo.update(instr.id, CustomInstructionUpdateRequest(content="new content"))
            assert update_res.success
            assert update_res.value is None

            # 2. Memory soft-delete
            mem = memory_repo.create(MemoryCreateRequest(
                scope=Scope.GLOBAL,
                content="Test memory to delete",
            )).value

            # Search includes active memory
            search_res = memory_repo.search(MemorySearchParams())
            assert search_res.success
            assert any(m.id == mem.id for m in search_res.value.items)

            # First delete succeeds
            mem_del_res = memory_repo.delete(mem.id)
            assert mem_del_res.success
            assert mem_del_res.value is True

            # Second delete returns False
            mem_del_again = memory_repo.delete(mem.id)
            assert mem_del_again.success
            assert mem_del_again.value is False

            # Search excludes deleted memory
            search_after_del = memory_repo.search(MemorySearchParams())
            assert search_after_del.success
            assert all(m.id != mem.id for m in search_after_del.value.items)

            # Search with status=deleted includes it
            search_deleted = memory_repo.search(MemorySearchParams(status=MemoryStatus.DELETED))
            assert search_deleted.success
            assert any(m.id == mem.id for m in search_deleted.value.items)
