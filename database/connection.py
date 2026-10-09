"""SQLite connection management for RECALL."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import threading

from database.config import DatabaseConfig, MigrationConfig
from database.exceptions import (
    ConfigurationError,
    ConnectionError,
    InitializationError,
    TransactionError,
)


class ThreadSafeCursor:
    """Thread-safe proxy for a SQLite cursor."""

    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock

    def fetchone(self) -> Any:
        with self._lock:
            return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        with self._lock:
            return self._cursor.fetchall()

    def fetchmany(self, size: int | None = None) -> list[Any]:
        with self._lock:
            return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    def __iter__(self) -> ThreadSafeCursor:
        return self

    def __next__(self) -> Any:
        with self._lock:
            row = self._cursor.fetchone()
            if row is None:
                raise StopIteration
            return row

    @property
    def rowcount(self) -> int:
        with self._lock:
            return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        with self._lock:
            return self._cursor.lastrowid

    @property
    def description(self) -> Any:
        with self._lock:
            return self._cursor.description

    def close(self) -> None:
        with self._lock:
            self._cursor.close()

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._cursor, name)


class ThreadSafeConnection:
    """Thread-safe proxy for a SQLite connection using re-entrant synchronization."""

    def __init__(self, conn: sqlite3.Connection, lock: Optional[threading.RLock] = None) -> None:
        self._conn = conn
        self._lock = lock or threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def raw_connection(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, parameters: Any = ()) -> ThreadSafeCursor:
        with self._lock:
            cursor = self._conn.execute(sql, parameters)
            return ThreadSafeCursor(cursor, self._lock)

    def executemany(self, sql: str, parameters: Any) -> ThreadSafeCursor:
        with self._lock:
            cursor = self._conn.executemany(sql, parameters)
            return ThreadSafeCursor(cursor, self._lock)

    def executescript(self, sql_script: str) -> ThreadSafeCursor:
        with self._lock:
            cursor = self._conn.executescript(sql_script)
            return ThreadSafeCursor(cursor, self._lock)

    def cursor(self) -> ThreadSafeCursor:
        with self._lock:
            cursor = self._conn.cursor()
            return ThreadSafeCursor(cursor, self._lock)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @property
    def in_transaction(self) -> bool:
        with self._lock:
            return self._conn.in_transaction

    @property
    def total_changes(self) -> int:
        with self._lock:
            return self._conn.total_changes

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, factory: Any) -> None:
        with self._lock:
            self._conn.row_factory = factory

    def __enter__(self) -> ThreadSafeConnection:
        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._lock.release()

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._conn, name)


class DatabaseConnection:
    """Manages SQLite connections with proper configuration and thread synchronization."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._connection: Optional[ThreadSafeConnection] = None
        self._lock = threading.RLock()

    def connect(self) -> ThreadSafeConnection:
        """Create and configure a new SQLite connection."""
        with self._lock:
            if self._connection is not None:
                return self._connection

            try:
                self._config.path.parent.mkdir(parents=True, exist_ok=True)
                raw_conn = sqlite3.connect(
                    self._config.path,
                    timeout=self._config.timeout,
                    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                    isolation_level=self._config.isolation_level,
                    check_same_thread=False,
                )
                raw_conn.row_factory = sqlite3.Row
                self._apply_pragmas(raw_conn)
                self._connection = ThreadSafeConnection(raw_conn, self._lock)
                return self._connection
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
        with self._lock:
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
    def connection(self) -> ThreadSafeConnection:
        if self._connection is None:
            return self.connect()
        return self._connection


class Transaction:
    """Database transaction context manager with lock synchronization."""

    def __init__(self, conn: Any, lock: Optional[threading.RLock] = None) -> None:
        self._conn = conn
        self._lock = lock if lock is not None else getattr(conn, "lock", None)
        self._committed = False
        self._rolled_back = False
        self._active = False

    def __enter__(self) -> Transaction:
        if self._lock is not None:
            self._lock.acquire()
        try:
            # With isolation_level=None, we must explicitly start a transaction
            self._conn.execute("BEGIN")
            self._active = True
            return self
        except Exception:
            if self._lock is not None:
                self._lock.release()
            raise

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self.rollback()
            elif not self._committed and not self._rolled_back:
                self.commit()
        finally:
            if self._lock is not None:
                self._lock.release()

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