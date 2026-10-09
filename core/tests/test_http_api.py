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
