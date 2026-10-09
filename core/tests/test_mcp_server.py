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
        "recall_save_memory",
        "recall_update_context",
        "recall_compact",
        "recall_list_custom_instructions",
        "recall_create_custom_instruction",
        "recall_update_custom_instruction",
        "recall_delete_custom_instruction",
    }
    assert {
        "content",
        "project_id",
        "session_id",
        "memory_type",
        "provenance",
    } <= set(tools["recall_update_context"].parameters["properties"])
    assert {
        "instruction_id",
        "content",
        "status",
        "metadata",
    } <= set(tools["recall_update_custom_instruction"].parameters["properties"])
    assert (
        tools["recall_compact"].parameters["properties"]["preserve_lineage"]["const"]
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


def test_new_tools_delegate_with_existing_typed_requests(manager, project_id):
    instruction = CustomInstruction(
        scope=Scope.GLOBAL,
        content="Prefer explicit decisions.",
    )
    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.update_context.return_value = Result.ok(
        UpdateContextResult(memory_id=uuid4())
    )
    manager.compact.return_value = Result.ok(CompactResult(preserved_count=2))
    manager.list_instructions.return_value = Result.ok([instruction])
    manager.create_instruction.return_value = Result.ok(instruction)
    manager.update_instruction.return_value = Result.ok(instruction)
    manager.delete_instruction.return_value = Result.ok(True)
    server = create_server(manager)

    updated_context = _protocol_call(
        server,
        "recall_update_context",
        {"project_id": str(project_id), "content": "Use SQLite."},
    )
    compacted = _protocol_call(
        server,
        "recall_compact",
        {"project_id": str(project_id), "max_active_memories": 7},
    )
    listed = _protocol_call(
        server,
        "recall_list_custom_instructions",
        {"scope": "global", "status": "active", "limit": 20, "offset": 5},
    )
    created = _protocol_call(
        server,
        "recall_create_custom_instruction",
        {"scope": "project", "project_id": str(project_id), "content": "Use tests."},
    )
    instruction_id = uuid4()
    updated = _protocol_call(
        server,
        "recall_update_custom_instruction",
        {"instruction_id": str(instruction_id), "status": "inactive"},
    )
    deleted = _protocol_call(
        server,
        "recall_delete_custom_instruction",
        {"instruction_id": str(instruction_id)},
    )

    assert not updated_context.isError
    update_request = manager.update_context.call_args.args[0]
    assert update_request.project_id == project_id
    assert update_request.content == "Use SQLite."
    assert not compacted.isError
    compact_request = manager.compact.call_args.args[0]
    assert compact_request.project_id == project_id
    assert compact_request.max_active_memories == 7
    assert not listed.isError
    list_request = manager.list_instructions.call_args.args[0]
    assert list_request.scope is Scope.GLOBAL
    assert list_request.status is InstructionStatus.ACTIVE
    assert (list_request.limit, list_request.offset) == (20, 5)
    assert listed.structuredContent["count"] == 1
    assert not created.isError
    create_request = manager.create_instruction.call_args.args[0]
    assert create_request.scope is Scope.PROJECT
    assert create_request.project_id == project_id
    assert not updated.isError
    update_instruction_request = manager.update_instruction.call_args.args[1]
    assert update_instruction_request.status is InstructionStatus.INACTIVE
    assert manager.update_instruction.call_args.args[0] == instruction_id
    assert not deleted.isError
    assert deleted.structuredContent == {
        "instruction_id": str(instruction_id),
        "deleted": True,
    }


def test_new_tools_reject_invalid_inputs_and_failed_mutations(manager, project_id):
    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.create_instruction.return_value = Result.err("SQLite unavailable")
    manager.update_instruction.return_value = Result.ok(None)
    manager.delete_instruction.return_value = Result.ok(False)
    server = create_server(manager)

    async def call_tools():
        async with create_connected_server_and_client_session(server) as client:
            invalid_update = await client.call_tool(
                "recall_update_context",
                {"session_id": str(uuid4()), "content": "No project"},
            )
            invalid_compact = await client.call_tool(
                "recall_compact",
                {"project_id": str(project_id), "max_active_memories": 0},
            )
            invalid_instruction = await client.call_tool(
                "recall_create_custom_instruction",
                {"scope": "project", "content": "Missing project"},
            )
            invalid_status = await client.call_tool(
                "recall_list_custom_instructions",
                {"status": "unknown"},
            )
            failed_create = await client.call_tool(
                "recall_create_custom_instruction",
                {"content": "Valid text"},
            )
            missing_update = await client.call_tool(
                "recall_update_custom_instruction",
                {"instruction_id": str(uuid4()), "content": "Changed"},
            )
            missing_delete = await client.call_tool(
                "recall_delete_custom_instruction",
                {"instruction_id": str(uuid4())},
            )
            still_usable = await client.call_tool(
                "recall_search",
                {"query": "valid", "project_id": str(project_id)},
            )
            return (
                invalid_update,
                invalid_compact,
                invalid_instruction,
                invalid_status,
                failed_create,
                missing_update,
                missing_delete,
                still_usable,
            )

    results = asyncio.run(call_tools())
    assert all(response.isError for response in results[:7])
    assert "project_id" in results[0].content[0].text
    assert "max_active_memories" in results[1].content[0].text
    assert "project_id" in results[2].content[0].text
    assert "status" in results[3].content[0].text
    assert "SQLite unavailable" in results[4].content[0].text
    assert "not found" in results[5].content[0].text
    assert "not found" in results[6].content[0].text
    assert not results[7].isError


def test_compaction_rejects_disabling_mandatory_lineage(manager, project_id):
    response = _protocol_call(
        create_server(manager),
        "recall_compact",
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
        "recall_compact",
        {"project_id": str(project_id)},
    )

    manager.get_project.return_value = Result.ok(Mock(id=project_id))
    manager.get_session.return_value = Result.ok(Mock(project_id=uuid4()))
    foreign_session = _protocol_call(
        create_server(manager),
        "recall_compact",
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
