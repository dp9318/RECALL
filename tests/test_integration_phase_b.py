"""Integration tests for Phase B: API encapsulation, route decoupling, and multi-process persistence."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from contracts.base import PaginatedResult, Result, Scope
from contracts.conflict import ConflictResolutionResult, ConflictResolutionStatus
from contracts.memory import Memory, MemoryStatus
from contracts.project import Project, Session
from api.app import create_app
from recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig
from database.connection import initialize_database
from recall_mcp.server import create_server


# ---------------------------------------------------------------------------
# 1. Architectural Boundary Regression Tests
# ---------------------------------------------------------------------------

def test_api_module_has_zero_uow_access():
    """Verify that the API implementation contains zero references to private _uow."""
    api_dir = Path(__file__).resolve().parent.parent / "api"
    uow_accesses: list[str] = []

    for py_file in api_dir.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "_uow":
                uow_accesses.append(f"{py_file.name}:{node.lineno}")

    assert not uow_accesses, (
        f"Architectural boundary violation: Found direct _uow access in api package at: {uow_accesses}"
    )


def test_api_routes_work_without_uow_on_manager():
    """Verify that all API routes function properly with a manager having no _uow attribute."""
    # A mock manager that raises AttributeError if _uow is ever accessed
    mock_manager = Mock(spec=[
        "get_project",
        "create_project",
        "update_project",
        "delete_project",
        "list_projects",
        "list_projects_paginated",
        "get_project_memory_count",
        "get_project_session_count",
        "get_session",
        "create_session",
        "update_session",
        "end_session",
        "list_sessions_paginated",
        "get_session_memory_count",
        "get_memory",
        "create_memory",
        "update_memory",
        "delete_memory",
        "search_memories",
        "search_memories_paginated",
        "get_active_memories",
        "retrieve",
        "assemble_context",
        "compact",
        "get_instruction",
        "create_instruction",
        "update_instruction",
        "delete_instruction",
        "list_instructions",
        "get_active_instructions",
        "get_conflicts",
        "detect_and_resolve_conflicts",
        "get_stats",
        "close",
        "_semantic_index",
    ])
    del mock_manager._uow  # Explicitly ensure _uow does not exist

    project_id = uuid4()
    mock_project = Project(id=project_id, name="Test Project", description="Encapsulation test")

    mock_manager.list_projects_paginated.return_value = Result.ok(
        PaginatedResult(items=[mock_project], total=1, limit=50, offset=0)
    )
    mock_manager.get_project.return_value = Result.ok(mock_project)
    mock_manager.get_project_memory_count.return_value = Result.ok(5)
    mock_manager.get_project_session_count.return_value = Result.ok(2)
    mock_manager.list_sessions_paginated.return_value = Result.ok(
        PaginatedResult(items=[], total=0, limit=50, offset=0)
    )
    mock_manager.get_conflicts.return_value = Result.ok(None)
    mock_manager.get_stats.return_value = Result.ok({
        "memories": {"active": 5},
        "custom_instructions": {"active": 1},
        "projects": 1,
        "sessions": 2,
        "total_memories": 5,
        "semantic_index": {"status": "healthy"},
    })
    mock_manager._semantic_index = Mock()
    mock_manager._semantic_index.health_check.return_value = Result.ok({"status": "healthy", "available": True})

    app = create_app(mock_manager)
    client = TestClient(app)

    # 1. Projects endpoint
    resp = client.get("/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["projects"][0]["name"] == "Test Project"
    assert data["projects"][0]["memory_count"] == 5
    assert data["projects"][0]["session_count"] == 2

    # 2. Sessions endpoint
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 3. Conflicts endpoint
    resp = client.get("/conflicts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 4. Stats endpoint
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json()["total_memories"] == 5


# ---------------------------------------------------------------------------
# 2. Decoupled Route Handler Invariant Tests
# ---------------------------------------------------------------------------

def test_stats_endpoint_does_not_invoke_list_conflicts_route():
    """Verify that GET /stats does not call the list_conflicts route handler directly."""
    mock_manager = Mock(spec=[
        "get_stats",
        "get_conflicts",
        "close",
        "_semantic_index",
    ])
    del mock_manager._uow

    mock_manager.get_stats.return_value = Result.ok({
        "memories": {"active": 3},
        "custom_instructions": {"active": 0},
        "projects": 1,
        "sessions": 1,
        "total_memories": 3,
        "semantic_index": {"status": "healthy"},
    })
    mock_manager.get_conflicts.return_value = Result.ok(None)
    mock_manager._semantic_index = Mock()
    mock_manager._semantic_index.health_check.return_value = Result.ok({"status": "healthy", "available": True})

    app = create_app(mock_manager)
    client = TestClient(app)

    # Check stats executes cleanly without invoking list_conflicts
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json()["unresolved_conflicts"] == 0
    mock_manager.get_conflicts.assert_called_once_with(project_id=None)


# ---------------------------------------------------------------------------
# 3. Cross-Surface Consistency (API ↔ MCP with Isolated Persistence)
# ---------------------------------------------------------------------------

def test_api_and_mcp_scope_and_lifecycle_consistency():
    """Exercise complete memory lifecycle and scope consistency between HTTP API and FastMCP."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "recall_integration.sqlite3"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        # In-process memory manager shared across API and MCP wrappers for isolated integration
        manager = create_memory_manager(config)
        app = create_app(manager)
        client = TestClient(app)
        mcp_server = create_server(manager)
        search_tool = mcp_server._tool_manager.get_tool("recall_search").fn
        save_tool = mcp_server._tool_manager.get_tool("recall_save_memory").fn

        try:
            # 1. Create a Project via HTTP API
            create_proj_resp = client.post("/projects", json={
                "name": "Integration Project",
                "description": "Cross-surface testing project",
            })
            assert create_proj_resp.status_code == 200
            project_data = create_proj_resp.json()
            project_id = project_data["project_id"]
            assert project_data["memory_count"] == 0

            # 2. Save a Memory via FastMCP tool
            mcp_save_res = save_tool(
                content="Architecture decision: SQLite is the canonical storage engine.",
                project_id=project_id,
                memory_type="decision",
            )
            assert "memory" in mcp_save_res
            memory_id = mcp_save_res["memory"]["id"]

            # 3. Verify Memory is visible in HTTP API project listing with updated count
            list_proj_resp = client.get("/projects")
            assert list_proj_resp.status_code == 200
            projects = list_proj_resp.json()["projects"]
            matched_project = next(p for p in projects if p["project_id"] == project_id)
            assert matched_project["memory_count"] == 1

            # 4. Verify Memory details in HTTP API
            get_mem_resp = client.get(f"/memories/{memory_id}")
            assert get_mem_resp.status_code == 200
            mem_data = get_mem_resp.json()
            assert mem_data["content"] == "Architecture decision: SQLite is the canonical storage engine."
            assert mem_data["memory_type"] == "decision"
            assert mem_data["project_id"] == project_id

            # 5. Update Memory content via HTTP API
            patch_resp = client.patch(f"/memories/{memory_id}", json={
                "content": "Architecture decision: SQLite WAL mode with synchronous NORMAL.",
                "importance": 90,
            })
            assert patch_resp.status_code == 200
            assert patch_resp.json()["importance"] == 90

            # 6. Verify Updated Memory is retrieved via MCP tool search
            search_res = search_tool(
                query="SQLite",
                project_id=project_id,
                limit=5,
            )
            assert search_res["total_found"] >= 1
            found_mem = search_res["memories"][0]
            assert "synchronous NORMAL" in found_mem["content"]

            # 7. Delete Memory via HTTP API
            del_resp = client.delete(f"/memories/{memory_id}")
            assert del_resp.status_code == 204

            # 8. Verify Project memory count reflects deletion
            list_proj_after = client.get("/projects").json()["projects"]
            matched_after = next(p for p in list_proj_after if p["project_id"] == project_id)
            assert matched_after["memory_count"] == 0

        finally:
            manager.close()


# ---------------------------------------------------------------------------
# 4. Error Handling and Defensive Boundary Tests
# ---------------------------------------------------------------------------

def test_api_handles_database_failures_gracefully():
    """Verify that database errors return structured 500 responses without leaking internals."""
    mock_manager = Mock(spec=[
        "list_projects_paginated",
        "get_project",
        "close",
        "_semantic_index",
    ])
    del mock_manager._uow

    # Simulate database connection / query failure
    mock_manager.list_projects_paginated.return_value = Result.err("database disk image is malformed")

    app = create_app(mock_manager)
    client = TestClient(app)

    resp = client.get("/projects")
    assert resp.status_code == 500
    body = resp.json()
    assert "detail" in body
    # Error message must be human-readable and not expose raw tracebacks
    assert "malformed" in body["detail"]
    assert "Traceback" not in body["detail"]


# ---------------------------------------------------------------------------
# 5. Multi-Process Concurrency and ChromaDB Persistence
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = """
import sys
from pathlib import Path
from uuid import UUID

from contracts.base import Scope
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig

db_path = Path(sys.argv[1])
config = DatabaseConfig.from_path(db_path)
manager = create_memory_manager(config)

try:
    proj_res = manager.create_project(ProjectCreateRequest(name="MultiProcess Project"))
    assert proj_res.success
    proj_id = proj_res.value.id

    mem_res = manager.create_memory(MemoryCreateRequest(
        project_id=proj_id,
        scope=Scope.PROJECT,
        content="Cross-process memory written by worker subprocess",
        memory_type="fact",
    ))
    assert mem_res.success

    # Print created identifiers as JSON for parent process
    print(f"RESULT:{{\\"project_id\\": \\"{proj_id}\\", \\"memory_id\\": \\"{mem_res.value.id}\\"}}")
finally:
    manager.close()
"""


def test_cross_process_sqlite_and_chromadb_concurrency():
    """Verify independent processes accessing the same persistent SQLite database and ChromaDB index.
    
    Demonstrates:
    1. SQLite canonical state written by an external process is immediately durable and readable.
    2. Derived ChromaDB vector index written by an external process is queryable after index sync.
    """
    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "shared.sqlite3"
        config = DatabaseConfig.from_path(db_path)
        initialize_database(config)

        # Process 1: Run worker script as an isolated subprocess
        proc = subprocess.run(
            [sys.executable, "-c", _WORKER_SCRIPT, str(db_path)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            env={**os.environ, "PYTHONPATH": str(repo_root)},
            check=True,
        )

        output = proc.stdout
        result_line = next(line for line in output.splitlines() if line.startswith("RESULT:"))
        worker_data = json.loads(result_line.replace("RESULT:", ""))
        project_id = UUID(worker_data["project_id"])
        memory_id = UUID(worker_data["memory_id"])

        # Process 2: Open database in current process with an independent MemoryManager
        process2_manager = create_memory_manager(config)
        try:
            # 1. Canonical SQLite consistency: project and memory must be immediately visible
            proj_result = process2_manager.get_project(project_id)
            assert proj_result.success
            assert proj_result.value is not None
            assert proj_result.value.name == "MultiProcess Project"

            mem_count_res = process2_manager.get_project_memory_count(project_id)
            assert mem_count_res.success
            assert mem_count_res.value == 1

            mem_result = process2_manager.get_memory(memory_id)
            assert mem_result.success
            assert mem_result.value is not None
            assert "worker subprocess" in mem_result.value.content

            # 2. Semantic retrieval consistency:
            # The worker process wrote the embedding to the shared ChromaDB directory.
            # Process 2 queries the vector store directly.
            search_result = process2_manager.search(
                query="worker subprocess",
                project_id=project_id,
                limit=5,
            )
            assert search_result.success
            # ChromaDB persistent directory persisted the vectors from Process 1
            assert search_result.value.total_found >= 1
            assert search_result.value.memories[0].id == memory_id

        finally:
            process2_manager.close()
