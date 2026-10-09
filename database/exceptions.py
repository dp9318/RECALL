"""Database module exceptions."""

from __future__ import annotations


class DatabaseError(Exception):
    """Base exception for database errors."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class ConfigurationError(DatabaseError):
    """Raised when database configuration is invalid."""


class ConnectionError(DatabaseError):
    """Raised when database connection fails."""


class MigrationError(DatabaseError):
    """Raised when a migration fails."""


class SchemaError(DatabaseError):
    """Raised when schema validation fails."""


class TransactionError(DatabaseError):
    """Raised when a transaction operation fails."""


class IntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""


class NotFoundError(DatabaseError):
    """Raised when a requested record is not found."""


class VersionConflictError(DatabaseError):
    """Raised when optimistic locking detects a version conflict."""


class InitializationError(DatabaseError):
    """Raised when database initialization fails."""


class ForeignKeyError(IntegrityError):
    """Raised when a foreign key constraint is violated."""


class UniqueConstraintError(IntegrityError):
    """Raised when a unique constraint is violated."""


class CheckConstraintError(IntegrityError):
    """Raised when a check constraint is violated."""