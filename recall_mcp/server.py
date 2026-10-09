"""Thin MCP adapter over the RECALL Core MemoryManager."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from contracts.base import Scope
from contracts.memory import MemoryCreateRequest
from contracts.retrieval import ContextAssemblyRequest, RetrievalRequest
from core.recall_core.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 1_000
MAX_CONTENT_LENGTH = 10_000
MAX_RESULTS = 50


def create_server(memory_manager: MemoryManager) -> FastMCP:
    """Create an MCP server bound to an explicitly constructed Core manager."""
    server = FastMCP("RECALL")

    @server.tool()
    def recall_search(
        query: str,
        project_id: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search RECALL memories within one required project scope."""
        project_uuid, session_uuid = _validate_scope(memory_manager, project_id, session_id)
        query = query.strip()
        if not query or len(query) > MAX_QUERY_LENGTH:
            raise ToolError(f"query must contain 1 to {MAX_QUERY_LENGTH} characters")
        _validate_limit(limit)

        result = memory_manager.retrieve(
            RetrievalRequest(
                query=query,
                project_id=project_uuid,
                session_id=session_uuid,
                limit=limit,
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL retrieval failed")

        return {
            "query": result.value.query,
            "project_id": str(project_uuid),
            "session_id": str(session_uuid) if session_uuid else None,
            "total_found": result.value.total_found,
            "memories": [_to_json(memory) for memory in result.value.memories],
        }

    @server.tool()
    def recall_get_context(
        project_id: str,
        session_id: str | None = None,
        query: str | None = None,
        limit: int = 10,
        include_historical: bool = False,
    ) -> dict[str, Any]:
        """Assemble project context through the RECALL Core."""
        project_uuid, session_uuid = _validate_scope(memory_manager, project_id, session_id)
        _validate_limit(limit)
        if query is not None:
            query = query.strip()
            if not query or len(query) > MAX_QUERY_LENGTH:
                raise ToolError(f"query must contain 1 to {MAX_QUERY_LENGTH} characters")

        result = memory_manager.assemble_context(
            ContextAssemblyRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                query=query,
                retrieval_limit=limit,
                include_historical=include_historical,
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL context assembly failed")
        return _to_json(result.value)

    @server.tool()
    def recall_save_memory(
        content: str,
        project_id: str,
        session_id: str | None = None,
        memory_type: str = "general",
    ) -> dict[str, Any]:
        """Save a user-authored memory through canonical Core persistence."""
        project_uuid, session_uuid = _validate_scope(memory_manager, project_id, session_id)
        content = content.strip()
        memory_type = memory_type.strip()
        if not content or len(content) > MAX_CONTENT_LENGTH:
            raise ToolError(f"content must contain 1 to {MAX_CONTENT_LENGTH} characters")
        if not memory_type or len(memory_type) > 64:
            raise ToolError("memory_type must contain 1 to 64 characters")

        result = memory_manager.create_memory(
            MemoryCreateRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                scope=Scope.PROJECT,
                memory_type=memory_type,
                content=content,
                provenance="user_explicit",
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL could not save the memory")
        return {
            "memory": _to_json(result.value),
            "metadata": _to_json(result.metadata),
        }

    return server


def _validate_scope(
    memory_manager: MemoryManager,
    project_id: str,
    session_id: str | None,
) -> tuple[UUID, UUID | None]:
    try:
        project_uuid = UUID(project_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolError("project_id must be a valid UUID") from exc

    session_uuid = None
    if session_id is not None:
        try:
            session_uuid = UUID(session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("session_id must be a valid UUID") from exc

        result = memory_manager.get_session(session_uuid)
        if not result.success or result.value is None:
            raise ToolError(result.error or "The requested session was not found")
        if result.value.project_id != project_uuid:
            raise ToolError("session_id does not belong to project_id")

    return project_uuid, session_uuid


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise ToolError(f"limit must be between 1 and {MAX_RESULTS}")


def _to_json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _to_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(item) for item in value]
    return value


def _load_core_factory(factory_path: str) -> MemoryManager:
    module_name, separator, attribute_name = factory_path.partition(":")
    if not separator or not module_name or not attribute_name:
        raise RuntimeError("RECALL_CORE_FACTORY must use the format 'package.module:factory'")

    factory = getattr(importlib.import_module(module_name), attribute_name)
    memory_manager = factory()
    if not isinstance(memory_manager, MemoryManager):
        raise TypeError("The configured RECALL core factory must return a MemoryManager")
    return memory_manager


def main() -> None:
    """Start the local stdio MCP server from an application-provided Core factory."""
    factory_path = os.environ.get("RECALL_CORE_FACTORY")
    if not factory_path:
        raise SystemExit(
            "RECALL_CORE_FACTORY is required. This checkout has no concrete database "
            "repositories or Core bootstrap; configure a factory returning MemoryManager."
        )

    memory_manager = _load_core_factory(factory_path)
    logger.info("Starting RECALL MCP server with the configured Core factory")
    create_server(memory_manager).run(transport="stdio")


if __name__ == "__main__":
    main()
