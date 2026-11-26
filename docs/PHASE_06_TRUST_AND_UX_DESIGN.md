# RECALL — Phase 06 & Phase 09: MCP Agent Boundaries & Community Edition Scope

**Status:** HTTP Operator & Capture Token Authentication Removed in Phase 09 (`RECALL 3.1.0` Target)  
**Architectural Principle:** **RECALL Community is a local-first, accountless application. Authentication is exclusive to RECALL Pro.**

---

## 1. Community Architecture

RECALL Community enforces agent safety and structural boundaries without user authentication:

1. **MCP Agent Boundary (`recall_mcp/server.py`)**:
   - Enforces permission modes (`RECALL_MCP_MODE=read-only` vs `standard`), fail-closed project allowlists (`RECALL_ALLOWED_PROJECT_IDS`), zero-write read paths (`create_session=False`), `agent_saved` provenance, `scope="global"` rejection unless explicitly enabled, and a non-bypassable compaction floor (`max_active_memories >= 5`).
2. **Accountless Local HTTP API (`api/app.py`, `api/routes/`)**:
   - All REST endpoints operate locally without authentication headers, login routes, session cookies, CSRF tokens, or operator/capture tokens.
3. **Core Authority & Provenance (`intelligence/conflict.py`, `intelligence/retrieval.py`, `recall_core/`)**:
   - Ranks `agent_saved` consistently below `user_explicit` and `explicit_user_update` across retrieval scoring, conflict resolution, and context assembly.

---

## 2. Authentication Policy (Removed in Phase 09)

RECALL Community is a local-first, accountless single-user application. Authentication is exclusive to RECALL Pro. Operator authentication, `/auth/*` routes, login UI, `.operator_token`, `.capture_token`, session cookies, and CSRF/Origin/Host auth middleware were completely removed in Phase 09 without flags or fallbacks.

---

## 3. Project Isolation & Authorization Model

Every MCP tool checks `RECALL_ALLOWED_PROJECT_IDS` **at the operation boundary** (inside tool dispatch + `_validate_scope` / `_validate_project_exists`), not merely at initial project resolution:

- **Missing or Empty `RECALL_ALLOWED_PROJECT_IDS`**:
  - Unset: defaults to **unrestricted** for backward compatibility with single-user multi-project setups, UNLESS `RECALL_MCP_STRICT_ISOLATION=true` (which fails closed if unset).
  - Set to empty string (`RECALL_ALLOWED_PROJECT_IDS=""`) or whitespace: **fail-closed** (`ToolError("No projects are authorized in RECALL_ALLOWED_PROJECT_IDS")`).
  - Malformed UUID entries in `RECALL_ALLOWED_PROJECT_IDS`: validated strictly at `create_server()` startup, raising `ValueError`/`SystemExit` immediately rather than silently skipping.
- **Invalid Project Identifiers**: Malformed UUIDs (non-UUID strings, empty strings, `"RECALL"` name passed as `project_id`) immediately raise `ToolError("project_id must be a valid UUID")` before any DB query.
- **Unauthorized Project UUIDs**: If `RECALL_ALLOWED_PROJECT_IDS` is configured and `project_uuid not in allowed_ids`, raise `ToolError("Access denied: project_id is not in RECALL_ALLOWED_PROJECT_IDS")` **before** querying existence (prevents UUID oracle probing!).
- **Global Context Isolation**: When `RECALL_ALLOWED_PROJECT_IDS` is active (and `RECALL_MCP_ALLOW_GLOBAL_CONTEXT` is not `true`), `recall_search` and `recall_get_context` filter out `Scope.GLOBAL` memories and global custom instructions so locked-down agents only see their allowlisted project(s).
- **Project Creation vs. Project Access (`recall_save_project`)**:
  - When `RECALL_ALLOWED_PROJECT_IDS` is active:
    - Passing `project_id=None` (name-only lookup/create) **fails closed immediately** before any DB lookup or creation with `ToolError("project_id is required when RECALL_ALLOWED_PROJECT_IDS is configured")` to prevent project-name existence oracles.
    - Passing `project_id` outside `allowed_ids` → `ToolError` (denied before DB lookup).
- **Fresh Sessions in Read-Only Mode (`create_session=False`)**:
  - On `recall_search` and `recall_get_context`, `_validate_scope(..., create_session=False)` calls `get_session(session_uuid)`: if the session exists and belongs to a different project, raise `ToolError`; if it does not exist yet, pass `session_uuid` to read paths without inserting a `sessions` row.
- **Global Custom Instructions (`recall_create_custom_instruction`)**:
  - Default `scope` changed from `"global"` to `"project"`.
  - When `RECALL_MCP_ALLOW_GLOBAL_INSTRUCTIONS` is unset/`false`: any `scope="global"` call raises `ToolError("Global custom instruction creation is disabled for MCP agents")`. Never silently creates `INACTIVE` instructions.
  - When `RECALL_MCP_MODE=read-only`: tool is not registered at all.

---

## 4. Exact Permission & Boundary Matrix

### MCP Tools (`recall_mcp/server.py`)
| MCP Tool | `read-only` Mode | `standard` Mode | Project Allowlist Check | Additional Constraints |
| :--- | :---: | :---: | :--- | :--- |
| `recall_search` | Allowed (zero writes) | Allowed (zero writes) | `project_uuid in allowed` | `create_session=False`; no SQLite inserts |
| `recall_get_context` | Allowed (zero writes) | Allowed (zero writes) | `project_uuid in allowed` | `create_session=False`; no SQLite inserts |
| `recall_save_memory` | **Disabled** (not registered) | Allowed | `project_uuid in allowed` | `provenance="agent_saved"` (hardcoded; non-overridable) |
| `recall_compact_memory` | **Disabled** (not registered) | Allowed | `project_uuid in allowed` | `preserve_lineage=True`, `max_active_memories >= 5` (floor) |
| `recall_create_custom_instruction` | **Disabled** (not registered) | Project-scoped only | `project_uuid in allowed` | `scope="global"` raises `ToolError` unless `RECALL_MCP_ALLOW_GLOBAL_INSTRUCTIONS=true` |
| `recall_save_project` | **Disabled** (not registered) | Allowed (when allowlist unset) | Resolved/created `id in allowed` | Denied if allowlist is active and target/new ID is not in `allowed` |

### HTTP REST Endpoints (`api/routes/`)
| Endpoint Group | `GET` (Read) | `POST` / `PATCH` / `DELETE` (Mutate) |
| :--- | :--- | :--- |
| `/health`, `/healthz`, `/memories`, `/custom-instructions`, `/projects`, `/sessions`, `/conflicts`, `/context`, `/stats`, `/capture` | Accountless local access (no auth headers or tokens) | Accountless local access (request validation & secret redaction enforced) |

---

## 5. Community Safety Invariants

1. **Zero-Write Read-Only Guarantee**: In `read-only` mode (and during `recall_search` / `recall_get_context` in `standard` mode), zero SQLite `INSERT`/`UPDATE`/`DELETE` statements execute (including `sessions` auto-creation).
2. **Accountless Local Execution**: No login, registration, user accounts, or token middleware exist in RECALL Community.
3. **Fail-Closed Project & Global Scope**: `RECALL_ALLOWED_PROJECT_IDS` checks occur before DB lookup on all 6 tools; `scope="global"` instructions are rejected with `ToolError` by default.
4. **Non-Bypassable Compaction Floor & Key Binding**: `max_active_memories < 5` raises `ToolError` in `recall_compact_memory` regardless of agent arguments. Optional `idempotency_key` is validated (`1 <= len <= 128`, `[A-Za-z0-9_.:-]+`) and bound to `(project_id, session_id, max_active_memories)` in `MemoryManager.compact()` (mismatched reuse returns `Result.err`).
5. **Provenance Consistency (`agent_saved`)**: Across `recall_mcp/server.py`, `intelligence/retrieval.py` (`+0.0` vs `+0.1` for `user_explicit` / `explicit_user_update`), `intelligence/conflict.py` (4-tier `provenance_rank`: `explicit_user_update: 4`, `user_explicit: 3`, `agent_saved: 2`, `inferred: 1`, `agent_inferred: 1`), and `recall_core/context_assembly.py`, `agent_saved` ranks above `agent_inferred` and strictly below `user_explicit` and active custom instructions.
