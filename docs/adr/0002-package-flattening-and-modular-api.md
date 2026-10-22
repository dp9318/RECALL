# ADR 0002 — Package Flattening, Modular API, and Core Facade Encapsulation

## Status

Accepted.

## Context

Prior to restructuring, the application core resided inside a nested subpackage `core/recall_core/`, and the HTTP API implementation was a 716-line monolith embedded directly within `core/recall_core/api.py`. The monolith directly accessed `memory_manager._uow` and underlying repository classes, violating the client encapsulation invariant established in `docs/ARCHITECTURE.md` and `docs/modules/CORE_MEMORY.md`.

Furthermore, packaging configuration was split between a subfolder `core/pyproject.toml` and root configuration, creating ambiguity over the project root, test discovery, and installation syntax. In addition, memory lineage relationships persisted during context compaction were hidden by hardcoded null values in API serialization because the domain facade lacked a public method to query lineage.

## Decision

1. **Flatten Core Package**: Promote `core/recall_core/` to top-level `recall_core/`. Maintain thin backward-compatibility re-export shims in `core/recall_core/` to prevent breaking existing tests and legacy commands.
2. **Modularize HTTP API**: Decompose the 716-line monolith into a dedicated top-level `api/` package featuring:
   - `app.py`: Application factory configuring CORS middleware and registering modular routers.
   - `dependencies.py`: Request-scoped dependency injection (`get_manager`) and validation helpers.
   - `serializers.py`: Typed response serialization helpers.
   - `main.py`: Executable CLI entry point for `uvicorn`.
   - `routes/`: Modular router definitions (`health.py`, `projects.py`, `memories.py`, `sessions.py`, `instructions.py`, `conflicts.py`, `stats.py`, `context.py`).
3. **Enforce Strict Layer Encapsulation**:
   - Forbid direct access to private attributes (`_uow`) or repositories from `api/` and `recall_mcp/`.
   - Add public facade query methods on `MemoryManager`: `list_projects_paginated`, `get_project_memory_count`, `get_project_session_count`, `list_sessions_paginated`, `get_session_memory_count`, `get_conflicts`, and `get_memory_lineage`.
   - Continuously enforce zero `_uow` access across `api/` using AST regression tests.
4. **Expose Memory Lineage**: Expose `MemoryManager.get_memory_lineage(memory_id)` to allow the API serializer to dynamically populate `superseded_by` and `related_memories`, unlocking lineage graph visualization in the Web Dashboard.
5. **Single Authoritative Root Packaging**: Consolidate build and dependency definitions into the root `pyproject.toml`, exposing standardized CLI console scripts `recall-mcp` and `recall-api`. Retire redundant `core/pyproject.toml` and root Node scaffolding.

## Consequences

- All client surfaces (`api/` and `recall_mcp/`) communicate with domain storage strictly through the public `MemoryManager` interface.
- Direct repository queries and raw SQL from the web/API layer are eliminated.
- Pytest and package installation operate predictably from the repository root via `pip install -e .`.
- Full parent-child and compaction lineage is visible in API responses and the Web Dashboard.
- Legacy import paths (`core.recall_core.api`) and invocations continue to work seamlessly via backward-compatibility shims until a future formal deprecation.
