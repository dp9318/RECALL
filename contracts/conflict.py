"""Conflict resolution contracts for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from contracts.base import ConflictResolutionStatus, Identifiable, TimestampMixin
from contracts.memory import Memory


class ConflictType(str, Enum):
    """Type of conflict detected."""
    CONTRADICTORY_CLAIM = "contradictory_claim"
    DUPLICATE_ENTITY = "duplicate_entity"
    STALE_INFORMATION = "stale_information"
    SCOPE_MISMATCH = "scope_mismatch"


@dataclass
class ConflictCandidate(Identifiable, TimestampMixin):
    """A memory candidate involved in a conflict."""
    memory: Optional[Memory] = None
    relevance_score: float = 0.0
    conflict_type: ConflictType = ConflictType.CONTRADICTORY_CLAIM
    evidence: list[str] = field(default_factory=list)


@dataclass
class ConflictDetectionResult:
    """Result of conflict detection."""
    conflicts_detected: bool = False
    candidates: list[ConflictCandidate] = field(default_factory=list)
    topic: Optional[str] = None


@dataclass
class ResolutionDecision:
    """A single resolution decision for a candidate."""
    candidate_id: UUID
    action: str  # "keep", "supersede", "archive", "unresolved"
    reason: str
    confidence: float = 0.0
    model_used: bool = False


@dataclass
class ConflictResolutionResult:
    """Result of conflict resolution."""
    status: ConflictResolutionStatus = ConflictResolutionStatus.UNRESOLVED
    decisions: list[ResolutionDecision] = field(default_factory=list)
    preferred_candidates: list[ConflictCandidate] = field(default_factory=list)
    superseded_candidates: list[ConflictCandidate] = field(default_factory=list)
    unresolved_candidates: list[ConflictCandidate] = field(default_factory=list)
    resolution_reason: str = ""
    model_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_resolved(self) -> bool:
        return self.status == ConflictResolutionStatus.RESOLVED

    def has_unresolved(self) -> bool:
        return len(self.unresolved_candidates) > 0 or self.status in (
            ConflictResolutionStatus.UNRESOLVED,
            ConflictResolutionStatus.ABSTAINED,
        )


@dataclass
class ConflictResolutionRequest:
    """Request to resolve conflicts."""
    candidates: list[ConflictCandidate]
    custom_instructions: list[Any] = field(default_factory=list)  # CustomInstruction
    project_context: Optional[Any] = None  # Project
    session_context: Optional[Any] = None  # Session