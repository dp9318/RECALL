"""Phase 06 security, trust-boundary, and installation UX tests."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError

from api.app import create_app
from contracts.base import ConflictResolutionStatus, MemoryStatus, Scope
from contracts.conflict import ConflictCandidate
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import Memory, MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from contracts.retrieval import CompactRequest
from database.config import DatabaseConfig
from intelligence.conflict import DefaultConflictResolver
from recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server, run_doctor


def _call_tool(server, _tool_name: str, **kwargs):
    tool = server._tool_manager._tools[_tool_name]
    return tool.fn(**kwargs)


# --- 1. REST Operator Authentication & CSRF / Origin / Host ---


def test_rest_operator_auth_blocks_unauthenticated_reads_and_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_OPERATOR_TOKEN", "op-secret-token")
    monkeypatch.setenv("RECALL_CAPTURE_TOKEN", "cap-secret-token")
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "auth_api.sqlite3")))
    try:
        app = create_app(manager, require_auth=True)
        client = TestClient(app, base_url="http://127.0.0.1:8080")

        # Public health stays accessible
        assert client.get("/health").status_code == 200
        assert client.get("/auth/status").json()["authenticated"] is False

        # Unauthenticated data-bearing GET & mutating POST/DELETE blocked
        assert client.get("/memories").status_code == 401
        assert client.get("/projects").status_code == 401
        assert client.post("/projects", json={"name": "Blocked"}).status_code == 401
        assert client.post("/context/query", json={"query": "secret"}).status_code == 401

        # Capture token cannot authenticate operator endpoints
        assert client.get(
            "/memories", headers={"Authorization": "Bearer cap-secret-token"}
        ).status_code == 401

        # Invalid Host header rejected (DNS-rebinding defense)
        assert client.get(
            "/memories",
            headers={"Host": "evil.example.com", "Authorization": "Bearer op-secret-token"},
        ).status_code == 403

        # Valid operator Bearer token succeeds
        ok = client.post(
            "/projects",
            json={"name": "AuthedProj"},
            headers={"Authorization": "Bearer op-secret-token"},
        )
        assert ok.status_code in (200, 201)
    finally:
        manager.close()


def test_dashboard_session_cookie_csrf_origin_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_OPERATOR_TOKEN", "op-session-secret")
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "sess_api.sqlite3")))
    try:
        app = create_app(manager, require_auth=True)
        client = TestClient(app, base_url="http://127.0.0.1:8080")

        # Invalid operator token rejected
        assert client.post("/auth/session", json={"token": "wrong"}).status_code == 401

        # Valid login sets HttpOnly session + CSRF cookies
        login = client.post("/auth/session", json={"token": "op-session-secret"})
        assert login.status_code == 200
        assert "recall_operator_session" in client.cookies
        csrf = client.cookies.get("recall_csrf_token")
        assert csrf

        # Cookie-authenticated GET works
        assert client.get("/projects").status_code == 200

        # Cookie-authenticated mutation without Origin/Referer fails closed (403)
        no_origin = client.post("/projects", json={"name": "NoOrigin"}, headers={"X-CSRF-Token": csrf})
        assert no_origin.status_code == 403

        # Cookie-authenticated mutation with bad Origin fails (403)
        bad_origin = client.post(
            "/projects",
            json={"name": "BadOrigin"},
            headers={"Origin": "http://evil.com", "X-CSRF-Token": csrf},
        )
        assert bad_origin.status_code == 403

        # Cookie-authenticated mutation without CSRF fails (403)
        no_csrf = client.post(
            "/projects",
            json={"name": "NoCsrf"},
            headers={"Origin": "http://127.0.0.1:8080"},
        )
        assert no_csrf.status_code == 403

        # Valid Origin + CSRF succeeds
        good = client.post(
            "/projects",
            json={"name": "GoodCookieProj"},
            headers={"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": csrf},
        )
        assert good.status_code in (200, 201)

        # Logout revokes session
        out = client.post(
            "/auth/logout",
            headers={"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": csrf},
        )
        assert out.status_code == 200
        assert client.get("/projects").status_code == 401
    finally:
        manager.close()


# --- 2. Project Isolation & Global Context Filtering ---


def test_mcp_project_allowlist_and_malformed_config(tmp_path, monkeypatch):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "iso.sqlite3")))
    try:
        proj_a = manager.create_project(ProjectCreateRequest(name="ProjA")).value
        proj_b = manager.create_project(ProjectCreateRequest(name="ProjB")).value
        manager.create_memory(
            MemoryCreateRequest(scope=Scope.GLOBAL, content="Global secret memory", provenance="user_explicit")
        )
        manager.create_instruction(
            CustomInstructionCreateRequest(scope=Scope.GLOBAL, content="Global rule")
        )

        # Malformed UUID fails fast at startup
        monkeypatch.setenv("RECALL_ALLOWED_PROJECT_IDS", "not-a-uuid")
        with pytest.raises(ValueError, match="Malformed UUID"):
            create_server(manager)

        # Empty allowlist fails closed on every tool
        monkeypatch.setenv("RECALL_ALLOWED_PROJECT_IDS", "")
        srv_empty = create_server(manager)
        with pytest.raises(ToolError, match="No projects are authorized"):
            _call_tool(srv_empty, "recall_search", query="test", project_id=str(proj_a.id))

        # Allowlist restricted to proj_a blocks proj_b across all tools + isolates global context
        monkeypatch.setenv("RECALL_ALLOWED_PROJECT_IDS", str(proj_a.id))
        srv = create_server(manager)

        ctx_a = _call_tool(srv, "recall_get_context", project_id=str(proj_a.id))
        assert ctx_a["custom_instructions"] == []
        assert all(m["scope"] != "global" for m in ctx_a["active_memories"])

        for tool_name, kwargs in [
            ("recall_search", {"query": "x", "project_id": str(proj_b.id)}),
            ("recall_get_context", {"project_id": str(proj_b.id)}),
            ("recall_save_memory", {"content": "x", "project_id": str(proj_b.id)}),
            ("recall_compact_memory", {"project_id": str(proj_b.id), "max_active_memories": 5}),
            ("recall_create_custom_instruction", {"content": "x", "scope": "project", "project_id": str(proj_b.id)}),
            ("recall_save_project", {"name": "ProjB", "project_id": str(proj_b.id)}),
            ("recall_save_project", {"name": "ProjB"}),  # name-only lookup blocked
        ]:
            with pytest.raises(ToolError):
                _call_tool(srv, tool_name, **kwargs)
    finally:
        manager.close()


# --- 3. Read-Only Zero-Write Guarantee ---


def test_mcp_read_only_mode_omits_write_tools_and_performs_zero_sqlite_writes(tmp_path, monkeypatch):
    db_path = tmp_path / "ro.sqlite3"
    manager = create_memory_manager(DatabaseConfig.from_path(str(db_path)))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="ROProj")).value
        monkeypatch.setenv("RECALL_MCP_MODE", "read-only")
        srv = create_server(manager)

        tools = set(srv._tool_manager._tools.keys())
        assert tools == {"recall_search", "recall_get_context"}

        conn = sqlite3.connect(str(db_path))
        before_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        fresh_session_id = str(uuid4())
        _call_tool(srv, "recall_search", query="hello", project_id=str(proj.id), session_id=fresh_session_id)
        _call_tool(srv, "recall_get_context", project_id=str(proj.id), session_id=fresh_session_id)

        conn = sqlite3.connect(str(db_path))
        after_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        assert after_sessions == before_sessions
    finally:
        manager.close()


# --- 4. Global Instruction Rejection, Provenance & Compaction Floor ---


def test_global_instruction_rejected_by_default_and_agent_saved_provenance(tmp_path, monkeypatch):
    monkeypatch.delenv("RECALL_MCP_ALLOW_GLOBAL_INSTRUCTIONS", raising=False)
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "prov.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="ProvProj")).value
        srv = create_server(manager)

        with pytest.raises(ToolError, match="Global custom instruction creation is disabled"):
            _call_tool(srv, "recall_create_custom_instruction", content="Poison global", scope="global")

        saved = _call_tool(srv, "recall_save_memory", content="Use SQLite.", project_id=str(proj.id))
        assert saved["memory"]["provenance"] == "agent_saved"

        # Conflict ranking: user_explicit > agent_saved > agent_inferred
        user_mem = Memory(id=uuid4(), project_id=proj.id, scope=Scope.PROJECT, content="Use Postgres.", provenance="user_explicit")
        agent_saved_mem = Memory(id=uuid4(), project_id=proj.id, scope=Scope.PROJECT, content="Use SQLite.", provenance="agent_saved")
        agent_inf_mem = Memory(id=uuid4(), project_id=proj.id, scope=Scope.PROJECT, content="Use MySQL.", provenance="agent_inferred")

        resolver = DefaultConflictResolver()
        r1 = resolver.apply_deterministic_rules([ConflictCandidate(id=user_mem.id, memory=user_mem), ConflictCandidate(id=agent_saved_mem.id, memory=agent_saved_mem)], [])
        assert r1.status == ConflictResolutionStatus.RESOLVED
        assert r1.preferred_candidates[0].memory.id == user_mem.id

        r2 = resolver.apply_deterministic_rules([ConflictCandidate(id=agent_saved_mem.id, memory=agent_saved_mem), ConflictCandidate(id=agent_inf_mem.id, memory=agent_inf_mem)], [])
        assert r2.status == ConflictResolutionStatus.RESOLVED
        assert r2.preferred_candidates[0].memory.id == agent_saved_mem.id
    finally:
        manager.close()


def test_compaction_floor_and_idempotency_parameter_binding(tmp_path):
    manager = create_memory_manager(DatabaseConfig.from_path(str(tmp_path / "floor.sqlite3")))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="FloorProj")).value
        srv = create_server(manager)

        with pytest.raises(ToolError, match=">= 5"):
            _call_tool(srv, "recall_compact_memory", project_id=str(proj.id), max_active_memories=4)

        for i in range(7):
            manager.create_memory(
                MemoryCreateRequest(project_id=proj.id, scope=Scope.PROJECT, content=f"Fact {i}", provenance="agent_inferred")
            )

        res1 = _call_tool(
            srv,
            "recall_compact_memory",
            project_id=str(proj.id),
            max_active_memories=5,
            idempotency_key="phase06-key-1",
        )
        assert res1["compacted_count"] == 3

        # Reusing same idempotency_key with different max_active_memories must fail
        with pytest.raises(ToolError, match="different compaction parameters"):
            _call_tool(
                srv,
                "recall_compact_memory",
                project_id=str(proj.id),
                max_active_memories=6,
                idempotency_key="phase06-key-1",
            )
    finally:
        manager.close()


def test_doctor_and_generate_mcp_config(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_DB_PATH", str(tmp_path / "doc.sqlite3"))
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(tmp_path / "chroma"))
    assert run_doctor() == 0

    from scripts.generate_mcp_config import generate_config
    out_file = tmp_path / "mcp.json"
    cfg = generate_config(out_file)
    std = cfg["standard_mcpServers_format (Cursor, Claude Desktop, Antigravity)"]["mcpServers"]["recall"]
    assert "cwd" in std
    assert std["env"]["RECALL_MCP_MODE"] == "standard"
