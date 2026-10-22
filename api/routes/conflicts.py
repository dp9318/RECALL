"""Conflict routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import _parse_uuid, get_manager
from api.serializers import _serialize_conflict
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["conflicts"])


@router.get("/conflicts")
def list_conflicts(
    project_id: str | None = None,
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True)
    result = manager.get_conflicts(project_id=project_uuid)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Unable to load conflicts")
    if result.value is None:
        return {"conflicts": [], "total": 0}
    conflict = _serialize_conflict(result.value, project_uuid)
    if not conflict["conflicting_memories"]:
        return {"conflicts": [], "total": 0}
    return {"conflicts": [conflict], "total": 1}
