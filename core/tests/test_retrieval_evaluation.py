from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from math import log2
from uuid import UUID, uuid4

import pytest

from contracts.base import MemoryStatus, Result, Scope
from contracts.memory import Memory
from contracts.retrieval import RetrievalRequest
from intelligence.retrieval import DefaultRetrievalService


@dataclass(frozen=True)
class RetrievalEvalCase:
    name: str
    query: str
    project_id: UUID
    relevant_ids: set[UUID]
    semantic_hits: list[tuple[UUID, float]]


class FakeMemoryRepository:
    def __init__(self, memories: Iterable[Memory]):
        self._memories = {memory.id: memory for memory in memories}

    def get_by_ids(self, ids: list[UUID]) -> Result[list[Memory]]:
        return Result.ok([
            self._memories[memory_id]
            for memory_id in ids
            if memory_id in self._memories
        ])

    def search(self, params):
        items = list(self._memories.values())
        if params.project_id is not None:
            items = [
                memory for memory in items
                if memory.project_id == params.project_id or memory.scope == Scope.GLOBAL
            ]
        if params.status is not None:
            items = [memory for memory in items if memory.status == params.status]
        return Result.ok(items)


class FakeSemanticIndex:
    def __init__(self, hits_by_query: dict[str, list[tuple[UUID, float]]]):
        self._hits_by_query = hits_by_query

    def search_similar(self, query: str, project_id: UUID | None, limit: int):
        hits = list(self._hits_by_query.get(query, []))
        if limit > 0:
            hits = hits[:limit]
        return Result.ok(hits)


def _make_memory(
    *,
    memory_id: UUID,
    project_id: UUID | None,
    content: str,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    scope: Scope = Scope.PROJECT,
) -> Memory:
    now = datetime.now(timezone.utc)
    return Memory(
        id=memory_id,
        project_id=project_id,
        session_id=None,
        scope=scope,
        memory_type="general",
        content=content,
        status=status,
        provenance="user_explicit",
        created_at=now,
        updated_at=now,
    )


def _build_dataset():
    project_a = uuid4()
    project_b = uuid4()
    memories = [
        _make_memory(
            memory_id=uuid4(),
            project_id=project_a,
            content="A car provides convenient transportation for commuting.",
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=project_a,
            content="A bicycle is powered by pedaling and suits short trips.",
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=project_a,
            content="Rainy weather is common in Seattle.",
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=project_b,
            content="A car is useful for road trips.",
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=None,
            scope=Scope.GLOBAL,
            content="Automobile travel is a common form of transportation.",
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=project_a,
            content="A car is useful for daily commuting.",
            status=MemoryStatus.ARCHIVED,
        ),
        _make_memory(
            memory_id=uuid4(),
            project_id=project_a,
            content="Car battery replacement is a frequent maintenance issue.",
        ),
    ]
    return project_a, project_b, memories


def _recall_at_k(returned_ids: list[UUID], relevant_ids: set[UUID], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return len(set(returned_ids[:k]).intersection(relevant_ids)) / len(relevant_ids)


def _mrr(returned_ids: list[UUID], relevant_ids: set[UUID]) -> float:
    if not relevant_ids:
        return 0.0
    for index, memory_id in enumerate(returned_ids, start=1):
        if memory_id in relevant_ids:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(returned_ids: list[UUID], relevant_ids: set[UUID], k: int) -> float:
    if not relevant_ids:
        return 0.0
    dcg = 0.0
    for rank, memory_id in enumerate(returned_ids[:k], start=1):
        if memory_id in relevant_ids:
            dcg += (2 ** 2 - 1) / log2(rank + 1)
    ideal = 0.0
    for rank in range(1, min(len(relevant_ids), k) + 1):
        ideal += (2 ** 2 - 1) / log2(rank + 1)
    return dcg / ideal if ideal else 0.0


def _run_case(case: RetrievalEvalCase, memories: list[Memory]) -> tuple[list[UUID], dict[str, float]]:
    repository = FakeMemoryRepository(memories)
    service = DefaultRetrievalService(
        memory_repo=repository,
        semantic_index=FakeSemanticIndex({case.query: case.semantic_hits}),
    )
    result = service.retrieve(
        RetrievalRequest(
            query=case.query,
            project_id=case.project_id,
            use_semantic=True,
            use_structured=False,
            limit=5,
        )
    )
    assert result.success, result.error
    returned_ids = [memory.id for memory in result.value.memories]
    metrics = {
        "recall_at_3": _recall_at_k(returned_ids, case.relevant_ids, 3),
        "mrr": _mrr(returned_ids, case.relevant_ids),
        "ndcg_at_3": _ndcg_at_k(returned_ids, case.relevant_ids, 3),
    }
    return returned_ids, metrics


def _baseline_cases(project_a: UUID, memories: list[Memory]) -> list[RetrievalEvalCase]:
    return [
        RetrievalEvalCase(
            name="different_wording_semantic_match",
            query="automobile travel",
            project_id=project_a,
            relevant_ids={memories[0].id, memories[4].id},
            semantic_hits=[
                (memories[0].id, 0.94),
                (memories[6].id, 0.87),
                (memories[4].id, 0.83),
                (memories[1].id, 0.16),
                (memories[2].id, 0.05),
            ],
        ),
        RetrievalEvalCase(
            name="project_scope_filter",
            query="daily commuting",
            project_id=project_a,
            relevant_ids={memories[0].id, memories[4].id},
            semantic_hits=[
                (memories[0].id, 0.96),
                (memories[5].id, 0.94),
                (memories[6].id, 0.70),
                (memories[4].id, 0.12),
            ],
        ),
        RetrievalEvalCase(
            name="inactive_memory_excluded",
            query="car battery",
            project_id=project_a,
            relevant_ids={memories[6].id},
            semantic_hits=[
                (memories[6].id, 0.96),
                (memories[0].id, 0.82),
            ],
        ),
        RetrievalEvalCase(
            name="no_relevant_matches",
            query="quantum entanglement",
            project_id=project_a,
            relevant_ids=set(),
            semantic_hits=[],
        ),
    ]


def test_retrieval_evaluation_baseline_metrics():
    project_a, _, memories = _build_dataset()
    cases = _baseline_cases(project_a, memories)
    summary = {}
    for case in cases:
        returned_ids, metrics = _run_case(case, memories)
        summary[case.name] = {
            "returned_ids": [str(memory_id) for memory_id in returned_ids],
            "recall_at_3": metrics["recall_at_3"],
            "mrr": metrics["mrr"],
            "ndcg_at_3": metrics["ndcg_at_3"],
        }

        if case.relevant_ids:
            assert metrics["recall_at_3"] >= 1.0, f"{case.name} missed a relevant memory: {summary[case.name]}"
            assert metrics["mrr"] >= 0.5, f"{case.name} MRR too low: {summary[case.name]}"
            assert metrics["ndcg_at_3"] >= 0.5, f"{case.name} NDCG too low: {summary[case.name]}"
        else:
            assert returned_ids == [], f"{case.name} should return no results: {summary[case.name]}"

    assert summary["different_wording_semantic_match"]["returned_ids"]
    assert str(memories[5].id) not in summary["inactive_memory_excluded"]["returned_ids"]
    assert str(memories[6].id) in summary["inactive_memory_excluded"]["returned_ids"]

    print(json.dumps(summary, indent=2, sort_keys=True))
