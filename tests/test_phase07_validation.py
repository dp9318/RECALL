"""Phase 07 full-system validation: session TTL expiry, restart recovery, DB idempotency, and operational resilience."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import OperatorSessionStore
from contracts.base import MemoryStatus, Scope
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from contracts.retrieval import CompactRequest, RetrievalRequest
from database.config import DatabaseConfig
from database.connection import initialize_database
from recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server, run_doctor


def test_operator_session_ttl_expiration(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_OPERATOR_TOKEN", "ttl-test-token")
    monkeypatch.setenv("RECALL_SESSION_TTL_SECONDS", "5")
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "ttl.sqlite3")))
    try:
        app = create_app(manager, require_auth=True)
        client = TestClient(app, base_url="http://127.0.0.1:8080")

        login = client.post("/auth/session", json={"token": "ttl-test-token"})
        assert login.status_code == 200
        assert client.get("/projects").status_code == 200

        # Simulate clock advancing past TTL
        import api.auth as auth_mod
        real_monotonic = auth_mod.time.monotonic
        monkeypatch.setattr(auth_mod.time, "monotonic", lambda: real_monotonic() + 10.0)

        expired = client.get("/projects")
        assert expired.status_code == 401
        assert client.get("/auth/status").json()["authenticated"] is False
    finally:
        manager.close()


def test_full_restart_persistence_chromadb_and_lineage_recovery(tmp_path, monkeypatch):
    db_path = tmp_path / "restart.sqlite3"
    chroma_path = tmp_path / "chroma"
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(chroma_path))

    m1 = create_memory_manager(DatabaseConfig.from_path(str(db_path)))
    try:
        proj = m1.create_project(ProjectCreateRequest(name="RestartProj")).value
        m1.create_instruction(
            CustomInstructionCreateRequest(scope=Scope.PROJECT, project_id=proj.id, content="Always use UTC.")
        )
        for i in range(6):
            m1.create_memory(
                MemoryCreateRequest(
                    project_id=proj.id,
                    scope=Scope.PROJECT,
                    content=f"Restart persistence fact {i} about SQLite WAL.",
                    provenance="agent_inferred",
                )
            )
        comp = m1.compact(CompactRequest(project_id=proj.id, max_active_memories=5, idempotency_key="r1"))
        assert comp.success and comp.value.summary_id is not None
        summary_id = comp.value.summary_id
    finally:
        m1.close()

    # Reopen fresh MemoryManager on same SQLite + ChromaDB
    m2 = create_memory_manager(DatabaseConfig.from_path(str(db_path)))
    try:
        instrs = m2.get_active_instructions(proj.id)
        assert instrs.success and len(instrs.value) == 1

        ret = m2.retrieve(RetrievalRequest(query="SQLite WAL", project_id=proj.id, limit=10))
        assert ret.success and ret.value.total_found >= 1

        dag = m2.traverse_lineage(summary_id)
        assert dag.success and len(dag.value["ancestors"]) == 2

        rebuilt = m2.rebuild_semantic_index()
        assert rebuilt.success and rebuilt.value >= 5
    finally:
        m2.close()


def test_database_migration_idempotency_and_integrity(tmp_path):
    db_path = tmp_path / "mig.sqlite3"
    cfg = DatabaseConfig.from_path(str(db_path))
    initialize_database(cfg)
    initialize_database(cfg)

    conn = sqlite3.connect(str(db_path))
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert integrity == "ok"
        assert version == 2
    finally:
        conn.close()


def test_operational_failure_modes_corrupted_db_and_invalid_env(tmp_path, monkeypatch):
    bad_db = tmp_path / "corrupt.sqlite3"
    bad_db.write_bytes(b"corrupted-header-bytes")
    monkeypatch.setenv("RECALL_DB_PATH", str(bad_db))
    assert run_doctor() == 1

    # Invalid MCP mode fails closed
    good_db = tmp_path / "good.sqlite3"
    manager = create_memory_manager(DatabaseConfig.from_path(str(good_db)))
    try:
        monkeypatch.setenv("RECALL_MCP_MODE", "admin-override")
        with pytest.raises(ValueError, match="Unsupported RECALL_MCP_MODE"):
            create_server(manager)
    finally:
        manager.close()


def test_smoke_test_mcp_script_runs_cleanly_in_isolated_temp_env(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "smoke_test_mcp.py"
    assert script.is_file()
    env = {
        **os.environ,
        "RECALL_DB_PATH": str(tmp_path / "smoke.sqlite3"),
        "RECALL_CHROMA_PATH": str(tmp_path / "smoke_chroma"),
        "RECALL_MCP_WARMUP": "false",
    }
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"smoke_test_mcp.py failed:\n{proc.stdout}\n{proc.stderr}"


def test_spa_deep_links_not_blocked_by_auth_middleware(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "spa.sqlite3")))
    try:
        app = create_app(manager, require_auth=True)
        client = TestClient(app, base_url="http://127.0.0.1:8080")
        for route in ("/overview", "/chat", "/memories", "/conflicts", "/instructions", "/settings"):
            resp = client.get(route, headers={"Accept": "text/html"})
            assert resp.status_code != 401
        assert client.get("/memories").status_code == 401
    finally:
        manager.close()
