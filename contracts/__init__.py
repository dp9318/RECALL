"""RECALL contracts package - shared DTOs and interfaces."""

from contracts.base import (
    ConflictResolutionStatus,
    Identifiable,
    InstructionStatus,
    MemoryStatus,
    PaginatedResult,
    PaginationParams,
    Result,
    Scope,
    TimestampMixin,
)
from contracts.conflict import (
    ConflictCandidate,
    ConflictDetectionResult,
    ConflictResolutionRequest,
    ConflictResolutionResult,
    ConflictType,
    ResolutionDecision,
)
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from contracts.memory import (
    Memory,
    MemoryCreateRequest,
    MemoryLineage,
    MemorySearchParams,
    MemoryUpdateRequest,
)
from contracts.project import (
    Project,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    Session,
    SessionCreateRequest,
    SessionUpdateRequest,
)
from contracts.retrieval import (
    AssembledContext,
    CompactRequest,
    CompactResult,
    ContextAssemblyRequest,
    RetrievalRequest,
    RetrievalResult,
    UpdateContextRequest,
    UpdateContextResult,
)

__all__ = [
    # base
    "Scope",
    "MemoryStatus",
    "InstructionStatus",
    "ConflictResolutionStatus",
    "Identifiable",
    "TimestampMixin",
    "Result",
    "PaginationParams",
    "PaginatedResult",
    # memory
    "Memory",
    "MemoryCreateRequest",
    "MemoryUpdateRequest",
    "MemorySearchParams",
    "MemoryLineage",
    # instruction
    "CustomInstruction",
    "CustomInstructionCreateRequest",
    "CustomInstructionUpdateRequest",
    "CustomInstructionListParams",
    # project
    "Project",
    "ProjectCreateRequest",
    "ProjectUpdateRequest",
    "Session",
    "SessionCreateRequest",
    "SessionUpdateRequest",
    # conflict
    "ConflictType",
    "ConflictCandidate",
    "ConflictDetectionResult",
    "ConflictResolutionRequest",
    "ConflictResolutionResult",
    "ResolutionDecision",
    # retrieval
    "RetrievalRequest",
    "RetrievalResult",
    "ContextAssemblyRequest",
    "AssembledContext",
    "CompactRequest",
    "CompactResult",
    "UpdateContextRequest",
    "UpdateContextResult",
]