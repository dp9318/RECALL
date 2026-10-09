"""Conflict resolution service interfaces and default implementations for RECALL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID

from contracts.base import Result, ConflictResolutionStatus, MemoryStatus
from contracts.conflict import (
    ConflictCandidate,
    ConflictDetectionResult,
    ConflictResolutionRequest,
    ConflictResolutionResult,
    ConflictType,
    ResolutionDecision,
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


class DefaultConflictDetector(ConflictDetector):
    """Heuristic conflict detector for candidate memory sets."""

    def detect(self, memories: list[Memory], query: str, project_id: Optional[UUID] = None) -> Result[ConflictDetectionResult]:
        if not memories:
            return Result.ok(ConflictDetectionResult(conflicts_detected=False, candidates=[]))

        candidates: list[ConflictCandidate] = []
        seen: set[UUID] = set()
        for memory in memories:
            if memory.id in seen:
                continue
            seen.add(memory.id)
            if not memory.is_active():
                continue
            candidates.append(
                ConflictCandidate(
                    id=memory.id,
                    memory=memory,
                    relevance_score=self._relevance(memory, query, project_id),
                    conflict_type=ConflictType.CONTRADICTORY_CLAIM,
                    evidence=[memory.content],
                )
            )

        conflicts = []
        for left_index, left in enumerate(candidates):
            for right in candidates[left_index + 1 :]:
                if left.memory is None or right.memory is None:
                    continue
                if left.memory.project_id is not None and right.memory.project_id is not None:
                    if left.memory.project_id != right.memory.project_id:
                        continue
                if left.memory.id == right.memory.id:
                    continue
                if self._is_conflicting(left.memory, right.memory):
                    conflicts.extend([left, right])

        unique_conflicts = []
        seen_ids: set[UUID] = set()
        for candidate in conflicts:
            if candidate.memory is None or candidate.memory.id in seen_ids:
                continue
            seen_ids.add(candidate.memory.id)
            unique_conflicts.append(candidate)

        return Result.ok(
            ConflictDetectionResult(
                conflicts_detected=bool(unique_conflicts),
                candidates=unique_conflicts,
                topic=query or "memory conflict",
            )
        )

    def package_candidates(self, memories: list[Memory], conflict_type: str) -> list[ConflictCandidate]:
        packaged: list[ConflictCandidate] = []
        for memory in memories:
            packaged.append(
                ConflictCandidate(
                    id=memory.id,
                    memory=memory,
                    relevance_score=1.0,
                    conflict_type=ConflictType(conflict_type) if conflict_type in {item.value for item in ConflictType} else ConflictType.CONTRADICTORY_CLAIM,
                    evidence=[memory.content],
                )
            )
        return packaged

    @staticmethod
    def _relevance(memory: Memory, query: str, project_id: Optional[UUID]) -> float:
        if not memory.content:
            return 0.0
        score = 0.3 if memory.project_id == project_id else 0.0
        score += 0.2 if memory.is_active() else 0.0
        score += 0.2 if memory.provenance in {"user_explicit", "explicit_user_update"} else 0.0
        text = (query or memory.content).lower()
        content = memory.content.lower()
        overlap = len(set(text.split()) & set(content.split()))
        return score + min(overlap / max(len(set(text.split())), 1), 1.0)

    @staticmethod
    def _is_conflicting(left: Memory, right: Memory) -> bool:
        if left.id == right.id:
            return False

        left_text = (left.content or "").strip().lower()
        right_text = (right.content or "").strip().lower()
        if not left_text or not right_text:
            return False

        left_tokens = {token for token in left_text.split() if token}
        right_tokens = {token for token in right_text.split() if token}
        if not left_tokens or not right_tokens:
            return False

        shared = left_tokens & right_tokens
        if not shared:
            return False

        if left.provenance == right.provenance == "user_explicit":
            return True

        return len(left_tokens - right_tokens) > 0 and len(right_tokens - left_tokens) > 0


class DefaultConflictResolver(ConflictResolver):
    """Deterministic conflict resolver with an optional model arbitration fallback."""

    def __init__(self, llm_adapter: Optional[Any] = None):
        self._llm_adapter = llm_adapter

    def resolve(self, request: ConflictResolutionRequest) -> Result[ConflictResolutionResult]:
        if not request.candidates:
            return Result.ok(
                ConflictResolutionResult(
                    status=ConflictResolutionStatus.UNRESOLVED,
                    resolution_reason="No memory candidates available for resolution.",
                )
            )

        result = self.apply_deterministic_rules(request.candidates, request.custom_instructions)
        if result.status in {ConflictResolutionStatus.RESOLVED, ConflictResolutionStatus.PARTIALLY_RESOLVED}:
            return Result.ok(result)

        if self._llm_adapter is not None:
            llm_context = self._build_evidence_context(request.candidates, request.custom_instructions)
            llm_result = self.invoke_llm_arbitration(request.candidates, llm_context)
            if llm_result.success:
                return llm_result

        return Result.ok(result)

    def apply_deterministic_rules(self, candidates: list[ConflictCandidate], custom_instructions: list[CustomInstruction]) -> ConflictResolutionResult:
        valid_candidates = [candidate for candidate in candidates if candidate.memory is not None]
        if not valid_candidates:
            return ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED, resolution_reason="No valid memory candidates available.")

        active_instructions = [instruction for instruction in custom_instructions if instruction.is_active()]
        matching_candidates = [
            candidate for candidate in valid_candidates
            if self._matches_instruction(candidate.memory, active_instructions)
        ]
        winner = max(matching_candidates or valid_candidates, key=self._priority)
        winner_memory = winner.memory
        if winner_memory is None:
            return ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED, resolution_reason="The winner could not be determined.")

        exposed_decisions: list[ResolutionDecision] = [
            ResolutionDecision(
                candidate_id=winner.id,
                action="keep",
                reason="Highest deterministic precedence among competing memories.",
                confidence=0.9,
            )
        ]
        superseded: list[ConflictCandidate] = []
        unresolved: list[ConflictCandidate] = []
        for candidate in valid_candidates:
            if candidate.id == winner.id:
                continue
            if self._is_explicitly_overridden(candidate, active_instructions):
                unresolved.append(candidate)
                continue
            superseded.append(candidate)
            exposed_decisions.append(
                ResolutionDecision(
                    candidate_id=candidate.id,
                    action="supersede",
                    reason="Lower precedence than the selected memory.",
                    confidence=0.7,
                )
            )

        if matching_candidates:
            return ConflictResolutionResult(
                status=ConflictResolutionStatus.RESOLVED,
                decisions=exposed_decisions,
                preferred_candidates=[winner],
                superseded_candidates=superseded,
                unresolved_candidates=unresolved,
                resolution_reason="Explicit custom instructions were applied to the selected memory.",
                metadata={"rule": "custom_instruction_precedence"},
            )

        if winner_memory.provenance == "user_explicit":
            return ConflictResolutionResult(
                status=ConflictResolutionStatus.RESOLVED,
                decisions=exposed_decisions,
                preferred_candidates=[winner],
                superseded_candidates=superseded,
                unresolved_candidates=unresolved,
                resolution_reason="Explicit user-supplied memory takes precedence over inferred alternatives.",
                metadata={"rule": "explicit_user_update"},
            )

        if len(valid_candidates) == 2 and winner_memory.is_active() and all(candidate.memory and candidate.memory.is_active() for candidate in valid_candidates):
            if winner_memory.updated_at >= max((candidate.memory.updated_at for candidate in valid_candidates if candidate.id != winner.id), default=winner_memory.updated_at):
                return ConflictResolutionResult(
                    status=ConflictResolutionStatus.RESOLVED,
                    decisions=exposed_decisions,
                    preferred_candidates=[winner],
                    superseded_candidates=superseded,
                    unresolved_candidates=unresolved,
                    resolution_reason="Most recent active memory wins when no explicit instruction overrides it.",
                    metadata={"rule": "most_recent_active"},
                )

        if not superseded:
            return ConflictResolutionResult(
                status=ConflictResolutionStatus.UNRESOLVED,
                decisions=exposed_decisions,
                preferred_candidates=[winner],
                unresolved_candidates=valid_candidates,
                resolution_reason="No deterministic precedence could be applied to competing memories.",
                metadata={"rule": "ambiguous"},
            )

        return ConflictResolutionResult(
            status=ConflictResolutionStatus.RESOLVED,
            decisions=exposed_decisions,
            preferred_candidates=[winner],
            superseded_candidates=superseded,
            unresolved_candidates=unresolved,
            resolution_reason="A deterministic rule selected the preferred memory.",
            metadata={"rule": "deterministic_precedence"},
        )

    def invoke_llm_arbitration(self, candidates: list[ConflictCandidate], context: str) -> Result[ConflictResolutionResult]:
        if self._llm_adapter is None:
            return Result.ok(
                ConflictResolutionResult(
                    status=ConflictResolutionStatus.ABSTAINED,
                    resolution_reason="No local model adapter is configured for arbitration.",
                    model_used=False,
                    metadata={"rule": "no_llm"},
                )
            )

        try:
            raw_response = self._llm_adapter.arbitrate(context)
            if hasattr(raw_response, "success"):
                if not raw_response.success:
                    return Result.ok(
                        ConflictResolutionResult(
                            status=ConflictResolutionStatus.ABSTAINED,
                            resolution_reason=raw_response.error or "LLM arbitration failed.",
                            model_used=True,
                            metadata={"rule": "llm_failed"},
                        )
                    )
                payload = raw_response.value
            else:
                payload = raw_response

            if not isinstance(payload, dict):
                return Result.ok(
                    ConflictResolutionResult(
                        status=ConflictResolutionStatus.ABSTAINED,
                        resolution_reason="LLM output was not a supported structured payload.",
                        model_used=True,
                        metadata={"rule": "invalid_response"},
                    )
                )

            outcome = payload.get("outcome") or payload.get("status")
            if outcome not in {member.value for member in ConflictResolutionStatus}:
                return Result.ok(
                    ConflictResolutionResult(
                        status=ConflictResolutionStatus.ABSTAINED,
                        resolution_reason="LLM outcome was not a valid RECALL status value.",
                        model_used=True,
                        metadata={"rule": "invalid_outcome"},
                    )
                )

            result = ConflictResolutionResult(
                status=ConflictResolutionStatus(outcome),
                resolution_reason=str(payload.get("reason") or "Model arbitration completed."),
                model_used=True,
                metadata={"rule": "llm_arbitration", "payload": payload},
            )
            preferred = payload.get("preferred_candidate")
            if preferred is not None:
                for candidate in candidates:
                    if getattr(candidate, "id", None) == preferred or getattr(candidate.memory, "id", None) == preferred:
                        result.preferred_candidates.append(candidate)
                        break
            return Result.ok(result)
        except Exception as exc:
            return Result.ok(
                ConflictResolutionResult(
                    status=ConflictResolutionStatus.ABSTAINED,
                    resolution_reason=f"LLM arbitration raised an exception: {exc}",
                    model_used=True,
                    metadata={"rule": "llm_exception"},
                )
            )

    @staticmethod
    def _priority(candidate: ConflictCandidate) -> float:
        memory = candidate.memory
        if memory is None:
            return 0.0

        score = 0.0
        if memory.provenance == "user_explicit":
            score += 10.0
        if memory.provenance == "explicit_user_update":
            score += 9.0
        if memory.is_active():
            score += 5.0
        if memory.status == MemoryStatus.ACTIVE:
            score += 2.0
        if isinstance(memory.metadata.get("confidence"), (int, float)):
            score += float(memory.metadata["confidence"]) * 10
        score += candidate.relevance_score
        return score

    @staticmethod
    def _matches_instruction(memory: Optional[Memory], custom_instructions: list[CustomInstruction]) -> bool:
        if memory is None:
            return False
        if not custom_instructions:
            return False
        memory_text = (memory.content or "").lower()
        for instruction in custom_instructions:
            if instruction.is_active() and instruction.content:
                instruction_text = instruction.content.lower()
                if instruction_text in memory_text or memory_text in instruction_text:
                    return True
        return False

    @staticmethod
    def _is_explicitly_overridden(candidate: ConflictCandidate, custom_instructions: list[CustomInstruction]) -> bool:
        if candidate.memory is None:
            return False
        if not custom_instructions:
            return False
        for instruction in custom_instructions:
            if instruction.is_active() and instruction.content and instruction.content.lower() in (candidate.memory.content or "").lower():
                return True
        return False

    @staticmethod
    def _build_evidence_context(candidates: list[ConflictCandidate], custom_instructions: list[CustomInstruction]) -> str:
        evidence = []
        for candidate in candidates:
            if candidate.memory is None:
                continue
            evidence.append(
                f"memory_id={candidate.memory.id}, provenance={candidate.memory.provenance}, content={candidate.memory.content}"
            )
        for instruction in custom_instructions:
            if instruction.is_active():
                evidence.append(f"instruction={instruction.content}")
        return "\n".join(evidence)


class DefaultConflictResolutionService(ConflictResolutionService):
    """Concrete service for conflict detection and resolution."""

    def __init__(self, detector: Optional[ConflictDetector] = None, resolver: Optional[ConflictResolver] = None):
        self._detector = detector or DefaultConflictDetector()
        self._resolver = resolver or DefaultConflictResolver()

    @property
    def detector(self) -> ConflictDetector:
        return self._detector

    @property
    def resolver(self) -> ConflictResolver:
        return self._resolver

    def detect_and_resolve(self, request: ConflictResolutionRequest) -> Result[ConflictResolutionResult]:
        if not request.candidates:
            return Result.ok(ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED, resolution_reason="No candidates supplied."))

        memories = [candidate.memory for candidate in request.candidates if candidate.memory is not None]
        detection = self._detector.detect(memories, query=" ".join((candidate.memory.content or "") for candidate in request.candidates if candidate.memory), project_id=getattr(request.project_context, "id", None))
        if detection.success and detection.value and detection.value.conflicts_detected:
            request.candidates = detection.value.candidates

        return self._resolver.resolve(request)