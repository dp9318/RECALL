"""Integration tests for the default Core composition and MCP startup."""

from __future__ import annotations

import asyncio
import sqlite3
from uuid import UUID

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from contracts.base import Result
from contracts.base import Scope
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import Memory
from contracts.project import ProjectCreateRequest
from core.recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig
from recall_mcp import server as mcp_server


async def _call_tool(server: FastMCP, name: str, arguments: dict):
    async with create_connected_server_and_client_session(server) as client:
        return await client.call_tool(name, arguments)


class _TestSemanticIndex:
    def __init__(self):
        self.memories: dict[UUID, Memory] = {}

    def index_memory(self, memory):
        self.memories[memory.id] = memory
        return Result.ok(True)

    update_memory = index_memory

    def remove_memory(self, memory_id):
        self.memories.pop(memory_id, None)
        return Result.ok(True)

    def search_similar(self, query, project_id, limit):
        tokens = set(query.lower().split())
        matches = [
            (memory.id, 1.0)
            for memory in self.memories.values()
            if (memory.project_id == project_id or memory.project_id is None)
            and tokens.intersection(memory.content.lower().split())
        ]
        return Result.ok(matches[:limit])

    def rebuild_from_canonical(self, memories):
        self.memories = {memory.id: memory for memory in memories}
        return Result.ok(len(memories))

    def health_check(self):
        return Result.ok({"status": "healthy"})


def test_default_factory_initializes_and_closes_user_database(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    manager = create_memory_manager()
    database_path = tmp_path / ".recall" / "recall.sqlite3"
    connection = manager._uow._db_connection

    try:
        assert database_path.is_file()
        assert connection.is_connected
        with sqlite3.connect(database_path) as database:
            assert database.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()[0] == 2
    finally:
        manager.close()

    assert not connection.is_connected


def test_factory_accepts_explicit_database_config(tmp_path):
    config = DatabaseConfig.from_path(tmp_path / "custom" / "recall.sqlite3")

    manager = create_memory_manager(config, semantic_index=_TestSemanticIndex())
    try:
        assert config.path.is_file()
        assert manager.get_stats().success
    finally:
        manager.close()


def test_mcp_protocol_uses_composed_services_for_save_search_and_context(
    tmp_path, capsys
):
    manager = create_memory_manager(
        DatabaseConfig.from_path(tmp_path / "recall.sqlite3"),
        semantic_index=_TestSemanticIndex(),
    )
    try:
        project = manager.create_project(ProjectCreateRequest(name="MCP integration")).value
        instruction = manager.create_instruction(
            CustomInstructionCreateRequest(
                scope=Scope.PROJECT,
                project_id=project.id,
                content="Prefer SQLite for canonical storage.",
            )
        )
        assert instruction.success, instruction.error

        server = mcp_server.create_server(manager)
        saved = asyncio.run(
            _call_tool(
                server,
                "recall_save_memory",
                {
                    "project_id": str(project.id),
                    "content": "SQLite stores canonical RECALL memories.",
                },
            )
        )
        assert not saved.isError
        memory_id = UUID(saved.structuredContent["memory"]["id"])

        search = asyncio.run(
            _call_tool(
                server,
                "recall_search",
                {
                    "project_id": str(project.id),
                    "query": "canonical RECALL memories",
                },
            )
        )
        assert not search.isError
        assert memory_id in {
            UUID(memory["id"]) for memory in search.structuredContent["memories"]
        }

        context = asyncio.run(
            _call_tool(
                server,
                "recall_get_context",
                {"project_id": str(project.id), "query": "canonical"},
            )
        )
        assert not context.isError
        assert context.structuredContent["custom_instructions"][0]["id"] == str(
            instruction.value.id
        )
        assert memory_id in {
            UUID(memory["id"]) for memory in context.structuredContent["active_memories"]
        }
        assert capsys.readouterr().out == ""
    finally:
        manager.close()


def test_main_uses_default_composition_and_closes_manager(
    tmp_path, monkeypatch, capsys
):
    manager = create_memory_manager(DatabaseConfig.from_path(tmp_path / "recall.sqlite3"))
    connection = manager._uow._db_connection
    transports = []

    def run(server, transport):
        transports.append(transport)

    monkeypatch.delenv("RECALL_CORE_FACTORY", raising=False)
    monkeypatch.setattr(mcp_server, "create_memory_manager", lambda: manager)
    monkeypatch.setattr(FastMCP, "run", run)

    mcp_server.main()

    assert transports == ["stdio"]
    assert not connection.is_connected
    assert capsys.readouterr().out == ""


def test_main_preserves_application_factory_override(tmp_path, monkeypatch):
    manager = create_memory_manager(DatabaseConfig.from_path(tmp_path / "custom.sqlite3"))
    connection = manager._uow._db_connection
    transports = []

    def run(server, transport):
        transports.append(transport)

    monkeypatch.setenv(
        "RECALL_CORE_FACTORY",
        "core.recall_core.bootstrap:create_memory_manager",
    )
    monkeypatch.setattr(
        "core.recall_core.bootstrap.create_memory_manager",
        lambda: manager,
    )
    monkeypatch.setattr(FastMCP, "run", run)

    mcp_server.main()

    assert transports == ["stdio"]
    assert not connection.is_connected


def test_main_reports_invalid_default_database_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("RECALL_CORE_FACTORY", raising=False)
    monkeypatch.setattr(
        mcp_server,
        "create_memory_manager",
        lambda: create_memory_manager(
            DatabaseConfig.from_path(tmp_path / "recall.sqlite3", timeout=0)
        ),
    )

    with pytest.raises(
        SystemExit,
        match="default Core composition: timeout must be positive",
    ):
        mcp_server.main()


def test_main_closes_manager_when_server_stops_with_error(
    tmp_path, monkeypatch
):
    manager = create_memory_manager(DatabaseConfig.from_path(tmp_path / "recall.sqlite3"))
    connection = manager._uow._db_connection

    def run(server, transport):
        raise RuntimeError("transport stopped")

    monkeypatch.delenv("RECALL_CORE_FACTORY", raising=False)
    monkeypatch.setattr(mcp_server, "create_memory_manager", lambda: manager)
    monkeypatch.setattr(FastMCP, "run", run)

    with pytest.raises(RuntimeError, match="transport stopped"):
        mcp_server.main()

    assert not connection.is_connected
