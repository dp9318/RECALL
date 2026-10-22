"""Memory routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import _parse_status, _parse_uuid, get_manager
from api.serializers import _serialize_memory
from contracts.base import Scope
from contracts.memory import MemoryCreateRequest, MemorySearchParams, MemoryStatus, MemoryUpdateRequest
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["memories"])


@router.get("/memories")
def list_memories(
    project_id: str | None = None,
    memory_type: str | None = None,
    status: str | None = None,
    include_historical: bool = False,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = None,
    sort_order: str | None = None,
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True) if project_id else None

    if status == "deleted":
        status_filter = MemoryStatus.DELETED
        include_historical = True
    elif status == "all":
        status_filter = None
    elif status:
        status_filter = _parse_status(status, MemoryStatus, "status")
    else:
        status_filter = MemoryStatus.ACTIVE

    params = MemorySearchParams(
        query=search,
        project_id=project_uuid,
        memory_type=memory_type,
        status=status_filter,
        limit=page_size,
        offset=(page - 1) * page_size,
        include_historical=include_historical,
    )

    if hasattr(manager, "search_memories_paginated"):
        result = manager.search_memories_paginated(params)
        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Unable to list memories")
        paginated = result.value
        memories = list(paginated.items if paginated else [])
        total = paginated.total if paginated else 0
    else:
        result = manager.search_memories(params)
        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Unable to list memories")
        memories = list(result.value or [])
        total = len(memories)

    return {
        "memories": [_serialize_memory(manager, memory) for memory in memories],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/memories/{memory_id}")
def get_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    memory_uuid = _parse_uuid(memory_id, "memory_id")
    result = manager.get_memory(memory_uuid)
    if not result.success or result.value is None or result.value.status == MemoryStatus.DELETED:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _serialize_memory(manager, result.value)


@router.post("/memories")
def create_memory(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_id = _parse_uuid(payload.get("project_id"), "project_id", allow_missing=True)
    session_id = _parse_uuid(payload.get("session_id"), "session_id", allow_missing=True)
    scope = payload.get("scope")
    if scope is None:
        scope_value = Scope.PROJECT if project_id is not None else Scope.GLOBAL
    else:
        scope_value = Scope(scope)
    memory_request = MemoryCreateRequest(
        project_id=project_id,
        session_id=session_id,
        scope=scope_value,
        memory_type=str(payload.get("memory_type") or "general"),
        content=str(payload.get("content") or ""),
        provenance=payload.get("provenance") or "api",
        supersedes_id=_parse_uuid(payload.get("supersedes_id"), "supersedes_id", allow_missing=True),
        metadata=(payload.get("metadata") or {}),
    )
    result = manager.create_memory(memory_request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Unable to create memory")
    return _serialize_memory(manager, result.value)


@router.patch("/memories/{memory_id}")
def update_memory(
    memory_id: str,
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    memory_uuid = _parse_uuid(memory_id, "memory_id")
    existing_result = manager.get_memory(memory_uuid)
    if not existing_result.success or existing_result.value is None or existing_result.value.status == MemoryStatus.DELETED:
        raise HTTPException(status_code=404, detail="Memory not found")

    content_val = payload.get("content")
    if content_val is not None:
        content_val = str(content_val).strip()
        if not content_val:
            raise HTTPException(status_code=400, detail="Content cannot be empty")

    status_value = _parse_status(payload.get("status"), MemoryStatus, "status")

    metadata_update: dict[str, Any] = {}
    if isinstance(payload.get("metadata"), dict):
        metadata_update.update(payload["metadata"])
    if "importance" in payload and payload["importance"] is not None:
        try:
            metadata_update["importance"] = int(payload["importance"])
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="importance must be an integer between 0 and 100") from exc
    if "tags" in payload and payload["tags"] is not None:
        if not isinstance(payload["tags"], list):
            raise HTTPException(status_code=400, detail="tags must be a list of strings")
        metadata_update["tags"] = [str(t).strip() for t in payload["tags"] if str(t).strip()]

    update_request = MemoryUpdateRequest(
        content=content_val,
        status=status_value,
        metadata=metadata_update if metadata_update else (payload.get("metadata") if "metadata" in payload else None),
        supersedes_id=_parse_uuid(payload.get("supersedes_id"), "supersedes_id", allow_missing=True),
    )
    result = manager.update_memory(memory_uuid, update_request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Memory update failed")
    return _serialize_memory(manager, result.value)


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_manager),
) -> Response:
    memory_uuid = _parse_uuid(memory_id, "memory_id")
    result = manager.delete_memory(memory_uuid)
    if not result.success or not result.value:
        raise HTTPException(status_code=404, detail=result.error or "Memory not found")
    return Response(status_code=204)
