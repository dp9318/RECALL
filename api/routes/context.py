"""Context routes for RECALL HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import _parse_uuid, get_manager
from contracts.retrieval import CompactRequest, RetrievalRequest
from recall_core.memory_manager import MemoryManager

router = APIRouter(tags=["context"])


@router.post("/context/query")
def query_context(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    query_text = str(payload.get("query") or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="query is required")
    project_id = _parse_uuid(payload.get("project_id"), "project_id", allow_missing=True)
    session_id = _parse_uuid(payload.get("session_id"), "session_id", allow_missing=True)
    result = manager.retrieve(
        RetrievalRequest(
            query=query_text,
            project_id=project_id,
            session_id=session_id,
            limit=int(payload.get("limit") or 5),
            include_historical=bool(payload.get("include_historical", False)),
        )
    )
    if not result.success or result.value is None:
        raise HTTPException(status_code=500, detail=result.error or "Context query failed")
    memories = list(result.value.memories or [])
    supporting = [
        {
            "memory_id": str(memory.id),
            "content": memory.content,
            "relevance_score": round(1.0 / (idx + 1), 3) if idx >= 0 else 0.0,
        }
        for idx, memory in enumerate(memories[:5])
    ]
    return {
        "response": (
            f"Retrieved {len(memories)} memory matches for: {query_text}"
            if memories
            else f"No matching memories were found for: {query_text}"
        ),
        "supporting_memories": supporting,
        "session_id": str(session_id) if session_id is not None else "",
    }


@router.post("/context/compact")
def compact_context(
    payload: dict[str, Any],
    manager: MemoryManager = Depends(get_manager),
) -> dict[str, Any]:
    project_id = _parse_uuid(payload.get("project_id"), "project_id")
    session_id = _parse_uuid(payload.get("session_id"), "session_id", allow_missing=True)
    result = manager.compact(
        CompactRequest(
            project_id=project_id,
            session_id=session_id,
            preserve_lineage=True,
            max_active_memories=int(payload.get("max_active_memories") or 50),
        )
    )
    if not result.success or result.value is None:
        raise HTTPException(status_code=400, detail=result.error or "Context compaction failed")
    return {"success": True, "message": "Context compacted successfully"}
