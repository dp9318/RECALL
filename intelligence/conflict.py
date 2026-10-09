"""Conflict resolution service interfaces for RECALL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from contracts.base import Result
from contracts.conflict import (
    ConflictCandidate,
    ConflictDetectionResult,
    ConflictResolutionRequest,
    ConflictResolutionResult,
)
from contracts.instruction import CustomInstruction
from contracts.memory import Memory
from contracts.project import Project, Session


class ConflictDetector(ABC):
    """Service interface for conflict detection."""

    @abstractmethod
    def detect(self, memories: list[Memory], query: str, project_id: Optional[UUID] = None) -> Result[ConflictDetectionResult]:
        """Detect conflicts among memories for a query."""
        ...

    @abstractmethod
    def package_candidates(self, memories: list[Memory], conflict_type: str) -> list[ConflictCandidate]:
        """Package memories as conflict candidates with metadata."""
        ...


class ConflictResolver(ABC):
    """Service interface for conflict resolution."""

    @abstractmethod
    def resolve(self, request: ConflictResolutionRequest) -> Result[ConflictResolutionResult]:
        """Resolve conflicts using deterministic rules and optional LLM arbitration."""
        ...

    @abstractmethod
    def apply_deterministic_rules(self, candidates: list[ConflictCandidate], custom_instructions: list[CustomInstruction]) -> ConflictResolutionResult:
        """Apply deterministic precedence rules without LLM."""
        ...

    @abstractmethod
    def invoke_llm_arbitration(self, candidates: list[ConflictCandidate], context: str) -> Result[ConflictResolutionResult]:
        """Invoke local LLM for bounded arbitration."""
        ...


class ConflictResolutionService(ABC):
    """Combined service for conflict detection and resolution."""

    @abstractmethod
    def detect_and_resolve(self, request: ConflictResolutionRequest) -> Result[ConflictResolutionResult]:
        """Detect and resolve conflicts in one operation."""
        ...

    @property
    @abstractmethod
    def detector(self) -> ConflictDetector:
        ...

    @property
    @abstractmethod
    def resolver(self) -> ConflictResolver:
        ...