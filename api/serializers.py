"""Serialization helpers for RECALL HTTP API responses."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from contracts.base import InstructionStatus, MemoryStatus
from contracts.conflict import ConflictResolutionStatus
from contracts.project import Project, Session
from recall_core.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


def _project_name_for(memory_manager: MemoryManager, project_id: UUID | None) -> str | None:
    if project_id is None:
        return None
    result = memory_manager.get_project(project_id)
    if result.success and result.value is not None:
        return result.value.name
    return None


def _serialize_memory(memory_manager: MemoryManager, memory: Any) -> dict[str, Any]:
    """Serialize a memory domain entity into a REST JSON representation.

    Lineage Resolution Rules:
    - Primary predecessor: `supersedes` holds the first predecessor ID where
      `rel.child_id == memory.id` and `rel.relationship == 'supersedes'`
      (or legacy `memory.supersedes_id`).
    - Additional predecessors (e.g. multi-parent compaction): Appended to `related_memories`.
    - Primary successor: `superseded_by` holds the first successor ID where
      `rel.parent_id == memory.id` and `rel.relationship == 'supersedes'`.
    - Additional successors (e.g. branching updates): Appended to `related_memories`.
    - Non-supersedes relationships (e.g. `derived_from`, `merged`): The counterpart ID
      is appended to `related_memories` (excluding self, supersedes, and superseded_by).
    """
    project_name = _project_name_for(memory_manager, getattr(memory, "project_id", None))
    metadata = getattr(memory, "metadata", None) or {}
    supersedes = str(memory.supersedes_id) if getattr(memory, "supersedes_id", None) else None
    superseded_by = None
    related_memories: list[str] = []

    if memory_manager is not None and hasattr(memory_manager, "get_memory_lineage") and getattr(memory, "id", None):
        try:
            lineage_res = memory_manager.get_memory_lineage(memory.id)
            if lineage_res.success and lineage_res.value:
                mem_id_str = str(memory.id)
                for rel in lineage_res.value:
                    parent_id_str = str(rel.parent_id)
                    child_id_str = str(rel.child_id)
                    if rel.relationship == "supersedes":
                        if parent_id_str == mem_id_str:
                            # Current memory is parent; child is a successor
                            if not superseded_by:
                                superseded_by = child_id_str
                            elif child_id_str != superseded_by and child_id_str not in related_memories:
                                related_memories.append(child_id_str)
                        elif child_id_str == mem_id_str:
                            # Current memory is child; parent is a predecessor
                            if not supersedes:
                                supersedes = parent_id_str
                            elif parent_id_str != supersedes and parent_id_str not in related_memories:
                                related_memories.append(parent_id_str)
                    else:
                        # Non-supersedes relationship (e.g. derived_from, merged, referenced)
                        other_id = child_id_str if parent_id_str == mem_id_str else parent_id_str
                        if (
                            other_id != mem_id_str
                            and other_id != supersedes
                            and other_id != superseded_by
                            and other_id not in related_memories
                        ):
                            related_memories.append(other_id)
        except Exception as exc:
            logger.warning("Failed to query memory lineage for %s: %s", getattr(memory, "id", None), exc)


    lineage = {
        "supersedes": supersedes,
        "superseded_by": superseded_by,
        "related_memories": related_memories,
    }
    importance = metadata.get("importance")
    if importance is None:
        importance = 50
    created_at = (
        memory.created_at.isoformat()
        if hasattr(memory, "created_at") and memory.created_at is not None
        else datetime.now(timezone.utc).isoformat()
    )
    updated_at = (
        memory.updated_at.isoformat()
        if hasattr(memory, "updated_at") and memory.updated_at is not None
        else created_at
    )
    return {
        "memory_id": str(memory.id),
        "project_id": str(memory.project_id) if memory.project_id is not None else None,
        "project_name": project_name,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "status": memory.status.value if hasattr(memory.status, "value") else str(memory.status),
        "importance": int(importance),
        "provenance": memory.provenance or "api",
        "lineage": lineage,
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": metadata.get("tags", []),
    }


def _serialize_instruction(instruction: Any, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    project_name = None
    if memory_manager is not None and getattr(instruction, "project_id", None):
        project_name = _project_name_for(memory_manager, instruction.project_id)
    return {
        "instruction_id": str(instruction.id),
        "scope": instruction.scope.value if hasattr(instruction.scope, "value") else str(instruction.scope),
        "project_id": str(instruction.project_id) if instruction.project_id is not None else None,
        "project_name": project_name,
        "content": instruction.content,
        "active": instruction.is_active() if hasattr(instruction, "is_active") else instruction.status == InstructionStatus.ACTIVE,
        "created_at": instruction.created_at.isoformat(),
        "updated_at": instruction.updated_at.isoformat(),
        "version": instruction.version,
    }


def _serialize_project(project: Project, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    memory_count = 0
    session_count = 0
    if memory_manager is not None:
        mem_res = memory_manager.get_project_memory_count(project.id, MemoryStatus.ACTIVE)
        if mem_res.success and mem_res.value is not None:
            memory_count = mem_res.value
        elif not mem_res.success:
            logger.warning(
                "Failed to query active memory count for project %s: %s",
                project.id,
                mem_res.error,
            )

        sess_res = memory_manager.get_project_session_count(project.id)
        if sess_res.success and sess_res.value is not None:
            session_count = sess_res.value
        elif not sess_res.success:
            logger.warning(
                "Failed to query session count for project %s: %s",
                project.id,
                sess_res.error,
            )
    return {
        "project_id": str(project.id),
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "memory_count": memory_count,
        "session_count": session_count,
    }


def _serialize_session(session: Session, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    project_name = None
    memory_captures = 0
    if memory_manager is not None:
        if getattr(session, "project_id", None):
            project_name = _project_name_for(memory_manager, session.project_id)
        mem_res = memory_manager.get_session_memory_count(session.id, include_historical=True)
        if mem_res.success and mem_res.value is not None:
            memory_captures = mem_res.value
        elif not mem_res.success:
            logger.warning(
                "Failed to query memory captures for session %s: %s",
                session.id,
                mem_res.error,
            )
    status = "active" if session.is_active() else "closed"
    return {
        "id": str(session.id),
        "session_id": str(session.id),
        "project_id": str(session.project_id),
        "project_name": project_name,
        "status": status,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "created_at": getattr(session, "created_at", session.started_at).isoformat(),
        "updated_at": getattr(session, "updated_at", session.started_at).isoformat(),
        "message_count": 0,
        "memory_captures": memory_captures,
    }


def _serialize_conflict(result: Any, project_id: UUID | None = None) -> dict[str, Any]:
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    mapped_status = {
        ConflictResolutionStatus.RESOLVED.value: "resolved",
        ConflictResolutionStatus.PARTIALLY_RESOLVED.value: "partially_resolved",
        ConflictResolutionStatus.UNRESOLVED.value: "unresolved",
        ConflictResolutionStatus.ABSTAINED.value: "abstained",
    }.get(status, "detected")
    conflicting_memories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in list(result.preferred_candidates) + list(result.superseded_candidates) + list(result.unresolved_candidates):
        memory = getattr(candidate, "memory", None)
        if memory is None:
            continue
        memory_id = str(memory.id)
        if memory_id in seen:
            continue
        seen.add(memory_id)
        conflicting_memories.append(
            {
                "memory_id": memory_id,
                "content": memory.content,
                "status": "preferred" if candidate in result.preferred_candidates else "conflicting",
                "confidence": getattr(candidate, "relevance_score", 0.0),
            }
        )
    preferred_ids = [str(candidate.memory.id) for candidate in result.preferred_candidates if candidate.memory is not None]
    superseded_ids = [str(candidate.memory.id) for candidate in result.superseded_candidates if candidate.memory is not None]
    return {
        "conflict_id": str(uuid4()),
        "project_id": str(project_id) if project_id is not None else "",
        "status": mapped_status,
        "conflicting_memories": conflicting_memories,
        "resolution": {
            "preferred_memories": preferred_ids,
            "superseded_memories": superseded_ids,
            "reason": result.resolution_reason or "No explicit resolution reason provided",
            "deterministic": not result.model_used,
            "local_model_used": result.model_used,
            "confidence": max((decision.confidence for decision in result.decisions), default=0.0),
        },
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
    }
