"""Integration tests for the default Core composition and MCP startup."""

from __future__ import annotations

import asyncio
import sqlite3
from uuid import UUID

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from contracts.base import MemoryStatus, Result
from contracts.base import Scope
from contracts.instruction import CustomInstructionCreateRequest, InstructionStatus
from contracts.memory import Memory, MemoryCreateRequest, MemorySearchParams
from contracts.project import ProjectCreateRequest
from contracts.retrieval import CompactRequest, RetrievalRequest
from core.recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig
from intelligence.conflict_adapters import CloudConflictAdapter, OllamaConflictAdapter
from recall_mcp import server as mcp_server


async def _call_tool(server: FastMCP, name: str, arguments: dict):
    async with create_connected_server_and_client_session(server) as client:
        return await client.call_tool(name, arguments)


async def _list_tools(server: FastMCP):
    async with create_connected_server_and_client_session(server) as client:
        return await client.list_tools()


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


def test_factory_configures_local_and_opt_in_cloud_conflict_adapters(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("RECALL_CONFLICT_CLOUD_PROVIDER", "gemini")
    monkeypatch.setenv("RECALL_CONFLICT_CLOUD_MODEL", "test-gemini-model")
    monkeypatch.setenv("RECALL_CONFLICT_CLOUD_API_KEY", "test-key")
    manager = create_memory_manager(
        DatabaseConfig.from_path(tmp_path / "conflicts.sqlite3"),
        semantic_index=_TestSemanticIndex(),
    )

    try:
        resolver = manager._conflict_service.resolver
        assert isinstance(resolver._llm_adapter, OllamaConflictAdapter)
        assert isinstance(resolver._cloud_adapter, CloudConflictAdapter)
        assert resolver._cloud_adapter.config.provider.value == "gemini"
        assert resolver._cloud_adapter.config.model == "test-gemini-model"
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
        other_project = manager.create_project(
            ProjectCreateRequest(name="Unrelated project")
        ).value
        instruction = manager.create_instruction(
            CustomInstructionCreateRequest(
                scope=Scope.PROJECT,
                project_id=project.id,
                content="Prefer SQLite for canonical storage.",
            )
        )
        assert instruction.success, instruction.error
        global_memory = manager.create_memory(
            MemoryCreateRequest(content="Global RECALL preference.")
        ).value
        unrelated_memory = manager.create_memory(
            MemoryCreateRequest(
                project_id=other_project.id,
                scope=Scope.PROJECT,
                content="Unrelated project memory.",
            )
        ).value

        server = mcp_server.create_server(manager)
        discovered = asyncio.run(_list_tools(server))
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
        assert {tool.name for tool in discovered.tools} == {
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
        context_memory_ids = {
            UUID(memory["id"])
            for memory in context.structuredContent["active_memories"]
        }
        assert global_memory.id in context_memory_ids
        assert unrelated_memory.id not in context_memory_ids

        update = asyncio.run(
            _call_tool(
                server,
                "recall_update_context",
                {
                    "project_id": str(project.id),
                    "content": "Use a transactional SQLite database.",
                },
            )
        )
        assert not update.isError
        updated_memory_id = UUID(update.structuredContent["memory_id"])
        assert manager.get_memory(updated_memory_id).value.metadata["explicit_update"]

        global_update = asyncio.run(
            _call_tool(
                server,
                "recall_update_context",
                {"content": "Global context is user-authored."},
            )
        )
        assert not global_update.isError
        global_updated_memory = manager.get_memory(
            UUID(global_update.structuredContent["memory_id"])
        )
        assert global_updated_memory.value.scope is Scope.GLOBAL

        compact = asyncio.run(
            _call_tool(
                server,
                "recall_compact",
                {
                    "project_id": str(project.id),
                    "max_active_memories": 1,
                },
            )
        )
        assert not compact.isError
        assert compact.structuredContent["compacted_count"] >= 1

        instruction_list = asyncio.run(
            _call_tool(
                server,
                "recall_list_custom_instructions",
                {"scope": "project", "project_id": str(project.id)},
            )
        )
        assert not instruction_list.isError
        assert instruction_list.structuredContent["count"] == 1
        assert (
            instruction_list.structuredContent["instructions"][0]["id"]
            == str(instruction.value.id)
        )

        created_instruction = asyncio.run(
            _call_tool(
                server,
                "recall_create_custom_instruction",
                {"content": "Prefer focused integration tests."},
            )
        )
        assert not created_instruction.isError
        global_instruction_id = created_instruction.structuredContent[
            "instruction"
        ]["id"]
        updated_instruction = asyncio.run(
            _call_tool(
                server,
                "recall_update_custom_instruction",
                {
                    "instruction_id": global_instruction_id,
                    "content": "Prefer isolated integration tests.",
                    "status": "inactive",
                },
            )
        )
        assert not updated_instruction.isError
        assert (
            updated_instruction.structuredContent["instruction"]["status"]
            == InstructionStatus.INACTIVE.value
        )
        deleted_instruction = asyncio.run(
            _call_tool(
                server,
                "recall_delete_custom_instruction",
                {"instruction_id": global_instruction_id},
            )
        )
        assert not deleted_instruction.isError
        assert deleted_instruction.structuredContent["deleted"] is True
        assert capsys.readouterr().out == ""
    finally:
        manager.close()


def test_compaction_persists_aggregate_summary_and_lineage_through_mcp(
    tmp_path,
):
    database_config = DatabaseConfig.from_path(tmp_path / "compact.sqlite3")
    manager = create_memory_manager(
        database_config,
        semantic_index=_TestSemanticIndex(),
    )
    connection = manager._uow._db_connection
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="Compaction persistence")
        ).value
        originals = [
            manager.create_memory(
                MemoryCreateRequest(
                    project_id=project.id,
                    scope=Scope.PROJECT,
                    content=f"source-{index} unique compaction evidence",
                )
            ).value
            for index in range(3)
        ]
        server = mcp_server.create_server(manager)

        response = asyncio.run(
            _call_tool(
                server,
                "recall_compact",
                {"project_id": str(project.id), "max_active_memories": 2},
            )
        )
        assert not response.isError
        assert response.structuredContent["compacted_count"] == 2
        assert response.structuredContent["superseded_count"] == 2
        assert response.structuredContent["preserved_count"] == 2

        active = manager._uow.memories.search(
            MemorySearchParams(
                project_id=project.id,
                status=MemoryStatus.ACTIVE,
                limit=100,
            )
        ).value.items
        assert len(active) == 2
        summary = next(memory for memory in active if memory.memory_type == "compaction_summary")
        assert all(f"source-{index} unique compaction evidence" in summary.content for index in range(2))
        assert set(summary.metadata["original_ids"]) == {
            str(memory.id) for memory in originals[:2]
        }

        lineage = manager._uow.memories.get_lineage(summary.id)
        assert lineage.success
        assert {
            (item.parent_id, item.child_id, item.relationship, item.reason)
            for item in lineage.value
        } == {
            (memory.id, summary.id, "supersedes", "compaction_summary")
            for memory in originals[:2]
        }
        for memory in originals[:2]:
            stored = manager.get_memory(memory.id).value
            assert stored.status is MemoryStatus.SUPERSEDED
            assert "compacted_at" in stored.metadata

        retrieval = manager.retrieve(
            RetrievalRequest(
                query="unique compaction evidence",
                project_id=project.id,
            )
        )
        assert retrieval.success
        assert summary.id in {memory.id for memory in retrieval.value.memories}

        second = manager.compact(
            CompactRequest(project_id=project.id, max_active_memories=2)
        )
        assert second.success
        assert second.value.compacted_count == 0
        assert second.value.preserved_count == 2
        assert len(manager._uow.memories.get_lineage(summary.id).value) == 2
    finally:
        manager.close()
    assert not connection.is_connected

    reopened = create_memory_manager(
        database_config,
        semantic_index=_TestSemanticIndex(),
    )
    try:
        rebuilt = reopened.rebuild_semantic_index()
        assert rebuilt.success
        stored_summary = reopened.get_memory(summary.id)
        assert stored_summary.success
        assert stored_summary.value.status is MemoryStatus.ACTIVE
        persisted_lineage = reopened._uow.memories.get_lineage(summary.id)
        assert persisted_lineage.success
        assert len(persisted_lineage.value) == 2
        retrieved = reopened.retrieve(
            RetrievalRequest(
                query="unique compaction evidence",
                project_id=project.id,
            )
        )
        assert retrieved.success
        assert summary.id in {memory.id for memory in retrieved.value.memories}
    finally:
        reopened.close()


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
