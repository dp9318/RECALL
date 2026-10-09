"""Retrieval and context assembly contracts for RECALL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from contracts.base import PaginationParams, Result
from contracts.conflict import ConflictResolutionResult
from contracts.instruction import CustomInstruction
from contracts.memory import Memory
from contracts.project import Project, Session


@dataclass
class RetrievalRequest:
    """Request for memory retrieval."""
    query: str
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    limit: int = 20
    include_historical: bool = False
    use_semantic: bool = True
    use_structured: bool = True


@dataclass
class RetrievalResult:
    """Result of memory retrieval."""
    memories: list[Memory] = field(default_factory=list)
    total_found: int = 0
    semantic_results: int = 0
    structured_results: int = 0
    query: str = ""
    project_id: Optional[UUID] = None


@dataclass
class ContextAssemblyRequest:
    """Request for context assembly."""
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    query: Optional[str] = None
    retrieval_limit: int = 20
    include_custom_instructions: bool = True
    include_resolved_conflicts: bool = True
    include_historical: bool = False


@dataclass
class AssembledContext:
    """Assembled context result for consumers."""
    project: Optional[Project] = None
    session: Optional[Session] = None
    custom_instructions: list[CustomInstruction] = field(default_factory=list)
    active_memories: list[Memory] = field(default_factory=list)
    resolved_memories: list[Memory] = field(default_factory=list)
    historical_memories: list[Memory] = field(default_factory=list)
    conflict_resolutions: list[ConflictResolutionResult] = field(default_factory=list)
    query: Optional[str] = None
    assembled_at: str = ""  # ISO format timestamp
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompactRequest:
    """Request for context compaction."""
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    preserve_lineage: bool = True
    max_active_memories: int = 50


@dataclass
class CompactResult:
    """Result of context compaction."""
    compacted_count: int = 0
    superseded_count: int = 0
    archived_count: int = 0
    preserved_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class UpdateContextRequest:
    """Request to update project context."""
    project_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    content: str = ""
    memory_type: str = "context_update"
    provenance: str = "user_explicit"


@dataclass
class UpdateContextResult:
    """Result of context update."""
    memory_id: UUID
    success: bool = True
    error: Optional[str] = None