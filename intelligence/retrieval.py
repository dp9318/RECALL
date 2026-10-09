"""Retrieval service interfaces for RECALL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from contracts.base import Result
from contracts.memory import Memory, MemorySearchParams
from contracts.retrieval import RetrievalRequest, RetrievalResult


class RetrievalService(ABC):
    """Service interface for memory retrieval operations."""

    @abstractmethod
    def retrieve(self, request: RetrievalRequest) -> Result[RetrievalResult]:
        """Retrieve memories based on the request."""
        ...

    @abstractmethod
    def search_structured(self, params: MemorySearchParams) -> Result[list[Memory]]:
        """Perform structured/keyword-based search."""
        ...

    @abstractmethod
    def search_semantic(self, query: str, project_id: Optional[UUID], limit: int) -> Result[list[tuple[UUID, float]]]:
        """Perform semantic search. Returns (memory_id, score) tuples."""
        ...

    @abstractmethod
    def rank_results(self, memories: list[Memory], query: str, project_id: Optional[UUID]) -> list[Memory]:
        """Rank memories by relevance to query and project context."""
        ...

    @abstractmethod
    def detect_conflicts(self, memories: list[Memory], query: str) -> Result[list[Memory]]:
        """Detect potential conflicts among retrieved memories."""
        ...


class EmbeddingService(ABC):
    """Service interface for embedding generation."""

    @abstractmethod
    def generate_embedding(self, text: str) -> Result[list[float]]:
        """Generate embedding for text."""
        ...

    @abstractmethod
    def generate_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        """Generate embeddings for multiple texts."""
        ...