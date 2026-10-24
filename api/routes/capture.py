"""Authenticated event capture route for RECALL automatic memory capture."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from api.dependencies import _parse_uuid, get_manager
from contracts.capture import (
    CaptureEventRequest,
    CaptureEventResponse,
    ELIGIBLE_CAPTURE_CATEGORIES,
)
from recall_core.capture_service import (
    resolve_or_create_capture_token,
    verify_capture_token,
)
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["capture"])


def verify_capture_auth(
    authorization: str | None = Header(None),
    x_recall_capture_token: str | None = Header(None),
) -> bool:
    """Verify that the caller holds the valid local capture token."""
    provided_token = ""
    if authorization and authorization.startswith("Bearer "):
        provided_token = authorization.split("Bearer ", 1)[1].strip()
    elif x_recall_capture_token:
        provided_token = x_recall_capture_token.strip()

    if not provided_token:
        raise HTTPException(
            status_code=401,
            detail="Missing capture authentication token. Provide Authorization: Bearer <token>",
        )

    expected_token = resolve_or_create_capture_token()
    if not verify_capture_token(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid capture authentication token",
        )

    return True


@router.post("/capture")
def capture_event(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
    _auth: bool = Depends(verify_capture_auth),
) -> dict[str, Any]:
    """Securely ingest an eligible agent event into persistent memory."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object")

    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=422, detail="Field 'content' is required and cannot be empty")

    event_category = payload.get("event_category")
    if not isinstance(event_category, str) or not event_category.strip():
        raise HTTPException(
            status_code=422,
            detail=f"Field 'event_category' is required. Must be one of: {sorted(ELIGIBLE_CAPTURE_CATEGORIES)}",
        )

    project_id = _parse_uuid(payload.get("project_id"), "project_id", allow_missing=True)
    session_id = _parse_uuid(payload.get("session_id"), "session_id", allow_missing=True)

    request = CaptureEventRequest(
        content=content.strip(),
        event_category=event_category.strip(),
        project_name=payload.get("project_name"),
        project_id=project_id,
        session_id=session_id,
        source=payload.get("source") or "api",
        caller_idempotency_key=payload.get("caller_idempotency_key"),
        metadata=payload.get("metadata") or {},
    )

    result = manager.capture_memory(request)
    if not result.success or result.value is None:
        err = result.error or "Capture processing failed"
        # Categorize error response status code
        if "below minimum threshold" in err or "exceeds maximum" in err or "Ineligible event category" in err:
            raise HTTPException(status_code=422, detail=err)
        if "does not match" in err or "belongs to project" in err:
            raise HTTPException(status_code=400, detail=err)
        raise HTTPException(status_code=500, detail=err)

    resp: CaptureEventResponse = result.value
    return {
        "status": resp.status,
        "memory_id": str(resp.memory_id) if resp.memory_id else None,
        "project_id": str(resp.project_id) if resp.project_id else None,
        "session_id": str(resp.session_id) if resp.session_id else None,
        "idempotency_key": resp.idempotency_key,
        "redactions_applied": resp.redactions_applied,
        "detail": resp.detail,
    }
