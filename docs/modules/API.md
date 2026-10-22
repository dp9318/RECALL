# RECALL — HTTP/JSON API Module Contract

## Goal

Provide a modular, robust FastAPI HTTP/JSON REST interface for the human-facing Web Dashboard and external HTTP clients, strictly orchestrating operations through the `MemoryManager` core domain facade without directly accessing database repositories or units of work.

## Architectural Boundaries

- **Strict Facade Encapsulation**: Handlers depend solely on `MemoryManager` injected via FastAPI dependency injection (`get_manager`). Direct access to `_uow`, repository classes, or database connections is prohibited and enforced continuously by AST regression tests.
- **Stateless Serialization**: Request validation and response serialization are decoupled from database entities. Serialization helpers in `api/serializers.py` convert domain dataclasses into standardized JSON responses with ISO-8601 timestamps and explicit lineage graphs.
- **No Direct Storage Mutation**: The API layer performs zero database queries or vector mutations directly.

## Modular Route Structure (`api/routes/`)

1. **Health (`health.py`)**:
   - `GET /health`, `GET /healthz`: Liveness and readiness probe reporting API version, database connectivity, and semantic index status.
2. **Projects (`projects.py`)**:
   - `GET /projects`: Paginated list of registered projects with memory and session counts.
   - `POST /projects`: Register a new project namespace.
   - `GET /projects/{project_id}`: Project details.
3. **Memories (`memories.py`)**:
   - `GET /memories`: Paginated, filtered memory list (by project, status, type, query).
   - `POST /memories`: Capture a new memory record.
   - `GET /memories/{memory_id}`: Detailed memory view including complete lineage graph (`supersedes`, `superseded_by`, `related_memories`).
     - **Lineage Specification**:
       - Primary predecessor: `lineage.supersedes` contains the first predecessor ID where `rel.child_id == memory_id` and `relationship == 'supersedes'`.
       - Additional predecessors: Multiple parents (e.g. from compaction summaries) are appended to `lineage.related_memories`.
       - Primary successor: `lineage.superseded_by` contains the first successor ID where `rel.parent_id == memory_id` and `relationship == 'supersedes'`.
       - Additional successors: Multiple successors (e.g. branching updates) are appended to `lineage.related_memories`.
       - Other relationships: Counterpart IDs for non-supersedes relationships (e.g. `derived_from`, `merged`, `referenced`) are appended to `lineage.related_memories` with duplicate and self-referential suppression.
   - `PATCH /memories/{memory_id}`: Update memory content, importance, tags, status.
   - `DELETE /memories/{memory_id}`: Deactivate/soft-delete a memory.
4. **Sessions (`sessions.py`)**:
   - `GET /sessions`: Paginated list of sessions for a project.
   - `POST /sessions`: Start a new agent session.
   - `GET /sessions/{session_id}`: Session status and statistics.
   - `PATCH /sessions/{session_id}`: End/close an active session.
5. **Custom Instructions (`instructions.py`)**:
   - `GET /custom-instructions`: List global or project-scoped user instructions.
   - `POST /custom-instructions`: Create an explicit custom instruction.
   - `PATCH /custom-instructions/{instruction_id}`: Update content or status.
   - `DELETE /custom-instructions/{instruction_id}`: Delete an instruction.
6. **Conflicts (`conflicts.py`)**:
   - `GET /conflicts`: List detected conflicts and resolution candidates.
   - `POST /conflicts`: Trigger deterministic evaluation and LLM arbitration.
7. **Stats (`stats.py`)**:
   - `GET /stats`: Global and project-level memory distribution, session count, active instructions, and conflict overview.
8. **Context (`context.py`)**:
   - `POST /context/query`: Search memories with semantic/lexical similarity.
   - `POST /context/compact`: Trigger context compaction with mandatory lineage preservation.

## Application Composition & Entry Points

- `api/app.py`: `create_app(memory_manager=None)` application factory configuring CORS middleware and aggregating modular routers.
- `api/main.py`: Executable CLI entry point running `uvicorn` on configured host and port (`RECALL_API_HOST`, `RECALL_API_PORT`).
- Console Script: Exposes `recall-api` CLI entry point via root `pyproject.toml`.
- Canonical Package: The top-level `api` package is the authoritative HTTP REST implementation (legacy `core/recall_core/api.py` shims retired per ADR 0003).
