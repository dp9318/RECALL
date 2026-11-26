"""Default application composition for RECALL Core."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from .memory_manager import MemoryManager
from database.config import DatabaseConfig
from database.connection import initialize_database
from database.exceptions import ConfigurationError
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


@dataclass(frozen=True)
class ResolvedRuntimePaths:
    """Resolved canonical SQLite and derived ChromaDB paths with provenance."""

    sqlite_path: Path
    chroma_path: Path
    sqlite_source: str
    chroma_source: str


def resolve_runtime_paths(
    config: DatabaseConfig | None = None,
    *,
    validate_env_parent: bool = True,
) -> ResolvedRuntimePaths:
    """Resolve canonical SQLite and ChromaDB paths with deterministic precedence.

    Precedence for SQLite:
    1. Explicit `DatabaseConfig` argument
    2. `RECALL_DB_PATH` environment / `.env` variable (must not be a directory; parent must exist)
    3. Canonical per-user default: `~/.recall/recall.sqlite3`

    Precedence for ChromaDB:
    1. `RECALL_CHROMA_PATH` environment / `.env` variable (must not be a file; parent must exist)
    2. Derived from SQLite path: `<sqlite_path>.chromadb`
    """
    if config is not None:
        sqlite_path = Path(config.path).expanduser().resolve()
        sqlite_source = "explicit_config"
    else:
        db_path_env = os.environ.get("RECALL_DB_PATH", "").strip()
        if db_path_env:
            sqlite_path = Path(db_path_env).expanduser().resolve()
            if sqlite_path.exists() and sqlite_path.is_dir():
                raise ConfigurationError(
                    f"RECALL_DB_PATH points to a directory, not a SQLite file: {sqlite_path}"
                )
            if validate_env_parent and not sqlite_path.parent.exists():
                raise ConfigurationError(
                    f"RECALL_DB_PATH parent directory does not exist: {sqlite_path.parent}"
                )
            sqlite_source = "env:RECALL_DB_PATH"
        else:
            sqlite_path = (Path.home() / ".recall" / "recall.sqlite3").resolve()
            sqlite_source = "default_canonical"

    chroma_env = os.environ.get("RECALL_CHROMA_PATH", "").strip()
    if chroma_env:
        chroma_path = Path(chroma_env).expanduser().resolve()
        if chroma_path.exists() and chroma_path.is_file():
            raise ConfigurationError(
                f"RECALL_CHROMA_PATH points to a file, not a directory: {chroma_path}"
            )
        if validate_env_parent and not chroma_path.parent.exists():
            raise ConfigurationError(
                f"RECALL_CHROMA_PATH parent directory does not exist: {chroma_path.parent}"
            )
        chroma_source = "env:RECALL_CHROMA_PATH"
    else:
        chroma_path = sqlite_path.with_suffix(sqlite_path.suffix + ".chromadb")
        chroma_source = "derived_from_sqlite"

    return ResolvedRuntimePaths(
        sqlite_path=sqlite_path,
        chroma_path=chroma_path,
        sqlite_source=sqlite_source,
        chroma_source=chroma_source,
    )


def create_memory_manager(
    config: DatabaseConfig | None = None,
    *,
    embedding_config: EmbeddingConfig | None = None,
    embedding_service: Optional[EmbeddingService] = None,
    semantic_index: Optional[SemanticIndexRepository] = None,
) -> MemoryManager:
    """Initialize SQLite and compose Core services for a local application."""
    resolved = resolve_runtime_paths(config)
    if config is None:
        config = DatabaseConfig.from_path(resolved.sqlite_path)

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
        chroma_persist_directory=resolved.chroma_path,
    )
    try:
        semantic_index = unit_of_work.semantic_index
        retrieval_service = DefaultRetrievalService(
            memory_repo=unit_of_work.memories,
            semantic_index=semantic_index,
        )
        manager = MemoryManager(
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
        manager.runtime_paths = resolved  # type: ignore[attr-defined]
        return manager
    except Exception:
        unit_of_work.close()
        raise
