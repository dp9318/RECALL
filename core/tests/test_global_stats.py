from __future__ import annotations

from contracts.base import Result, Scope
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest
from core.recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig


class HealthySemanticIndex:
    def index_memory(self, memory):
        return Result.ok(True)

    def health_check(self):
        return Result.ok({"status": "healthy", "available": True})


def test_global_stats_count_project_memories(tmp_path):
    manager = create_memory_manager(
        DatabaseConfig.from_path(tmp_path / "stats.sqlite3"),
        semantic_index=HealthySemanticIndex(),
    )
    try:
        project = manager.create_project(ProjectCreateRequest(name="Stats test"))
        assert project.success and project.value is not None

        created = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.value.id,
                scope=Scope.PROJECT,
                content="Global dashboard stats must include this memory.",
            )
        )
        assert created.success

        stats = manager.get_stats()
        assert stats.success
        assert stats.value["projects"] == 1
        assert stats.value["memories"]["active"] == 1
    finally:
        manager.close()
