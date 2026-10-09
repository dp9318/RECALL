"""Thin MCP adapter over the RECALL Core MemoryManager."""

from __future__ import annotations

import importlib
import os
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from contracts.base import InstructionStatus, Scope
from contracts.instruction import (
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
)
from contracts.memory import MemoryCreateRequest
from contracts.retrieval import (
    CompactRequest,
    ContextAssemblyRequest,
    RetrievalRequest,
    UpdateContextRequest,
)
from core.recall_core.bootstrap import create_memory_manager
from core.recall_core.memory_manager import MemoryManager

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
        query = _validate_text(query, "query", max_length=MAX_QUERY_LENGTH)
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
            query = _validate_text(query, "query", max_length=MAX_QUERY_LENGTH)

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
        content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        memory_type = _validate_text(memory_type, "memory_type", max_length=64, default="general")

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

    @server.tool()
    def recall_update_context(
        content: str,
        project_id: str | None = None,
        session_id: str | None = None,
        memory_type: str = "context_update",
        provenance: str = "user_explicit",
    ) -> dict[str, Any]:
        """Persist explicit project or global context through Core."""
        project_uuid, session_uuid = _validate_optional_scope(
            memory_manager, project_id, session_id
        )
        content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        memory_type = _validate_text(memory_type, "memory_type", max_length=64)
        provenance = _validate_text(provenance, "provenance", max_length=128)

        result = memory_manager.update_context(
            UpdateContextRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                content=content,
                memory_type=memory_type,
                provenance=provenance,
            )
        )
        if not result.success or result.value is None or not result.value.success:
            error = result.error or (
                result.value.error if result.value is not None else None
            )
            raise ToolError(error or "RECALL could not update context")
        return _to_json(result.value)

    @server.tool()
    def recall_compact(
        project_id: str,
        session_id: str | None = None,
        preserve_lineage: Literal[True] = True,
        max_active_memories: int = 50,
    ) -> dict[str, Any]:
        """Compact a project's memories through the existing Core operation."""
        project_uuid, session_uuid = _validate_optional_scope(
            memory_manager, project_id, session_id, project_required=True
        )
        if not isinstance(preserve_lineage, bool):
            raise ToolError("preserve_lineage must be a boolean")
        if not preserve_lineage:
            raise ToolError("preserve_lineage must be true; compaction always preserves lineage")
        if (
            isinstance(max_active_memories, bool)
            or not isinstance(max_active_memories, int)
            or max_active_memories < 1
        ):
            raise ToolError("max_active_memories must be a positive integer")

        result = memory_manager.compact(
            CompactRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                preserve_lineage=preserve_lineage,
                max_active_memories=max_active_memories,
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL compaction failed")
        return _to_json(result.value)

    @server.tool()
    def recall_list_custom_instructions(
        scope: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List custom instructions using supported Core filters."""
        if scope is not None:
            scope_value = _parse_enum(scope, Scope, "scope")
        else:
            scope_value = None
        if status is not None:
            status_value = _parse_enum(status, InstructionStatus, "status")
        else:
            status_value = None
        project_uuid = _parse_optional_uuid(project_id, "project_id")
        if project_uuid is not None:
            _validate_project_exists(memory_manager, project_uuid)
        _validate_pagination(limit, offset)

        result = memory_manager.list_instructions(
            CustomInstructionListParams(
                scope=scope_value,
                project_id=project_uuid,
                status=status_value,
                limit=limit,
                offset=offset,
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL could not list instructions")
        instructions = [_to_json(item) for item in result.value]
        return {"instructions": instructions, "count": len(instructions)}

    @server.tool()
    def recall_create_custom_instruction(
        content: str,
        scope: str = "global",
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a global or project-scoped custom instruction."""
        content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        scope_value = _parse_enum(scope, Scope, "scope")
        project_uuid = _parse_optional_uuid(project_id, "project_id")
        if scope_value is Scope.PROJECT:
            if project_uuid is None:
                raise ToolError("project_id is required for project-scoped instructions")
            _validate_project_exists(memory_manager, project_uuid)
        elif project_uuid is not None:
            raise ToolError("project_id is only valid for project-scoped instructions")

        result = memory_manager.create_instruction(
            CustomInstructionCreateRequest(
                content=content,
                scope=scope_value,
                project_id=project_uuid,
                metadata=metadata or {},
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL could not create instruction")
        return {"instruction": _to_json(result.value)}

    @server.tool()
    def recall_update_custom_instruction(
        instruction_id: str,
        content: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update supported fields on an existing custom instruction."""
        instruction_uuid = _parse_uuid(instruction_id, "instruction_id")
        if content is not None:
            content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        if status is not None:
            status_value = _parse_enum(status, InstructionStatus, "status")
        else:
            status_value = None
        if content is None and status_value is None and metadata is None:
            raise ToolError("At least one of content, status, or metadata is required")

        result = memory_manager.update_instruction(
            instruction_uuid,
            CustomInstructionUpdateRequest(
                content=content,
                status=status_value,
                metadata=metadata,
            ),
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "The requested instruction was not found")
        return {"instruction": _to_json(result.value)}

    @server.tool()
    def recall_delete_custom_instruction(instruction_id: str) -> dict[str, Any]:
        """Deactivate a custom instruction through Core persistence."""
        instruction_uuid = _parse_uuid(instruction_id, "instruction_id")
        result = memory_manager.delete_instruction(instruction_uuid)
        if not result.success:
            raise ToolError(result.error or "RECALL could not delete instruction")
        if not result.value:
            raise ToolError("The requested instruction was not found")
        return {"instruction_id": str(instruction_uuid), "deleted": True}

    return server


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value.strip())
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolError(f"{field_name} must be a valid UUID") from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value is None:
        return None
    return _parse_uuid(value, field_name)


def _parse_enum(value: str, enum_type: type[Enum], field_name: str) -> Any:
    try:
        return enum_type(value)
    except (ValueError, TypeError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ToolError(f"{field_name} must be one of: {allowed}") from exc


def _validate_optional_scope(
    memory_manager: MemoryManager,
    project_id: str | None,
    session_id: str | None,
    *,
    project_required: bool = False,
) -> tuple[UUID | None, UUID | None]:
    project_uuid = _parse_optional_uuid(project_id, "project_id")
    if project_required and project_uuid is None:
        raise ToolError("project_id is required")
    if project_uuid is not None:
        _validate_project_exists(memory_manager, project_uuid)

    session_uuid = _parse_optional_uuid(session_id, "session_id")
    if session_uuid is not None:
        if project_uuid is None:
            raise ToolError("project_id is required when session_id is provided")
        result = memory_manager.get_session(session_uuid)
        if not result.success or result.value is None:
            raise ToolError(result.error or "The requested session was not found")
        if result.value.project_id != project_uuid:
            raise ToolError("session_id does not belong to project_id")
    return project_uuid, session_uuid


def _validate_project_exists(memory_manager: MemoryManager, project_id: UUID) -> None:
    result = memory_manager.get_project(project_id)
    if not result.success or result.value is None:
        raise ToolError(result.error or "The requested project was not found")


def _validate_pagination(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ToolError(f"limit must be between 1 and {MAX_RESULTS}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ToolError("offset must be a non-negative integer")


def _validate_text(value: Any, field_name: str, *, max_length: int | None = None, default: str | None = None) -> str:
    if value is None:
        if default is not None:
            value = default
        else:
            raise ToolError(f"{field_name} is required")
    if not isinstance(value, str):
        raise ToolError(f"{field_name} must be a string")
    text = value.strip()
    if default is not None and text == "":
        return default.strip()
    if not text:
        if max_length is not None:
            raise ToolError(f"{field_name} must contain 1 to {max_length} characters")
        raise ToolError(f"{field_name} is required")
    if max_length is not None and len(text) > max_length:
        raise ToolError(f"{field_name} must contain 1 to {max_length} characters")
    return text


def _validate_scope(
    memory_manager: MemoryManager,
    project_id: str | UUID,
    session_id: str | UUID | None,
) -> tuple[UUID, UUID | None]:
    try:
        project_uuid = UUID(str(project_id).strip())
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolError("project_id must be a valid UUID") from exc
    _validate_project_exists(memory_manager, project_uuid)

    session_uuid = None
    if session_id is not None:
        try:
            session_uuid = UUID(str(session_id).strip())
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("session_id must be a valid UUID") from exc

        result = memory_manager.get_session(session_uuid)
        if not result.success or result.value is None:
            raise ToolError(result.error or "The requested session was not found")
        if result.value.project_id != project_uuid:
            raise ToolError("session_id does not belong to project_id")

    return project_uuid, session_uuid


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
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

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(
            f"Could not import RECALL_CORE_FACTORY module '{module_name}': {exc}"
        ) from exc
    try:
        factory = getattr(module, attribute_name)
    except AttributeError as exc:
        raise RuntimeError(
            f"RECALL_CORE_FACTORY module '{module_name}' has no factory '{attribute_name}'"
        ) from exc
    if not callable(factory):
        raise RuntimeError(
            f"RECALL_CORE_FACTORY target '{factory_path}' is not callable"
        )

    try:
        memory_manager = factory()
    except Exception as exc:
        raise RuntimeError(
            f"RECALL_CORE_FACTORY '{factory_path}' failed to initialize: {exc}"
        ) from exc
    if not isinstance(memory_manager, MemoryManager):
        raise TypeError("The configured RECALL core factory must return a MemoryManager")
    return memory_manager


def main() -> None:
    """Start MCP with the default Core composition or an application override."""
    factory_path = os.environ.get("RECALL_CORE_FACTORY")
    try:
        memory_manager = (
            _load_core_factory(factory_path)
            if factory_path
            else create_memory_manager()
        )
    except Exception as exc:
        source = f"RECALL_CORE_FACTORY '{factory_path}'" if factory_path else "default Core composition"
        raise SystemExit(f"RECALL startup failed using {source}: {exc}") from exc

    try:
        create_server(memory_manager).run(transport="stdio")
    finally:
        memory_manager.close()


if __name__ == "__main__":
    main()
