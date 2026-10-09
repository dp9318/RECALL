"""Regression tests for MCP and context-update validation."""

from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from contracts.base import Result, Scope
from contracts.memory import Memory
from contracts.retrieval import AssembledContext, RetrievalResult, UpdateContextRequest
from core.recall_core.memory_manager import MemoryManager
from recall_mcp.server import create_server


def test_direct_tool_calls_reject_invalid_runtime_values():
    project_id = uuid4()
    manager = Mock()
    manager.get_session.return_value = Result.ok(Mock(project_id=project_id))
    manager.retrieve.return_value = Result.ok(RetrievalResult(query="sqlite"))
    manager.assemble_context.return_value = Result.ok(
        AssembledContext(assembled_at="2024-01-01T00:00:00+00:00")
    )
    manager.create_memory.return_value = Result.ok(
        Memory(
            project_id=project_id,
            scope=Scope.PROJECT,
            content="Persisted decision",
            provenance="user_explicit",
        )
    )

    server = create_server(manager)
    search_tool = next(
        tool.fn for tool in server._tool_manager.list_tools() if tool.name == "recall_search"
    )

    with pytest.raises(ToolError, match="query is required"):
        search_tool(query=None, project_id=str(project_id))
    with pytest.raises(ToolError, match="project_id must be a valid UUID"):
        search_tool(query="valid", project_id=123)
    with pytest.raises(ToolError, match="session_id must be a valid UUID"):
        search_tool(query="valid", project_id=str(project_id), session_id=True)


def test_update_context_keeps_scope_enum(
    mock_uow,
    mock_retrieval_service,
    mock_conflict_service,
    mock_semantic_index,
    sample_project,
):
    manager = MemoryManager(
        unit_of_work=mock_uow,
        retrieval_service=mock_retrieval_service,
        conflict_service=mock_conflict_service,
        semantic_index=mock_semantic_index,
    )
    memory = Memory(
        id=uuid4(),
        project_id=sample_project.id,
        scope=Scope.PROJECT,
        content="Explicit update",
    )
    mock_uow.memories.create.return_value = Result.ok(memory)
    mock_semantic_index.index_memory.return_value = Result.ok(True)

    result = manager.update_context(UpdateContextRequest(project_id=sample_project.id, content="Explicit update"))

    assert result.success
    created = mock_uow.memories.create.call_args.args[0]
    assert created.scope is Scope.PROJECT
    assert created.memory_type == "context_update"
