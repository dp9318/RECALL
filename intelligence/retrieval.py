"""Retrieval service interfaces and default implementations for RECALL."""

from __future__ import annotations

import re
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


class DefaultEmbeddingService(EmbeddingService):
    """Deterministic bag-of-words embedding generator used when no external model is present."""

    def __init__(self, dimensions: int = 64):
        self.dimensions = max(8, dimensions)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        if not text:
            return []
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return [token for token in text.split() if token]

    def generate_embedding(self, text: str) -> Result[list[float]]:
        tokens = self._tokenize(text)
        vector = [0.0] * self.dimensions
        if not tokens:
            return Result.ok(vector)
        for token in tokens:
            index = abs(sum(ord(char) for char in token)) % self.dimensions
            vector[index] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        if norm:
            vector = [value / norm for value in vector]
        return Result.ok(vector)

    def generate_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        return Result.ok([self.generate_embedding(text).value for text in texts])


class DefaultRetrievalService(RetrievalService):
    """Default retrieval implementation combining structured and semantic evidence."""

    def __init__(
        self,
        memory_repo=None,
        semantic_index=None,
        embedding_service: Optional[EmbeddingService] = None,
        limit: int = 20,
    ) -> None:
        self.memory_repo = memory_repo
        self.semantic_index = semantic_index
        self.embedding_service = embedding_service or DefaultEmbeddingService()
        self.limit = limit

    def retrieve(self, request: RetrievalRequest) -> Result[RetrievalResult]:
        memories: list[Memory] = []
        structured_memories: list[Memory] = []

        if request.use_structured:
            search_params = MemorySearchParams(
                query=request.query,
                project_id=request.project_id,
                session_id=request.session_id,
                limit=request.limit,
                include_historical=request.include_historical,
            )
            structured = self.search_structured(search_params)
            if not structured.success:
                return Result.err(structured.error or "Structured retrieval failed")
            structured_memories = structured.value or []
            memories.extend(structured_memories)

        if request.use_semantic and self.semantic_index is not None:
            semantic_hits = self.search_semantic(request.query, request.project_id, request.limit)
            if not semantic_hits.success:
                return Result.err(semantic_hits.error or "Semantic retrieval failed")
            if semantic_hits.value:
                semantic_ids = [memory_id for memory_id, _ in semantic_hits.value]
                if self.memory_repo is not None:
                    fetch_result = self.memory_repo.get_by_ids(semantic_ids)
                    if fetch_result.success:
                        memories.extend(fetch_result.value or [])

        deduped: dict[UUID, Memory] = {}
        for memory in memories:
            if memory.id not in deduped:
                deduped[memory.id] = memory

        ranked = self.rank_results(list(deduped.values()), request.query, request.project_id)
        ranked = ranked[: request.limit]

        return Result.ok(
            RetrievalResult(
                memories=ranked,
                total_found=len(ranked),
                semantic_results=len([1 for _, _ in (self.search_semantic(request.query, request.project_id, request.limit).value or [])]) if request.use_semantic and self.semantic_index is not None else 0,
                structured_results=len(structured_memories),
                query=request.query,
                project_id=request.project_id,
            )
        )

    def search_structured(self, params: MemorySearchParams) -> Result[list[Memory]]:
        if self.memory_repo is None:
            return Result.ok([])
        result = self.memory_repo.search(params)
        if not result.success:
            return Result.err(result.error or "Structured memory search failed")
        items = result.value.items if hasattr(result.value, "items") else result.value
        return Result.ok(items or [])

    def search_semantic(self, query: str, project_id: Optional[UUID], limit: int) -> Result[list[tuple[UUID, float]]]:
        if self.semantic_index is not None:
            result = self.semantic_index.search_similar(query, project_id, limit)
            if not result.success:
                return Result.err(result.error or "Semantic search failed")
            return Result.ok(result.value or [])

        if self.memory_repo is None:
            return Result.ok([])

        search_result = self.memory_repo.search(
            MemorySearchParams(query=query, project_id=project_id, limit=limit, include_historical=True)
        )
        if not search_result.success:
            return Result.err(search_result.error or "Semantic fallback search failed")
        items = search_result.value.items if hasattr(search_result.value, "items") else search_result.value
        scored: list[tuple[UUID, float]] = []
        for memory in items or []:
            score = self._keyword_similarity(memory.content, query)
            scored.append((memory.id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return Result.ok(scored[:limit])

    def rank_results(self, memories: list[Memory], query: str, project_id: Optional[UUID]) -> list[Memory]:
        if not memories:
            return []

        ranked = []
        for memory in memories:
            score = self._keyword_similarity(memory.content, query)
            score += 0.15 if memory.project_id == project_id else 0.0
            score += 0.2 if memory.is_active() else 0.0
            score += 0.1 if memory.provenance in {"user_explicit", "explicit_user_update"} else 0.0
            ranked.append((memory, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return [memory for memory, _ in ranked]

    def detect_conflicts(self, memories: list[Memory], query: str) -> Result[list[Memory]]:
        if len(memories) < 2:
            return Result.ok([])

        conflicts: list[Memory] = []
        for index, left in enumerate(memories):
            for right in memories[index + 1 :]:
                if left.id == right.id:
                    continue
                if left.project_id != right.project_id and left.project_id is not None and right.project_id is not None:
                    continue
                if not left.is_active() or not right.is_active():
                    continue
                left_tokens = set(self._tokenize(left.content))
                right_tokens = set(self._tokenize(right.content))
                overlap = len(left_tokens & right_tokens)
                if overlap == 0 and query:
                    continue
                if self._keyword_similarity(left.content, right.content) > 0.15:
                    conflicts.extend([left, right])
        seen: set[UUID] = set()
        ordered: list[Memory] = []
        for memory in conflicts:
            if memory.id not in seen:
                seen.add(memory.id)
                ordered.append(memory)
        return Result.ok(ordered)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        if not text:
            return set()
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return {token for token in normalized.split() if token}

    @staticmethod
    def _keyword_similarity(left: str, right: str) -> float:
        if not left and not right:
            return 0.0
        left_tokens = DefaultRetrievalService._tokenize(left)
        right_tokens = DefaultRetrievalService._tokenize(right)
        if not left_tokens or not right_tokens:
            if left and right:
                return 0.2
            return 0.0
        overlap = len(left_tokens & right_tokens)
        denominator = max(len(left_tokens), len(right_tokens))
        if denominator == 0:
            return 0.0
        return overlap / denominator
