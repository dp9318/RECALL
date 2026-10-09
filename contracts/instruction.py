"""Custom instruction contracts for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from contracts.base import Identifiable, InstructionStatus, Scope, TimestampMixin


@dataclass
class CustomInstruction(Identifiable, TimestampMixin):
    """User-authored custom instruction."""
    scope: Scope = Scope.GLOBAL
    project_id: Optional[UUID] = None
    content: str = ""
    status: InstructionStatus = InstructionStatus.ACTIVE
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == InstructionStatus.ACTIVE

    def scope_matches(self, project_id: Optional[UUID]) -> bool:
        if self.scope == Scope.GLOBAL:
            return True
        if self.scope == Scope.PROJECT:
            return self.project_id == project_id
        return False


@dataclass
class CustomInstructionCreateRequest:
    """Request to create a custom instruction."""
    scope: Scope = Scope.GLOBAL
    project_id: Optional[UUID] = None
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomInstructionUpdateRequest:
    """Request to update a custom instruction."""
    content: Optional[str] = None
    status: Optional[InstructionStatus] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class CustomInstructionListParams:
    """Parameters for listing custom instructions."""
    scope: Optional[Scope] = None
    project_id: Optional[UUID] = None
    status: Optional[InstructionStatus] = None
    limit: int = 50
    offset: int = 0