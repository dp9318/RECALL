"""Comprehensive persistence and transaction lifecycle tests for RECALL.

Verifies:
1. State survival across manager recreation and database reconnection (memories, instructions, metadata, lineage).
2. Proper transaction boundaries and rollback guarantees without premature repository commits.
3. Timezone consistency (all timestamps stored as offset-aware UTC).
4. Concurrent write transactions avoiding SQLITE_BUSY / database locked deadlocks.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from contracts.base import Result, Scope
from contracts.instruction import (
    CustomInstructionCreateRequest,
    CustomInstructionUpdateRequest,
    InstructionStatus,
)
from contracts.memory import (
    MemoryCreateRequest,
    MemoryLineage,
    MemoryStatus,
    MemoryUpdateRequest,
)
from contracts.project import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    SessionCreateRequest,
    SessionUpdateRequest,
)
from database.config import DatabaseConfig
from database.connection import DatabaseConnection, initialize_database
from database.repositories.unit_of_work import SQLiteUnitOfWork
from recall_core.bootstrap import create_memory_manager


@pytest.fixture
def persistence_db(tmp_path):
    """Provide an isolated, initialized SQLite database path."""
    db_path = tmp_path / "persistence_test.sqlite3"
    config = DatabaseConfig.from_path(db_path)
    initialize_database(config)
    return db_path


def test_memory_and_lineage_survive_reconnection(persistence_db):
    """Verify memory content, metadata, associations, and lineage survive reconnection."""
    config = DatabaseConfig.from_path(persistence_db)
    manager1 = create_memory_manager(config)

    # Create project and session
    proj = manager1.create_project(
        ProjectCreateRequest(name="Lifecycle Project", description="Testing reconnection")
    ).value
    sess = manager1.create_session(SessionCreateRequest(project_id=proj.id)).value

    # Create initial memory with rich metadata
    mem1 = manager1.create_memory(
        MemoryCreateRequest(
            project_id=proj.id,
            session_id=sess.id,
            scope=Scope.PROJECT,
            memory_type="architecture",
            content="Use SQLite for canonical storage",
            metadata={"priority": "high", "tags": ["db", "core"]},
        )
    ).value

    # Create superseding memory
    mem2 = manager1.create_memory(
        MemoryCreateRequest(
            project_id=proj.id,
            session_id=sess.id,
            scope=Scope.PROJECT,
            memory_type="architecture",
            content="Use SQLite WAL mode for canonical storage",
            supersedes_id=mem1.id,
            metadata={"priority": "critical", "tags": ["db", "wal"]},
        )
    ).value

    manager1.close()

    # Reconnect with a fresh MemoryManager on the same database
    manager2 = create_memory_manager(config)
    try:
        re_proj = manager2.get_project(proj.id).value
        assert re_proj is not None
        assert re_proj.name == "Lifecycle Project"

        re_mem1 = manager2.get_memory(mem1.id).value
        assert re_mem1 is not None
        assert re_mem1.status == MemoryStatus.SUPERSEDED
        assert re_mem1.metadata == {"priority": "high", "tags": ["db", "core"]}
        assert re_mem1.project_id == proj.id
        assert re_mem1.session_id == sess.id

        re_mem2 = manager2.get_memory(mem2.id).value
        assert re_mem2 is not None
        assert re_mem2.status == MemoryStatus.ACTIVE
        assert re_mem2.supersedes_id == mem1.id
        assert re_mem2.content == "Use SQLite WAL mode for canonical storage"

        lineage = manager2.get_memory_lineage(mem1.id).value
        assert len(lineage) == 1
        assert lineage[0].parent_id == mem1.id
        assert lineage[0].child_id == mem2.id
        assert lineage[0].relationship == "supersedes"
    finally:
        manager2.close()


def test_custom_instructions_survive_reconnection(persistence_db):
    """Verify custom instructions content, version, and active status survive reconnection."""
    config = DatabaseConfig.from_path(persistence_db)
    manager1 = create_memory_manager(config)

    proj = manager1.create_project(ProjectCreateRequest(name="Instruction Project")).value

    # Create global instruction
    global_inst = manager1.create_instruction(
        CustomInstructionCreateRequest(
            scope=Scope.GLOBAL,
            content="Global instruction: strict UTC timestamps",
            metadata={"author": "lead"},
        )
    ).value

    # Create project instruction
    proj_inst = manager1.create_instruction(
        CustomInstructionCreateRequest(
            scope=Scope.PROJECT,
            project_id=proj.id,
            content="Project instruction: use pytest",
        )
    ).value

    # Update global instruction
    updated_global = manager1.update_instruction(
        global_inst.id,
        CustomInstructionUpdateRequest(
            content="Global instruction: strict UTC everywhere",
        ),
    ).value
    assert updated_global.version == 2

    # Delete project instruction
    del_res = manager1.delete_instruction(proj_inst.id)
    assert del_res.success and del_res.value is True

    manager1.close()

    # Reconnect
    manager2 = create_memory_manager(config)
    try:
        re_global = manager2.get_instruction(global_inst.id).value
        assert re_global is not None
        assert re_global.content == "Global instruction: strict UTC everywhere"
        assert re_global.version == 2
        assert re_global.status == InstructionStatus.ACTIVE
        assert re_global.metadata == {"author": "lead"}

        re_proj = manager2.get_instruction(proj_inst.id).value
        assert re_proj is not None
        assert re_proj.status == InstructionStatus.DELETED

        # Active for project should return only the active global instruction
        active_list = manager2.get_active_instructions(proj.id).value
        assert len(active_list) == 1
        assert active_list[0].id == global_inst.id
    finally:
        manager2.close()


def test_transaction_rollback_prevents_partial_commits(persistence_db):
    """Verify that a transaction rolls back completely on error without leaving partial changes."""
    config = DatabaseConfig.from_path(persistence_db)
    uow = SQLiteUnitOfWork(config)

    # Initial instruction
    inst = uow.custom_instructions.create(
        CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="Stable baseline")
    ).value

    # Start transaction, update, and simulate failure
    with pytest.raises(RuntimeError, match="Simulated crash during transaction"):
        with uow.begin() as tx:
            uow.custom_instructions.update(
                inst.id,
                CustomInstructionUpdateRequest(content="Corrupted mutation"),
            )
            raise RuntimeError("Simulated crash during transaction")

    # Verify rollback succeeded and content remains unchanged
    re_inst = uow.custom_instructions.get(inst.id).value
    assert re_inst.content == "Stable baseline"
    assert re_inst.version == 1

    uow.close()


def test_transaction_commit_handles_instruction_and_lineage(persistence_db):
    """Verify that multi-operation transactions commit atomically without premature commit errors."""
    config = DatabaseConfig.from_path(persistence_db)
    uow = SQLiteUnitOfWork(config)

    with uow.begin() as tx:
        inst = uow.custom_instructions.create(
            CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="Atomic instruction")
        ).value
        updated = uow.custom_instructions.update(
            inst.id,
            CustomInstructionUpdateRequest(content="Updated atomic instruction"),
        ).value
        assert updated is not None

        # Create parent and child memories inside transaction
        parent = uow.memories.create(
            MemoryCreateRequest(scope=Scope.GLOBAL, content="Parent memory")
        ).value
        child = uow.memories.create(
            MemoryCreateRequest(scope=Scope.GLOBAL, content="Child memory")
        ).value
        parent_id = parent.id
        child_id = child.id

        lineage = uow.memories.create_lineage(
            MemoryLineage(
                id=uuid4(),
                parent_id=parent_id,
                child_id=child_id,
                relationship="derived",
                reason="testing transaction",
            )
        ).value
        assert lineage is not None

    # After clean transaction exit, changes should be committed
    saved_inst = uow.custom_instructions.get(inst.id).value
    assert saved_inst.content == "Updated atomic instruction"
    assert saved_inst.version == 2

    saved_lineage = uow.memories.get_lineage(parent_id).value
    assert len(saved_lineage) == 1
    assert saved_lineage[0].child_id == child_id

    uow.close()


def test_all_timestamps_are_offset_aware_utc(persistence_db):
    """Verify that updated_at and created_at timestamps across all tables are offset-aware UTC."""
    config = DatabaseConfig.from_path(persistence_db)
    manager = create_memory_manager(config)

    proj = manager.create_project(ProjectCreateRequest(name="Timezone Project")).value
    sess = manager.create_session(SessionCreateRequest(project_id=proj.id)).value
    mem = manager.create_memory(
        MemoryCreateRequest(
            project_id=proj.id,
            session_id=sess.id,
            scope=Scope.PROJECT,
            content="Timezone memory",
        )
    ).value
    inst = manager.create_instruction(
        CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="Timezone rule")
    ).value

    # Perform updates to trigger updated_at logic
    manager.update_project(proj.id, ProjectUpdateRequest(name="Updated Timezone Project"))
    manager.update_session(sess.id, SessionUpdateRequest(metadata={"updated": True}))
    manager.update_memory(mem.id, MemoryUpdateRequest(content="Updated timezone memory"))
    manager.update_instruction(inst.id, CustomInstructionUpdateRequest(content="Updated timezone rule"))

    # Supersede memory
    manager.create_memory(
        MemoryCreateRequest(
            project_id=proj.id,
            session_id=sess.id,
            scope=Scope.PROJECT,
            content="Superseding timezone memory",
            supersedes_id=mem.id,
        )
    )

    manager.close()

    # Inspect raw database TEXT values directly to ensure all have explicit UTC offset
    with sqlite3.connect(persistence_db) as conn:
        for table, col in [
            ("projects", "created_at"),
            ("projects", "updated_at"),
            ("sessions", "started_at"),
            ("sessions", "created_at"),
            ("sessions", "updated_at"),
            ("memories", "created_at"),
            ("memories", "updated_at"),
            ("memory_lineage", "created_at"),
            ("custom_instructions", "created_at"),
            ("custom_instructions", "updated_at"),
        ]:
            rows = conn.execute(f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL").fetchall()
            for (ts_str,) in rows:
                dt = datetime.fromisoformat(ts_str)
                assert dt.tzinfo is not None, f"Naive timestamp found in {table}.{col}: '{ts_str}'"
                # Check offset is UTC (+00:00 or Z)
                assert dt.utcoffset().total_seconds() == 0, f"Non-UTC offset found in {table}.{col}: '{ts_str}'"


def test_concurrent_write_transactions_prevent_deadlock(persistence_db):
    """Verify that concurrent read-then-write transactions succeed without SQLITE_BUSY deadlocks."""
    config = DatabaseConfig.from_path(persistence_db, timeout=10.0)

    results = []
    errors = []

    def writer_thread(thread_idx: int):
        uow = SQLiteUnitOfWork(config)
        try:
            with uow.begin() as tx:
                # Read first (would cause deadlock with plain BEGIN DEFERRED)
                existing = uow.custom_instructions.get_active_for_scope("global")
                time.sleep(0.05)  # simulate brief processing
                # Write
                res = uow.custom_instructions.create(
                    CustomInstructionCreateRequest(
                        scope=Scope.GLOBAL,
                        content=f"Concurrent rule from thread {thread_idx}",
                    )
                )
                assert res.success, res.error
            results.append(thread_idx)
        except Exception as exc:
            errors.append((thread_idx, exc))
        finally:
            uow.close()

    threads = [threading.Thread(target=writer_thread, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent transaction errors encountered: {errors}"
    assert len(results) == 3


def test_historical_naive_timestamps_compatibility(persistence_db):
    """Verify that historical naive timestamps from pre-v3.0.0 co-exist and deserialize safely."""
    proj_id = uuid4()
    mem_id = uuid4()
    inst_id = uuid4()

    # Seed historical records with naive ISO timestamps (no +00:00 suffix)
    naive_ts = "2026-10-24T04:00:00.000000"
    with sqlite3.connect(persistence_db) as conn:
        conn.execute(
            """
            INSERT INTO projects (project_id, name, description, created_at, updated_at)
            VALUES (?, 'Legacy Project', 'Created in v2.1.1', ?, ?)
            """,
            (str(proj_id), naive_ts, naive_ts),
        )
        conn.execute(
            """
            INSERT INTO memories (memory_id, project_id, scope, memory_type, content, status, created_at, updated_at)
            VALUES (?, ?, 'project', 'fact', 'Legacy memory from v2.1.1', 'active', ?, ?)
            """,
            (str(mem_id), str(proj_id), naive_ts, naive_ts),
        )
        conn.execute(
            """
            INSERT INTO custom_instructions (instruction_id, scope, content, status, version, created_at, updated_at)
            VALUES (?, 'global', 'Legacy instruction from v2.1.1', 'active', 1, ?, ?)
            """,
            (str(inst_id), naive_ts, naive_ts),
        )
        conn.commit()

    # Reconnect via MemoryManager
    config = DatabaseConfig.from_path(persistence_db)
    manager = create_memory_manager(config)
    try:
        # Retrieve legacy entities
        legacy_proj = manager.get_project(proj_id).value
        assert legacy_proj is not None
        assert legacy_proj.name == "Legacy Project"
        assert legacy_proj.created_at is not None

        legacy_mem = manager.get_memory(mem_id).value
        assert legacy_mem is not None
        assert legacy_mem.content == "Legacy memory from v2.1.1"
        assert legacy_mem.created_at is not None

        legacy_inst = manager.get_instruction(inst_id).value
        assert legacy_inst is not None
        assert legacy_inst.content == "Legacy instruction from v2.1.1"
        assert legacy_inst.created_at is not None

        # Create a new UTC entity alongside legacy entities
        new_mem = manager.create_memory(
            MemoryCreateRequest(
                project_id=proj_id,
                scope=Scope.PROJECT,
                content="New v3.0.0 memory with UTC timestamp",
            )
        ).value
        assert new_mem is not None
        assert new_mem.created_at.tzinfo == timezone.utc

        # List active instructions and verify legacy instruction is present
        active_instructions = manager.get_active_instructions(proj_id).value
        assert any(i.id == inst_id for i in active_instructions)

        # Ensure serializer formatting works on both legacy (naive) and new (aware) timestamps
        assert legacy_mem.created_at.isoformat() is not None
        assert new_mem.created_at.isoformat() is not None
    finally:
        manager.close()
