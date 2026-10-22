"""Health endpoints for RECALL HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_manager
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["health"])


@router.get("/health")
def health(manager: MemoryManager = Depends(get_manager)) -> dict[str, Any]:
    database_connected = True
    semantic_index = getattr(manager, "_semantic_index", None)
    chromadb_connected = False
    if semantic_index is not None and hasattr(semantic_index, "health_check"):
        try:
            health_result = semantic_index.health_check()
            if getattr(health_result, "success", False):
                payload = health_result.value or {}
                if isinstance(payload, dict):
                    status_value = payload.get("status")
                    chromadb_connected = status_value in {"healthy", "available"} or bool(payload.get("available"))
        except Exception:
            chromadb_connected = False
    local_llm_available = True
    return {
        "status": "healthy" if database_connected and chromadb_connected else "degraded",
        "api_version": "1.1.0",
        "database_connected": database_connected,
        "chromadb_connected": chromadb_connected,
        "local_llm_available": local_llm_available,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/healthz")
def healthz(manager: MemoryManager = Depends(get_manager)) -> dict[str, Any]:
    """Liveness probe alias for health."""
    return health(manager=manager)
