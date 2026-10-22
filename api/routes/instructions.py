"""Custom instruction routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import _parse_status, _parse_uuid, get_manager
from api.serializers import _serialize_instruction
from contracts.base import InstructionStatus, Scope
from contracts.instruction import (
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["instructions"])


@router.get("/custom-instructions")
def list_custom_instructions(
    project_id: str | None = None,
    scope: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True) if project_id else None
    params = CustomInstructionListParams(
        scope=_parse_status(scope, Scope, "scope") if scope is not None else None,
        project_id=project_uuid,
        status=_parse_status(status, InstructionStatus, "status") if status is not None else None,
        limit=limit,
        offset=offset,
    )
    result = manager.list_instructions(params)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Unable to list instructions")
    instructions = list(result.value or [])
    return {
        "instructions": [_serialize_instruction(instruction, manager) for instruction in instructions],
        "total": len(instructions),
    }


@router.post("/custom-instructions")
def create_custom_instruction(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    scope_value = Scope(payload.get("scope") or Scope.GLOBAL.value)
    project_id = _parse_uuid(payload.get("project_id"), "project_id", allow_missing=True)
    if scope_value == Scope.PROJECT:
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required for project-scoped instructions")
        project_result = manager.get_project(project_id)
        if not project_result.success or project_result.value is None:
            raise HTTPException(status_code=404, detail="Project not found")

    request = CustomInstructionCreateRequest(
        scope=scope_value,
        project_id=project_id,
        content=str(payload.get("content") or ""),
    )
    result = manager.create_instruction(request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Unable to create instruction")
    if payload.get("active") is False:
        update = CustomInstructionUpdateRequest(status=InstructionStatus.INACTIVE)
        manager.update_instruction(result.value.id, update)
    return _serialize_instruction(result.value, manager)


@router.patch("/custom-instructions/{instruction_id}")
def update_custom_instruction(
    instruction_id: str,
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    instruction_uuid = _parse_uuid(instruction_id, "instruction_id")
    active = payload.get("active")
    status_value = payload.get("status")
    if status_value is not None and active is None:
        parsed_status = _parse_status(str(status_value), InstructionStatus, "status")
    elif active is not None and status_value is None:
        parsed_status = InstructionStatus.ACTIVE if active else InstructionStatus.INACTIVE
    else:
        parsed_status = _parse_status(str(status_value), InstructionStatus, "status") if status_value is not None else None
    request = CustomInstructionUpdateRequest(
        content=payload.get("content"),
        status=parsed_status,
        metadata=payload.get("metadata"),
    )
    result = manager.update_instruction(instruction_uuid, request)
    if not result.success or result.value is None:
        raise HTTPException(status_code=404, detail=result.error or "Instruction not found")
    return _serialize_instruction(result.value, manager)


@router.delete("/custom-instructions/{instruction_id}")
def delete_custom_instruction(
    instruction_id: str,
    manager: MemoryManager = Depends(get_manager),
) -> Response:
    instruction_uuid = _parse_uuid(instruction_id, "instruction_id")
    result = manager.delete_instruction(instruction_uuid)
    if not result.success or not result.value:
        raise HTTPException(status_code=404, detail=result.error or "Instruction not found")
    return Response(status_code=204)
