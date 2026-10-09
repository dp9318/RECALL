"""Memory domain contracts for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from contracts.base import Identifiable, MemoryStatus, Scope, TimestampMixin


@dataclass
class Memory(Identifiable, TimestampMixin):
    """Canonical memory record."""
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    scope: Scope = Scope.GLOBAL
    memory_type: str = "general"
    content: str = ""
    status: MemoryStatus = MemoryStatus.ACTIVE
    provenance: Optional[str] = None
    supersedes_id: Optional[UUID] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == MemoryStatus.ACTIVE

    def is_historical(self) -> bool:
        return self.status in (MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED)


@dataclass
class MemoryLineage(Identifiable, TimestampMixin):
    """Lineage/supersession relationship between memories."""
    parent_id: UUID = field(default_factory=lambda: UUID(int=0))
    child_id: UUID = field(default_factory=lambda: UUID(int=0))
    relationship: str = "supersedes"
    reason: Optional[str] = None


@dataclass
class MemoryCreateRequest:
    """Request to create a new memory."""
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    scope: Scope = Scope.GLOBAL
    memory_type: str = "general"
    content: str = ""
    provenance: Optional[str] = None
    supersedes_id: Optional[UUID] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryUpdateRequest:
    """Request to update an existing memory."""
    content: Optional[str] = None
    status: Optional[MemoryStatus] = None
    metadata: Optional[dict[str, Any]] = None
    supersedes_id: Optional[UUID] = None


@dataclass
class MemorySearchParams:
    """Parameters for memory search."""
    query: Optional[str] = None
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    scope: Optional[Scope] = None
    memory_type: Optional[str] = None
    status: Optional[MemoryStatus] = None
    limit: int = 50
    offset: int = 0
    include_historical: bool = False