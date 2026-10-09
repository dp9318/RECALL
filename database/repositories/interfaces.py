"""Repository interfaces for RECALL database operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from contracts.base import PaginatedResult, PaginationParams, Result
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from contracts.memory import Memory, MemoryCreateRequest, MemoryLineage, MemorySearchParams, MemoryUpdateRequest
from contracts.project import Project, ProjectCreateRequest, ProjectUpdateRequest, Session, SessionCreateRequest, SessionUpdateRequest


class ProjectRepository(ABC):
    """Repository interface for project operations."""

    @abstractmethod
    def create(self, request: ProjectCreateRequest) -> Result[Project]:
        """Create a new project."""
        ...

    @abstractmethod
    def get(self, project_id: UUID) -> Result[Optional[Project]]:
        """Get a project by ID."""
        ...

    @abstractmethod
    def update(self, project_id: UUID, request: ProjectUpdateRequest) -> Result[Optional[Project]]:
        """Update a project."""
        ...

    @abstractmethod
    def delete(self, project_id: UUID) -> Result[bool]:
        """Delete a project."""
        ...

    @abstractmethod
    def list(self, params: PaginationParams) -> Result[PaginatedResult[Project]]:
        """List projects with pagination."""
        ...


class SessionRepository(ABC):
    """Repository interface for session operations."""

    @abstractmethod
    def create(self, request: SessionCreateRequest) -> Result[Session]:
        """Create a new session."""
        ...

    @abstractmethod
    def get(self, session_id: UUID) -> Result[Optional[Session]]:
        """Get a session by ID."""
        ...

    @abstractmethod
    def get_active_for_project(self, project_id: UUID) -> Result[Optional[Session]]:
        """Get the active session for a project."""
        ...

    @abstractmethod
    def update(self, session_id: UUID, request: SessionUpdateRequest) -> Result[Optional[Session]]:
        """Update a session."""
        ...

    @abstractmethod
    def list(self, params: PaginationParams, project_id: Optional[UUID] = None) -> Result[PaginatedResult[Session]]:
        """List sessions with pagination."""
        ...


class MemoryRepository(ABC):
    """Repository interface for memory operations."""

    @abstractmethod
    def create(self, request: MemoryCreateRequest) -> Result[Memory]:
        """Create a new memory."""
        ...

    @abstractmethod
    def get(self, memory_id: UUID) -> Result[Optional[Memory]]:
        """Get a memory by ID."""
        ...

    @abstractmethod
    def update(self, memory_id: UUID, request: MemoryUpdateRequest) -> Result[Optional[Memory]]:
        """Update a memory."""
        ...

    @abstractmethod
    def delete(self, memory_id: UUID) -> Result[bool]:
        """Delete (deactivate) a memory."""
        ...

    @abstractmethod
    def search(self, params: MemorySearchParams) -> Result[PaginatedResult[Memory]]:
        """Search memories with filters."""
        ...

    @abstractmethod
    def get_active_for_project(self, project_id: UUID, limit: int = 50) -> Result[list[Memory]]:
        """Get active memories for a project."""
        ...

    @abstractmethod
    def get_by_ids(self, memory_ids: list[UUID]) -> Result[list[Memory]]:
        """Get memories by IDs."""
        ...

    @abstractmethod
    def create_lineage(self, lineage: MemoryLineage) -> Result[MemoryLineage]:
        """Create a lineage record."""
        ...

    @abstractmethod
    def get_lineage(self, memory_id: UUID) -> Result[list[MemoryLineage]]:
        """Get lineage for a memory."""
        ...


class CustomInstructionRepository(ABC):
    """Repository interface for custom instruction operations."""

    @abstractmethod
    def create(self, request: CustomInstructionCreateRequest) -> Result[CustomInstruction]:
        """Create a new custom instruction."""
        ...

    @abstractmethod
    def get(self, instruction_id: UUID) -> Result[Optional[CustomInstruction]]:
        """Get a custom instruction by ID."""
        ...

    @abstractmethod
    def update(self, instruction_id: UUID, request: CustomInstructionUpdateRequest) -> Result[Optional[CustomInstruction]]:
        """Update a custom instruction."""
        ...

    @abstractmethod
    def delete(self, instruction_id: UUID) -> Result[bool]:
        """Delete (deactivate) a custom instruction."""
        ...

    @abstractmethod
    def list(self, params: CustomInstructionListParams) -> Result[PaginatedResult[CustomInstruction]]:
        """List custom instructions with filters."""
        ...

    @abstractmethod
    def get_active_for_scope(self, scope: str, project_id: Optional[UUID] = None) -> Result[list[CustomInstruction]]:
        """Get active instructions for a scope."""
        ...


class SemanticIndexRepository(ABC):
    """Repository interface for semantic index (ChromaDB) operations."""

    @abstractmethod
    def index_memory(self, memory: Memory) -> Result[bool]:
        """Index a memory in the semantic store."""
        ...

    @abstractmethod
    def update_memory(self, memory: Memory) -> Result[bool]:
        """Update a memory in the semantic store."""
        ...

    @abstractmethod
    def remove_memory(self, memory_id: UUID) -> Result[bool]:
        """Remove a memory from the semantic store."""
        ...

    @abstractmethod
    def search_similar(self, query: str, project_id: Optional[UUID], limit: int) -> Result[list[tuple[UUID, float]]]:
        """Search for similar memories. Returns (memory_id, score) tuples."""
        ...

    @abstractmethod
    def rebuild_from_canonical(self, memories: list[Memory]) -> Result[int]:
        """Rebuild the semantic index from canonical memories. Returns count indexed."""
        ...

    @abstractmethod
    def health_check(self) -> Result[dict[str, Any]]:
        """Check health of semantic index."""
        ...


class DatabaseTransaction(ABC):
    """Interface for database transactions."""

    @abstractmethod
    def __enter__(self) -> DatabaseTransaction:
        ...

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...

    @abstractmethod
    def commit(self) -> None:
        ...

    @abstractmethod
    def rollback(self) -> None:
        ...


class UnitOfWork(ABC):
    """Unit of work pattern for atomic operations."""

    @property
    @abstractmethod
    def projects(self) -> ProjectRepository:
        ...

    @property
    @abstractmethod
    def sessions(self) -> SessionRepository:
        ...

    @property
    @abstractmethod
    def memories(self) -> MemoryRepository:
        ...

    @property
    @abstractmethod
    def custom_instructions(self) -> CustomInstructionRepository:
        ...

    @property
    @abstractmethod
    def semantic_index(self) -> SemanticIndexRepository:
        ...

    @abstractmethod
    def begin(self) -> DatabaseTransaction:
        """Begin a transaction."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the unit of work."""
        ...