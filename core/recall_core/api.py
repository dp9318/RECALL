"""HTTP JSON API for the RECALL dashboard.

This module exposes the Frontend-facing API contract over the existing
MemoryManager and repository stack.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from contracts.base import InstructionStatus, MemoryStatus, PaginationParams, Result, Scope
from contracts.conflict import ConflictCandidate, ConflictResolutionStatus
from contracts.instruction import (
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from contracts.memory import MemoryCreateRequest, MemorySearchParams, MemoryUpdateRequest
from contracts.project import Project, ProjectCreateRequest, Session, SessionCreateRequest
from contracts.retrieval import CompactRequest, RetrievalRequest
from core.recall_core.bootstrap import create_memory_manager
from core.recall_core.memory_manager import MemoryManager


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


def _project_name_for(memory_manager: MemoryManager, project_id: UUID | None) -> str | None:
    if project_id is None:
        return None
    result = memory_manager.get_project(project_id)
    if result.success and result.value is not None:
        return result.value.name
    return None


def _serialize_memory(memory_manager: MemoryManager, memory: Any) -> dict[str, Any]:
    project_name = _project_name_for(memory_manager, getattr(memory, "project_id", None))
    metadata = getattr(memory, "metadata", None) or {}
    lineage = {
        "supersedes": str(memory.supersedes_id) if getattr(memory, "supersedes_id", None) else None,
        "superseded_by": None,
        "related_memories": [],
    }
    importance = metadata.get("importance")
    if importance is None:
        importance = 50
    created_at = memory.created_at.isoformat() if hasattr(memory, "created_at") and memory.created_at is not None else datetime.now(timezone.utc).isoformat()
    updated_at = memory.updated_at.isoformat() if hasattr(memory, "updated_at") and memory.updated_at is not None else created_at
    return {
        "memory_id": str(memory.id),
        "project_id": str(memory.project_id) if memory.project_id is not None else None,
        "project_name": project_name,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "status": memory.status.value if hasattr(memory.status, "value") else str(memory.status),
        "importance": int(importance),
        "provenance": memory.provenance or "api",
        "lineage": lineage,
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": metadata.get("tags", []),
    }


def _serialize_instruction(instruction: Any, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    project_name = None
    if memory_manager is not None and getattr(instruction, "project_id", None):
        project_name = _project_name_for(memory_manager, instruction.project_id)
    return {
        "instruction_id": str(instruction.id),
        "scope": instruction.scope.value if hasattr(instruction.scope, "value") else str(instruction.scope),
        "project_id": str(instruction.project_id) if instruction.project_id is not None else None,
        "project_name": project_name,
        "content": instruction.content,
        "active": instruction.is_active() if hasattr(instruction, "is_active") else instruction.status == InstructionStatus.ACTIVE,
        "created_at": instruction.created_at.isoformat(),
        "updated_at": instruction.updated_at.isoformat(),
        "version": instruction.version,
    }


def _serialize_project(project: Project, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    memory_count = 0
    session_count = 0
    if memory_manager is not None:
        try:
            mem_res = memory_manager._uow.memories.search(
                MemorySearchParams(project_id=project.id, status=MemoryStatus.ACTIVE, limit=1)
            )
            if mem_res.success and mem_res.value:
                memory_count = mem_res.value.total
        except Exception:
            memory_count = 0
        try:
            sess_res = memory_manager._uow.sessions.list(
                PaginationParams(limit=1), project_id=project.id
            )
            if sess_res.success and sess_res.value:
                session_count = sess_res.value.total
        except Exception:
            session_count = 0
    return {
        "project_id": str(project.id),
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "memory_count": memory_count,
        "session_count": session_count,
    }


def _serialize_session(session: Session, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    project_name = None
    memory_captures = 0
    if memory_manager is not None:
        if getattr(session, "project_id", None):
            project_name = _project_name_for(memory_manager, session.project_id)
        try:
            mem_res = memory_manager._uow.memories.search(
                MemorySearchParams(session_id=session.id, limit=1, include_historical=True)
            )
            if mem_res.success and mem_res.value:
                memory_captures = mem_res.value.total
        except Exception:
            memory_captures = 0
    status = "active" if session.is_active() else "closed"
    return {
        "id": str(session.id),
        "session_id": str(session.id),
        "project_id": str(session.project_id),
        "project_name": project_name,
        "status": status,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "created_at": getattr(session, "created_at", session.started_at).isoformat(),
        "updated_at": getattr(session, "updated_at", session.started_at).isoformat(),
        "message_count": 0,
        "memory_captures": memory_captures,
    }


def _serialize_conflict(result: Any, project_id: UUID | None = None) -> dict[str, Any]:
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    mapped_status = {
        ConflictResolutionStatus.RESOLVED.value: "resolved",
        ConflictResolutionStatus.PARTIALLY_RESOLVED.value: "partially_resolved",
        ConflictResolutionStatus.UNRESOLVED.value: "unresolved",
        ConflictResolutionStatus.ABSTAINED.value: "abstained",
    }.get(status, "detected")
    conflicting_memories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in list(result.preferred_candidates) + list(result.superseded_candidates) + list(result.unresolved_candidates):
        memory = getattr(candidate, "memory", None)
        if memory is None:
            continue
        memory_id = str(memory.id)
        if memory_id in seen:
            continue
        seen.add(memory_id)
        conflicting_memories.append(
            {
                "memory_id": memory_id,
                "content": memory.content,
                "status": "preferred" if candidate in result.preferred_candidates else "conflicting",
                "confidence": getattr(candidate, "relevance_score", 0.0),
            }
        )
    preferred_ids = [str(candidate.memory.id) for candidate in result.preferred_candidates if candidate.memory is not None]
    superseded_ids = [str(candidate.memory.id) for candidate in result.superseded_candidates if candidate.memory is not None]
    return {
        "conflict_id": str(uuid4()),
        "project_id": str(project_id) if project_id is not None else "",
        "status": mapped_status,
        "conflicting_memories": conflicting_memories,
        "resolution": {
            "preferred_memories": preferred_ids,
            "superseded_memories": superseded_ids,
            "reason": result.resolution_reason or "No explicit resolution reason provided",
            "deterministic": not result.model_used,
            "local_model_used": result.model_used,
            "confidence": max((decision.confidence for decision in result.decisions), default=0.0),
        },
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
    }


def create_app(memory_manager: MemoryManager | None = None) -> FastAPI:
    """Build the FastAPI application bound to a RECALL MemoryManager."""
    app = FastAPI(title="RECALL HTTP API", version="1.0.0")
    cors_origins = [
        origin.strip()
        for origin in os.getenv("RECALL_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if not cors_origins:
        cors_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.memory_manager = memory_manager

    def get_manager() -> MemoryManager:
        manager = app.state.memory_manager
        if manager is not None:
            return manager
        try:
            manager = create_memory_manager()
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise HTTPException(status_code=503, detail=f"RECALL core is unavailable: {exc}") from exc
        app.state.memory_manager = manager
        return manager

    @app.get("/health")
    def health() -> dict[str, Any]:
        manager = get_manager()
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
            "api_version": "1.0.0",
            "database_connected": database_connected,
            "chromadb_connected": chromadb_connected,
            "local_llm_available": local_llm_available,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/projects")
    def list_projects(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        manager = get_manager()
        paginated_result = manager._uow.projects.list(PaginationParams(limit=limit, offset=offset))
        if not paginated_result.success or paginated_result.value is None:
            raise HTTPException(status_code=500, detail=paginated_result.error or "Unable to list projects")
        paginated = paginated_result.value
        projects = list(paginated.items)
        payload = {
            "projects": [_serialize_project(project, manager) for project in projects],
            "total": paginated.total,
        }
        return payload

    @app.post("/projects")
    def create_project(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    @app.get("/memories")
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
    ) -> dict[str, Any]:
        manager = get_manager()
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

        payload = {
            "memories": [_serialize_memory(manager, memory) for memory in memories],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
        return payload

    @app.get("/memories/{memory_id}")
    def get_memory(memory_id: str) -> dict[str, Any]:
        manager = get_manager()
        memory_uuid = _parse_uuid(memory_id, "memory_id")
        result = manager.get_memory(memory_uuid)
        if not result.success or result.value is None or result.value.status == MemoryStatus.DELETED:
            raise HTTPException(status_code=404, detail="Memory not found")
        return _serialize_memory(manager, result.value)

    @app.post("/memories")
    def create_memory(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    @app.patch("/memories/{memory_id}")
    def update_memory(memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
        memory_uuid = _parse_uuid(memory_id, "memory_id")
        existing_result = manager.get_memory(memory_uuid)
        if not existing_result.success or existing_result.value is None or existing_result.value.status == MemoryStatus.DELETED:
            raise HTTPException(status_code=404, detail="Memory not found")
        existing_memory = existing_result.value

        content_val = payload.get("content")
        if content_val is not None:
            content_val = str(content_val).strip()
            if not content_val:
                raise HTTPException(status_code=400, detail="Content cannot be empty")

        status_value = _parse_status(payload.get("status"), MemoryStatus, "status")

        # Metadata merging: preserve existing metadata, apply payload["metadata"], and merge top-level importance/tags
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

    @app.delete("/memories/{memory_id}")
    def delete_memory(memory_id: str) -> Response:
        manager = get_manager()
        memory_uuid = _parse_uuid(memory_id, "memory_id")
        result = manager.delete_memory(memory_uuid)
        if not result.success or not result.value:
            raise HTTPException(status_code=404, detail=result.error or "Memory not found")
        return Response(status_code=204)

    @app.get("/custom-instructions")
    def list_custom_instructions(
        project_id: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        manager = get_manager()
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

    @app.post("/custom-instructions")
    def create_custom_instruction(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    @app.patch("/custom-instructions/{instruction_id}")
    def update_custom_instruction(instruction_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    @app.delete("/custom-instructions/{instruction_id}")
    def delete_custom_instruction(instruction_id: str) -> Response:
        manager = get_manager()
        instruction_uuid = _parse_uuid(instruction_id, "instruction_id")
        result = manager.delete_instruction(instruction_uuid)
        if not result.success:
            raise HTTPException(status_code=404, detail=result.error or "Instruction not found")
        return Response(status_code=204)

    @app.get("/conflicts")
    def list_conflicts(project_id: str | None = None) -> dict[str, Any]:
        manager = get_manager()
        project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True)
        available = manager._uow.memories.search(MemorySearchParams(project_id=project_uuid, status=MemoryStatus.ACTIVE, limit=200))
        if not available.success:
            raise HTTPException(status_code=500, detail=available.error or "Unable to load conflicts")
        memories = list(available.value.items if available.value is not None else [])
        if len(memories) < 2:
            return {"conflicts": [], "total": 0}
        candidates = [
            ConflictCandidate(id=memory.id, memory=memory, relevance_score=1.0)
            for memory in memories
        ]
        result = manager.detect_and_resolve_conflicts(candidates, [], project_id=project_uuid)
        if not result.success:
            return {"conflicts": [], "total": 0}
        conflict = _serialize_conflict(result.value, project_uuid)
        if not conflict["conflicting_memories"]:
            return {"conflicts": [], "total": 0}
        return {"conflicts": [conflict], "total": 1}

    @app.get("/sessions")
    def list_sessions(project_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        manager = get_manager()
        project_uuid = _parse_uuid(project_id, "project_id", allow_missing=True)
        result = manager._uow.sessions.list(PaginationParams(limit=limit, offset=offset), project_id=project_uuid)
        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Unable to list sessions")
        sessions = list(result.value.items if result.value is not None else [])
        return {
            "sessions": [_serialize_session(session, manager) for session in sessions],
            "total": result.value.total if result.value is not None else len(sessions),
        }

    @app.post("/sessions")
    def create_session(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    @app.get("/stats")
    def get_stats() -> dict[str, Any]:
        manager = get_manager()
        result = manager.get_stats()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Unable to load stats")
        payload = result.value or {}
        memory_payload = payload.get("memories", {})
        instruction_payload = payload.get("custom_instructions", {})
        total_memories = sum(int(v) for v in memory_payload.values()) if isinstance(memory_payload, dict) else 0
        total_instructions = sum(int(v) for v in instruction_payload.values()) if isinstance(instruction_payload, dict) else 0
        semantic_health = payload.get("semantic_index", {})

        unresolved_conflicts = 0
        try:
            conflicts_data = list_conflicts()
            unresolved_conflicts = sum(
                1 for c in conflicts_data.get("conflicts", [])
                if c.get("status") in {"unresolved", "detected"}
            )
        except Exception:
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

    @app.post("/context/query")
    def query_context(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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
            "response": f"Retrieved {len(memories)} memory matches for: {query_text}" if memories else f"No matching memories were found for: {query_text}",
            "supporting_memories": supporting,
            "session_id": str(session_id) if session_id is not None else "",
        }

    @app.post("/context/compact")
    def compact_context(payload: dict[str, Any]) -> dict[str, Any]:
        manager = get_manager()
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

    return app


app = create_app()


def main() -> None:
    """Run the dashboard API on the configured host and port."""
    import uvicorn

    host = os.getenv("RECALL_API_HOST", "0.0.0.0")
    port = int(os.getenv("RECALL_API_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
