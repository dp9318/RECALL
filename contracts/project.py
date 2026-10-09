"""Project and session contracts for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from contracts.base import Identifiable, TimestampMixin


@dataclass
class Project(Identifiable, TimestampMixin):
    """Project record."""
    name: str = ""
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectCreateRequest:
    """Request to create a project."""
    name: str = ""
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectUpdateRequest:
    """Request to update a project."""
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class Session(Identifiable, TimestampMixin):
    """Session record."""
    project_id: UUID = field(default_factory=lambda: UUID(int=0))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.ended_at is None


@dataclass
class SessionCreateRequest:
    """Request to create a session."""
    project_id: UUID = field(default_factory=lambda: UUID(int=0))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionUpdateRequest:
    """Request to update a session."""
    ended_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None