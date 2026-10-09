"""SQLite Unit of Work implementation."""

from __future__ import annotations

import sys
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional
from uuid import UUID

from contracts.base import Result
from database.config import DatabaseConfig
from database.connection import DatabaseConnection, Transaction
from database.repositories import (
    CustomInstructionRepository,
    MemoryRepository,
    ProjectRepository,
    SemanticIndexRepository,
    SessionRepository,
    UnitOfWork,
)
from database.repositories.instruction_repo import SQLiteCustomInstructionRepository
from database.repositories.memory_repo import SQLiteMemoryRepository
from database.repositories.project_repo import SQLiteProjectRepository
from database.repositories.session_repo import SQLiteSessionRepository


class SQLiteUnitOfWork:
    """SQLite implementation of Unit of Work pattern."""

    def __init__(
        self,
        config: DatabaseConfig,
        semantic_index: Optional[SemanticIndexRepository] = None,
        embedding_function: Any = None,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        self._config = config
        self._db_connection = DatabaseConnection(config)
        self._conn: Optional[sqlite3.Connection] = None
        self._transaction: Optional[Transaction] = None
        self._embedding_function = embedding_function
        self._embedding_provider = embedding_provider
        self._embedding_model = embedding_model

        # Lazy-initialized repositories
        self._projects: Optional[SQLiteProjectRepository] = None
        self._sessions: Optional[SQLiteSessionRepository] = None
        self._memories: Optional[SQLiteMemoryRepository] = None
        self._custom_instructions: Optional[SQLiteCustomInstructionRepository] = None
        self._semantic_index = semantic_index

    def _ensure_connection(self) -> sqlite3.Connection:
        """Ensure we have an active connection."""
        if self._conn is None:
            self._conn = self._db_connection.connect()
        return self._conn

    @property
    def projects(self) -> ProjectRepository:
        if self._projects is None:
            self._projects = SQLiteProjectRepository(self._ensure_connection())
        return self._projects

    @property
    def sessions(self) -> SessionRepository:
        if self._sessions is None:
            self._sessions = SQLiteSessionRepository(self._ensure_connection())
        return self._sessions

    @property
    def memories(self) -> MemoryRepository:
        if self._memories is None:
            self._memories = SQLiteMemoryRepository(self._ensure_connection())
        return self._memories

    @property
    def custom_instructions(self) -> CustomInstructionRepository:
        if self._custom_instructions is None:
            self._custom_instructions = SQLiteCustomInstructionRepository(self._ensure_connection())
        return self._custom_instructions

    @property
    def semantic_index(self) -> SemanticIndexRepository:
        if self._semantic_index is None:
            # Lazy import to avoid circular dependency
            from database.repositories.semantic_index_repo import SQLiteSemanticIndexRepository
            self._semantic_index = SQLiteSemanticIndexRepository(
                self._ensure_connection(),
                persist_directory=self._config.path.with_suffix(
                    self._config.path.suffix + ".chromadb"
                ),
                embedding_function=self._embedding_function,
                embedding_provider=self._embedding_provider,
                embedding_model=self._embedding_model,
            )
        return self._semantic_index

    def begin(self) -> _TransactionContextManager:
        """Begin a transaction."""
        if self._transaction is not None:
            raise RuntimeError("Transaction already in progress")

        conn = self._ensure_connection()
        self._transaction = Transaction(conn)
        return _TransactionContextManager(self._transaction, self._clear_transaction)


    def _clear_transaction(self) -> None:
        """Clear the current transaction reference."""
        self._transaction = None

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._transaction is None:
            raise RuntimeError("No transaction in progress")
        if self._transaction._committed:
            raise RuntimeError("Transaction already committed")
        if self._transaction._rolled_back:
            raise RuntimeError("Transaction already rolled back")
        self._transaction.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._transaction is None:
            raise RuntimeError("No transaction in progress")
        if self._transaction._rolled_back:
            raise RuntimeError("Transaction already rolled back")
        if self._transaction._committed:
            raise RuntimeError("Transaction already committed")
        self._transaction.rollback()

    def close(self) -> None:
        """Close the unit of work and release resources."""
        try:
            if self._semantic_index is not None:
                close = getattr(self._semantic_index, "close", None)
                if callable(close):
                    close()
        finally:
            # Rollback any pending transaction
            if self._transaction and not self._transaction._committed and not self._transaction._rolled_back:
                try:
                    self._transaction.rollback()
                except Exception:
                    pass
            self._transaction = None

            # Close the database connection
            self._db_connection.close()
            self._conn = None

    def __enter__(self) -> SQLiteUnitOfWork:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


class _TransactionContextManager:
    """Context manager for transactions that properly handles rollback."""

    def __init__(self, transaction: Transaction, clear_callback: callable) -> None:
        self._transaction = transaction
        self._clear_callback = clear_callback

    def __enter__(self) -> Transaction:
        self._transaction.__enter__()
        return self._transaction

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        try:
            self._transaction.__exit__(exc_type, exc_val, exc_tb)
        finally:
            # Clear the transaction reference in the UnitOfWork
            self._clear_callback()
        # Don't suppress exceptions
        return False

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._transaction is None:
            raise RuntimeError("No transaction in progress")
        if self._transaction._committed:
            raise RuntimeError("Transaction already committed")
        if self._transaction._rolled_back:
            raise RuntimeError("Transaction already rolled back")
        self._transaction.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._transaction is None:
            raise RuntimeError("No transaction in progress")
        if self._transaction._rolled_back:
            raise RuntimeError("Transaction already rolled back")
        if self._transaction._committed:
            raise RuntimeError("Transaction already committed")
        self._transaction.rollback()