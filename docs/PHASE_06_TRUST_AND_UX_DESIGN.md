# RECALL 3.0.0 — Phase 06: Antigravity MCP Trust, Permission & Installation UX (Revised Design)

**Status:** Revised Architecture — Awaiting User Implementation Approval  
**Branch:** `dev/recall-3.0.0` (Design exercise only; zero code, schema, or MCP contract modifications made)

---

## 1. Revised Architecture

RECALL enforces defense-in-depth across three layers rather than relying on MCP tool omission or `127.0.0.1` loopback binding alone:

1. **MCP Agent Boundary (`recall_mcp/server.py`)**:
   - Enforces permission modes (`RECALL_MCP_MODE=read-only` vs `standard`), fail-closed project allowlists (`RECALL_ALLOWED_PROJECT_IDS`), zero-write read paths (`create_session=False`), `agent_saved` provenance, `scope="global"` rejection unless explicitly enabled, and a non-bypassable compaction floor (`max_active_memories >= 5`).
2. **HTTP Operator Boundary (`api/app.py`, `api/routes/`)**:
   - Enables operator authentication **by default** for all data-bearing `GET` routes and all mutating REST endpoints (`POST`/`PATCH`/`DELETE` on `/memories`, `/custom-instructions`, `/projects`, `/sessions`, `/conflicts`, `/context`, `/context/query`, `/context/compact`, `/stats`), separate from `.capture_token`. Only `/health`, `/healthz`, `POST /auth/session`, and `GET /` (SPA static HTML/assets) remain public.
   - Protects browser-based Dashboard access with `HttpOnly; SameSite=Strict` session cookies, double-submit CSRF tokens, and strict `Host`/`Origin` validation across both `/` and `/api` route prefixes.
3. **Core Authority & Provenance (`intelligence/conflict.py`, `intelligence/retrieval.py`, `recall_core/`)**:
   - Ranks `agent_saved` consistently below `user_explicit` and `explicit_user_update` across retrieval scoring, conflict resolution, and context assembly.

---

## 2. Authentication & Session Lifecycle (Operator Auth)

1. **Operator Token Generation & Storage**:
   - Stored outside untrusted repo trees at `~/.recall/.operator_token` (or `RECALL_OPERATOR_TOKEN_PATH`) with restrictive user-only ACLs (`0600` on POSIX, Windows SID-scoped `icacls /inheritance:r /grant:r *<SID>:(F)` — reusing the Phase 03 `secure_write_token_file` pattern).
   - Never reused for `.capture_token` (`POST /capture` remains isolated to capture hooks).
   - Never logged to `stdout`, `stderr`, or FastAPI error responses.
2. **Initial Dashboard Session Establishment**:
   - Same-origin Dashboard served from `api/app.py` (`/`): Operator authenticates once via `POST /api/auth/session` (or `/auth/session`) by presenting the local operator token (or local CLI-printed one-time bootstrap URL/code when `api/main.py` starts).
   - Server sets:
     - `recall_operator_session` cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure=True` when `RECALL_API_HTTPS=true` (omitted only on plain `http://127.0.0.1` local loopback where browsers reject `Secure` over HTTP, while still enforcing `HttpOnly; SameSite=Strict` + `Host`/`Origin` checks).
     - `recall_csrf_token` cookie: `SameSite=Strict`, `HttpOnly=False` (readable by same-origin `frontend/src/api/client.ts` to echo in `X-CSRF-Token` header on mutating requests).
   - Non-browser operator clients (scripts/CLI) may authenticate with `Authorization: Bearer <operator_token>` (exempt from CSRF cookie check since Bearer headers are not auto-sent by browsers).
3. **CSRF, `Origin`, and `Host` Validation**:
   - **Host Header Validation**: Middleware rejects any request whose `Host` header is not in `{"127.0.0.1", "localhost", "[::1]"}` (with configured port) to block DNS-rebinding attacks against `127.0.0.1:8080`. (`testserver` is permitted only when `require_auth=False` in test fixtures.)
   - **Origin / Referer Validation**: For cookie-authenticated mutating requests (including `POST /auth/logout`), `Origin` (or `Referer` parsed via `urllib.parse.urlparse` for exact `(scheme, netloc)`) must match the allowed Dashboard origin; **fail closed** if both `Origin` and `Referer` are absent.
   - **CSRF Check**: Cookie-authenticated `POST`/`PATCH`/`DELETE` requests (including `POST /auth/logout`) must include `X-CSRF-Token` matching `recall_csrf_token` via `hmac.compare_digest`.
   - **CORS & Vite Dev Alignment**: Replace `allow_methods=["*"]` / `allow_headers=["*"]` in `api/app.py` with explicit `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]` and `["Content-Type", "Authorization", "X-CSRF-Token"]`. Update `frontend/src/api/client.ts` in `DEV` to default `API_BASE_URL` to `'/api'` (using Vite's `/api` proxy in `frontend/vite.config.ts`) so browser requests are same-origin and avoid `localhost` vs `127.0.0.1` `SameSite=Strict` cross-site mismatches.
4. **Expiration, Revocation & Local Process Exposure**:
   - Sessions are stored in-memory (HMAC-signed token + expiry `RECALL_SESSION_TTL_SECONDS`, default `28800` / 8h) and support `POST /api/auth/logout` (clears cookies + revokes session ID).
   - **Local OS Boundary**: Because any process running as the same OS user can inspect same-user files/env, operator token auth is stored under `~/.recall/` (not in workspace `.env`) and mitigates blind HTTP/CORS/DNS-rebinding/agent-`curl` bypasses; OS-level multi-user isolation requires running RECALL under a dedicated service account.
5. **Backward Compatibility for Existing Dashboard & Tests**:
   - `frontend/src/api/client.ts` updated to send `credentials: 'include'`, echo `X-CSRF-Token`, and prompt for the operator token in a minimal modal on `401 Unauthorized`.
   - `create_app(memory_manager=..., require_auth: bool = True)` allows `tests/test_http_api.py` fixtures to pass `require_auth=False` explicitly (and test auth enforcement directly with `require_auth=True`).

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

## 4. Exact Permission Matrix

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
| `/health`, `/healthz`, `/auth/session` | Public (loopback + Host check) | `POST /auth/session` requires operator token; `POST /auth/logout` clears cookie |
| `/memories`, `/custom-instructions`, `/projects`, `/sessions`, `/conflicts`, `/context`, `/stats` | **Operator Auth Required** (unless `require_auth=False` in tests) | **Operator Auth Required** (Bearer `.operator_token` OR `HttpOnly` session cookie + `X-CSRF-Token` + `Origin`/`Host` check) |
| `/capture` (`POST`) | N/A | **Capture Auth Required** (`.capture_token` Bearer — cannot access operator CRUD) |

---

## 5. Security Invariants

1. **Zero-Write Read-Only Guarantee**: In `read-only` mode (and during `recall_search` / `recall_get_context` in `standard` mode), zero SQLite `INSERT`/`UPDATE`/`DELETE` statements execute (including `sessions` auto-creation).
2. **Default-On Operator Auth**: Mutating REST endpoints reject unauthenticated requests (`401`) unless `create_app(..., require_auth=False)` is explicitly passed in test harnesses.
3. **Fail-Closed Project & Global Scope**: `RECALL_ALLOWED_PROJECT_IDS` checks occur before DB lookup on all 6 tools; `scope="global"` instructions are rejected with `ToolError` by default.
4. **Non-Bypassable Compaction Floor & Key Binding**: `max_active_memories < 5` raises `ToolError` in `recall_compact_memory` regardless of agent arguments. Optional `idempotency_key` is validated (`1 <= len <= 128`, `[A-Za-z0-9_.:-]+`) and bound to `(project_id, session_id, max_active_memories)` in `MemoryManager.compact()` (mismatched reuse returns `Result.err`).
5. **Provenance Consistency (`agent_saved`)**: Across `recall_mcp/server.py`, `intelligence/retrieval.py` (`+0.0` vs `+0.1` for `user_explicit` / `explicit_user_update`), `intelligence/conflict.py` (4-tier `provenance_rank`: `explicit_user_update: 4`, `user_explicit: 3`, `agent_saved: 2`, `inferred: 1`, `agent_inferred: 1`), and `recall_core/context_assembly.py`, `agent_saved` ranks above `agent_inferred` and strictly below `user_explicit` and active custom instructions.

---

## 6. Threat Scenarios & Mitigations

| Threat | Mitigation |
| :--- | :--- |
| Agent calls `DELETE http://127.0.0.1:8080/projects/<id>` | Blocked by mandatory `.operator_token` auth (`401 Unauthorized`). |
| Malicious webpage triggers CSRF / DNS rebinding against `:8080` | Blocked by `Host` validation, `SameSite=Strict`, `Origin` check, and `X-CSRF-Token`. |
| Agent uses `.capture_token` to call `DELETE /custom-instructions/<id>` | Blocked by token separation (`.capture_token` is valid only on `/capture`). |
| Agent passes `project_id` of another repo to `recall_search` | Blocked before DB lookup by `RECALL_ALLOWED_PROJECT_IDS` (`ToolError`). |
| Agent passes `max_active_memories=1` to wipe active context | Blocked by non-bypassable floor `>= 5` (`ToolError`). |
| Agent creates `scope="global"` instruction to hijack other projects | Blocked by `ToolError` when `RECALL_MCP_ALLOW_GLOBAL_INSTRUCTIONS` is false. |

---

## 7. Backward-Compatibility Strategy

- **Existing HTTP Tests**: `tests/test_http_api.py` passes `require_auth=False` to `create_app()` for legacy CRUD tests, while new `tests/test_mcp_trust_and_ux.py` / auth tests verify `require_auth=True` default behavior.
- **Dashboard (`frontend/`)**: Seamless `POST /api/auth/session` cookie bootstrap + `X-CSRF-Token` header in `apiClient`.
- **MCP 6-Tool Contract**: Tool names remain unchanged; `recall_compact_memory` adds optional `idempotency_key: str | None = None` backward-compatibly.
- **Onboarding UX**: `scripts/generate_mcp_config.py` emits `"cwd"` + explicit `RECALL_DB_PATH`/`RECALL_CHROMA_PATH`; `python -m recall_mcp.server --doctor` validates Python env, SQLite integrity, ChromaDB, and model cache before stdio startup.

---

## 8. Acceptance Tests (Including Adversarial Cases)

To be implemented in `tests/test_mcp_trust_and_ux.py` (and targeted updates to `tests/test_mcp_server.py`):
1. **Read-Only Zero-Write Test**: In `RECALL_MCP_MODE=read-only`, verify only 2 tools register, and calling `recall_search` / `recall_get_context` with a fresh `session_id` leaves `sessions`, `memories`, and `custom_instructions` row counts unchanged (verified via SQLite `total_changes` / row count).
2. **Project Allowlist Adversarial Tests**: Verify `RECALL_ALLOWED_PROJECT_IDS=""` fails closed; verify unauthorized `project_id` on all 6 tools (including `recall_save_project(name=...)` and `recall_create_custom_instruction`) raises `ToolError` without leaking project existence.
3. **Global Instruction Rejection Test**: Verify `recall_create_custom_instruction(..., scope="global")` raises `ToolError` by default and creates zero rows.
4. **Compaction Floor Adversarial Test**: Verify `recall_compact_memory(..., max_active_memories=4)` and `max_active_memories=0` / `True` raise `ToolError`; verify `>= 5` preserves Phase 05 idempotency and lineage.
5. **Provenance Consistency Test**: Verify `recall_save_memory` writes `provenance="agent_saved"`, receives lower retrieval score and conflict rank than `user_explicit`, and never overrides `user_explicit` or `explicit_user_update`.
6. **Operator Auth & CSRF Adversarial Tests**: Verify unauthenticated `POST`/`PATCH`/`DELETE` on `/memories`, `/custom-instructions`, `/projects` return `401`; `.capture_token` on `/projects` returns `401`; cookie-auth without `X-CSRF-Token` or with bad `Host`/`Origin` returns `403`; valid session + CSRF succeeds.
7. **Onboarding `--doctor` & Config Generation**: Verify `generate_mcp_config.py` includes `"cwd"` and `recall-mcp --doctor` exits `0` on healthy env.

---

## 9. Remaining Risks & Unresolved Decisions

- **Same-OS-User Local Threat**: An agent with unrestricted local shell execution as the same OS user can theoretically read `~/.recall/.operator_token` or SQLite directly; full OS-level isolation requires running RECALL under a separate OS user/service account (out of scope for single-user desktop mode).
- **Existing `tests/test_mcp_server.py` Update**: `test_mcp_server.py` currently asserts `provenance == "user_explicit"` for `recall_save_memory`; it will be updated to `"agent_saved"` upon implementation approval.
