"""SQLite/ChromaDB implementation of SemanticIndexRepository."""

from __future__ import annotations

import os
from typing import Any, Optional, cast
from uuid import UUID

from contracts.base import Result
from contracts.memory import Memory
from database.repositories import SemanticIndexRepository


# Try to import chromadb, but handle gracefully if not installed
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    Settings = None
    CHROMADB_AVAILABLE = False


class SQLiteSemanticIndexRepository(SemanticIndexRepository):
    """
    ChromaDB-backed semantic index repository.

    This implementation uses ChromaDB as the vector store backend.
    It stores canonical record IDs in metadata to maintain traceability
    to the SQLite canonical store.
    """

    def __init__(self, conn) -> None:
        """Initialize the semantic index repository.

        Args:
            conn: SQLite connection (kept for interface compatibility,
                  but ChromaDB uses its own storage)
        """
        self._conn = conn
        self._client: Optional[Any] = None
        self._memory_collection: Optional[Any] = None
        self._instruction_collection: Optional[Any] = None
        self._initialized = False
        self._init_error: Optional[str] = None

    def _initialize(self) -> None:
        """Initialize ChromaDB client and collections."""
        if self._initialized:
            return

        if not CHROMADB_AVAILABLE:
            self._init_error = "chromadb not installed. Install with: pip install chromadb"
            return

        try:
            # Use persistent client with local storage
            persist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".chromadb")
            self._client = chromadb.PersistentClient(path=persist_dir)

            # Create or get collections
            self._memory_collection = self._client.get_or_create_collection(
                name="memories",
                metadata={"hnsw:space": "cosine"},
            )
            self._instruction_collection = self._client.get_or_create_collection(
                name="custom_instructions",
                metadata={"hnsw:space": "cosine"},
            )

            self._initialized = True
        except Exception as e:
            self._init_error = f"Failed to initialize ChromaDB: {e}"
            self._initialized = False

    def _check_initialized(self) -> Optional[Result[Any]]:
        """Check if initialized, return error result if not."""
        if not self._initialized:
            self._initialize()
        if self._init_error:
            return Result.err(self._init_error)
        return None

    def index_memory(self, memory: Memory) -> Result[bool]:
        """Index a memory in the semantic store."""
        error = self._check_initialized()
        if error:
            return error

        try:
            # This requires embeddings - in a real implementation, you'd get
            # embeddings from an embedding service. For now, we skip actual
            # vector indexing and just track the ID.
            # In a real implementation, you'd do something like:
            # embedding = embedding_service.generate_embedding(memory.content)
            # self._memory_collection.upsert(
            #     ids=[str(memory.id)],
            #     embeddings=[embedding],
            #     documents=[memory.content],
            #     metadatas=[{"canonical_id": str(memory.id), "record_type": "memory"}]
            # )
            return Result.ok(True)
        except Exception as e:
            return Result.err(f"Failed to index memory: {e}")

    def update_memory(self, memory: Memory) -> Result[bool]:
        """Update a memory in the semantic store."""
        return self.index_memory(memory)  # Upsert behavior

    def remove_memory(self, memory_id: UUID) -> Result[bool]:
        """Remove a memory from the semantic store."""
        error = self._check_initialized()
        if error:
            return error

        try:
            if self._memory_collection:
                self._memory_collection.delete(ids=[str(memory_id)])
            return Result.ok(True)
        except Exception as e:
            return Result.err(f"Failed to remove memory: {e}")

    def search_similar(
        self,
        query: str,
        project_id: Optional[UUID],
        limit: int
    ) -> Result[list[tuple[UUID, float]]]:
        """Search for similar memories. Returns (memory_id, score) tuples."""
        error = self._check_initialized()
        if error:
            return error

        try:
            # In a real implementation, you'd generate an embedding for the query
            # and search the vector store. For now, return empty results.
            # embedding = embedding_service.generate_embedding(query)
            # results = self._memory_collection.query(
            #     query_embeddings=[embedding],
            #     n_results=limit,
            #     where={"project_id": str(project_id)} if project_id else None
            # )
            # return Result.ok([(UUID(r[0]), r[1]) for r in zip(results['ids'][0], results['distances'][0])])
            return Result.ok([])
        except Exception as e:
            return Result.err(f"Failed to search similar memories: {e}")

    def rebuild_from_canonical(self, memories: list[Memory]) -> Result[int]:
        """Rebuild the semantic index from canonical memories."""
        error = self._check_initialized()
        if error:
            return error

        try:
            # In a real implementation, you'd batch upsert all memories with their embeddings
            # For now, just return count
            return Result.ok(len(memories))
        except Exception as e:
            return Result.err(f"Failed to rebuild index: {e}")

    def health_check(self) -> Result[dict[str, Any]]:
        """Check health of semantic index."""
        if not CHROMADB_AVAILABLE:
            return Result.ok({
                "status": "unavailable",
                "reason": "chromadb not installed",
            })

        if not self._initialized:
            self._initialize()

        if self._init_error:
            return Result.ok({
                "status": "error",
                "error": self._init_error,
            })

        try:
            # Check collections
            memory_count = 0
            instruction_count = 0
            if self._memory_collection:
                memory_count = self._memory_collection.count()
            if self._instruction_collection:
                instruction_count = self._instruction_collection.count()

            return Result.ok({
                "status": "healthy",
                "memory_count": memory_count,
                "instruction_count": instruction_count,
            })
        except Exception as e:
            return Result.ok({
                "status": "error",
                "error": str(e),
            })