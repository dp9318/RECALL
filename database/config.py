"""Database configuration for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuration for SQLite database connection."""

    path: Path
    timeout: float = 30.0
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    foreign_keys: bool = True
    busy_timeout: int = 5000
    cache_size: int = -2000
    temp_store: str = "MEMORY"
    pragmas: dict[str, str | int] = field(default_factory=dict)
    isolation_level: Optional[str] = None

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.busy_timeout < 0:
            raise ValueError("busy_timeout must be non-negative")

    def get_pragmas(self) -> dict[str, str | int]:
        """Get all pragmas including defaults."""
        pragmas = {
            "journal_mode": self.journal_mode,
            "synchronous": self.synchronous,
            "foreign_keys": "ON" if self.foreign_keys else "OFF",
            "busy_timeout": self.busy_timeout,
            "cache_size": self.cache_size,
            "temp_store": self.temp_store,
        }
        pragmas.update(self.pragmas)
        return pragmas

    @classmethod
    def from_path(cls, path: str | Path, **kwargs: Any) -> DatabaseConfig:
        """Create config from a path string."""
        return cls(path=Path(path), **kwargs)


@dataclass(frozen=True)
class MigrationConfig:
    """Configuration for migration behavior."""

    migrations_dir: Path
    table_name: str = "schema_version"
    lock_timeout: float = 10.0

    def __post_init__(self) -> None:
        if self.lock_timeout <= 0:
            raise ValueError("lock_timeout must be positive")