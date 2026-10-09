"""Migration manager for RECALL database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from database.config import DatabaseConfig, MigrationConfig
from database.connection import get_connection, transaction
from database.exceptions import MigrationError, SchemaError
from database.schema.ddl import ALL_TABLES, CREATE_INDEXES, SCHEMA_VERSION


@dataclass(frozen=True)
class Migration:
    """Represents a single migration."""

    version: int
    description: str
    sql: str


class MigrationManager:
    """Manages database schema migrations."""

    def __init__(self, config: DatabaseConfig, migration_config: Optional[MigrationConfig] = None) -> None:
        self._config = config
        self._migration_config = migration_config or MigrationConfig(
            migrations_dir=Path(__file__).parent / "versions"
        )
        self._migrations: list[Migration] = []
        self._load_migrations()

    def _load_migrations(self) -> None:
        """Load migrations from files and built-in initial migration."""
        self._migrations = []

        self._migrations.append(Migration(
            version=1,
            description="Initial schema",
            sql=self._get_initial_migration_sql()
        ))

        versions_dir = self._migration_config.migrations_dir
        if versions_dir.exists():
            for path in sorted(versions_dir.glob("*.sql")):
                version = self._extract_version(path.name)
                if version is not None and version > 1:
                    sql = path.read_text(encoding="utf-8")
                    self._migrations.append(Migration(
                        version=version,
                        description=f"Migration {version}",
                        sql=sql
                    ))

        self._migrations.sort(key=lambda m: m.version)

    def _extract_version(self, filename: str) -> Optional[int]:
        """Extract version number from migration filename (e.g., '002_add_table.sql' -> 2)."""
        try:
            parts = filename.split("_", 1)
            return int(parts[0])
        except (ValueError, IndexError):
            return None

    def _get_initial_migration_sql(self) -> str:
        """Get the SQL for the initial migration (version 1)."""
        statements = []
        statements.extend(ALL_TABLES)
        statements.extend(CREATE_INDEXES)
        return "\n".join(statements)

    def get_current_version(self, conn: sqlite3.Connection) -> int:
        """Get the current schema version from the database."""
        try:
            cursor = conn.execute(
                f"SELECT MAX(version) FROM {self._migration_config.table_name}"
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except sqlite3.OperationalError:
            return 0

    def get_applied_migrations(self, conn: sqlite3.Connection) -> list[int]:
        """Get list of applied migration versions."""
        try:
            cursor = conn.execute(
                f"SELECT version FROM {self._migration_config.table_name} ORDER BY version"
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []

    def apply_migrations(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Apply all pending migrations. Returns number of migrations applied."""
        if conn is not None:
            current_version = self.get_current_version(conn)
            applied = 0

            for migration in self._migrations:
                if migration.version <= current_version:
                    continue

                self._apply_migration(conn, migration)
                applied += 1

            return applied

        with get_connection(self._config) as conn:
            current_version = self.get_current_version(conn)
            applied = 0

            for migration in self._migrations:
                if migration.version <= current_version:
                    continue

                self._apply_migration(conn, migration)
                applied += 1

            return applied

    def _apply_migration(self, conn: sqlite3.Connection, migration: Migration) -> None:
        """Apply a single migration. DDL statements implicitly commit, so no transaction wrapper."""
        try:
            # Execute migration SQL (DDL statements implicitly commit)
            conn.executescript(migration.sql)
            # Record migration version (separate statement, auto-commits)
            conn.execute(
                f"INSERT INTO {self._migration_config.table_name} (version, description) VALUES (?, ?)",
                (migration.version, migration.description)
            )
        except sqlite3.Error as e:
            raise MigrationError(
                f"Failed to apply migration {migration.version}: {e}", cause=e
            ) from e

    def verify_schema(self, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Verify that the database schema matches expectations."""
        if conn is not None:
            return self._verify_schema_on_connection(conn)

        with get_connection(self._config) as conn:
            return self._verify_schema_on_connection(conn)

    def _verify_schema_on_connection(self, conn: sqlite3.Connection) -> bool:
        """Verify schema on an existing connection."""
        expected_tables = {
            "schema_version", "projects", "sessions", "memories",
            "memory_lineage", "custom_instructions",
            "memory_index_metadata", "instruction_index_metadata"
        }

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        actual_tables = {row[0] for row in cursor.fetchall()}

        missing = expected_tables - actual_tables
        if missing:
            raise SchemaError(f"Missing tables: {missing}")

        current_version = self.get_current_version(conn)
        if current_version != SCHEMA_VERSION:
            raise SchemaError(
                f"Schema version mismatch: expected {SCHEMA_VERSION}, got {current_version}"
            )

        return True

    def initialize(self) -> None:
        """Initialize database and apply all migrations."""
        with get_connection(self._config) as conn:
            self.apply_migrations(conn)
            self.verify_schema(conn)


@contextmanager
def migration_lock(conn: sqlite3.Connection, timeout: float = 10.0) -> Iterator[None]:
    """Acquire an advisory lock for migrations."""
    try:
        conn.execute("PRAGMA busy_timeout = ?", (int(timeout * 1000),))
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.execute("COMMIT")
    except sqlite3.Error as e:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise MigrationError(f"Failed to acquire migration lock: {e}", cause=e) from e