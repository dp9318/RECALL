"""Conflict resolution service interfaces and default implementations for RECALL."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID

from contracts.base import Result, ConflictResolutionStatus, MemoryStatus, Scope
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
from intelligence.conflict_adapters import LocalContextWindowExceededError

MAX_ARBITRATION_CONTEXT_CHARS = 16_000


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
            if project_id is not None and (
                memory.project_id != project_id
                and not (
                    memory.project_id is None
                    and memory.scope == Scope.GLOBAL
                )
            ):
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

        left_text = re.sub(r"[^a-z0-9]+", " ", (left.content or "").lower()).strip()
        right_text = re.sub(r"[^a-z0-9]+", " ", (right.content or "").lower()).strip()
        if not left_text or not right_text:
            return False

        stop_words = {
            "a", "an", "and", "as", "for", "in", "is", "of", "on", "the",
            "to", "with",
        }
        left_tokens = set(left_text.split()) - stop_words
        right_tokens = set(right_text.split()) - stop_words
        if not left_tokens or not right_tokens:
            return False

        shared = left_tokens & right_tokens
        if not shared:
            return False

        negations = {"not", "never", "avoid", "without", "cannot"}
        left_negative = bool(set(left_text.split()) & negations)
        right_negative = bool(set(right_text.split()) & negations)
        if left_negative != right_negative:
            return True

        decision_verbs = {"use", "choose", "select", "prefer"}
        left_words = left_text.split()
        right_words = right_text.split()
        left_decision = next(
            (
                (word, left_words[index + 1])
                for index, word in enumerate(left_words[:-1])
                if word in decision_verbs
            ),
            None,
        )
        right_decision = next(
            (
                (word, right_words[index + 1])
                for index, word in enumerate(right_words[:-1])
                if word in decision_verbs
            ),
            None,
        )
        return bool(
            left_decision
            and right_decision
            and left_decision[0] == right_decision[0]
            and left_decision[1] != right_decision[1]
            and len(shared) >= 2
        )


class DefaultConflictResolver(ConflictResolver):
    """Deterministic resolver with local arbitration and overflow-only cloud fallback."""

    def __init__(
        self,
        llm_adapter: Optional[Any] = None,
        cloud_adapter: Optional[Any] = None,
    ):
        self._llm_adapter = llm_adapter
        self._cloud_adapter = cloud_adapter

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
            if llm_context is None:
                result.resolution_reason = (
                    f"{result.resolution_reason} Arbitration was skipped because "
                    f"the complete evidence exceeds {MAX_ARBITRATION_CONTEXT_CHARS} "
                    "characters."
                ).strip()
                result.metadata["arbitration_skipped"] = "evidence_limit"
                return Result.ok(result)
            llm_result = self.invoke_llm_arbitration(request.candidates, llm_context)
            if llm_result.success:
                return llm_result

        return Result.ok(result)

    def apply_deterministic_rules(self, candidates: list[ConflictCandidate], custom_instructions: list[CustomInstruction]) -> ConflictResolutionResult:
        valid_candidates = []
        seen_ids: set[UUID] = set()
        for candidate in candidates:
            if (
                candidate.memory is not None
                and candidate.memory.is_active()
                and candidate.memory.id not in seen_ids
            ):
                valid_candidates.append(candidate)
                seen_ids.add(candidate.memory.id)
        if not valid_candidates:
            return ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED, resolution_reason="No valid memory candidates available.")

        active_instructions = [instruction for instruction in custom_instructions if instruction.is_active()]
        matching_candidates = [
            candidate for candidate in valid_candidates
            if self._matches_instruction(candidate.memory, active_instructions)
        ]
        eligible_candidates = matching_candidates or valid_candidates
        candidate_ids = {
            candidate.memory.id
            for candidate in eligible_candidates
            if candidate.memory is not None
        }
        explicitly_superseded = {
            candidate.memory.supersedes_id
            for candidate in eligible_candidates
            if candidate.memory is not None
            and candidate.memory.supersedes_id in candidate_ids
        }
        winner_pool = [
            candidate
            for candidate in eligible_candidates
            if candidate.memory is not None
            and candidate.memory.id not in explicitly_superseded
        ] or eligible_candidates
        winner_priority = max(self._priority(candidate) for candidate in winner_pool)
        winners = [
            candidate
            for candidate in winner_pool
            if self._priority(candidate) == winner_priority
        ]
        if len(winners) != 1:
            return ConflictResolutionResult(
                status=ConflictResolutionStatus.UNRESOLVED,
                unresolved_candidates=valid_candidates,
                resolution_reason=(
                    "Multiple candidates have equal deterministic precedence; "
                    "arbitration is required."
                ),
                metadata={"rule": "ambiguous_equal_precedence"},
            )
        winner = winners[0]
        winner_memory = winner.memory
        if winner_memory is None:
            return ConflictResolutionResult(status=ConflictResolutionStatus.UNRESOLVED, resolution_reason="The winner could not be determined.")

        exposed_decisions: list[ResolutionDecision] = [
            ResolutionDecision(
                candidate_id=winner_memory.id,
                action="keep",
                reason="Highest deterministic precedence among competing memories.",
                confidence=0.9,
            )
        ]
        superseded: list[ConflictCandidate] = []
        unresolved: list[ConflictCandidate] = []
        for candidate in valid_candidates:
            if candidate.memory is None or candidate.memory.id == winner_memory.id:
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

        selected_adapter = self._llm_adapter
        fallback_used = False
        try:
            try:
                raw_response = selected_adapter.arbitrate(context)
            except LocalContextWindowExceededError as overflow:
                if self._cloud_adapter is None:
                    return Result.ok(
                        ConflictResolutionResult(
                            status=ConflictResolutionStatus.ABSTAINED,
                            resolution_reason=(
                                f"{overflow} Cloud fallback is not configured."
                            ),
                            model_used=True,
                            metadata={"rule": "local_context_overflow"},
                        )
                    )
                selected_adapter = self._cloud_adapter
                fallback_used = True
                try:
                    raw_response = selected_adapter.arbitrate(context)
                except Exception as cloud_error:
                    return Result.ok(
                        ConflictResolutionResult(
                            status=ConflictResolutionStatus.ABSTAINED,
                            resolution_reason=(
                                "Local model context window was exceeded and cloud "
                                f"fallback failed: {cloud_error}"
                            ),
                            model_used=True,
                            metadata={
                                "rule": "cloud_fallback_failed",
                                "provider": getattr(
                                    selected_adapter, "provider", "cloud"
                                ),
                                "model": getattr(selected_adapter, "model", None),
                            },
                        )
                    )
            provider = getattr(
                selected_adapter, "provider", "cloud" if fallback_used else "local"
            )
            model = getattr(selected_adapter, "model", None)
            model_metadata = {
                "provider": provider,
                "model": model,
                "fallback": fallback_used,
            }
            if hasattr(raw_response, "success"):
                if not raw_response.success:
                    return Result.ok(
                        ConflictResolutionResult(
                            status=ConflictResolutionStatus.ABSTAINED,
                            resolution_reason=raw_response.error or "LLM arbitration failed.",
                            model_used=True,
                            metadata={"rule": "llm_failed", **model_metadata},
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
                        metadata={"rule": "invalid_response", **model_metadata},
                    )
                )

            outcome = payload.get("outcome") or payload.get("status")
            if outcome not in {member.value for member in ConflictResolutionStatus}:
                return Result.ok(
                    ConflictResolutionResult(
                        status=ConflictResolutionStatus.ABSTAINED,
                        resolution_reason="LLM outcome was not a valid RECALL status value.",
                        model_used=True,
                        metadata={"rule": "invalid_outcome", **model_metadata},
                    )
                )

            preferred_id = payload.get("preferred_candidate")
            candidate_ids = {
                str(identifier)
                for candidate in candidates
                for identifier in (
                    candidate.id,
                    candidate.memory.id if candidate.memory is not None else None,
                )
                if identifier is not None
            }
            if preferred_id is not None and str(preferred_id) not in candidate_ids:
                return Result.ok(
                    ConflictResolutionResult(
                        status=ConflictResolutionStatus.ABSTAINED,
                        resolution_reason=(
                            "Model selected an identifier that was not in the "
                            "conflict candidate set."
                        ),
                        model_used=True,
                        metadata={"rule": "invalid_candidate", **model_metadata},
                    )
                )
            if outcome == ConflictResolutionStatus.RESOLVED.value and preferred_id is None:
                return Result.ok(
                    ConflictResolutionResult(
                        status=ConflictResolutionStatus.ABSTAINED,
                        resolution_reason=(
                            "Model marked the conflict resolved without selecting "
                            "a supplied candidate."
                        ),
                        model_used=True,
                        metadata={
                            "rule": "missing_preferred_candidate",
                            **model_metadata,
                        },
                    )
                )

            result = ConflictResolutionResult(
                status=ConflictResolutionStatus(outcome),
                resolution_reason=str(payload.get("reason") or "Model arbitration completed."),
                model_used=True,
                metadata={"rule": "llm_arbitration", **model_metadata},
            )
            if preferred_id is not None:
                for candidate in candidates:
                    if str(getattr(candidate, "id", None)) == str(preferred_id) or (
                        candidate.memory is not None
                        and str(candidate.memory.id) == str(preferred_id)
                    ):
                        result.preferred_candidates.append(candidate)
                        break
            return Result.ok(result)
        except Exception as exc:
            return Result.ok(
                ConflictResolutionResult(
                    status=ConflictResolutionStatus.ABSTAINED,
                    resolution_reason=f"Local model arbitration failed: {exc}",
                    model_used=True,
                    metadata={"rule": "llm_exception", "provider": "local"},
                )
            )

    @staticmethod
    def _priority(candidate: ConflictCandidate) -> tuple[int, int, float]:
        memory = candidate.memory
        if memory is None:
            return (0, 0, 0.0)

        provenance_rank = {
            "explicit_user_update": 3,
            "user_explicit": 2,
            "inferred": 1,
        }.get(memory.provenance or "", 0)
        return (
            provenance_rank,
            int(memory.status == MemoryStatus.ACTIVE),
            memory.updated_at.timestamp(),
        )

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
    def _build_evidence_context(candidates: list[ConflictCandidate], custom_instructions: list[CustomInstruction]) -> Optional[str]:
        evidence = []
        total_chars = 0
        for candidate in candidates:
            if candidate.memory is None:
                continue
            line = (
                f"memory_id={candidate.memory.id}, provenance={candidate.memory.provenance}, "
                f"content={candidate.memory.content}"
            )
            added_chars = len(line) + (1 if evidence else 0)
            if total_chars + added_chars > MAX_ARBITRATION_CONTEXT_CHARS:
                return None
            evidence.append(line)
            total_chars += added_chars
        for instruction in custom_instructions:
            if instruction.is_active():
                line = f"instruction={instruction.content}"
                added_chars = len(line) + (1 if evidence else 0)
                if total_chars + added_chars > MAX_ARBITRATION_CONTEXT_CHARS:
                    return None
                evidence.append(line)
                total_chars += added_chars
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
        if not detection.success:
            return Result.err(detection.error or "Conflict detection failed.")
        if not detection.value or not detection.value.conflicts_detected:
            return Result.ok(
                ConflictResolutionResult(
                    status=ConflictResolutionStatus.UNRESOLVED,
                    resolution_reason="No conflicting active memories were detected.",
                    metadata={"rule": "no_conflict"},
                )
            )
        request.candidates = detection.value.candidates

        return self._resolver.resolve(request)