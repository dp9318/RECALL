"""Session routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import _parse_uuid, get_manager
from api.serializers import _serialize_session
from contracts.project import SessionCreateRequest
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
def list_sessions(
    project_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True)
    result = manager.list_sessions_paginated(project_id=project_uuid, limit=limit, offset=offset)
    if not result.success or result.value is None:
        raise HTTPException(status_code=500, detail=result.error or "Unable to list sessions")
    sessions = list(result.value.items)
    return {
        "sessions": [_serialize_session(session, manager) for session in sessions],
        "total": result.value.total,
    }


@router.post("/sessions")
def create_session(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_uuid = _parse_uuid(payload.get("project_id"), "project_id")
    project_result = manager.get_project(project_uuid)
    if not project_result.success or project_result.value is None:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id_raw = payload.get("session_id") or payload.get("id")
    session_uuid = _parse_uuid(session_id_raw, "session_id", allow_missing=True) if session_id_raw else None

    if session_uuid is not None:
        existing = manager.get_session(session_uuid)
        if existing.success and existing.value is not None:
            if existing.value.project_id != project_uuid:
                raise HTTPException(status_code=409, detail="Session already belongs to a different project")
            return _serialize_session(existing.value, manager)

    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be a dictionary")

    request = SessionCreateRequest(
        project_id=project_uuid,
        id=session_uuid,
        metadata=metadata or {},
    )
    result = manager.create_session(request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Session creation failed")
    return _serialize_session(result.value, manager)
