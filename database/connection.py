"""SQLite connection management for RECALL."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from database.config import DatabaseConfig, MigrationConfig
from database.exceptions import (
    ConfigurationError,
    ConnectionError,
    InitializationError,
    TransactionError,
)


class DatabaseConnection:
    """Manages SQLite connections with proper configuration."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection."""
        if self._connection is not None:
            return self._connection

        try:
            self._config.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self._config.path,
                timeout=self._config.timeout,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                isolation_level=self._config.isolation_level,
            )
            conn.row_factory = sqlite3.Row
            self._apply_pragmas(conn)
            self._connection = conn
            return conn
        except sqlite3.Error as e:
            raise ConnectionError(f"Failed to connect to database: {e}", cause=e) from e

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply all configured pragmas to the connection."""
        pragmas = self._config.get_pragmas()
        for name, value in pragmas.items():
            try:
                if isinstance(value, str):
                    conn.execute(f"PRAGMA {name} = '{value}'")
                else:
                    conn.execute(f"PRAGMA {name} = {value}")
            except sqlite3.Error as e:
                raise ConfigurationError(
                    f"Failed to set pragma {name}={value}: {e}", cause=e
                ) from e

    def close(self) -> None:
        """Close the connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
            finally:
                self._connection = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            return self.connect()
        return self._connection


class Transaction:
    """Database transaction context manager for isolation_level=None."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._committed = False
        self._rolled_back = False
        self._active = False

    def __enter__(self) -> Transaction:
        # With isolation_level=None, we must explicitly start a transaction
        self._conn.execute("BEGIN")
        self._active = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.rollback()
        elif not self._committed and not self._rolled_back:
            self.commit()

    def commit(self) -> None:
        """Commit the transaction."""
        if self._committed:
            raise TransactionError("Transaction already committed")
        if self._rolled_back:
            raise TransactionError("Transaction already rolled back")
        if not self._active:
            raise TransactionError("No active transaction to commit")
        try:
            self._conn.execute("COMMIT")
            self._committed = True
            self._active = False
        except sqlite3.Error as e:
            raise TransactionError(f"Failed to commit transaction: {e}", cause=e) from e

    def rollback(self) -> None:
        """Rollback the transaction."""
        if self._rolled_back:
            raise TransactionError("Transaction already rolled back")
        if self._committed:
            raise TransactionError("Transaction already committed")
        if not self._active:
            raise TransactionError("No active transaction to rollback")
        try:
            self._conn.execute("ROLLBACK")
            self._rolled_back = True
            self._active = False
        except sqlite3.Error as e:
            raise TransactionError(f"Failed to rollback transaction: {e}", cause=e) from e


@contextmanager
def get_connection(config: DatabaseConfig) -> Iterator[sqlite3.Connection]:
    """Context manager for a database connection."""
    db = DatabaseConnection(config)
    conn = db.connect()
    try:
        yield conn
    finally:
        db.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[Transaction]:
    """Context manager for a database transaction."""
    tx = Transaction(conn)
    try:
        with tx:
            yield tx
    except Exception:
        if not tx._committed and not tx._rolled_back:
            tx.rollback()
        raise
    else:
        if not tx._committed and not tx._rolled_back:
            tx.commit()


def initialize_database(config: DatabaseConfig) -> None:
    """Initialize database with required pragmas, run migrations, and verify connectivity."""
    from database.migrations.manager import MigrationManager
    from database.exceptions import DatabaseError

    db = DatabaseConnection(config)
    try:
        conn = db.connect()
        conn.execute("SELECT 1")
        # Run migrations
        migration_config = MigrationConfig(migrations_dir=Path(__file__).parent / "migrations" / "versions")
        manager = MigrationManager(config, migration_config)
        manager.apply_migrations(conn)
        # Verify schema after migrations
        manager.verify_schema(conn)
    except sqlite3.Error as e:
        raise InitializationError(f"Database initialization failed: {e}", cause=e) from e
    except DatabaseError:
        raise
    finally:
        db.close()