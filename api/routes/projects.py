"""Project routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import _parse_uuid, get_manager
from api.serializers import _serialize_project
from contracts.project import ProjectCreateRequest
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    paginated_result = manager.list_projects_paginated(limit=limit, offset=offset)
    if not paginated_result.success or paginated_result.value is None:
        raise HTTPException(status_code=500, detail=paginated_result.error or "Unable to list projects")
    paginated = paginated_result.value
    projects = list(paginated.items)
    return {
        "projects": [_serialize_project(project, manager) for project in projects],
        "total": paginated.total,
    }


@router.post("/projects")
def create_project(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    description = payload.get("description")
    if description is not None:
        description = str(description).strip() or None
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be a dictionary")
    request = ProjectCreateRequest(
        name=name,
        description=description,
        metadata=metadata or {},
    )
    result = manager.create_project(request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Project creation failed")
    return _serialize_project(result.value, manager)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    manager: MemoryManager = Depends(get_manager),
) -> Response:
    project_uuid = _parse_uuid(project_id, "project_id")
    result = manager.delete_project(project_uuid)
    if not result.success:
        if result.error and "not found" in result.error.lower():
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error or "Project deletion failed")
    if not result.value:
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)
