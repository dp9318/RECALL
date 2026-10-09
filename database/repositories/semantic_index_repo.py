"""ChromaDB implementation of SemanticIndexRepository."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from contracts.base import MemoryStatus, Result, Scope
from contracts.memory import Memory
from database.repositories import SemanticIndexRepository

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMADB_AVAILABLE = False


class SQLiteSemanticIndexRepository(SemanticIndexRepository):
    """ChromaDB-backed derived index for canonical SQLite memories."""

    COLLECTION_NAME = "memories"
    IDENTITY_KEYS = ("recall_embedding_provider", "recall_embedding_model")

    def __init__(
        self,
        conn,
        persist_directory: str | Path | None = None,
        embedding_function: Any = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        # Keep the SQLite connection for compatibility with the repository contract.
        self._conn = conn
        self._persist_directory = Path(
            persist_directory or Path.home() / ".recall" / "chroma"
        )
        self._embedding_function = embedding_function
        self._embedding_provider = embedding_provider
        self._embedding_model = embedding_model
        self._client: Optional[Any] = None
        self._memory_collection: Optional[Any] = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self._identity_mismatch = False

    def _initialize(self) -> None:
        if self._initialized or self._init_error:
            return
        if not CHROMADB_AVAILABLE:
            self._init_error = (
                "ChromaDB is unavailable. Install RECALL's semantic extra with "
                "`python -m pip install -e 'core[semantic]'`."
            )
            return
        if (
            self._embedding_function is None
            or not self._embedding_provider
            or not self._embedding_model
        ):
            self._init_error = (
                "Semantic embedding is not configured. Use the Core composition "
                "factory or inject an embedding function with provider and model identity."
            )
            return

        try:
            self._persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self._persist_directory)
            )
            existing = {
                getattr(collection, "name", collection)
                for collection in self._client.list_collections()
            }
            if self.COLLECTION_NAME in existing:
                self._memory_collection = self._client.get_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=None,
                )
            else:
                self._memory_collection = self._client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata=self._expected_metadata(),
                    embedding_function=self._embedding_function,
                )
            actual_metadata = self._memory_collection.metadata or {}
            expected_metadata = self._expected_metadata()
            mismatches = {
                key: (actual_metadata.get(key), expected_metadata[key])
                for key in self.IDENTITY_KEYS
                if actual_metadata.get(key) != expected_metadata[key]
            }
            if actual_metadata.get("hnsw:space") != "cosine":
                mismatches["hnsw:space"] = (
                    actual_metadata.get("hnsw:space"),
                    "cosine",
                )
            self._initialized = True
            if mismatches:
                self._identity_mismatch = True
                self._init_error = (
                    "Chroma memory collection embedding identity does not match "
                    f"the configured provider/model: {mismatches}. Run the explicit "
                    "semantic-index rebuild to re-embed canonical SQLite memories."
                )
            else:
                self._memory_collection = self._client.get_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=self._embedding_function,
                )
        except Exception as exc:
            self._init_error = f"Failed to initialize ChromaDB: {exc}"

    def _check_initialized(self) -> Optional[Result[Any]]:
        if not self._initialized:
            self._initialize()
        if self._init_error:
            return Result.err(self._init_error)
        return None

    def _expected_metadata(self) -> dict[str, str]:
        return {
            "hnsw:space": "cosine",
            "recall_embedding_provider": self._embedding_provider or "",
            "recall_embedding_model": self._embedding_model or "",
        }

    @staticmethod
    def _memory_metadata(memory: Memory) -> dict[str, str]:
        return {
            "canonical_id": str(memory.id),
            "record_type": "memory",
            "project_id": str(memory.project_id) if memory.project_id else "__global__",
            "session_id": str(memory.session_id) if memory.session_id else "__none__",
            "scope": (
                memory.scope.value
                if isinstance(memory.scope, Scope)
                else str(memory.scope)
            ),
            "memory_type": memory.memory_type,
            "status": (
                memory.status.value
                if isinstance(memory.status, MemoryStatus)
                else str(memory.status)
            ),
        }

    def _upsert_memories(self, memories: list[Memory]) -> None:
        if not memories:
            return
        self._memory_collection.upsert(
            ids=[str(memory.id) for memory in memories],
            documents=[memory.content for memory in memories],
            metadatas=[self._memory_metadata(memory) for memory in memories],
        )

    def index_memory(self, memory: Memory) -> Result[bool]:
        error = self._check_initialized()
        if error:
            return error
        try:
            if memory.status != MemoryStatus.ACTIVE:
                self._memory_collection.delete(ids=[str(memory.id)])
                return Result.ok(True)
            self._upsert_memories([memory])
            return Result.ok(True)
        except Exception as exc:
            return Result.err(f"Failed to index memory {memory.id}: {exc}")

    def update_memory(self, memory: Memory) -> Result[bool]:
        return self.index_memory(memory)

    def remove_memory(self, memory_id: UUID) -> Result[bool]:
        error = self._check_initialized()
        if error:
            return error
        try:
            self._memory_collection.delete(ids=[str(memory_id)])
            return Result.ok(True)
        except Exception as exc:
            return Result.err(f"Failed to remove memory {memory_id}: {exc}")

    def search_similar(
        self,
        query: str,
        project_id: Optional[UUID],
        limit: int,
    ) -> Result[list[tuple[UUID, float]]]:
        if limit <= 0 or not query.strip():
            return Result.ok([])
        error = self._check_initialized()
        if error:
            return error

        try:
            where: dict[str, Any] = {"status": MemoryStatus.ACTIVE.value}
            if project_id is not None:
                where = {
                    "$and": [
                        where,
                        {
                            "$or": [
                                {"project_id": str(project_id)},
                                {
                                    "$and": [
                                        {"scope": Scope.GLOBAL.value},
                                        {"project_id": "__global__"},
                                    ]
                                },
                            ]
                        },
                    ]
                }
            results = self._memory_collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
                include=["distances"],
            )
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return Result.ok(
                [
                    (UUID(memory_id), 1.0 - float(distance))
                    for memory_id, distance in zip(ids, distances)
                ]
            )
        except Exception as exc:
            return Result.err(f"Failed to search similar memories: {exc}")

    def rebuild_from_canonical(self, memories: list[Memory]) -> Result[int]:
        try:
            if not self._initialized:
                self._initialize()
            if self._identity_mismatch:
                self._client.delete_collection(name=self.COLLECTION_NAME)
                self._memory_collection = self._client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata=self._expected_metadata(),
                    embedding_function=self._embedding_function,
                )
                self._identity_mismatch = False
                self._init_error = None
            elif self._init_error:
                return Result.err(self._init_error)

            existing_ids = self._memory_collection.get().get("ids", [])
            for start in range(0, len(existing_ids), 500):
                self._memory_collection.delete(ids=existing_ids[start : start + 500])

            active_memories = [
                memory for memory in memories if memory.status == MemoryStatus.ACTIVE
            ]
            for start in range(0, len(active_memories), 128):
                self._upsert_memories(active_memories[start : start + 128])
            return Result.ok(len(active_memories))
        except Exception as exc:
            return Result.err(f"Failed to rebuild semantic index: {exc}")

    def health_check(self) -> Result[dict[str, Any]]:
        if not CHROMADB_AVAILABLE:
            return Result.ok({
                "status": "unavailable",
                "reason": (
                    "ChromaDB is unavailable; install `core[semantic]` to enable "
                    "semantic retrieval."
                ),
            })
        if not self._initialized:
            self._initialize()
        if self._init_error:
            return Result.ok({
                "status": "error" if self._identity_mismatch else "unavailable",
                "reason": self._init_error,
            })
        try:
            embeddings = self._embedding_function(
                ["RECALL semantic index health check"]
            )
            if len(embeddings) != 1 or not embeddings[0]:
                raise ValueError(
                    "The configured embedding function returned no vector"
                )
            return Result.ok({
                "status": "healthy",
                "memory_count": self._memory_collection.count(),
                "embedding_provider": self._embedding_provider,
                "embedding_model": self._embedding_model,
                "embedding_dimensions": len(embeddings[0]),
            })
        except Exception as exc:
            return Result.ok({"status": "error", "error": str(exc)})

    def close(self) -> None:
        """Release the Chroma client when its implementation exposes close()."""
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._memory_collection = None
        self._client = None
        self._initialized = False
