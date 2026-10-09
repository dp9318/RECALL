"""Tests for the RECALL dashboard HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

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
                "projects": type(
                    "ProjectsRepo",
                    (),
                    {
                        "list": lambda self, params: Result.ok(type("Page", (), {"items": [], "total": 0})()),
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

    def create_project(self, request):
        return Result.ok(type("Project", (), {
            "id": uuid4(),
            "name": request.name,
            "description": request.description,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })())

    def get_session(self, session_id):
        return Result.ok(None)

    def create_session(self, request):
        from contracts.project import Session
        return Result.ok(Session(
            id=request.id or uuid4(),
            project_id=request.project_id,
            started_at=datetime.now(timezone.utc),
            metadata=request.metadata,
        ))

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


def test_real_sqlite_project_creation_and_listing(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager
    from contracts.project import SessionCreateRequest

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # 1. Validation: Empty or whitespace project name returns 400
        bad_resp1 = client.post("/projects", json={"name": ""})
        assert bad_resp1.status_code == 400
        assert "Project name is required" in bad_resp1.json()["detail"]

        bad_resp2 = client.post("/projects", json={"name": "   "})
        assert bad_resp2.status_code == 400
        assert "Project name is required" in bad_resp2.json()["detail"]

        bad_resp3 = client.post("/projects", json={})
        assert bad_resp3.status_code == 400
        assert "Project name is required" in bad_resp3.json()["detail"]

        # 2. Successful creation
        create_resp = client.post("/projects", json={
            "name": "  Apollo Project  ",
            "description": "Space mission project"
        })
        assert create_resp.status_code == 200
        project_data = create_resp.json()
        assert project_data["name"] == "Apollo Project"
        assert project_data["description"] == "Space mission project"
        assert project_data["project_id"]
        assert project_data["memory_count"] == 0
        assert project_data["session_count"] == 0
        project_id = project_data["project_id"]

        # 3. List projects verifies total and returned fields
        list_resp = client.get("/projects")
        assert list_resp.status_code == 200
        list_body = list_resp.json()
        assert list_body["total"] == 1
        assert len(list_body["projects"]) == 1
        assert list_body["projects"][0]["project_id"] == project_id
        assert list_body["projects"][0]["name"] == "Apollo Project"

        # 4. Persistence across reopen / restart
        manager.close()
        restarted_manager = create_memory_manager(config)
        restarted_app = create_app(restarted_manager)
        restarted_client = TestClient(restarted_app)

        try:
            persisted_list = restarted_client.get("/projects")
            assert persisted_list.status_code == 200
            assert persisted_list.json()["total"] == 1
            assert persisted_list.json()["projects"][0]["project_id"] == project_id

            # 5. Live memory and session counts
            mem_resp = restarted_client.post("/memories", json={
                "project_id": project_id,
                "content": "Lunar landing coordinates",
                "scope": "project",
            })
            assert mem_resp.status_code == 200

            sess_result = restarted_manager.create_session(SessionCreateRequest(project_id=UUID(project_id)))
            assert sess_result.success

            updated_list = restarted_client.get("/projects")
            assert updated_list.status_code == 200
            proj = updated_list.json()["projects"][0]
            assert proj["memory_count"] == 1
            assert proj["session_count"] == 1

            sessions_resp = restarted_client.get("/sessions")
            assert sessions_resp.status_code == 200
            sess_body = sessions_resp.json()
            assert sess_body["total"] == 1
            assert sess_body["sessions"][0]["project_name"] == "Apollo Project"
            assert sess_body["sessions"][0]["project_id"] == project_id
        finally:
            restarted_manager.close()
    finally:
        pass


def test_real_sqlite_memory_editing_and_metadata_preservation(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # 1. Create a memory with importance, tags, and unrelated custom metadata
        create_resp = client.post("/memories", json={
            "content": "Initial memory content",
            "scope": "global",
            "memory_type": "decision",
            "provenance": "developer_audit",
            "metadata": {
                "importance": 70,
                "tags": ["frontend", "v1"],
                "unrelated_custom_field": "custom_value_123",
                "nested_info": {"author": "alice", "reviewed": True},
            },
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        memory_id = created["memory_id"]
        created_at = created["created_at"]
        assert created["content"] == "Initial memory content"
        assert created["importance"] == 70
        assert created["tags"] == ["frontend", "v1"]
        assert created["provenance"] == "developer_audit"

        stored_mem = manager._uow.memories.get(UUID(memory_id)).value
        assert stored_mem.metadata["unrelated_custom_field"] == "custom_value_123"
        assert stored_mem.metadata["nested_info"] == {"author": "alice", "reviewed": True}

        # 2. Case A: Update content only, omitting metadata
        # Existing metadata (importance, tags, unrelated keys) MUST remain unchanged
        update_resp_1 = client.patch(f"/memories/{memory_id}", json={
            "content": "Updated content only",
        })
        assert update_resp_1.status_code == 200
        updated_1 = update_resp_1.json()
        assert updated_1["content"] == "Updated content only"
        assert updated_1["memory_id"] == memory_id
        assert updated_1["created_at"] == created_at
        assert updated_1["importance"] == 70
        assert updated_1["tags"] == ["frontend", "v1"]
        assert updated_1["provenance"] == "developer_audit"

        stored_mem = manager._uow.memories.get(UUID(memory_id)).value
        assert stored_mem.metadata["unrelated_custom_field"] == "custom_value_123"
        assert stored_mem.metadata["nested_info"] == {"author": "alice", "reviewed": True}
        assert stored_mem.metadata["importance"] == 70
        assert stored_mem.metadata["tags"] == ["frontend", "v1"]

        # 3. Case B: Update importance and tags via top-level fields
        # Unrelated metadata keys MUST NOT be dropped
        update_resp_2 = client.patch(f"/memories/{memory_id}", json={
            "importance": 95,
            "tags": ["v2", "release"],
        })
        assert update_resp_2.status_code == 200
        updated_2 = update_resp_2.json()
        assert updated_2["importance"] == 95
        assert updated_2["tags"] == ["v2", "release"]
        assert updated_2["content"] == "Updated content only"

        stored_mem = manager._uow.memories.get(UUID(memory_id)).value
        assert stored_mem.metadata["unrelated_custom_field"] == "custom_value_123"
        assert stored_mem.metadata["nested_info"] == {"author": "alice", "reviewed": True}
        assert stored_mem.metadata["importance"] == 95
        assert stored_mem.metadata["tags"] == ["v2", "release"]

        # 4. Case C: Verify persistence after reopening database
        manager.close()
        restarted_manager = create_memory_manager(config)
        restarted_app = create_app(restarted_manager)
        restarted_client = TestClient(restarted_app)

        try:
            get_resp = restarted_client.get(f"/memories/{memory_id}")
            assert get_resp.status_code == 200
            reopened = get_resp.json()
            assert reopened["content"] == "Updated content only"
            assert reopened["importance"] == 95
            assert reopened["tags"] == ["v2", "release"]
            assert reopened["created_at"] == created_at

            reopened_mem = restarted_manager._uow.memories.get(UUID(memory_id)).value
            assert reopened_mem.metadata["unrelated_custom_field"] == "custom_value_123"

            # 5. Case D: Error cases and validation
            assert restarted_client.patch(f"/memories/{uuid4()}", json={"content": "new"}).status_code == 404

            bad_content = restarted_client.patch(f"/memories/{memory_id}", json={"content": "   "})
            assert bad_content.status_code == 400
            assert "Content cannot be empty" in bad_content.json()["detail"]

            bad_status = restarted_client.patch(f"/memories/{memory_id}", json={"status": "invalid_status"})
            assert bad_status.status_code == 400

            bad_imp = restarted_client.patch(f"/memories/{memory_id}", json={"importance": "not_a_number"})
            assert bad_imp.status_code == 400

            bad_tags = restarted_client.patch(f"/memories/{memory_id}", json={"tags": "not_a_list"})
            assert bad_tags.status_code == 400

            # Soft-delete the memory
            del_resp = restarted_client.delete(f"/memories/{memory_id}")
            assert del_resp.status_code == 204

            # Attempting to edit a deleted memory must return 404
            after_del_patch = restarted_client.patch(f"/memories/{memory_id}", json={"content": "revive"})
            assert after_del_patch.status_code == 404
        finally:
            restarted_manager.close()
    finally:
        pass


def test_real_sqlite_overview_statistics_and_consistency(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # Empty system stats
        stats_0 = client.get("/stats").json()
        assert stats_0["total_memories"] == 0
        assert stats_0["active_memories"] == 0
        assert stats_0["total_projects"] == 0
        assert stats_0["total_sessions"] == 0
        assert stats_0["total_instructions"] == 0
        assert stats_0["unresolved_conflicts"] == 0

        # Create 1 project
        proj_res = client.post("/projects", json={"name": "Test Project"})
        assert proj_res.status_code == 200
        proj_id = proj_res.json()["project_id"]

        # Create 3 memories (2 active, 1 deleted)
        m1 = client.post("/memories", json={"content": "M1", "project_id": proj_id}).json()["memory_id"]
        m2 = client.post("/memories", json={"content": "M2", "project_id": proj_id}).json()["memory_id"]
        m3 = client.post("/memories", json={"content": "M3", "project_id": proj_id}).json()["memory_id"]
        client.delete(f"/memories/{m3}")

        # Create 2 custom instructions (1 active, 1 inactive)
        i1 = client.post("/custom-instructions", json={"content": "I1", "scope": "global", "active": True}).json()["instruction_id"]
        i2 = client.post("/custom-instructions", json={"content": "I2", "scope": "global", "active": False}).json()["instruction_id"]

        # Fetch stats
        stats = client.get("/stats").json()
        assert stats["total_projects"] == 1
        assert stats["total_memories"] == 3
        assert stats["active_memories"] == 2
        assert stats["total_instructions"] == 2
        assert stats["active_instructions"] == 1
        assert stats["unresolved_conflicts"] == 0

        # Verify consistency with endpoint paginations:
        projects_total = client.get("/projects").json()["total"]
        assert projects_total == stats["total_projects"]

        active_mem_total = client.get("/memories").json()["total"]
        assert active_mem_total == stats["active_memories"]

        instructions_total = client.get("/custom-instructions").json()["total"]
        assert instructions_total == stats["total_instructions"]
    finally:
        manager.close()


def test_real_sqlite_sessions_lifecycle_and_mcp_unification(tmp_path):
    import pytest
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager
    from recall_mcp.server import create_server
    from mcp.server.fastmcp.exceptions import ToolError

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # Create Project Alpha
        res_pa = client.post("/projects", json={"name": "Project Alpha"})
        assert res_pa.status_code == 200
        proj_a_id = res_pa.json()["project_id"]

        # 1. POST /sessions creates and persists a session
        sess_resp = client.post("/sessions", json={"project_id": proj_a_id, "metadata": {"origin": "api"}})
        assert sess_resp.status_code == 200
        sess_data = sess_resp.json()
        assert sess_data["project_id"] == proj_a_id
        assert sess_data["project_name"] == "Project Alpha"
        sess_1_id = sess_data["session_id"]
        assert sess_1_id

        # Verify via GET /sessions
        list_sess = client.get("/sessions")
        assert list_sess.status_code == 200
        assert list_sess.json()["total"] == 1
        assert list_sess.json()["sessions"][0]["session_id"] == sess_1_id
        assert list_sess.json()["sessions"][0]["memory_captures"] == 0

        # 2. Repeating same creation request is safe and idempotent
        idempotent_resp = client.post("/sessions", json={"project_id": proj_a_id, "session_id": sess_1_id})
        assert idempotent_resp.status_code == 200
        assert idempotent_resp.json()["session_id"] == sess_1_id

        # 3. Unknown projects (404) and invalid IDs (400) rejected
        bad_proj = client.post("/sessions", json={"project_id": str(uuid4())})
        assert bad_proj.status_code == 404
        assert "Project not found" in bad_proj.json()["detail"]

        bad_uuid = client.post("/sessions", json={"project_id": "not-a-uuid"})
        assert bad_uuid.status_code == 400

        bad_sess_uuid = client.post("/sessions", json={"project_id": proj_a_id, "session_id": "not-a-uuid"})
        assert bad_sess_uuid.status_code == 400

        bad_meta = client.post("/sessions", json={"project_id": proj_a_id, "metadata": "not-a-dict"})
        assert bad_meta.status_code == 400

        # 4. A session ID cannot be reused under a different project
        res_pb = client.post("/projects", json={"name": "Project Beta"})
        assert res_pb.status_code == 200
        proj_b_id = res_pb.json()["project_id"]

        conflict_resp = client.post("/sessions", json={"project_id": proj_b_id, "session_id": sess_1_id})
        assert conflict_resp.status_code == 409
        assert "already belongs to a different project" in conflict_resp.json()["detail"]

        # 5. MCP memory-save call with explicit session_id creates or reuses the session
        mcp_server = create_server(manager)
        mcp_save_tool = mcp_server._tool_manager.get_tool("recall_save_memory")
        assert mcp_save_tool is not None

        custom_sess_id = str(uuid4())
        # First save with brand-new session_id -> auto-creates session
        save_res_1 = mcp_save_tool.fn(
            content="Memory 1 under custom session",
            project_id=proj_a_id,
            session_id=custom_sess_id,
            memory_type="fact",
        )
        assert save_res_1["memory"]["session_id"] == custom_sess_id
        assert save_res_1["memory"]["project_id"] == proj_a_id

        # Verify session is in repository
        stored_sess = manager.get_session(UUID(custom_sess_id))
        assert stored_sess.success and stored_sess.value is not None
        assert str(stored_sess.value.project_id) == proj_a_id

        # Second save with same session_id -> reuses session
        save_res_2 = mcp_save_tool.fn(
            content="Memory 2 under custom session",
            project_id=proj_a_id,
            session_id=custom_sess_id,
            memory_type="fact",
        )
        assert save_res_2["memory"]["session_id"] == custom_sess_id

        # Attempt to save with custom_sess_id under Project Beta -> rejected
        with pytest.raises(ToolError, match="session_id does not belong to project_id"):
            mcp_save_tool.fn(
                content="Memory under wrong project",
                project_id=proj_b_id,
                session_id=custom_sess_id,
            )

        # 6. Session memory-capture counts and Overview totals match persisted data
        sessions_report = client.get("/sessions")
        assert sessions_report.status_code == 200
        assert sessions_report.json()["total"] == 2
        sess_items = {s["session_id"]: s for s in sessions_report.json()["sessions"]}
        assert sess_items[custom_sess_id]["memory_captures"] == 2
        assert sess_items[sess_1_id]["memory_captures"] == 0

        stats_report = client.get("/stats")
        assert stats_report.status_code == 200
        assert stats_report.json()["total_sessions"] == 2

        # 7. Omitting session_id retains documented unassociated-memory behavior
        save_unassociated = mcp_save_tool.fn(
            content="Unassociated memory content",
            project_id=proj_a_id,
            session_id=None,
        )
        assert save_unassociated["memory"]["session_id"] is None

        after_unassociated_stats = client.get("/stats").json()
        assert after_unassociated_stats["total_sessions"] == 2
    finally:
        manager.close()


def test_real_sqlite_custom_instructions_project_scoped_lifecycle(tmp_path):
    from database.config import DatabaseConfig
    from core.recall_core.bootstrap import create_memory_manager

    config = DatabaseConfig.from_path(tmp_path / "recall.sqlite3")
    manager = create_memory_manager(config)
    app = create_app(manager)
    client = TestClient(app)

    try:
        # Create Project Alpha
        res_pa = client.post("/projects", json={"name": "Project Gamma"})
        assert res_pa.status_code == 200
        proj_id = res_pa.json()["project_id"]

        # Global scope requires no project
        g_resp = client.post("/custom-instructions", json={
            "content": "Global rule for all projects",
            "scope": "global",
        })
        assert g_resp.status_code == 200
        assert g_resp.json()["scope"] == "global"
        assert g_resp.json()["project_id"] is None
        assert g_resp.json()["project_name"] is None

        # Project scope with missing project_id fails
        missing_resp = client.post("/custom-instructions", json={
            "content": "Project rule without project",
            "scope": "project",
        })
        assert missing_resp.status_code == 400
        assert "project_id is required" in missing_resp.json()["detail"]

        # Project scope with nonexistent project_id fails
        nonexistent_resp = client.post("/custom-instructions", json={
            "content": "Project rule with unknown project",
            "scope": "project",
            "project_id": str(uuid4()),
        })
        assert nonexistent_resp.status_code == 404
        assert "Project not found" in nonexistent_resp.json()["detail"]

        # Project scope with valid project_id succeeds and persists
        p_resp = client.post("/custom-instructions", json={
            "content": "Project specific rule",
            "scope": "project",
            "project_id": proj_id,
        })
        assert p_resp.status_code == 200
        p_data = p_resp.json()
        assert p_data["scope"] == "project"
        assert p_data["project_id"] == proj_id
        assert p_data["project_name"] == "Project Gamma"
        instr_id = p_data["instruction_id"]

        # Listing custom instructions includes project_name
        list_resp = client.get("/custom-instructions")
        assert list_resp.status_code == 200
        matched = next((i for i in list_resp.json()["instructions"] if i["instruction_id"] == instr_id), None)
        assert matched is not None
        assert matched["project_id"] == proj_id
        assert matched["project_name"] == "Project Gamma"
    finally:
        manager.close()



