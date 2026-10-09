"""Tests for the RECALL dashboard HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from contracts.base import Result, Scope
from contracts.memory import Memory, MemoryStatus
from core.recall_core.api import create_app


class FakeSemanticIndex:
    def health_check(self):
        return Result.ok({"status": "healthy", "available": True})


class FakeMemoryManager:
    def __init__(self):
        self._semantic_index = FakeSemanticIndex()
        self._uow = type(
            "UOW",
            (),
            {
                "memories": type(
                    "MemoriesRepo",
                    (),
                    {
                        "search": lambda self, params: Result.ok(type("Page", (), {"items": [], "total": 0})()),
                    },
                )(),
                "sessions": type(
                    "SessionsRepo",
                    (),
                    {
                        "list": lambda self, params, project_id=None: Result.ok(type("Page", (), {"items": [], "total": 0})()),
                    },
                )(),
                "custom_instructions": type(
                    "InstructionsRepo",
                    (),
                    {"list": lambda self, params: Result.ok(type("Page", (), {"items": [], "total": 0})())},
                )(),
            },
        )()

    def get_project(self, project_id):
        return Result.ok(type("Project", (), {"name": "Demo Project"})())

    def list_projects(self, limit=50, offset=0):
        return Result.ok([])

    def get_stats(self):
        return Result.ok({
            "projects": 1,
            "sessions": 0,
            "memories": {"active": 1, "superseded": 0, "archived": 0, "deleted": 0},
            "custom_instructions": {"active": 0, "inactive": 0},
            "semantic_index": {"status": "healthy", "available": True},
        })

    def search_memories(self, params):
        project_id = uuid4()
        memory = Memory(
            id=uuid4(),
            project_id=project_id,
            scope=Scope.PROJECT,
            memory_type="fact",
            content="Project uses SQLite as the canonical store.",
            status=MemoryStatus.ACTIVE,
            provenance="api_test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return Result.ok([memory])

    def search_memories_paginated(self, params):
        from contracts.base import PaginatedResult
        if params.status == MemoryStatus.DELETED:
            return Result.ok(PaginatedResult(items=[], total=0, limit=params.limit, offset=params.offset))
        memories = self.search_memories(params).value
        return Result.ok(PaginatedResult(items=memories, total=len(memories), limit=params.limit, offset=params.offset))

    def get_memory(self, memory_id):
        return Result.ok(
            Memory(
                id=memory_id,
                project_id=uuid4(),
                scope=Scope.PROJECT,
                memory_type="fact",
                content="Retrieved fact",
                status=MemoryStatus.ACTIVE,
                provenance="api_test",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    def create_memory(self, request):
        memory = Memory(
            id=uuid4(),
            project_id=request.project_id,
            session_id=request.session_id,
            scope=request.scope,
            memory_type=request.memory_type,
            content=request.content,
            status=MemoryStatus.ACTIVE,
            provenance=request.provenance,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return Result.ok(memory)

    def update_memory(self, memory_id, request):
        return Result.ok(
            Memory(
                id=memory_id,
                project_id=uuid4(),
                scope=Scope.PROJECT,
                memory_type="fact",
                content=request.content or "Updated fact",
                status=request.status or MemoryStatus.ACTIVE,
                provenance="api_test",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    def delete_memory(self, memory_id):
        return Result.ok(True)

    def list_instructions(self, params):
        return Result.ok([])

    def create_instruction(self, request):
        return Result.ok(type("Instruction", (), {"id": uuid4(), "scope": request.scope, "project_id": request.project_id, "content": request.content, "status": "active", "version": 1, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc), "is_active": lambda self: True})())

    def update_instruction(self, instruction_id, request):
        return Result.ok(type("Instruction", (), {"id": instruction_id, "scope": Scope.GLOBAL, "project_id": None, "content": request.content or "Updated instruction", "status": "active", "version": 1, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc), "is_active": lambda self: True})())

    def delete_instruction(self, instruction_id):
        return Result.ok(True)

    def detect_and_resolve_conflicts(self, candidates, instructions, project_id=None, session_id=None):
        return Result.ok(type("ConflictResolutionResult", (), {"status": "unresolved", "preferred_candidates": [], "superseded_candidates": [], "unresolved_candidates": candidates, "resolution_reason": "No conflict detected", "model_used": False, "decisions": []})())

    def retrieve(self, request):
        return Result.ok(type("RetrievalResult", (), {"memories": [], "total_found": 0, "query": request.query, "project_id": request.project_id})())

    def compact(self, request):
        return Result.ok(type("CompactResult", (), {"compacted_count": 0})())


def test_health_and_projects_routes():
    client = TestClient(create_app(FakeMemoryManager()))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] in {"healthy", "degraded"}

    projects = client.get("/projects")
    assert projects.status_code == 200
    assert "projects" in projects.json()


def test_memories_and_custom_instruction_routes():
    client = TestClient(create_app(FakeMemoryManager()))

    memories = client.get("/memories")
    assert memories.status_code == 200
    payload = memories.json()
    assert payload["memories"]
    assert payload["total"] >= 1

    create = client.post("/memories", json={"project_id": str(uuid4()), "content": "My memory", "memory_type": "fact"})
    assert create.status_code == 200
    assert create.json()["content"] == "My memory"

    instructions = client.get("/custom-instructions")
    assert instructions.status_code == 200
    assert "instructions" in instructions.json()

    delete_instr = client.delete(f"/custom-instructions/{uuid4()}")
    assert delete_instr.status_code == 204


def test_context_query_route():
    client = TestClient(create_app(FakeMemoryManager()))

    response = client.post("/context/query", json={"query": "sqlite", "project_id": str(uuid4())})
    assert response.status_code == 200
    body = response.json()
    assert "response" in body
    assert "supporting_memories" in body


def test_cors_headers_allow_dashboard_origin():
    client = TestClient(create_app(FakeMemoryManager()))
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in {"http://localhost:5173", "*"}


def test_real_sqlite_memory_lifecycle_and_restart_persistence(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # 1. Health check
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database_connected"] is True

        # 2. Create memory with explicit content
        test_content = "RECALL_TEMP_PERSISTENCE_TEST_abc123"
        payload = {
            "content": test_content,
            "scope": "global",
            "memory_type": "fact",
            "metadata": {"source": "integration_test", "importance": 80},
        }
        create_resp = client.post("/memories", json=payload)
        assert create_resp.status_code == 200, create_resp.text
        created = create_resp.json()
        memory_id = created["memory_id"]
        assert created["content"] == test_content
        assert created["status"] == "active"
        assert created["importance"] == 80

        # 3. Retrieve memory
        get_resp = client.get(f"/memories/{memory_id}")
        assert get_resp.status_code == 200
        retrieved = get_resp.json()
        assert retrieved["memory_id"] == memory_id
        assert retrieved["content"] == test_content
        assert retrieved["status"] == "active"

        # 4. Restart persistence verification (simulate process restart)
        manager.close()

        restarted_manager = create_memory_manager(config)
        restarted_app = create_app(restarted_manager)
        restarted_client = TestClient(restarted_app)

        try:
            persisted_resp = restarted_client.get(f"/memories/{memory_id}")
            assert persisted_resp.status_code == 200
            persisted = persisted_resp.json()
            assert persisted["memory_id"] == memory_id
            assert persisted["content"] == test_content

            # 5. Deletion
            del_resp = restarted_client.delete(f"/memories/{memory_id}")
            assert del_resp.status_code == 204

            # 6. Verify deleted record returns 404 on direct fetch
            after_del_resp = restarted_client.get(f"/memories/{memory_id}")
            assert after_del_resp.status_code == 404

            # 7. Normal list (active only) must hide the deleted memory
            active_list = restarted_client.get("/memories")
            assert active_list.status_code == 200
            assert all(m["memory_id"] != memory_id for m in active_list.json()["memories"])

            # 8. Deleted list must include the deleted memory
            deleted_list = restarted_client.get("/memories?status=deleted")
            assert deleted_list.status_code == 200
            assert any(m["memory_id"] == memory_id for m in deleted_list.json()["memories"])

            # 9. Delete nonexistent UUID returns 404
            nonexistent_del_resp = restarted_client.delete(f"/memories/{uuid4()}")
            assert nonexistent_del_resp.status_code == 404
        finally:
            restarted_manager.close()
    finally:
        pass


def test_real_sqlite_endpoints_and_error_handling(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # Valid but nonexistent UUID -> 404
        random_uuid = str(uuid4())
        resp = client.get(f"/memories/{random_uuid}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Memory not found"

        # Malformed UUID in path -> 400
        resp = client.get("/memories/not-a-valid-uuid")
        assert resp.status_code == 400
        assert "Invalid memory_id" in resp.json()["detail"]

        # Malformed body -> 422
        resp = client.post("/memories", content="{invalid_json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

        # Projects, Sessions, Custom Instructions endpoints return 200
        proj_resp = client.get("/projects")
        assert proj_resp.status_code == 200
        assert "projects" in proj_resp.json()

        sess_resp = client.get("/sessions")
        assert sess_resp.status_code == 200
        assert "sessions" in sess_resp.json()

        instr_resp = client.get("/custom-instructions")
        assert instr_resp.status_code == 200
        assert "instructions" in instr_resp.json()

        # Create custom instruction works
        create_instr = client.post("/custom-instructions", json={"content": "Always prefer concise answers", "scope": "global"})
        assert create_instr.status_code == 200
        assert create_instr.json()["content"] == "Always prefer concise answers"
    finally:
        manager.close()


def test_real_sqlite_concurrent_requests_thread_safety(tmp_path):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        def worker(thread_idx: int):
            results = []
            for i in range(10):
                content = f"Concurrent test {thread_idx}_{i}"
                res = client.post("/memories", json={"content": content, "scope": "global"})
                assert res.status_code == 200, res.text
                mem_id = res.json()["memory_id"]

                get_res = client.get(f"/memories/{mem_id}")
                assert get_res.status_code == 200, get_res.text
                assert get_res.json()["content"] == content
                results.append(mem_id)
            return results

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            all_created_ids = []
            for f in as_completed(futures):
                all_created_ids.extend(f.result())

        assert len(all_created_ids) == 50

        # Check total count
        list_res = client.get("/memories?page_size=100")
        assert list_res.status_code == 200
        assert list_res.json()["total"] == 50
    finally:
        manager.close()


def test_real_sqlite_memories_filtering_and_pagination(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # Initially empty
        empty_res = client.get("/memories")
        assert empty_res.status_code == 200
        assert empty_res.json()["memories"] == []
        assert empty_res.json()["total"] == 0

        # Create 5 active memories
        created_ids = []
        for i in range(5):
            res = client.post("/memories", json={"content": f"Active memory #{i}", "scope": "global"})
            assert res.status_code == 200
            created_ids.append(res.json()["memory_id"])

        # Soft-delete 2 of them
        client.delete(f"/memories/{created_ids[0]}")
        client.delete(f"/memories/{created_ids[1]}")

        # Default GET /memories returns only 3 active memories
        default_res = client.get("/memories")
        assert default_res.status_code == 200
        active_items = default_res.json()["memories"]
        assert len(active_items) == 3
        assert default_res.json()["total"] == 3
        assert all(m["status"] == "active" for m in active_items)

        # GET /memories?status=deleted returns 2 deleted memories
        deleted_res = client.get("/memories?status=deleted")
        assert deleted_res.status_code == 200
        deleted_items = deleted_res.json()["memories"]
        assert len(deleted_items) == 2
        assert deleted_res.json()["total"] == 2
        assert all(m["status"] == "deleted" for m in deleted_items)

        # GET /memories?status=all returns 3 non-deleted memories
        all_res = client.get("/memories?status=all")
        assert all_res.status_code == 200
        assert all_res.json()["total"] == 3

        # Pagination: page_size=2 should return 2 items on page 1, with total=3
        paged_res = client.get("/memories?page=1&page_size=2")
        assert paged_res.status_code == 200
        assert len(paged_res.json()["memories"]) == 2
        assert paged_res.json()["total"] == 3

        # Page 2 should return 1 item with total=3
        paged_res2 = client.get("/memories?page=2&page_size=2")
        assert paged_res2.status_code == 200
        assert len(paged_res2.json()["memories"]) == 1
        assert paged_res2.json()["total"] == 3

        # Stats returns correct memory counts
        stats_res = client.get("/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["active_memories"] == 3
        assert stats["total_memories"] == 5  # 3 active + 2 deleted
    finally:
        manager.close()

