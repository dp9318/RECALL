"""Tests for the RECALL MCP adapter and tool protocol."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session
import pytest

from contracts.base import Result, Scope
from contracts.memory import Memory
from contracts.retrieval import AssembledContext, RetrievalResult
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
        "recall_save_memory",
    }


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
    manager.retrieve.assert_not_called()


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
    assert request.provenance == "user_explicit"
    assert result[1]["memory"]["provenance"] == "user_explicit"


def test_save_does_not_report_success_when_core_fails(manager, project_id):
    manager.create_memory.return_value = Result.err("SQLite unavailable")

    with pytest.raises(ToolError, match="SQLite unavailable"):
        _call_tool(
            create_server(manager),
            "recall_save_memory",
            {"content": "Persisted decision", "project_id": str(project_id)},
        )
