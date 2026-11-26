"""Phase 07 & Phase 09 full-system validation: accountless dashboard flow, restart recovery, DB idempotency, and operational resilience."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from contracts.base import MemoryStatus, Scope
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from contracts.retrieval import CompactRequest, RetrievalRequest
from database.config import DatabaseConfig
from database.connection import initialize_database
from recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server, run_doctor


def test_accountless_api_operates_without_auth_routes_or_headers(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "accountless.sqlite3")))
    try:
        app = create_app(manager)
        client = TestClient(app, base_url="http://127.0.0.1:8080")

        # Authentication routes do not exist
        assert not any("/auth" in getattr(route, "path", "") for route in app.routes)
        assert client.get("/api/auth/status").status_code == 404
        assert client.post("/api/auth/session", json={"token": "unused"}).status_code in (404, 405)
        assert client.post("/api/auth/logout").status_code in (404, 405)
        assert client.post("/auth/session", json={"token": "unused"}).status_code in (404, 405)
        assert client.post("/auth/logout").status_code in (404, 405)

        # Endpoints succeed directly without credentials
        assert client.get("/health").status_code == 200
        assert client.get("/stats").status_code == 200
        assert client.get("/projects").status_code == 200
        assert client.get("/sessions").status_code == 200
        assert client.get("/memories").status_code == 200

        created = client.post("/projects", json={"name": "CommunityProj"})
        assert created.status_code in (200, 201)
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


def test_spa_deep_links_and_api_open_directly_without_auth(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "spa.sqlite3")))
    try:
        app = create_app(manager)
        client = TestClient(app, base_url="http://127.0.0.1:8080")
        for route in ("/overview", "/chat", "/memories", "/conflicts", "/instructions", "/settings"):
            resp = client.get(route, headers={"Accept": "text/html"})
            assert resp.status_code != 401
        assert client.get("/memories").status_code == 200
        assert client.get("/stats").status_code == 200
        assert client.get("/projects").status_code == 200
        assert client.get("/sessions").status_code == 200
    finally:
        manager.close()


def test_accountless_end_to_end_http_persistence_across_restart(tmp_path):
    db_path = tmp_path / "e2e_http_restart.sqlite3"
    m1 = create_memory_manager(DatabaseConfig.from_path(str(db_path)))
    try:
        c1 = TestClient(create_app(m1), base_url="http://127.0.0.1:8080")
        proj_resp = c1.post("/projects", json={"name": "E2EAccountless"})
        assert proj_resp.status_code in (200, 201)
        project_id = proj_resp.json()["project_id"]

        mem_resp = c1.post(
            "/memories",
            json={
                "project_id": project_id,
                "content": "RECALL Community runs locally without user authentication.",
                "memory_type": "decision",
            },
        )
        assert mem_resp.status_code in (200, 201)
        memory_id = mem_resp.json()["memory_id"]

        query_resp = c1.post(
            "/context/query",
            json={"query": "local accountless", "project_id": project_id},
        )
        assert query_resp.status_code == 200
        assert any(m["memory_id"] == memory_id for m in query_resp.json()["supporting_memories"])
    finally:
        m1.close()

    # Restart server and verify data remains directly readable without credentials
    m2 = create_memory_manager(DatabaseConfig.from_path(str(db_path)))
    try:
        c2 = TestClient(create_app(m2), base_url="http://127.0.0.1:8080")
        listed = c2.get(f"/memories?project_id={project_id}")
        assert listed.status_code == 200
        assert any(m["memory_id"] == memory_id for m in listed.json()["memories"])
    finally:
        m2.close()


def test_frontend_client_has_no_auth_gates_or_credentials():
    repo_root = Path(__file__).resolve().parent.parent
    app_tsx = (repo_root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    client_ts = (repo_root / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    for forbidden in ("/auth/", "loginOperator", "logoutOperator", "getAuthStatus", "X-CSRF-Token", "Operator Sign-In", "recall_csrf_token"):
        assert forbidden not in app_tsx, f"Unexpected auth remnant {forbidden!r} in App.tsx"
        assert forbidden not in client_ts, f"Unexpected auth remnant {forbidden!r} in client.ts"

    esbuild_bin = repo_root / "frontend" / "node_modules" / ".bin" / ("esbuild.cmd" if sys.platform == "win32" else "esbuild")
    if not esbuild_bin.exists():
        pytest.skip("frontend node_modules/.bin/esbuild not installed")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        bundle_js = tmp_path / "client.mjs"
        build_proc = subprocess.run(
            [
                str(esbuild_bin),
                str(repo_root / "frontend" / "src" / "api" / "client.ts"),
                "--bundle",
                "--format=esm",
                "--define:import.meta.env.DEV=false",
                "--define:import.meta.env.VITE_API_BASE_URL=undefined",
                f"--outfile={bundle_js}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert build_proc.returncode == 0, build_proc.stderr

        test_script = tmp_path / "run_client_test.mjs"
        test_script.write_text(
            f"""
import assert from 'node:assert/strict';

const requests = [];
globalThis.fetch = async (url, init = {{}}) => {{
  requests.push({{ url: String(url), init }});
  return new Response(JSON.stringify({{ projects: [], sessions: [], total: 0 }}), {{ status: 200 }});
}};

const mod = await import({bundle_js.as_uri()!r});
const apiClient = mod.default;

await apiClient.getStats();
await apiClient.getProjects();
await apiClient.createProject({{ name: 'DirectProj' }});

assert.equal(requests.length, 3);
for (const req of requests) {{
  assert.equal(req.init.credentials, undefined);
  const headers = new Headers(req.init.headers || {{}});
  assert.equal(headers.has('Authorization'), false);
  assert.equal(headers.has('X-CSRF-Token'), false);
}}
console.log('FRONTEND_CLIENT_ACCOUNTLESS_OK');
""",
            encoding="utf-8",
        )
        node_proc = subprocess.run(
            ["node", str(test_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert node_proc.returncode == 0, f"{node_proc.stdout}\n{node_proc.stderr}"
        assert "FRONTEND_CLIENT_ACCOUNTLESS_OK" in node_proc.stdout
