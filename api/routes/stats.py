"""Statistics routes for RECALL HTTP API."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_manager
from api.serializers import _serialize_conflict
from database.exceptions import DatabaseError
from recall_core.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats(manager: MemoryManager = Depends(get_manager)) -> dict[str, Any]:
    result = manager.get_stats()
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Unable to load stats")
    payload = result.value or {}
    memory_payload = payload.get("memories", {})
    instruction_payload = payload.get("custom_instructions", {})
    total_memories = payload.get("total_memories")
    if total_memories is None:
        total_memories = sum(int(v) for v in memory_payload.values()) if isinstance(memory_payload, dict) else 0
    total_instructions = sum(int(v) for v in instruction_payload.values()) if isinstance(instruction_payload, dict) else 0
    semantic_health = payload.get("semantic_index", {})

    unresolved_conflicts = 0
    try:
        conflict_res = manager.get_conflicts(project_id=None)
        if conflict_res.success and conflict_res.value is not None:
            conflict = _serialize_conflict(conflict_res.value, None)
            if conflict.get("conflicting_memories") and conflict.get("status") in {"unresolved", "detected"}:
                unresolved_conflicts = 1
        elif not conflict_res.success:
            logger.warning("Failed to evaluate conflicts for stats: %s", conflict_res.error)
    except (sqlite3.Error, DatabaseError) as exc:
        logger.warning("Database error evaluating conflicts for stats: %s", exc)
        unresolved_conflicts = 0

    return {
        "total_memories": total_memories,
        "active_memories": int(memory_payload.get("active", 0)) if isinstance(memory_payload, dict) else 0,
        "total_projects": int(payload.get("projects", 0)),
        "total_sessions": int(payload.get("sessions", 0)),
        "total_instructions": total_instructions,
        "active_instructions": int(instruction_payload.get("active", 0)) if isinstance(instruction_payload, dict) else 0,
        "unresolved_conflicts": unresolved_conflicts,
        "semantic_index_status": "healthy" if (semantic_health.get("status") == "healthy" or semantic_health.get("available") is True) else "degraded",
        "last_indexed_at": semantic_health.get("last_indexed_at"),
        "database_connected": True,
        "chromadb_connected": bool(semantic_health.get("available") or semantic_health.get("status") == "healthy"),
        "local_llm_available": True,
    }
