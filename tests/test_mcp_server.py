"""Tests for the RECALL MCP adapter and tool protocol."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session
import pytest

from contracts.base import InstructionStatus, Result, Scope
from contracts.instruction import CustomInstruction
from contracts.memory import Memory
from contracts.project import Project
from contracts.retrieval import (
    AssembledContext,
    CompactResult,
    RetrievalResult,
    UpdateContextResult,
)
from recall_mcp.server import create_server


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def manager(project_id, session_id):
    core = Mock()
    core.get_session.return_value = Result.ok(
        Mock(project_id=project_id)
    )
    core.retrieve.return_value = Result.ok(RetrievalResult(query="sqlite"))
    core.assemble_context.return_value = Result.ok(
        AssembledContext(assembled_at=datetime.now(timezone.utc).isoformat())
    )
    core.create_memory.return_value = Result.ok(
        Memory(
            project_id=project_id,
            scope=Scope.PROJECT,
            content="Persisted decision",
            provenance="user_explicit",
        )
    )
    return core


def _tools(server):
    return {tool.name: tool for tool in server._tool_manager.list_tools()}


def _call_tool(server, name, arguments):
    return asyncio.run(server.call_tool(name, arguments))


def _protocol_call(server, name, arguments):
    async def call():
        async with create_connected_server_and_client_session(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(call())


def test_server_registers_only_core_backed_tools(manager):
    tools = _tools(create_server(manager))

    assert set(tools) == {
        "recall_search",
        "recall_get_context",
        "recall_compact_memory",
        "recall_create_custom_instruction",
        "recall_save_memory",
        "recall_save_project",
    }
    assert {
        "name",
        "description",
        "project_id",
        "metadata",
    } <= set(tools["recall_save_project"].parameters["properties"])
    assert (
        tools["recall_compact_memory"].parameters["properties"]["preserve_lineage"]["const"]
        is True
    )


def test_search_protocol_delegates_with_project_scope(manager, project_id):
    server = create_server(manager)

    result = _protocol_call(
        server,
        "recall_search",
        {"query": " sqlite ", "project_id": str(project_id), "limit": 5},
    )

    manager.retrieve.assert_called_once()
    request = manager.retrieve.call_args.args[0]
    assert request.query == "sqlite"
    assert request.project_id == project_id
    assert request.limit == 5
    assert result.isError is False
    assert result.structuredContent["project_id"] == str(project_id)
    assert result.structuredContent["memories"] == []


def test_mcp_protocol_reports_core_errors(manager, project_id):
    manager.retrieve.return_value = Result.err("semantic index unavailable")

    response = _protocol_call(
        create_server(manager),
        "recall_search",
        {"query": "valid", "project_id": str(project_id)},
    )

    assert response.isError is True
    assert "semantic index unavailable" in response.content[0].text


def test_protocol_invalid_input_returns_error_and_server_remains_usable(
    manager, project_id
):
    async def call_tools():
        async with create_connected_server_and_client_session(
            create_server(manager)
        ) as client:
            invalid = await client.call_tool(
                "recall_search",
                {"query": " ", "project_id": str(project_id)},
            )
            valid = await client.call_tool(
                "recall_search",
                {"query": "valid", "project_id": str(project_id)},
            )
            return invalid, valid

    invalid, valid = asyncio.run(call_tools())

    assert invalid.isError is True
    assert "query" in invalid.content[0].text
    assert valid.isError is False


def test_search_rejects_invalid_query_and_limit(manager, project_id):
    server = create_server(manager)

    with pytest.raises(ToolError, match="query"):
        _call_tool(
            server,
            "recall_search",
            {"query": " ", "project_id": str(project_id)},
        )
    with pytest.raises(ToolError, match="limit"):
        _call_tool(
            server,
            "recall_search",
            {"query": "valid", "project_id": str(project_id), "limit": 51},
        )
    with pytest.raises(ToolError, match="limit"):
        _call_tool(
            server,
            "recall_search",
            {"query": "valid", "project_id": str(project_id), "limit": 1.5},
        )
    manager.retrieve.assert_not_called()


def test_project_scoped_tools_reject_missing_project(manager, project_id):
    manager.get_project.return_value = Result.ok(None)

    with pytest.raises(ToolError, match="project"):
        _call_tool(
            create_server(manager),
            "recall_get_context",
            {"project_id": str(project_id)},
        )

    manager.assemble_context.assert_not_called()


def test_session_scope_must_match_project(manager, project_id):
    other_project = uuid4()
    manager.get_session.return_value = Result.ok(Mock(project_id=other_project))

    with pytest.raises(ToolError, match="does not belong"):
        _call_tool(
            create_server(manager),
            "recall_search",
            {
                "query": "valid",
                "project_id": str(project_id),
                "session_id": str(uuid4()),
            },
        )
    manager.retrieve.assert_not_called()


def test_search_surfaces_core_failure_as_mcp_error(manager, project_id):
    manager.retrieve.return_value = Result.err("semantic index unavailable")

    with pytest.raises(ToolError, match="semantic index unavailable"):
        _call_tool(
            create_server(manager),
            "recall_search",
            {"query": "valid", "project_id": str(project_id)},
        )


def test_context_delegates_and_serializes_core_result(manager, project_id):
    server = create_server(manager)

    result = _call_tool(
        server,
        "recall_get_context",
        {"project_id": str(project_id), "include_historical": True},
    )

    manager.assemble_context.assert_called_once()
    request = manager.assemble_context.call_args.args[0]
    assert request.project_id == project_id
    assert request.include_historical is True
    assert result[1]["assembled_at"]


def test_save_uses_canonical_core_creation_and_preserves_provenance(manager, project_id):
    server = create_server(manager)

    result = _call_tool(
        server,
        "recall_save_memory",
        {
            "content": " Persisted decision ",
            "project_id": str(project_id),
            "memory_type": " decision ",
        },
    )

    manager.create_memory.assert_called_once()
    request = manager.create_memory.call_args.args[0]
    assert request.project_id == project_id
    assert request.scope is Scope.PROJECT
    assert request.content == "Persisted decision"
    assert request.memory_type == "decision"
    assert request.provenance == "agent_saved"
    assert result[1]["memory"]["provenance"] == "user_explicit"


def test_save_does_not_report_success_when_core_fails(manager, project_id):
    manager.create_memory.return_value = Result.err("SQLite unavailable")

    with pytest.raises(ToolError, match="SQLite unavailable"):
        _call_tool(
            create_server(manager),
            "recall_save_memory",
            {"content": "Persisted decision", "project_id": str(project_id)},
        )


def test_retained_tools_delegate_with_existing_typed_requests(manager, project_id):
    instruction = CustomInstruction(
        scope=Scope.GLOBAL,
        content="Prefer explicit decisions.",
    )
    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.compact.return_value = Result.ok(CompactResult(preserved_count=2))
    manager.create_instruction.return_value = Result.ok(instruction)
    manager.get_project_by_name.return_value = Result.ok(None)
    manager.create_project.return_value = Result.ok(
        Project(id=project_id, name="demo", description="Demo project")
    )
    server = create_server(manager)

    compacted = _protocol_call(
        server,
        "recall_compact_memory",
        {"project_id": str(project_id), "max_active_memories": 7},
    )
    created_inst = _protocol_call(
        server,
        "recall_create_custom_instruction",
        {"scope": "project", "project_id": str(project_id), "content": "Use tests."},
    )
    saved_project = _protocol_call(
        server,
        "recall_save_project",
        {"name": "demo", "description": "Demo project"},
    )
    saved_memory = _protocol_call(
        server,
        "recall_save_memory",
        {"content": "Persisted decision", "project_id": str(project_id)},
    )

    assert not compacted.isError
    compact_request = manager.compact.call_args.args[0]
    assert compact_request.project_id == project_id
    assert compact_request.max_active_memories == 7

    assert not created_inst.isError
    create_request = manager.create_instruction.call_args.args[0]
    assert create_request.scope is Scope.PROJECT
    assert create_request.project_id == project_id

    assert not saved_project.isError
    assert saved_project.structuredContent["project"]["name"] == "demo"

    assert not saved_memory.isError
    assert saved_memory.structuredContent["memory"]["content"] == "Persisted decision"


def test_new_tools_reject_invalid_inputs_and_failed_mutations(manager, project_id):
    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.create_instruction.return_value = Result.err("SQLite unavailable")
    server = create_server(manager)

    async def call_tools():
        async with create_connected_server_and_client_session(server) as client:
            invalid_compact = await client.call_tool(
                "recall_compact_memory",
                {"project_id": str(project_id), "max_active_memories": 0},
            )
            invalid_instruction = await client.call_tool(
                "recall_create_custom_instruction",
                {"scope": "project", "content": "Missing project"},
            )
            failed_create = await client.call_tool(
                "recall_create_custom_instruction",
                {"content": "Valid text", "scope": "project", "project_id": str(project_id)},
            )
            invalid_project_uuid = await client.call_tool(
                "recall_save_project",
                {"name": "Valid Name", "project_id": "not-a-uuid"},
            )
            invalid_project_name = await client.call_tool(
                "recall_save_project",
                {"name": "   "},
            )
            still_usable = await client.call_tool(
                "recall_search",
                {"query": "valid", "project_id": str(project_id)},
            )
            return (
                invalid_compact,
                invalid_instruction,
                failed_create,
                invalid_project_uuid,
                invalid_project_name,
                still_usable,
            )

    results = asyncio.run(call_tools())
    assert all(response.isError for response in results[:5])
    assert "max_active_memories" in results[0].content[0].text
    assert "project_id" in results[1].content[0].text
    assert "SQLite unavailable" in results[2].content[0].text
    assert "project_id" in results[3].content[0].text.lower()
    assert "name" in results[4].content[0].text.lower()
    assert not results[5].isError


def test_compaction_rejects_disabling_mandatory_lineage(manager, project_id):
    response = _protocol_call(
        create_server(manager),
        "recall_compact_memory",
        {"project_id": str(project_id), "preserve_lineage": False},
    )

    assert response.isError is True
    assert "preserve_lineage" in response.content[0].text
    assert "True" in response.content[0].text
    manager.compact.assert_not_called()


def test_compaction_protocol_rejects_invalid_project_and_session(
    manager, project_id
):
    manager.get_project.return_value = Result.ok(None)
    missing_project = _protocol_call(
        create_server(manager),
        "recall_compact_memory",
        {"project_id": str(project_id)},
    )

    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.get_session.return_value = Result.ok(Mock(project_id=uuid4()))
    foreign_session = _protocol_call(
        create_server(manager),
        "recall_compact_memory",
        {
            "project_id": str(project_id),
            "session_id": str(uuid4()),
        },
    )

    assert missing_project.isError is True
    assert "project" in missing_project.content[0].text.lower()
    assert foreign_session.isError is True
    assert "does not belong" in foreign_session.content[0].text
    manager.compact.assert_not_called()


def test_prohibited_agent_operations_rejected_by_mcp_protocol(manager):
    server = create_server(manager)
    prohibited_tools = [
        "recall_update_context",
        "recall_list_custom_instructions",
        "recall_update_custom_instruction",
        "recall_delete_custom_instruction",
        "recall_compact",
        "recall_delete_memory",
        "recall_update_memory",
        "recall_delete_project",
        "recall_update_project",
    ]

    async def call_prohibited():
        async with create_connected_server_and_client_session(server) as client:
            responses = []
            for tool_name in prohibited_tools:
                resp = await client.call_tool(tool_name, {})
                responses.append((tool_name, resp))
            return responses

    results = asyncio.run(call_prohibited())
    for tool_name, resp in results:
        assert resp.isError is True, f"Expected {tool_name} to be rejected"
        assert "not listed" in resp.content[0].text.lower() or "unknown" in resp.content[0].text.lower()


def test_recall_save_project_identity_preservation_and_validation(manager, project_id):
    server = create_server(manager)
    existing_project = Project(id=project_id, name="Canonical Name", description="Desc")

    # 1. Existing ID with same name returns existing project
    manager.get_project.return_value = Result.ok(existing_project)
    res_same = _protocol_call(
        server,
        "recall_save_project",
        {"name": "Canonical Name", "project_id": str(project_id)},
    )
    assert not res_same.isError
    assert res_same.structuredContent["project"]["id"] == str(project_id)
    assert res_same.structuredContent["project"]["name"] == "Canonical Name"

    # 2. Existing ID with conflicting name raises error and preserves identity
    res_conflict = _protocol_call(
        server,
        "recall_save_project",
        {"name": "Conflicting Name", "project_id": str(project_id)},
    )
    assert res_conflict.isError is True
    assert "conflict" in res_conflict.content[0].text.lower() or "canonical" in res_conflict.content[0].text.lower()

    # 3. Explicit ID provided, but name belongs to another project ID
    other_id = uuid4()
    manager.get_project.return_value = Result.ok(None)
    manager.get_project_by_name.return_value = Result.ok(
        Project(id=other_id, name="Existing Name")
    )
    res_name_taken = _protocol_call(
        server,
        "recall_save_project",
        {"name": "Existing Name", "project_id": str(project_id)},
    )
    assert res_name_taken.isError is True
    assert "already exists" in res_name_taken.content[0].text.lower()


def test_save_project_followed_by_save_memory_and_concurrency(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from database.config import DatabaseConfig
    from recall_core.bootstrap import create_memory_manager
    from tests.test_mcp_bootstrap import _TestSemanticIndex

    db_path = tmp_path / "mcp_project_test.sqlite3"
    core = create_memory_manager(
        DatabaseConfig.from_path(db_path),
        semantic_index=_TestSemanticIndex(),
    )
    server = create_server(core)

    # 1. Concurrent project creation with same name
    project_name = "Concurrent MCP Project"

    def run_save():
        return _call_tool(
            server,
            "recall_save_project",
            {"name": project_name, "description": "Concurrent test"},
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_save) for _ in range(5)]
        results = [f.result() for f in futures]

    project_ids = {r[1]["project"]["id"] for r in results}
    assert len(project_ids) == 1, "Concurrent creation must be idempotent and return identical project_id"
    created_project_id = project_ids.pop()

    # 2. Sequential duplicate call is also idempotent
    dup_res = _call_tool(
        server,
        "recall_save_project",
        {"name": project_name},
    )
    assert dup_res[1]["project"]["id"] == created_project_id

    # 3. Pipeline: recall_save_project followed by recall_save_memory
    mem_res = _call_tool(
        server,
        "recall_save_memory",
        {
            "project_id": created_project_id,
            "content": "First decision memory after project creation",
            "memory_type": "decision",
        },
    )
    assert mem_res[1]["memory"]["project_id"] == created_project_id
    assert mem_res[1]["memory"]["content"] == "First decision memory after project creation"

    # Verify memory is searchable via protocol
    search_res = _protocol_call(
        server,
        "recall_search",
        {"query": "decision", "project_id": created_project_id},
    )
    assert not search_res.isError
    assert len(search_res.structuredContent["memories"]) == 1
    assert search_res.structuredContent["memories"][0]["id"] == mem_res[1]["memory"]["id"]


def test_save_project_cross_process_concurrency(tmp_path):
    import sqlite3
    import subprocess
    import sys

    from database.config import DatabaseConfig
    from database.connection import initialize_database

    db_path = str(tmp_path / "cross_process_test.sqlite3")
    initialize_database(DatabaseConfig.from_path(db_path))
    project_name = "Cross-Process Normalized Project"

    worker_code = """
import sys
import asyncio
from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server

db_path = sys.argv[1]
name = sys.argv[2]

core = create_memory_manager(DatabaseConfig.from_path(db_path))
server = create_server(core)
try:
    res = asyncio.run(server.call_tool("recall_save_project", {"name": name}))
    project_id = res[1]["project"]["id"]
    print(f"PROJECT_ID:{project_id}")
finally:
    core.close()
"""

    names_variations = [
        project_name,
        f"  {project_name}  ",
        project_name.lower(),
        project_name.upper(),
    ]

    processes = []
    for var_name in names_variations:
        p = subprocess.Popen(
            [sys.executable, "-c", worker_code, db_path, var_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(p)

    outputs = []
    for p in processes:
        stdout, stderr = p.communicate(timeout=30)
        assert p.returncode == 0, f"Child process failed: {stderr}\nOutput: {stdout}"
        outputs.append(stdout)

    project_ids = set()
    for out in outputs:
        for line in out.strip().splitlines():
            if line.startswith("PROJECT_ID:"):
                project_ids.add(line.split(":", 1)[1].strip())

    assert len(project_ids) == 1, f"Expected 1 canonical project ID across all processes, got: {project_ids}"
    canonical_id = project_ids.pop()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, name FROM projects WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (project_name,))
        rows = cursor.fetchall()
        assert len(rows) == 1, f"Expected exactly 1 row in SQLite database, found: {rows}"
        assert rows[0][0] == canonical_id
    finally:
        conn.close()
