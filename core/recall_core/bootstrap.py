"""Default application composition for RECALL Core."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.recall_core.memory_manager import MemoryManager
from database.config import DatabaseConfig
from database.connection import initialize_database
from database.repositories import SemanticIndexRepository, SQLiteUnitOfWork
from intelligence.conflict import DefaultConflictResolutionService, DefaultConflictResolver
from intelligence.conflict_adapters import (
    CloudConflictAdapter,
    CloudConflictConfig,
    OllamaConflictAdapter,
)
from intelligence.embeddings import (
    ChromaSentenceTransformerEmbeddingFunction,
    EmbeddingConfig,
    SentenceTransformerEmbeddingService,
)
from intelligence.retrieval import DefaultRetrievalService, EmbeddingService


def create_memory_manager(
    config: DatabaseConfig | None = None,
    *,
    embedding_config: EmbeddingConfig | None = None,
    embedding_service: Optional[EmbeddingService] = None,
    semantic_index: Optional[SemanticIndexRepository] = None,
) -> MemoryManager:
    """Initialize SQLite and compose Core services for a local application."""
    if config is None:
        config = DatabaseConfig.from_path(
            Path.home() / ".recall" / "recall.sqlite3"
        )

    embedding_config = embedding_config or EmbeddingConfig.from_env()
    embedding_service = embedding_service or SentenceTransformerEmbeddingService(
        embedding_config
    )
    embedding_function = ChromaSentenceTransformerEmbeddingFunction(
        embedding_service, embedding_config
    )
    cloud_conflict_config = CloudConflictConfig.from_env()
    cloud_conflict_adapter = (
        CloudConflictAdapter(cloud_conflict_config)
        if cloud_conflict_config is not None
        else None
    )
    initialize_database(config)
    unit_of_work = SQLiteUnitOfWork(
        config,
        semantic_index=semantic_index,
        embedding_function=embedding_function,
        embedding_provider=embedding_config.provider,
        embedding_model=embedding_config.model,
    )
    try:
        semantic_index = unit_of_work.semantic_index
        retrieval_service = DefaultRetrievalService(
            memory_repo=unit_of_work.memories,
            semantic_index=semantic_index,
        )
        return MemoryManager(
            unit_of_work=unit_of_work,
            retrieval_service=retrieval_service,
            conflict_service=DefaultConflictResolutionService(
                resolver=DefaultConflictResolver(
                    llm_adapter=OllamaConflictAdapter(),
                    cloud_adapter=cloud_conflict_adapter,
                )
            ),
            semantic_index=semantic_index,
        )
    except Exception:
        unit_of_work.close()
        raise
