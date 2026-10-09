from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError
from uuid import UUID, uuid4

import pytest

from contracts.base import ConflictResolutionStatus, MemoryStatus, Result, Scope
from contracts.conflict import (
    ConflictCandidate,
    ConflictDetectionResult,
    ConflictResolutionRequest,
    ConflictResolutionResult,
)
from contracts.memory import Memory
from contracts.project import Project
from intelligence.conflict import (
    DefaultConflictDetector,
    DefaultConflictResolutionService,
    DefaultConflictResolver,
    MAX_ARBITRATION_CONTEXT_CHARS,
)
from intelligence.conflict_adapters import (
    CloudConflictAdapter,
    CloudConflictConfig,
    CloudConflictProvider,
    LocalContextWindowExceededError,
    OllamaConflictAdapter,
)


def _memory(
    content: str,
    *,
    provenance: str = "inferred",
    project_id=None,
    scope: Scope = Scope.PROJECT,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    updated_at: datetime | None = None,
    supersedes_id=None,
) -> Memory:
    now = updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Memory(
        id=uuid4(),
        project_id=project_id,
        scope=scope,
        content=content,
        status=status,
        provenance=provenance,
        updated_at=now,
        created_at=now,
        supersedes_id=supersedes_id,
    )


def _candidate(memory: Memory) -> ConflictCandidate:
    return ConflictCandidate(id=memory.id, memory=memory)


class _StaticDetector(DefaultConflictDetector):
    def __init__(self, detected: bool):
        self.detected = detected

    def detect(self, memories, query, project_id=None):
        candidates = [_candidate(memory) for memory in memories]
        return Result.ok(
            ConflictDetectionResult(
                conflicts_detected=self.detected,
                candidates=candidates,
                topic=query,
            )
        )


class _SpyResolver:
    def __init__(self):
        self.called = False

    def resolve(self, request):
        self.called = True
        return Result.ok(
            ConflictResolutionResult(
                status=ConflictResolutionStatus.RESOLVED,
                resolution_reason="test resolver",
            )
        )


class _LocalAdapter:
    def __init__(self, outcome: Exception | dict):
        self.outcome = outcome
        self.calls = 0

    def arbitrate(self, context):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _CloudAdapter:
    def __init__(self, outcome: Exception | dict):
        self.outcome = outcome
        self.calls = 0

    def arbitrate(self, context):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_detector_excludes_compatible_claims_and_finds_different_decisions():
    detector = DefaultConflictDetector()
    project_id = uuid4()
    compatible = [
        _memory("Use SQLite for canonical storage.", project_id=project_id),
        _memory("Use SQLite for persistent memory storage.", project_id=project_id),
    ]
    incompatible = [
        _memory("Use SQLite for canonical storage.", project_id=project_id),
        _memory("Use PostgreSQL for canonical storage.", project_id=project_id),
    ]

    compatible_result = detector.detect(compatible, "canonical storage", project_id)
    incompatible_result = detector.detect(incompatible, "canonical storage", project_id)

    assert compatible_result.success
    assert not compatible_result.value.conflicts_detected
    assert incompatible_result.success
    assert incompatible_result.value.conflicts_detected
    assert {item.memory.id for item in incompatible_result.value.candidates} == {
        memory.id for memory in incompatible
    }


def test_detector_filters_inactive_and_unrelated_project_memories():
    detector = DefaultConflictDetector()
    project_id = uuid4()
    other_project_id = uuid4()
    local = _memory("Use SQLite for canonical storage.", project_id=project_id)
    inactive = _memory(
        "Use PostgreSQL for canonical storage.",
        project_id=project_id,
        status=MemoryStatus.ARCHIVED,
    )
    unrelated = _memory(
        "Use PostgreSQL for canonical storage.", project_id=other_project_id
    )
    global_memory = _memory(
        "Use PostgreSQL for canonical storage.",
        project_id=None,
        scope=Scope.GLOBAL,
    )

    result = detector.detect(
        [local, inactive, unrelated, global_memory], "database choice", project_id
    )

    assert result.success
    assert result.value.conflicts_detected
    assert {candidate.memory.id for candidate in result.value.candidates} == {
        local.id,
        global_memory.id,
    }


def test_repeated_detection_is_stable_and_does_not_change_canonical_status():
    first = _memory("Use SQLite for canonical storage.")
    second = _memory("Use PostgreSQL for canonical storage.")
    detector = DefaultConflictDetector()

    first_result = detector.detect([first, second], "database choice")
    second_result = detector.detect([first, second], "database choice")

    assert first_result.success and second_result.success
    assert [
        candidate.memory.id for candidate in first_result.value.candidates
    ] == [candidate.memory.id for candidate in second_result.value.candidates]
    assert first.status == second.status == MemoryStatus.ACTIVE


def test_service_does_not_resolve_or_mutate_when_no_conflict_is_detected():
    first = _memory("Use SQLite for canonical storage.")
    second = _memory("SQLite stores durable memory data.")
    spy_resolver = _SpyResolver()
    service = DefaultConflictResolutionService(
        detector=_StaticDetector(detected=False),
        resolver=spy_resolver,
    )
    request = ConflictResolutionRequest(
        candidates=[_candidate(first), _candidate(second)]
    )

    result = service.detect_and_resolve(request)

    assert result.success
    assert result.value.metadata["rule"] == "no_conflict"
    assert not spy_resolver.called
    assert first.status == second.status == MemoryStatus.ACTIVE


def test_deterministic_resolution_prefers_explicit_user_memory():
    inferred = _memory(
        "Use PostgreSQL for canonical storage.",
        provenance="inferred",
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    explicit = _memory(
        "Use SQLite for canonical storage.",
        provenance="user_explicit",
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    service = DefaultConflictResolutionService()

    result = service.detect_and_resolve(
        ConflictResolutionRequest(
            candidates=[_candidate(inferred), _candidate(explicit)],
            project_context=Project(id=explicit.project_id),
        )
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.RESOLVED
    assert [candidate.memory.id for candidate in result.value.preferred_candidates] == [
        explicit.id
    ]
    assert [candidate.memory.id for candidate in result.value.superseded_candidates] == [
        inferred.id
    ]
    assert inferred.status == explicit.status == MemoryStatus.ACTIVE


def test_explicit_user_update_has_precedence_over_older_explicit_memory():
    prior = _memory(
        "Use PostgreSQL for canonical storage.",
        provenance="user_explicit",
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    update = _memory(
        "Use SQLite for canonical storage.",
        provenance="explicit_user_update",
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        supersedes_id=prior.id,
    )

    result = DefaultConflictResolutionService().detect_and_resolve(
        ConflictResolutionRequest(
            candidates=[_candidate(prior), _candidate(update)]
        )
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.RESOLVED
    assert result.value.preferred_candidates[0].memory.id == update.id


def test_equal_precedence_is_unresolved_instead_of_arbitrarily_selecting():
    updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _memory(
        "Use SQLite for canonical storage.", updated_at=updated_at
    )
    second = _memory(
        "Use PostgreSQL for canonical storage.", updated_at=updated_at
    )
    service = DefaultConflictResolver()

    result = service.resolve(
        ConflictResolutionRequest(
            candidates=[_candidate(first), _candidate(second)]
        )
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.UNRESOLVED
    assert result.value.metadata["rule"] == "ambiguous_equal_precedence"
    assert result.value.preferred_candidates == []


def test_explicit_supersession_wins_and_deleted_candidate_is_ignored():
    previous = _memory(
        "Use SQLite for canonical storage.",
        provenance="user_explicit",
    )
    update = _memory(
        "Use PostgreSQL for canonical storage.",
        provenance="inferred",
        supersedes_id=previous.id,
    )
    deleted = _memory(
        "Use MySQL for canonical storage.",
        status=MemoryStatus.DELETED,
    )

    result = DefaultConflictResolver().resolve(
        ConflictResolutionRequest(
            candidates=[
                _candidate(previous),
                _candidate(update),
                _candidate(deleted),
            ]
        )
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.RESOLVED
    assert [candidate.memory.id for candidate in result.value.preferred_candidates] == [
        update.id
    ]
    assert all(
        candidate.memory.id != deleted.id
        for candidate in result.value.superseded_candidates
    )
    assert previous.status == update.status == MemoryStatus.ACTIVE


def test_cloud_fallback_only_runs_when_local_context_window_is_exceeded():
    selected_id = str(uuid4())
    local = _LocalAdapter(LocalContextWindowExceededError("context exceeded"))
    cloud = _CloudAdapter(
        {
            "outcome": "resolved",
            "preferred_candidate": selected_id,
            "reason": "Supported by explicit evidence.",
        }
    )
    resolver = DefaultConflictResolver(local, cloud)
    candidate_memory = Memory(id=UUID(selected_id), content="Candidate")
    candidate = _candidate(candidate_memory)

    result = resolver.invoke_llm_arbitration([candidate], "bounded evidence")

    assert result.success
    assert result.value.status == ConflictResolutionStatus.RESOLVED
    assert result.value.metadata["provider"] == "cloud"
    assert result.value.metadata["fallback"] is True
    assert local.calls == cloud.calls == 1


def test_cloud_is_not_used_for_non_overflow_local_failure():
    local = _LocalAdapter(RuntimeError("local server unavailable"))
    cloud = _CloudAdapter(
        {
            "outcome": "resolved",
            "preferred_candidate": None,
            "reason": "not expected",
        }
    )

    result = DefaultConflictResolver(local, cloud).invoke_llm_arbitration(
        [], "evidence"
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.ABSTAINED
    assert local.calls == 1
    assert cloud.calls == 0


def test_oversized_evidence_is_not_truncated_or_sent_to_either_model():
    local = _LocalAdapter({"outcome": "unresolved"})
    cloud = _CloudAdapter({"outcome": "unresolved"})
    candidate = _candidate(
        _memory("x" * (MAX_ARBITRATION_CONTEXT_CHARS + 1))
    )

    result = DefaultConflictResolver(local, cloud).resolve(
        ConflictResolutionRequest(candidates=[candidate])
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.UNRESOLVED
    assert result.value.metadata["arbitration_skipped"] == "evidence_limit"
    assert "complete evidence exceeds" in result.value.resolution_reason
    assert local.calls == cloud.calls == 0


def test_llm_cannot_select_candidate_outside_evidence_set():
    candidate = _candidate(_memory("A candidate"))
    local = _LocalAdapter(
        {
            "outcome": "resolved",
            "preferred_candidate": str(uuid4()),
            "reason": "fabricated id",
        }
    )

    result = DefaultConflictResolver(local).invoke_llm_arbitration(
        [candidate], "evidence"
    )

    assert result.success
    assert result.value.status == ConflictResolutionStatus.ABSTAINED
    assert result.value.metadata["rule"] == "invalid_candidate"


@pytest.mark.parametrize(
    ("provider", "api_response"),
    [
        (
            CloudConflictProvider.OPENAI,
            {"choices": [{"message": {"content": '{"outcome":"unresolved"}'}}]},
        ),
        (
            CloudConflictProvider.ANTHROPIC,
            {"content": [{"type": "text", "text": '{"outcome":"unresolved"}'}]},
        ),
        (
            CloudConflictProvider.GEMINI,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"outcome":"unresolved"}'}]
                        }
                    }
                ]
            },
        ),
    ],
)
def test_cloud_adapter_parses_native_provider_responses(provider, api_response):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(api_response).encode()

    requests = []

    def fake_opener(request, timeout):
        requests.append((request, timeout))
        return Response()

    adapter = CloudConflictAdapter(
        CloudConflictConfig(
            provider=provider,
            api_key="test-key",
            model="test-model",
        ),
        opener=fake_opener,
    )

    result = adapter.arbitrate("test evidence")

    assert result == {"outcome": "unresolved"}
    request = requests[0][0]
    assert request.method == "POST"
    assert b"test evidence" in request.data
    if provider == CloudConflictProvider.OPENAI:
        assert request.get_header("Authorization") == "Bearer test-key"
    elif provider == CloudConflictProvider.ANTHROPIC:
        assert request.get_header("X-api-key") == "test-key"
    else:
        assert request.get_header("X-goog-api-key") == "test-key"


def test_ollama_context_overflow_is_a_typed_signal():
    def fake_opener(request, timeout):
        raise HTTPError(
            request.full_url,
            400,
            "bad request",
            hdrs=None,
            fp=BytesIO(b'{"error":"input length exceeds context length"}'),
        )

    adapter = OllamaConflictAdapter(opener=fake_opener)

    with pytest.raises(LocalContextWindowExceededError):
        adapter.arbitrate("long evidence")


def test_cloud_configuration_requires_key_and_model(monkeypatch):
    monkeypatch.setenv("RECALL_CONFLICT_CLOUD_PROVIDER", "anthropic")
    monkeypatch.delenv("RECALL_CONFLICT_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("RECALL_CONFLICT_CLOUD_MODEL", raising=False)

    with pytest.raises(ValueError, match="API_KEY is required"):
        CloudConflictConfig.from_env()
