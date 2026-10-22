"""Dependency injection and common parsing helpers for the RECALL HTTP API."""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, Request

from recall_core.bootstrap import create_memory_manager
from recall_core.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


def _parse_uuid(value: str | None, field_name: str, *, allow_missing: bool = False) -> UUID | None:
    if value is None or value == "":
        if allow_missing:
            return None
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    try:
        return UUID(value)
    except ValueError as exc:  # pragma: no cover - defensive validation
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value}") from exc


def _parse_status(value: str | None, enum_type: type, field_name: str) -> Any | None:
    if value is None or value == "":
        return None
    try:
        return enum_type(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value}") from exc


def get_manager(request: Request) -> MemoryManager:
    """Retrieve the active MemoryManager from application state or create a default instance."""
    if hasattr(request, "app") and hasattr(request.app, "state"):
        manager = getattr(request.app.state, "memory_manager", None)
        if manager is not None:
            return manager
        try:
            manager = create_memory_manager()
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise HTTPException(status_code=503, detail=f"RECALL core is unavailable: {exc}") from exc
        request.app.state.memory_manager = manager
        return manager

    # Fallback when called without request state
    try:
        return create_memory_manager()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RECALL core is unavailable: {exc}") from exc
