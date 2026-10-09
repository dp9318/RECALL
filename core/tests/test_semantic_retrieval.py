"""Semantic retrieval integration tests with isolated Chroma and embeddings fakes."""

from __future__ import annotations

import asyncio
import math
import os
import sys
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

import database.repositories.semantic_index_repo as semantic_repo_module
from contracts.base import MemoryStatus, Result, Scope
from contracts.memory import Memory, MemoryCreateRequest, MemoryUpdateRequest
from contracts.project import ProjectCreateRequest
from contracts.retrieval import ContextAssemblyRequest, RetrievalRequest
from core.recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig
from intelligence.embeddings import (
    ChromaSentenceTransformerEmbeddingFunction,
    EmbeddingConfig,
    SentenceTransformerEmbeddingService,
)
from intelligence.retrieval import DefaultRetrievalService, EmbeddingService
from recall_mcp.server import create_server


class FakeEmbeddingService(EmbeddingService):
    """Small deterministic vectorizer with a known synonym pair for tests."""

    _vehicle_terms = {"car", "automobile", "vehicle", "motor"}

    def generate_embedding(self, text: str) -> Result[list[float]]:
        result = self.generate_embeddings([text])
        return Result.ok(result.value[0]) if result.success else Result.err(result.error or "")

    def generate_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 32
            for token in text.lower().split():
                if token in self._vehicle_terms:
                    vector[0] += 1.0
                else:
                    vector[1 + sum(map(ord, token)) % 31] += 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return Result.ok(vectors)


class FailingEmbeddingService(EmbeddingService):
    def generate_embedding(self, text: str) -> Result[list[float]]:
        return Result.err("embedding provider failed")

    def generate_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        return Result.err("embedding provider failed")


class FakeCollection:
    def __init__(self, metadata, embedding_function):
        self.metadata = metadata
        self.embedding_function = embedding_function
        self.records: dict[str, tuple[str, dict, list[float]]] = {}

    @staticmethod
    def _matches(metadata, where):
        if not where:
            return True
        if "$and" in where:
            return all(FakeCollection._matches(metadata, part) for part in where["$and"])
        if "$or" in where:
            return any(FakeCollection._matches(metadata, part) for part in where["$or"])
        return all(metadata.get(key) == value for key, value in where.items())

    def upsert(self, ids, documents, metadatas):
        vectors = self.embedding_function(documents)
        for identifier, document, metadata, vector in zip(
            ids, documents, metadatas, vectors
        ):
            self.records[identifier] = (document, metadata, vector)

    def delete(self, ids):
        for identifier in ids:
            self.records.pop(identifier, None)

    def count(self, where=None):
        return sum(
            self._matches(metadata, where)
            for _, metadata, _ in self.records.values()
        )

    def get(self):
        return {"ids": list(self.records)}

    def query(self, query_texts, n_results, where, include):
        query_vector = self.embedding_function(query_texts)[0]
        scored = []
        for identifier, (document, metadata, vector) in self.records.items():
            if self._matches(metadata, where):
                distance = 1 - sum(a * b for a, b in zip(query_vector, vector))
                scored.append((identifier, distance))
        scored.sort(key=lambda item: item[1])
        selected = scored[:n_results]
        return {
            "ids": [[identifier for identifier, _ in selected]],
            "distances": [[distance for _, distance in selected]],
        }


class FakeChromaClient:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}
        self.closed = False

    def list_collections(self):
        return list(self.collections)

    def create_collection(self, name, metadata, embedding_function):
        collection = FakeCollection(metadata, embedding_function)
        self.collections[name] = collection
        return collection

    def get_collection(self, name, embedding_function=None):
        collection = self.collections[name]
        if embedding_function is not None:
            collection.embedding_function = embedding_function
        return collection

    def delete_collection(self, name):
        del self.collections[name]

    def close(self):
        self.closed = True


@pytest.fixture
def fake_chroma(monkeypatch):
    clients: dict[str, FakeChromaClient] = {}

    def persistent_client(path):
        return clients.setdefault(path, FakeChromaClient())

    monkeypatch.setattr(semantic_repo_module, "CHROMADB_AVAILABLE", True)
    monkeypatch.setattr(
        semantic_repo_module,
        "chromadb",
        SimpleNamespace(PersistentClient=persistent_client),
    )
    return clients


def _manager(tmp_path, fake_chroma, *, model="sentence-transformers/test-model"):
    return create_memory_manager(
        DatabaseConfig.from_path(tmp_path / "recall.sqlite3"),
        embedding_config=EmbeddingConfig(model=model),
        embedding_service=FakeEmbeddingService(),
    )


def test_composed_semantic_retrieval_searches_vectors_and_filters_scope(
    tmp_path, fake_chroma
):
    manager = _manager(tmp_path, fake_chroma)
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="Semantic test")
        ).value
        other_project = manager.create_project(
            ProjectCreateRequest(name="Other project")
        ).value
        vehicle = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="A car provides personal transport.",
            )
        )
        global_vehicle = manager.create_memory(
            MemoryCreateRequest(
                content="A vehicle can be a useful personal asset.",
            )
        )
        manager.create_memory(
            MemoryCreateRequest(
                project_id=other_project.id,
                scope=Scope.PROJECT,
                content="An automobile is used for transport.",
            )
        )

        result = manager.retrieve(
            RetrievalRequest(
                query="automobile",
                project_id=project.id,
                use_structured=False,
            )
        )

        assert result.success, result.error
        ids = {memory.id for memory in result.value.memories}
        assert ids == {vehicle.value.id, global_vehicle.value.id}
        assert result.value.semantic_results == 2
    finally:
        manager.close()
    chroma_path = str(
        (tmp_path / "recall.sqlite3").with_suffix(".sqlite3.chromadb")
    )
    assert fake_chroma[chroma_path].closed


def test_semantic_results_are_checked_against_canonical_status_and_context(
    tmp_path, fake_chroma
):
    manager = _manager(tmp_path, fake_chroma)
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="Context test")
        ).value
        saved = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="A car is convenient for commuting.",
            )
        )
        assembled = manager.assemble_context(
            ContextAssemblyRequest(project_id=project.id, query="automobile")
        )
        assert assembled.success, assembled.error
        assert saved.value.id in {m.id for m in assembled.value.active_memories}

        updated_content = manager.update_memory(
            saved.value.id,
            MemoryUpdateRequest(content="A bicycle is convenient for commuting."),
        )
        assert updated_content.success
        indexed = manager.retrieve(
            RetrievalRequest(
                query="bicycle",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert indexed.success, indexed.error
        assert indexed.value.memories[0].content == updated_content.value.content

        updated = manager.update_memory(
            saved.value.id,
            MemoryUpdateRequest(status=MemoryStatus.ARCHIVED),
        )
        assert updated.success
        result = manager.retrieve(
            RetrievalRequest(
                query="automobile",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert result.success, result.error
        assert result.value.memories == []
        assert result.value.semantic_results == 0

        to_delete = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="A vehicle is helpful for commuting.",
            )
        )
        deleted = manager.delete_memory(to_delete.value.id)
        assert deleted.success
        after_delete = manager.retrieve(
            RetrievalRequest(
                query="automobile",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert after_delete.success, after_delete.error
        assert after_delete.value.memories == []
    finally:
        manager.close()


def test_model_identity_mismatch_requires_explicit_rebuild_from_sqlite(
    tmp_path, fake_chroma
):
    first = _manager(tmp_path, fake_chroma)
    project = first.create_project(ProjectCreateRequest(name="Reindex")).value
    canonical = first.create_memory(
        MemoryCreateRequest(
            project_id=project.id,
            scope=Scope.PROJECT,
            content="A car needs fuel.",
        )
    ).value
    first.close()

    changed = _manager(
        tmp_path,
        fake_chroma,
        model="sentence-transformers/changed-model",
    )
    try:
        blocked = changed.retrieve(
            RetrievalRequest(
                query="automobile",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert not blocked.success
        assert "identity does not match" in blocked.error

        rebuilt = changed.rebuild_semantic_index()
        assert rebuilt.success, rebuilt.error
        assert rebuilt.value == 1

        result = changed.retrieve(
            RetrievalRequest(
                query="automobile",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert result.success, result.error
        assert [memory.id for memory in result.value.memories] == [canonical.id]
    finally:
        changed.close()


def test_mcp_uses_the_composed_semantic_index(tmp_path, fake_chroma):
    manager = _manager(tmp_path, fake_chroma)
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="MCP semantic test")
        ).value
        server = create_server(manager)
        saved = asyncio.run(
            _call_mcp_tool(
                server,
                "recall_save_memory",
                {
                    "project_id": str(project.id),
                    "content": "A car is useful for long trips.",
                },
            )
        )
        assert not saved.isError
        memory_id = saved.structuredContent["memory"]["id"]

        result = asyncio.run(
            _call_mcp_tool(
                server,
                "recall_search",
                {
                    "project_id": str(project.id),
                    "query": "automobile",
                    "limit": 5,
                },
            )
        )
        assert not result.isError
        assert memory_id in {
            memory["id"] for memory in result.structuredContent["memories"]
        }
    finally:
        manager.close()


async def _call_mcp_tool(server: FastMCP, name: str, arguments: dict):
    async with create_connected_server_and_client_session(server) as client:
        return await client.call_tool(name, arguments)


@pytest.mark.skipif(
    os.environ.get("RECALL_RUN_REAL_SEMANTIC_TESTS") != "1",
    reason="Set RECALL_RUN_REAL_SEMANTIC_TESTS=1 to run model-download integration",
)
def test_real_sentence_transformers_chroma_core_and_mcp_round_trip(
    tmp_path, monkeypatch, capsys
):
    import chromadb

    monkeypatch.setenv("RECALL_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv(
        "RECALL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    monkeypatch.setenv("RECALL_EMBEDDING_DEVICE", "cpu")
    config = EmbeddingConfig.from_env()
    assert config == EmbeddingConfig()
    embedding_service = SentenceTransformerEmbeddingService(config)
    assert embedding_service._model is None

    vectors = embedding_service.generate_embeddings(
        [
            "A car provides convenient transportation.",
            "An automobile is useful for getting around.",
            "Bananas are a yellow fruit.",
        ]
    )
    assert vectors.success, vectors.error
    assert [len(vector) for vector in vectors.value] == [384, 384, 384]
    cosine = lambda left, right: sum(a * b for a, b in zip(left, right))
    assert cosine(vectors.value[0], vectors.value[1]) > cosine(
        vectors.value[0], vectors.value[2]
    )

    database_config = DatabaseConfig.from_path(tmp_path / "real.sqlite3")
    manager = create_memory_manager(
        database_config,
        embedding_config=config,
        embedding_service=embedding_service,
    )
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="Real semantic integration")
        ).value
        other_project = manager.create_project(
            ProjectCreateRequest(name="Out-of-scope project")
        ).value
        empty_search = manager.retrieve(
            RetrievalRequest(
                query="an unrelated empty collection query",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert empty_search.success, empty_search.error
        assert empty_search.value.memories == []

        project_memory = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="A car provides convenient transportation.",
            )
        ).value
        global_memory = manager.create_memory(
            MemoryCreateRequest(
                content="An automobile is useful for getting around.",
            )
        ).value
        other_memory = manager.create_memory(
            MemoryCreateRequest(
                project_id=other_project.id,
                scope=Scope.PROJECT,
                content="A car provides convenient transportation.",
            )
        ).value
        historical = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="An automobile once provided transportation.",
            )
        ).value
        assert manager.update_memory(
            historical.id,
            MemoryUpdateRequest(status=MemoryStatus.ARCHIVED),
        ).success

        result = manager.retrieve(
            RetrievalRequest(
                query="An automobile for getting around",
                project_id=project.id,
                use_structured=False,
                limit=10,
            )
        )
        assert result.success, result.error
        found_ids = {memory.id for memory in result.value.memories}
        assert {project_memory.id, global_memory.id} <= found_ids
        assert other_memory.id not in found_ids
        assert historical.id not in found_ids
        assert result.value.semantic_results == 2
        for retrieved in result.value.memories:
            canonical = manager.get_memory(retrieved.id)
            assert canonical.success
            assert canonical.value.content == retrieved.content

        health = manager.get_stats()
        assert health.success, health.error
        assert health.value["semantic_index"]["status"] == "healthy"
        assert health.value["semantic_index"]["embedding_dimensions"] == 384
        assert health.value["semantic_index"]["memory_count"] == 3

        server = create_server(manager)
        mcp_saved = asyncio.run(
            _call_mcp_tool(
                server,
                "recall_save_memory",
                {
                    "project_id": str(project.id),
                    "content": "A car is suitable for a long journey.",
                },
            )
        )
        assert not mcp_saved.isError
        mcp_memory_id = mcp_saved.structuredContent["memory"]["id"]
        mcp_search = asyncio.run(
            _call_mcp_tool(
                server,
                "recall_search",
                {
                    "project_id": str(project.id),
                    "query": "automobile for travel",
                    "limit": 10,
                },
            )
        )
        assert not mcp_search.isError
        assert mcp_memory_id in {
            memory["id"] for memory in mcp_search.structuredContent["memories"]
        }
        mcp_context = asyncio.run(
            _call_mcp_tool(
                server,
                "recall_get_context",
                {
                    "project_id": str(project.id),
                    "query": "automobile",
                    "limit": 10,
                },
            )
        )
        assert not mcp_context.isError
        assert mcp_memory_id in {
            memory["id"]
            for memory in mcp_context.structuredContent["active_memories"]
        }
        assert capsys.readouterr().out == ""

        updated = manager.update_memory(
            project_memory.id,
            MemoryUpdateRequest(
                content="A bicycle is propelled by pedaling.",
            ),
        )
        assert updated.success, updated.error
        updated_result = manager.retrieve(
            RetrievalRequest(
                query="cycle powered by pedals",
                project_id=project.id,
                use_structured=False,
                limit=10,
            )
        )
        assert updated_result.success, updated_result.error
        assert project_memory.id in {
            memory.id for memory in updated_result.value.memories
        }

        deleted = manager.delete_memory(project_memory.id)
        assert deleted.success
        deleted_result = manager.retrieve(
            RetrievalRequest(
                query="cycle powered by pedals",
                project_id=project.id,
                use_structured=False,
                limit=10,
            )
        )
        assert deleted_result.success, deleted_result.error
        assert project_memory.id not in {
            memory.id for memory in deleted_result.value.memories
        }
    finally:
        manager.close()

    reopened = create_memory_manager(
        database_config,
        embedding_config=config,
        embedding_service=embedding_service,
    )
    try:
        persistent = reopened.retrieve(
            RetrievalRequest(
                query="automobile transportation",
                project_id=project.id,
                use_structured=False,
                limit=10,
            )
        )
        assert persistent.success, persistent.error
        assert global_memory.id in {memory.id for memory in persistent.value.memories}

        collection = reopened._uow.semantic_index._memory_collection
        collection.modify(
            metadata={
                "recall_embedding_provider": config.provider,
                "recall_embedding_model": "different-model",
            }
        )
    finally:
        reopened.close()

    mismatched = create_memory_manager(
        database_config,
        embedding_config=config,
        embedding_service=embedding_service,
    )
    try:
        mismatch_result = mismatched.retrieve(
            RetrievalRequest(
                query="automobile transportation",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert not mismatch_result.success
        assert "identity does not match" in mismatch_result.error

        rebuilt = mismatched.rebuild_semantic_index()
        assert rebuilt.success, rebuilt.error
        assert rebuilt.value == 3
        after_rebuild = mismatched.retrieve(
            RetrievalRequest(
                query="automobile transportation",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert after_rebuild.success, after_rebuild.error
        assert global_memory.id in {
            memory.id for memory in after_rebuild.value.memories
        }
        assert project_memory.id not in {
            memory.id for memory in after_rebuild.value.memories
        }
    finally:
        mismatched.close()

    assert isinstance(chromadb.__version__, str)

def test_default_retrieval_does_not_fake_semantic_results_with_keywords():
    result = DefaultRetrievalService().retrieve(
        RetrievalRequest(query="keyword-looking text", use_structured=False)
    )
    assert not result.success
    assert "no semantic index is configured" in result.error


def test_embedding_failure_is_not_reported_as_semantic_success(
    tmp_path, fake_chroma
):
    manager = create_memory_manager(
        DatabaseConfig.from_path(tmp_path / "failure.sqlite3"),
        embedding_config=EmbeddingConfig(model="sentence-transformers/test-model"),
        embedding_service=FailingEmbeddingService(),
    )
    try:
        project = manager.create_project(
            ProjectCreateRequest(name="Embedding failure")
        ).value
        created = manager.create_memory(
            MemoryCreateRequest(
                project_id=project.id,
                scope=Scope.PROJECT,
                content="Canonical record",
            )
        )
        assert created.success
        assert "semantic_index_error" in created.metadata

        result = manager.retrieve(
            RetrievalRequest(
                query="record",
                project_id=project.id,
                use_structured=False,
            )
        )
        assert not result.success
        assert "embedding provider failed" in result.error

        stats = manager.get_stats()
        assert stats.success
        assert stats.value["semantic_index"]["status"] == "error"
    finally:
        manager.close()


def test_sentence_transformer_missing_dependency_is_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    service = SentenceTransformerEmbeddingService(EmbeddingConfig())
    result = service.generate_embedding("local test")
    assert not result.success
    assert "Install RECALL's semantic extra" in result.error


def test_sentence_transformer_model_load_failure_is_actionable(monkeypatch):
    def fail_to_load(model, device):
        raise OSError("model not found")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=fail_to_load),
    )
    service = SentenceTransformerEmbeddingService(
        EmbeddingConfig(model="local/missing-model")
    )
    result = service.generate_embedding("local test")
    assert not result.success
    assert "local/missing-model" in result.error
    assert "verify the model name" in result.error


def test_embedding_configuration_uses_documented_environment(monkeypatch):
    for name in (
        "RECALL_EMBEDDING_PROVIDER",
        "RECALL_EMBEDDING_MODEL",
        "RECALL_EMBEDDING_DEVICE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert EmbeddingConfig.from_env() == EmbeddingConfig()

    monkeypatch.setenv("RECALL_EMBEDDING_MODEL", "local/custom-model")
    monkeypatch.setenv("RECALL_EMBEDDING_DEVICE", "cpu")
    assert EmbeddingConfig.from_env().model == "local/custom-model"

    with pytest.raises(ValueError, match="Unsupported RECALL_EMBEDDING_PROVIDER"):
        EmbeddingConfig(provider="remote-provider")


def test_embedding_function_reuses_provider_for_document_and_query_text():
    config = EmbeddingConfig()
    embedding_function = ChromaSentenceTransformerEmbeddingFunction(
        FakeEmbeddingService(), config
    )
    vectors = embedding_function(["car", "automobile"])
    assert vectors[0] == vectors[1]
    assert embedding_function.name() == "recall_sentence_transformers"
    assert embedding_function.get_config()["model"] == config.model
