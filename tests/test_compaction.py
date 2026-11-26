"""Phase 05 tests for atomic, versioned, lineage-preserving milestone compaction."""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest

from contracts.base import MemoryStatus, Result, Scope
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import MemoryCreateRequest, MemorySearchParams
from contracts.project import ProjectCreateRequest, SessionCreateRequest
from contracts.retrieval import CompactRequest
from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager


def _create_inferred(manager, project_id, content: str, *, session_id=None, provenance="agent_inferred", metadata=None):
    res = manager.create_memory(
        MemoryCreateRequest(
            project_id=project_id,
            session_id=session_id,
            scope=Scope.PROJECT,
            content=content,
            provenance=provenance,
            metadata=metadata or {},
        )
    )
    assert res.success, res.error
    return res.value


def test_compaction_round_trip_versioning_and_idempotency(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_rt.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="CompactProj")).value
        manager.create_instruction(
            CustomInstructionCreateRequest(scope=Scope.PROJECT, project_id=proj.id, content="Always preserve lineage.")
        )

        created = [_create_inferred(manager, proj.id, f"Inferred step {i}") for i in range(5)]

        res1 = manager.compact(
            CompactRequest(project_id=proj.id, max_active_memories=2, idempotency_key="milestone-1")
        )
        assert res1.success, res1.error
        assert res1.value.compacted_count == 4
        assert res1.value.superseded_count == 4
        assert res1.value.compaction_version == 1
        assert res1.value.summary_id is not None
        assert res1.value.idempotent_replay is False

        # Replay with same idempotency_key must not compact again
        res2 = manager.compact(
            CompactRequest(project_id=proj.id, max_active_memories=2, idempotency_key="milestone-1")
        )
        assert res2.success, res2.error
        assert res2.value.idempotent_replay is True
        assert res2.value.summary_id == res1.value.summary_id
        assert res2.value.compaction_version == 1
        assert res2.value.compacted_count == 0

        # Source memories remain in SQLite as SUPERSEDED (never hard-deleted)
        for mem in created[:4]:
            loaded = manager.get_memory(mem.id).value
            assert loaded is not None
            assert loaded.status == MemoryStatus.SUPERSEDED
            assert loaded.metadata.get("compaction_summary_id") == str(res1.value.summary_id)

        # Custom instruction untouched
        instrs = manager.get_active_instructions(proj.id).value
        assert len(instrs) == 1
    finally:
        manager.close()


def test_compaction_atomic_rollback_on_lineage_failure(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_rb.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="RollbackProj")).value
        created = [_create_inferred(manager, proj.id, f"Fact {i}") for i in range(4)]

        orig_create_lineage = manager._uow.memories.create_lineage
        calls = {"count": 0}

        def failing_create_lineage(lineage):
            calls["count"] += 1
            if calls["count"] == 2:
                return Result.err("Simulated lineage failure")
            return orig_create_lineage(lineage)

        manager._uow.memories.create_lineage = failing_create_lineage

        res = manager.compact(CompactRequest(project_id=proj.id, max_active_memories=1))
        assert res.success
        assert res.value.compacted_count == 0
        assert any("lineage" in err.lower() for err in res.value.errors)

        # Verify rollback: zero summaries, all 4 source memories still ACTIVE
        all_mems = manager._uow.memories.search(
            MemorySearchParams(project_id=proj.id, include_historical=True, limit=50)
        ).value.items
        assert len(all_mems) == 4
        assert all(m.status == MemoryStatus.ACTIVE for m in all_mems)
        assert all(m.id in {c.id for c in created} for m in all_mems)
    finally:
        manager.close()


def test_compaction_outbox_crash_recovery_on_chromadb_failure(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_outbox.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="OutboxProj")).value
        created = [_create_inferred(manager, proj.id, f"Outbox fact {i}") for i in range(3)]

        orig_index = manager._semantic_index.index_memory
        manager._semantic_index.index_memory = lambda m: Result.err("Simulated ChromaDB outage")

        res = manager.compact(CompactRequest(project_id=proj.id, max_active_memories=1))
        assert res.success
        assert res.value.summary_id is not None
        assert res.value.errors  # Recorded outbox sync error without losing SQLite commit

        # Durable outbox marker must be present in SQLite
        summary = manager.get_memory(res.value.summary_id).value
        assert summary.metadata.get("pending_semantic_sync") == "upsert"
        superseded_m = manager.get_memory(created[0].id).value
        assert superseded_m.metadata.get("pending_semantic_sync") == "remove"

        # Restore ChromaDB and replay outbox
        manager._semantic_index.index_memory = orig_index
        flush_res = manager.flush_pending_semantic_sync(proj.id)
        assert flush_res.success, flush_res.error
        assert flush_res.value >= 3

        summary_after = manager.get_memory(res.value.summary_id).value
        assert not summary_after.metadata.get("pending_semantic_sync")
        superseded_after = manager.get_memory(created[0].id).value
        assert not superseded_after.metadata.get("pending_semantic_sync")
    finally:
        manager.close()


def test_compaction_protects_authoritative_and_unresolved_memories(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_elig.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="EligProj")).value
        authoritative = _create_inferred(manager, proj.id, "Use SQLite.", provenance="explicit_user_update")
        pinned = _create_inferred(manager, proj.id, "Pinned note.", provenance="agent_inferred", metadata={"pinned": True})
        unresolved = _create_inferred(manager, proj.id, "Unresolved note.", provenance="agent_inferred", metadata={"unresolved": True})
        eligible = [_create_inferred(manager, proj.id, f"Eligible {i}") for i in range(3)]

        res = manager.compact(CompactRequest(project_id=proj.id, max_active_memories=1))
        assert res.success, res.error
        assert res.value.compacted_count == 3

        assert manager.get_memory(authoritative.id).value.status == MemoryStatus.ACTIVE
        assert manager.get_memory(pinned.id).value.status == MemoryStatus.ACTIVE
        assert manager.get_memory(unresolved.id).value.status == MemoryStatus.ACTIVE
        for m in eligible:
            assert manager.get_memory(m.id).value.status == MemoryStatus.SUPERSEDED
    finally:
        manager.close()


def test_compaction_session_scoping_and_deep_bidirectional_lineage(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_dag.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="DagProj")).value
        sess_a = manager.create_session(SessionCreateRequest(project_id=proj.id)).value
        sess_b = manager.create_session(SessionCreateRequest(project_id=proj.id)).value

        m_a = [_create_inferred(manager, proj.id, f"Session A {i}", session_id=sess_a.id) for i in range(3)]
        m_b = _create_inferred(manager, proj.id, "Session B stays active", session_id=sess_b.id)

        r1 = manager.compact(CompactRequest(project_id=proj.id, session_id=sess_a.id, max_active_memories=1))
        assert r1.success, r1.error
        assert r1.value.compaction_version == 1
        assert manager.get_memory(m_b.id).value.status == MemoryStatus.ACTIVE

        # Round 2: compact summary_v1 + new memories into summary_v2
        _create_inferred(manager, proj.id, "Session A extra 1", session_id=sess_a.id)
        _create_inferred(manager, proj.id, "Session A extra 2", session_id=sess_a.id)
        r2 = manager.compact(CompactRequest(project_id=proj.id, session_id=sess_a.id, max_active_memories=1))
        assert r2.success, r2.error
        assert r2.value.compaction_version == 2

        # Deep bidirectional traversal
        from_leaf = manager.traverse_lineage(m_a[0].id).value
        assert r1.value.summary_id in from_leaf["descendants"]
        assert r2.value.summary_id in from_leaf["descendants"]

        from_root = manager.traverse_lineage(r2.value.summary_id).value
        assert r1.value.summary_id in from_root["ancestors"]
        assert m_a[0].id in from_root["ancestors"]
    finally:
        manager.close()


def test_concurrent_compaction_allocates_monotonic_versions(tmp_path):
    db_path = str(tmp_path / "compact_conc.sqlite3")
    manager = create_memory_manager(DatabaseConfig.from_path(db_path))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="ConcCompact")).value
        for i in range(6):
            _create_inferred(manager, proj.id, f"Concurrent item {i}")

        results = []
        errors = []

        def worker(idx: int):
            try:
                res = manager.compact(
                    CompactRequest(
                        project_id=proj.id,
                        max_active_memories=2,
                        idempotency_key=f"conc-{idx}",
                    )
                )
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors
        assert len(results) == 2
        assert all(r.success for r in results)
        versions = sorted(r.value.compaction_version for r in results if r.value.compaction_version is not None)
        assert len(versions) >= 1
        assert versions == list(range(1, len(versions) + 1))
    finally:
        manager.close()


def test_historical_archival_preserves_recoverability_and_lineage(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "compact_arch.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="ArchProj")).value
        # Create 105 memories and compact them in one pass so >100 become SUPERSEDED -> ARCHIVED
        created = [_create_inferred(manager, proj.id, f"Historical {i}") for i in range(105)]

        res = manager.compact(CompactRequest(project_id=proj.id, max_active_memories=1))
        assert res.success, res.error
        assert res.value.compacted_count == 105
        assert res.value.archived_count == 5

        # Archived rows remain recoverable with lineage intact
        archived_mems = manager._uow.memories.search(
            MemorySearchParams(project_id=proj.id, status=MemoryStatus.ARCHIVED, include_historical=True, limit=200)
        ).value.items
        assert len(archived_mems) >= 5
        lineage = manager.get_memory_lineage(archived_mems[0].id).value
        assert len(lineage) >= 1
    finally:
        manager.close()
