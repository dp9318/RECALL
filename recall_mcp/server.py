"""Thin MCP adapter over the RECALL Core MemoryManager."""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from contracts.base import Result, Scope
from contracts.instruction import CustomInstructionCreateRequest
from contracts.memory import MemoryCreateRequest
from contracts.project import ProjectCreateRequest, SessionCreateRequest
from contracts.retrieval import (
    CompactRequest,
    ContextAssemblyRequest,
    RetrievalRequest,
)
from recall_core.bootstrap import create_memory_manager
from recall_core.memory_manager import MemoryManager

# Configure standard error logger so MCP JSON-RPC protocol on stdout is not corrupted
logger = logging.getLogger("recall_mcp")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s.%(msecs)03d] [%(levelname)s] [RECALL-MCP] %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

MAX_QUERY_LENGTH = 1_000
MAX_CONTENT_LENGTH = 10_000
MAX_RESULTS = 50
MIN_COMPACT_ACTIVE_MEMORIES = 5
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_ALLOWED_FACTORY_PREFIXES = ("recall_core.", "tests.")


def _load_mcp_mode() -> str:
    mode = os.environ.get("RECALL_MCP_MODE", "standard").strip().lower()
    if mode not in {"standard", "read-only"}:
        raise ValueError(f"Unsupported RECALL_MCP_MODE {mode!r}; expected 'standard' or 'read-only'")
    return mode


def _load_allowed_project_ids() -> set[UUID] | None:
    raw = os.environ.get("RECALL_ALLOWED_PROJECT_IDS")
    if raw is None:
        if os.environ.get("RECALL_MCP_STRICT_ISOLATION", "false").lower() in ("true", "1", "yes"):
            return set()
        return None
    stripped = raw.strip()
    if not stripped:
        return set()
    allowed: set[UUID] = set()
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            allowed.add(UUID(token))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Malformed UUID in RECALL_ALLOWED_PROJECT_IDS: {token!r}") from exc
    return allowed


def _validate_project_authorized(project_uuid: UUID, allowed_projects: set[UUID] | None) -> None:
    if allowed_projects is None:
        return
    if not allowed_projects:
        raise ToolError("No projects are authorized in RECALL_ALLOWED_PROJECT_IDS")
    if project_uuid not in allowed_projects:
        raise ToolError("Access denied: project_id is not in RECALL_ALLOWED_PROJECT_IDS")


def create_server(memory_manager: MemoryManager) -> FastMCP:
    """Create and configure a FastMCP server bound to the RECALL Core MemoryManager.

    Registers the canonical agent tools (or read-only subset when RECALL_MCP_MODE=read-only).
    """
    mcp_mode = _load_mcp_mode()
    allowed_projects = _load_allowed_project_ids()
    allow_global_instructions = (
        os.environ.get("RECALL_MCP_ALLOW_GLOBAL_INSTRUCTIONS", "false").lower() in ("true", "1", "yes")
    )
    allow_global_context = (
        allowed_projects is None
        or os.environ.get("RECALL_MCP_ALLOW_GLOBAL_CONTEXT", "false").lower() in ("true", "1", "yes")
    )
    server = FastMCP("RECALL")

    @server.tool()
    def recall_search(
        query: str,
        project_id: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search RECALL memories within one required project scope."""
        query = _validate_text(query, "query", max_length=MAX_QUERY_LENGTH)
        project_uuid, session_uuid = _validate_scope(
            memory_manager,
            project_id,
            session_id,
            create_session=False,
            allowed_projects=allowed_projects,
        )
        _validate_limit(limit)
        t_start = time.perf_counter()
        logger.info(f"recall_search START: query='{query[:60]}...', project_id='{project_id}', limit={limit}")

        t_retrieve_start = time.perf_counter()
        result = memory_manager.retrieve(
            RetrievalRequest(
                query=query,
                project_id=project_uuid,
                session_id=session_uuid,
                limit=limit,
                include_global=allow_global_context,
            )
        )
        t_retrieve_end = time.perf_counter()
        if not result.success or result.value is None:
            logger.error(f"recall_search FAILED after {t_retrieve_end - t_start:.3f}s: {result.error}")
            raise ToolError(result.error or "RECALL retrieval failed")

        total_elapsed = time.perf_counter() - t_start
        logger.info(
            f"recall_search DONE: found={result.value.total_found} memories | "
            f"core_retrieve={t_retrieve_end - t_retrieve_start:.3f}s, total={total_elapsed:.3f}s"
        )

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
        t_start = time.perf_counter()
        logger.info(f"recall_get_context START: project_id='{project_id}', query={query!r}, limit={limit}")
        project_uuid, session_uuid = _validate_scope(
            memory_manager,
            project_id,
            session_id,
            create_session=False,
            allowed_projects=allowed_projects,
        )
        _validate_limit(limit)
        if query is not None:
            query = _validate_text(query, "query", max_length=MAX_QUERY_LENGTH)

        t_assemble_start = time.perf_counter()
        result = memory_manager.assemble_context(
            ContextAssemblyRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                query=query,
                retrieval_limit=limit,
                include_historical=include_historical,
                include_global=allow_global_context,
            )
        )
        t_assemble_end = time.perf_counter()
        if not result.success or result.value is None:
            logger.error(f"recall_get_context FAILED after {t_assemble_end - t_start:.3f}s: {result.error}")
            raise ToolError(result.error or "RECALL context assembly failed")
        
        total_elapsed = time.perf_counter() - t_start
        logger.info(
            f"recall_get_context DONE: core_assemble={t_assemble_end - t_assemble_start:.3f}s, total={total_elapsed:.3f}s"
        )
        return _to_json(result.value)

    if mcp_mode == "read-only":
        return server

    @server.tool()
    def recall_save_memory(
        content: str,
        project_id: str,
        session_id: str | None = None,
        memory_type: str = "general",
    ) -> dict[str, Any]:
        """Save an agent-submitted memory through canonical Core persistence."""
        t_start = time.perf_counter()
        logger.info(f"recall_save_memory START: project_id='{project_id}', type='{memory_type}'")
        project_uuid, session_uuid = _validate_scope(
            memory_manager,
            project_id,
            session_id,
            create_session=True,
            allowed_projects=allowed_projects,
        )
        content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        memory_type = _validate_text(memory_type, "memory_type", max_length=64, default="general")

        t_save_start = time.perf_counter()
        result = memory_manager.create_memory(
            MemoryCreateRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                scope=Scope.PROJECT,
                memory_type=memory_type,
                content=content,
                provenance="agent_saved",
            )
        )
        t_save_end = time.perf_counter()
        if not result.success or result.value is None:
            logger.error(f"recall_save_memory FAILED after {t_save_end - t_start:.3f}s: {result.error}")
            raise ToolError(result.error or "RECALL could not save the memory")
        
        logger.info(f"recall_save_memory DONE: id={result.value.id} in {time.perf_counter() - t_start:.3f}s")
        return {
            "memory": _to_json(result.value),
            "metadata": _to_json(result.metadata),
        }

    @server.tool()
    def recall_compact_memory(
        project_id: str,
        session_id: str | None = None,
        preserve_lineage: Literal[True] = True,
        max_active_memories: int = 50,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Compact a project's memories through the existing Core operation."""
        project_uuid, session_uuid = _validate_optional_scope(
            memory_manager,
            project_id,
            session_id,
            project_required=True,
            create_session=False,
            allowed_projects=allowed_projects,
        )
        if not isinstance(preserve_lineage, bool):
            raise ToolError("preserve_lineage must be a boolean")
        if not preserve_lineage:
            raise ToolError("preserve_lineage must be true; compaction always preserves lineage")
        if (
            isinstance(max_active_memories, bool)
            or not isinstance(max_active_memories, int)
            or max_active_memories < MIN_COMPACT_ACTIVE_MEMORIES
        ):
            raise ToolError(
                f"max_active_memories must be an integer >= {MIN_COMPACT_ACTIVE_MEMORIES}"
            )
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY_RE.match(idempotency_key):
                raise ToolError(
                    "idempotency_key must be 1..128 characters matching [A-Za-z0-9_.:-]+"
                )

        result = memory_manager.compact(
            CompactRequest(
                project_id=project_uuid,
                session_id=session_uuid,
                preserve_lineage=preserve_lineage,
                max_active_memories=max_active_memories,
                idempotency_key=idempotency_key,
            )
        )
        if not result.success or result.value is None:
            raise ToolError(result.error or "RECALL compaction failed")
        return _to_json(result.value)

    @server.tool()
    def recall_create_custom_instruction(
        content: str,
        scope: str = "project",
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a project-scoped (or explicitly enabled global) custom instruction."""
        content = _validate_text(content, "content", max_length=MAX_CONTENT_LENGTH)
        scope_value = _parse_enum(scope, Scope, "scope")
        project_uuid = _parse_optional_uuid(project_id, "project_id")
        if scope_value is Scope.GLOBAL:
            if not allow_global_instructions:
                raise ToolError("Global custom instruction creation is disabled for MCP agents")
            if project_uuid is not None:
                raise ToolError("project_id is only valid for project-scoped instructions")
            if allowed_projects is not None:
                raise ToolError("Global custom instructions are disabled when RECALL_ALLOWED_PROJECT_IDS is active")
        else:
            if project_uuid is None:
                raise ToolError("project_id is required for project-scoped instructions")
            _validate_project_authorized(project_uuid, allowed_projects)
            _validate_project_exists(memory_manager, project_uuid)

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
    def recall_save_project(
        name: str,
        description: str | None = None,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Safely create or retrieve a project scope for memory association."""
        t_start = time.perf_counter()
        name = _validate_text(name, "name", max_length=255)
        if description is not None:
            description = _validate_text(description, "description", max_length=2000)
        project_uuid = _parse_optional_uuid(project_id, "project_id")

        if allowed_projects is not None:
            if project_uuid is None:
                raise ToolError("project_id is required when RECALL_ALLOWED_PROJECT_IDS is configured")
            _validate_project_authorized(project_uuid, allowed_projects)

        logger.info(f"recall_save_project START: name='{name}', project_id={project_id}")

        project = _resolve_or_create_project(
            memory_manager,
            name=name,
            description=description,
            project_uuid=project_uuid,
            metadata=metadata,
        )
        total_elapsed = time.perf_counter() - t_start
        logger.info(f"recall_save_project DONE: id={project.id} in {total_elapsed:.3f}s")
        return {"project": _to_json(project)}

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
    create_session: bool = True,
    allowed_projects: set[UUID] | None = None,
) -> tuple[UUID | None, UUID | None]:
    project_uuid = _parse_optional_uuid(project_id, "project_id")
    if project_required and project_uuid is None:
        raise ToolError("project_id is required")
    if project_uuid is not None:
        _validate_project_authorized(project_uuid, allowed_projects)
        _validate_project_exists(memory_manager, project_uuid)

    session_uuid = _parse_optional_uuid(session_id, "session_id")
    if session_uuid is not None:
        if project_uuid is None:
            raise ToolError("project_id is required when session_id is provided")
        if create_session:
            session_uuid = _resolve_or_create_session(memory_manager, project_uuid, session_uuid)
        else:
            existing = memory_manager.get_session(session_uuid)
            if existing.success and existing.value is not None and existing.value.project_id != project_uuid:
                raise ToolError("session_id does not belong to project_id")
    return project_uuid, session_uuid


def _resolve_or_create_session(
    memory_manager: MemoryManager,
    project_uuid: UUID,
    session_uuid: UUID,
) -> UUID:
    result = memory_manager.get_session(session_uuid)
    if result.success and result.value is not None:
        if result.value.project_id != project_uuid:
            raise ToolError("session_id does not belong to project_id")
        return session_uuid

    create_req = SessionCreateRequest(project_id=project_uuid, id=session_uuid)
    create_result = memory_manager.create_session(create_req)
    if not create_result.success or create_result.value is None:
        existing = memory_manager.get_session(session_uuid)
        if existing.success and existing.value is not None:
            if existing.value.project_id != project_uuid:
                raise ToolError("session_id does not belong to project_id")
            return session_uuid
        raise ToolError(create_result.error or "Failed to register session")
    return session_uuid


_project_lock = threading.Lock()


def _resolve_or_create_project(
    memory_manager: MemoryManager,
    name: str,
    description: str | None,
    project_uuid: UUID | None,
    metadata: dict[str, Any] | None,
) -> Any:
    with _project_lock:
        if hasattr(memory_manager, "resolve_or_create_project"):
            result = memory_manager.resolve_or_create_project(
                name=name,
                description=description,
                project_id=project_uuid,
                metadata=metadata,
            )
            if isinstance(result, Result):
                if not result.success or result.value is None:
                    raise ToolError(result.error or "Failed to resolve or create project")
                return result.value

        # Fallback for mock managers where individual repository methods are configured
        if project_uuid is not None:
            existing = memory_manager.get_project(project_uuid)
            if existing.success and existing.value is not None:
                proj = existing.value
                if proj.name.strip().lower() != name.strip().lower():
                    raise ToolError(
                        f"Project '{project_uuid}' already exists with name '{proj.name}', "
                        f"which conflicts with requested name '{name}'"
                    )
                return proj

            by_name = memory_manager.get_project_by_name(name)
            if by_name.success and by_name.value is not None:
                if by_name.value.id != project_uuid:
                    raise ToolError(
                        f"A project named '{name}' already exists with ID '{by_name.value.id}', "
                        f"which conflicts with requested ID '{project_uuid}'"
                    )

            create_req = ProjectCreateRequest(
                id=project_uuid,
                name=name,
                description=description,
                metadata=metadata or {},
            )
            create_result = memory_manager.create_project(create_req)
            if not create_result.success or create_result.value is None:
                raise ToolError(create_result.error or "Failed to create project")
            return create_result.value

        by_name = memory_manager.get_project_by_name(name)
        if by_name.success and by_name.value is not None:
            return by_name.value

        create_req = ProjectCreateRequest(
            name=name,
            description=description,
            metadata=metadata or {},
        )
        create_result = memory_manager.create_project(create_req)
        if not create_result.success or create_result.value is None:
            re_by_name = memory_manager.get_project_by_name(name)
            if re_by_name.success and re_by_name.value is not None:
                return re_by_name.value
            raise ToolError(create_result.error or "Failed to create project")
        return create_result.value



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
    *,
    create_session: bool = True,
    allowed_projects: set[UUID] | None = None,
) -> tuple[UUID, UUID | None]:
    try:
        project_uuid = UUID(str(project_id).strip())
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolError("project_id must be a valid UUID") from exc
    _validate_project_authorized(project_uuid, allowed_projects)
    _validate_project_exists(memory_manager, project_uuid)

    session_uuid = None
    if session_id is not None:
        try:
            session_uuid = UUID(str(session_id).strip())
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("session_id must be a valid UUID") from exc

        if create_session:
            session_uuid = _resolve_or_create_session(memory_manager, project_uuid, session_uuid)
        else:
            existing = memory_manager.get_session(session_uuid)
            if existing.success and existing.value is not None and existing.value.project_id != project_uuid:
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
    allow_unsafe = os.environ.get("RECALL_ALLOW_UNSAFE_FACTORY", "false").lower() in ("true", "1", "yes")
    if not allow_unsafe and not module_name.startswith(_ALLOWED_FACTORY_PREFIXES):
        raise RuntimeError(
            f"RECALL_CORE_FACTORY module '{module_name}' is not in allowlisted prefixes {_ALLOWED_FACTORY_PREFIXES}"
        )

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


def run_doctor() -> int:
    """Run pre-flight diagnostics for RECALL MCP installation and configuration."""
    report: dict[str, Any] = {
        "python": sys.version.split()[0],
        "mcp_mode": None,
        "allowed_projects": None,
        "core_init": "error",
        "stats": None,
        "ok": False,
    }
    try:
        report["mcp_mode"] = _load_mcp_mode()
        allowed = _load_allowed_project_ids()
        report["allowed_projects"] = [str(p) for p in sorted(allowed)] if allowed is not None else "unrestricted"
        factory_path = os.environ.get("RECALL_CORE_FACTORY")
        manager = _load_core_factory(factory_path) if factory_path else create_memory_manager()
        try:
            report["core_init"] = "ok"
            stats_res = manager.get_stats()
            if stats_res.success:
                report["stats"] = stats_res.value
            report["ok"] = bool(stats_res.success)
        finally:
            manager.close()
    except Exception as exc:
        report["error"] = str(exc)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


def main() -> None:
    """Start MCP with the default Core composition or an application override."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if "--doctor" in sys.argv[1:]:
        raise SystemExit(run_doctor())
    t_start = time.perf_counter()
    logger.info("Initializing RECALL MCP Server...")
    
    factory_path = os.environ.get("RECALL_CORE_FACTORY")
    try:
        t_factory_start = time.perf_counter()
        if factory_path:
            logger.info(f"Loading custom factory from RECALL_CORE_FACTORY='{factory_path}'...")
            memory_manager = _load_core_factory(factory_path)
        else:
            logger.info("Creating default Core memory manager (SQLite + ChromaDB + Models)...")
            memory_manager = create_memory_manager()
        t_factory_end = time.perf_counter()
        logger.info(f"MemoryManager initialized in {t_factory_end - t_factory_start:.3f}s")
    except Exception as exc:
        source = f"RECALL_CORE_FACTORY '{factory_path}'" if factory_path else "default Core composition"
        logger.error(f"RECALL startup failed using {source}: {exc}")
        raise SystemExit(f"RECALL startup failed using {source}: {exc}") from exc

    try:
        t_server_start = time.perf_counter()
        server = create_server(memory_manager)
        t_server_end = time.perf_counter()
        logger.info(f"FastMCP tools registered in {t_server_end - t_server_start:.3f}s")

        # Explicit startup warmup to eliminate first-query cold-start latency.
        # stdout is redirected to stderr during warmup so stdio transport is never corrupted.
        enable_warmup = os.environ.get("RECALL_MCP_WARMUP", "true").lower() in ("true", "1", "yes")
        if enable_warmup and hasattr(memory_manager, "warmup"):
            t_warmup_start = time.perf_counter()
            logger.info("Warming up RECALL semantic retrieval pipeline...")
            try:
                import contextlib
                with contextlib.redirect_stdout(sys.stderr):
                    warmup_result = memory_manager.warmup()
                t_warmup_end = time.perf_counter()
                if warmup_result.success:
                    logger.info(f"Semantic retrieval pipeline warmed up in {t_warmup_end - t_warmup_start:.3f}s")
                else:
                    logger.warning(f"Semantic warmup skipped or non-fatal failure: {warmup_result.error}")
            except Exception as warmup_exc:
                logger.warning(f"Semantic warmup exception (non-fatal): {warmup_exc}")

        logger.info(f"Starting FastMCP stdio transport (Total startup time: {time.perf_counter() - t_start:.3f}s)...")

        # mcp server
        server.run(transport="stdio")
    finally:
        logger.info("Shutting down RECALL MCP server and closing resources...")
        memory_manager.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
