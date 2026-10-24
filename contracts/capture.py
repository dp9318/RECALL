"""Capture domain contracts for RECALL automatic memory capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

ELIGIBLE_CAPTURE_CATEGORIES = {
    "decision",
    "convention",
    "architecture",
    "task_outcome",
}


@dataclass
class CaptureEventRequest:
    """Request to capture an eligible event into persistent memory."""
    content: str
    event_category: str
    project_name: Optional[str] = None
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    source: str = "agent_hook"
    caller_idempotency_key: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureEventResponse:
    """Response from capture processing."""
    status: str  # 'persisted', 'suppressed_duplicate', 'skipped_boilerplate', 'skipped_low_relevance'
    memory_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    idempotency_key: Optional[str] = None
    redactions_applied: int = 0
    detail: Optional[str] = None
