"""Phase 08 tests for canonical DB resolution, fail-closed invalid paths, ChromaDB recovery, and MCP round-trip."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from contracts.base import Scope
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from database.config import DatabaseConfig
from database.exceptions import ConfigurationError
from recall_core.bootstrap import create_memory_manager, resolve_runtime_paths
from recall_mcp.server import create_server, run_doctor
from scripts.verify_and_repair_chroma import inspect_consistency, repair_with_backup


def test_canonical_path_resolution_precedence(tmp_path, monkeypatch):
    # 1. Default canonical per-user DB when RECALL_DB_PATH / RECALL_CHROMA_PATH unset
    monkeypatch.delenv("RECALL_DB_PATH", raising=False)
    monkeypatch.delenv("RECALL_CHROMA_PATH", raising=False)
    default_paths = resolve_runtime_paths()
    expected_sqlite = (Path.home() / ".recall" / "recall.sqlite3").resolve()
    assert default_paths.sqlite_path == expected_sqlite
    assert default_paths.sqlite_source == "default_canonical"
    assert default_paths.chroma_path == expected_sqlite.with_suffix(".sqlite3.chromadb")
    assert default_paths.chroma_source == "derived_from_sqlite"

    # 2. Explicit env RECALL_DB_PATH & RECALL_CHROMA_PATH
    custom_db = tmp_path / "custom.sqlite3"
    custom_chroma = tmp_path / "custom_chroma"
    monkeypatch.setenv("RECALL_DB_PATH", str(custom_db))
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(custom_chroma))
    env_paths = resolve_runtime_paths()
    assert env_paths.sqlite_path == custom_db.resolve()
    assert env_paths.sqlite_source == "env:RECALL_DB_PATH"
    assert env_paths.chroma_path == custom_chroma.resolve()
    assert env_paths.chroma_source == "env:RECALL_CHROMA_PATH"

    # 3. Explicit DatabaseConfig overrides RECALL_DB_PATH
    explicit_db = tmp_path / "explicit.sqlite3"
    exp_paths = resolve_runtime_paths(DatabaseConfig.from_path(explicit_db))
    assert exp_paths.sqlite_path == explicit_db.resolve()
    assert exp_paths.sqlite_source == "explicit_config"


def test_invalid_or_missing_parent_db_path_fails_closed(tmp_path, monkeypatch):
    # Directory passed as RECALL_DB_PATH
    monkeypatch.setenv("RECALL_DB_PATH", str(tmp_path))
    monkeypatch.delenv("RECALL_CHROMA_PATH", raising=False)
    with pytest.raises(ConfigurationError, match="directory"):
        resolve_runtime_paths()

    # Non-existent parent directory must not silently create unintended DB
    missing_parent_db = tmp_path / "does_not_exist" / "typo.sqlite3"
    monkeypatch.setenv("RECALL_DB_PATH", str(missing_parent_db))
    with pytest.raises(ConfigurationError, match="parent directory does not exist"):
        resolve_runtime_paths()
    assert not missing_parent_db.exists()
    assert not missing_parent_db.parent.exists()


def test_doctor_reports_resolved_paths_and_runs_cleanly(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "doc_p08.sqlite3"
    chroma_dir = tmp_path / "doc_p08_chroma"
    monkeypatch.setenv("RECALL_DB_PATH", str(db_path))
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(chroma_dir))
    assert run_doctor() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sqlite_path"] == str(db_path.resolve())
    assert payload["sqlite_source"] == "env:RECALL_DB_PATH"
    assert payload["chroma_path"] == str(chroma_dir.resolve())
    assert payload["chroma_source"] == "env:RECALL_CHROMA_PATH"
    assert payload["ok"] is True


def test_chroma_consistency_verify_and_backup_repair(tmp_path, monkeypatch):
    db_path = tmp_path / "repair.sqlite3"
    chroma_dir = tmp_path / "repair_chroma"
    monkeypatch.setenv("RECALL_DB_PATH", str(db_path))
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(chroma_dir))

    manager = create_memory_manager(DatabaseConfig.from_path(db_path))
    try:
        proj = manager.create_project(ProjectCreateRequest(name="RepairProj")).value
        mem = manager.create_memory(
            MemoryCreateRequest(
                project_id=proj.id,
                scope=Scope.PROJECT,
                content="Canonical SQLite memory for Chroma recovery test.",
                provenance="user_explicit",
            )
        ).value
        # Simulate stale/missing Chroma entry by deleting from Chroma directly
        manager._semantic_index.remove_memory(mem.id)
    finally:
        manager.close()

    pre = inspect_consistency(db_path, chroma_dir)
    assert pre["consistent"] is False
    assert str(mem.id) in pre["missing_in_chroma"]

    post = repair_with_backup(db_path, chroma_dir)
    assert post["consistent"] is True
    assert post["sqlite_active_count"] == 1
    assert post["chroma_embedding_count"] == 1
    assert post["backup_path"] is not None
    assert Path(post["backup_path"]).is_dir()


def test_mcp_round_trip_restart_and_clean_module_startup(tmp_path, monkeypatch):
    db_path = tmp_path / "rt.sqlite3"
    chroma_dir = tmp_path / "rt_chroma"
    monkeypatch.setenv("RECALL_DB_PATH", str(db_path))
    monkeypatch.setenv("RECALL_CHROMA_PATH", str(chroma_dir))

    # 1. Verify python -m recall_mcp.server --doctor emits zero RuntimeWarning and zero non-JSON stdout
    proc = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-m", "recall_mcp.server", "--doctor"],
        env={**os.environ, "RECALL_DB_PATH": str(db_path), "RECALL_CHROMA_PATH": str(chroma_dir)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RuntimeWarning" not in proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["sqlite_path"] == str(db_path.resolve())
    assert doc["chroma_path"] == str(chroma_dir.resolve())

    # 2. Write -> Search -> GetContext -> Restart -> Verify Persistence
    m1 = create_memory_manager()
    try:
        srv1 = create_server(m1)

        async def _session1():
            async with create_connected_server_and_client_session(srv1) as client:
                tools = await client.list_tools()
                assert len(tools.tools) == 6
                proj_res = await client.call_tool("recall_save_project", {"name": "P08RoundTrip"})
                assert not proj_res.isError
                pid = proj_res.structuredContent["project"]["id"]
                save_res = await client.call_tool(
                    "recall_save_memory",
                    {"project_id": pid, "content": "Phase 08 round-trip semantic persistence check."},
                )
                assert not save_res.isError
                search_res = await client.call_tool(
                    "recall_search",
                    {"project_id": pid, "query": "round-trip semantic persistence"},
                )
                assert not search_res.isError
                assert search_res.structuredContent["total_found"] >= 1
                ctx_res = await client.call_tool("recall_get_context", {"project_id": pid})
                assert not ctx_res.isError
                assert len(ctx_res.structuredContent["active_memories"]) >= 1
                return pid

        pid = asyncio.run(_session1())
    finally:
        m1.close()

    m2 = create_memory_manager()
    try:
        srv2 = create_server(m2)

        async def _session2():
            async with create_connected_server_and_client_session(srv2) as client:
                search_res = await client.call_tool(
                    "recall_search",
                    {"project_id": pid, "query": "round-trip semantic persistence"},
                )
                assert not search_res.isError
                assert search_res.structuredContent["total_found"] >= 1

        asyncio.run(_session2())
    finally:
        m2.close()
