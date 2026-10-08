"""Base contracts and common types for RECALL modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID, uuid4


class Scope(str, Enum):
    """Scope of a memory or instruction."""
    GLOBAL = "global"
    PROJECT = "project"


class MemoryStatus(str, Enum):
    """Status of a memory record."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETED = "deleted"


class InstructionStatus(str, Enum):
    """Status of a custom instruction."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"


class ConflictResolutionStatus(str, Enum):
    """Result status of conflict resolution."""
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Generic result wrapper for operations."""
    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, value: T, metadata: Optional[dict[str, Any]] = None, **extra_metadata: Any) -> Result[T]:
        combined = {**(metadata or {}), **extra_metadata}
        return cls(success=True, value=value, metadata=combined)

    @classmethod
    def err(cls, error: str, metadata: Optional[dict[str, Any]] = None, **extra_metadata: Any) -> Result[T]:
        combined = {**(metadata or {}), **extra_metadata}
        return cls(success=False, error=error, metadata=combined)


@dataclass
class PaginationParams:
    """Pagination parameters for list operations."""
    limit: int = 50
    offset: int = 0

    def __post_init__(self):
        if self.limit <= 0:
            self.limit = 50
        if self.limit > 200:
            self.limit = 200
        if self.offset < 0:
            self.offset = 0


@dataclass
class PaginatedResult(Generic[T]):
    """Paginated result wrapper."""
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total


@dataclass
class TimestampMixin:
    """Mixin for timestamp fields."""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Identifiable:
    """Mixin for identifiable entities."""
    id: UUID = field(default_factory=uuid4)