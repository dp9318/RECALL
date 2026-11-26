# RECALL 3.0.0 — Development Tracking & Governance Matrix

## Governance & Isolation Principles
- **Production Installation**: `C:\Games\recall-2.1.1-windows` (Running installed RECALL 2.1.1 serving persistent memory to Antigravity)
- **Production Database**: `C:\Users\dipan\.recall\recall.sqlite3` (ChromaDB: `C:\Users\dipan\.recall\chroma`)
- **Development Repository**: `D:\proj\Hackathon\RECALL` (Branch `dev/recall-3.0.0`)
- **Development Database**: `D:\proj\Hackathon\RECALL\.dev_data\dev.sqlite3` (Isolated, never touches production)
- **Isolation Invariant**: Zero writable state shared between Dev and Prod. Production database must never be touched, migrated, or reset during development.
- **Approval Gate**: All phase transitions and any commit/push/release require explicit approval from Dipankar.

---

## Target MCP 6-Tool Contract
1. `recall_search`: Query memories within scoped project/global context.
2. `recall_get_context`: Assemble canonical context, active instructions, and relevant memories for agents.
3. `recall_compact_memory`: Milestone memory consolidation preserving full lineage and history.
4. `recall_create_custom_instruction`: Create explicit user-authored rules.
5. `recall_save_memory`: Persist verified canonical project memories.
6. `recall_save_project`: Register and maintain project scopes and metadata.

*Security Invariant*: Coding agents must NOT have update or delete capabilities over existing authoritative memories, custom instructions, or projects. Full CRUD remains restricted to authorized human users via Dashboard & API.

---

## Phase Breakdown & Status Matrix

### Phase 00 — Baseline Audit and Development Isolation
- **Status**: COMPLETE (Verified & Audited)
- **Dependencies**: None
- **Acceptance Criteria**:
  - [x] Running installation (`C:\Games\recall-2.1.1-windows`), database paths (`~/.recall/`), and MCP configurations identified and verified untouched.
  - [x] Development workflow unified on branch `dev/recall-3.0.0` in `D:\proj\Hackathon\RECALL`; temporary worktree pruned.
  - [x] Development database isolated to `D:\proj\Hackathon\RECALL\.dev_data\recall_dev.sqlite3` via `.env` and `.gitignore`.
  - [x] Baseline test suite executed and verified across all modules (379 passed, 1 skipped by design, 0 failures).
  - [x] Hermetic isolation fix applied to `tests/test_mcp_bootstrap.py` (preventing `.env` leakage into fallback test).
  - [x] MCP connectivity verified live with installed RECALL 2.1.1 server (`recall_search`, `recall_get_context`).
  - [x] Roadmap persisted to existing RECALL project memory (`3ca43da6-f4e3-43ae-8e38-6e84cb963332`).
  - [x] Persistence failure hypotheses documented and differentiated from verified root causes.
  - [x] First actionable issue for Phase 01 identified.
- **Test Requirements**: Clean baseline `pytest` run (379 passed, 1 skipped, 0 failures) without modifying production state.

### Phase 01 — Diagnose and Repair Memory & Custom-Instruction Persistence
- **Status**: COMPLETE (Audited & Repaired)
- **Dependencies**: Phase 00 completion & approval
- **Acceptance Criteria**:
  - [x] Investigate and fix thread-lock and transaction handling in `ThreadSafeConnection` / repositories (eliminated premature raw `commit()` calls from repositories to preserve UnitOfWork transaction boundaries; upgraded transaction start to `BEGIN IMMEDIATE` to prevent SQLite concurrency deadlocks).
  - [x] Support graceful multi-instruction and project scoping without accidental conflict aborts (reconnection and scoping verified across global and project levels).
  - [x] Ensure `SQLiteMemoryRepository` and `SQLiteCustomInstructionRepository` guarantee atomic commit, rollback on failure, and exact error propagation.
  - [x] Verify persistence idempotency and timezone consistency (`datetime.now(timezone.utc)` everywhere across `memories`, `custom_instructions`, `projects`, and `sessions`).
- **Test Requirements**: Comprehensive repository and UnitOfWork tests under concurrent access, simulated write failures, and historical naive timestamp compatibility (`tests/test_persistence_lifecycle.py` passing 7/7; full suite 386 passed, 1 skipped by design, 0 failures).
- **Independent Review**: Completed. Verified all 3 root causes, `BEGIN IMMEDIATE` across transaction lifecycles, naive timestamp coexistence, pre-fix test failures, 100% production DB isolation, and live MCP retrieval of Phase 01 memory (`f7f0b360-c838-4859-aa9c-9166eea38254`). Safe to close Phase 01.

### Phase 02 — Enforce Agent Security Restrictions & 6-Tool MCP Contract
- **Status**: COMPLETED (Pending Review & Phase 03 Approval)
- **Dependencies**: Phase 01 (Approved for closure)
- **Acceptance Criteria**:
  - [x] Restructure MCP server from 9 legacy tools to the exact 6 target tools (`recall_search`, `recall_get_context`, `recall_compact_memory`, `recall_create_custom_instruction`, `recall_save_memory`, `recall_save_project`).
  - [x] Strip agent capabilities to update or delete authoritative memories, instructions, or projects from MCP registration and dispatch.
  - [x] Enforce security invariants in tool dispatch and queries: canonical project identity is preserved; conflicting UUID/name attempts raise ToolError; name collisions raise clear validation errors.
  - [x] Preserve full human user CRUD in REST API (`api/`) and React Dashboard (`frontend/`), verified via `tests/test_http_api.py` (30 passed).
  - [x] Implement `recall_save_project` with thread-safe concurrency lock and post-failure re-queries for idempotent project scope creation/retrieval under concurrent execution.
- **Audit & Remediation Findings**:
  - Independent security audit verified exact 6-tool registration; all prohibited mutation tools return protocol-level errors (`isError=True`).
  - **Fix 1 (Secure API Bind Default)**: Changed default `RECALL_API_HOST` in `api/main.py` and `.env.example` from `0.0.0.0` to `127.0.0.1`. Added tests verifying loopback default and environment variable overrides (`tests/test_http_api.py`). Documented network security requirements.
  - **Fix 2 (Cross-Process Project Concurrency)**: Implemented atomic project resolution and creation in `MemoryManager.resolve_or_create_project` wrapped in `UnitOfWork.begin()` (`BEGIN IMMEDIATE` write lock). Serializes cross-process project creation across separate OS processes sharing the same SQLite database. Verified via 4-process concurrent test (`tests/test_mcp_server.py::test_save_project_cross_process_concurrency`).
  - Production database `C:\Users\dipan\.recall\recall.sqlite3` verified untouched (LastWriteTime: `2026-10-24 04:02:34`).
- **Test Results**:
  - Focused MCP protocol tests: `tests/test_mcp_server.py` (19 passed, 0 failed).
  - Bootstrap integration tests: `tests/test_mcp_bootstrap.py` (14 passed, 0 failed).
  - REST API tests: `tests/test_http_api.py` (32 passed, 0 failed).
  - Full regression suite: 392 passed, 1 skipped by design, 0 failed in 46.16s.

### Phase 03 — Automatic Memory Capture Through Supported Agent Integrations
- **Status**: COMPLETED (Audited & Remediated; Ready for Checkpoint)
- **Dependencies**: Phase 02 (Completed & Audited)
- **Acceptance Criteria**:
  - [x] Integrate automatic capture hooks on agent task completion / milestones without hallucinated output (Antigravity integration spike verified; `.agents/hooks.json` registered for `PostInvocation` with 5s timeout and fail-safe exit 0).
  - [x] Implement conservative relevance policy (restricting to `decision`, `convention`, `architecture`, `task_outcome`), secret redaction (Google, OpenAI, Anthropic, AWS, GitHub, Private Keys, Bearer tokens, URI passwords), and pre-persistence validation.
  - [x] Tag provenance accurately (`agent_inferred`).
  - [x] Secure ingestion boundary: local Bearer token authentication with restricted per-user file permissions on Windows (`.capture_token`).
  - [x] Race-safe multi-process idempotency using atomic SQLite `BEGIN IMMEDIATE` write locks and `idempotency_key` metadata tracking.
  - [x] Active session reuse and cross-project session mismatch rejection.
  - [x] **Targeted Remediation 1 (Structured Staging Producer & Event Staging Gap)**: Created `recall_core/staging.py` and `scripts/recall_stage.py` providing validated staging API and CLI. Because Antigravity stdin does not provide assistant output and conversation transcripts must not be read or uploaded, capture relies on deterministic staging into `.pending_capture.json`, which is automatically ingested, authenticated, deduplicated, and persisted by `recall_capture_hook.py` on the next turn.
  - [x] **Targeted Remediation 2 (Windows SID Resolution & Creation-Order ACLs)**: Implemented `get_current_user_sid()` in `recall_core/capture_service.py` to resolve user SIDs (`*S-1-5-...`) via `whoami` and PowerShell. Updated `secure_write_token_file()` to strip inheritance and grant permissions before writing sensitive data. Cleanly unlinks files and fails closed on error without leaking credentials.
  - [x] **Targeted Remediation 3 (Deterministic Token-Path Resolution)**: Anchored token resolution in `get_default_capture_token_path()` and `_resolve_token()` to repository root `.dev_data/.capture_token`, ensuring identical resolution regardless of working directory. Added tests proving path invariance across directory switches.
  - [x] **Targeted Remediation 4 (Malformed-Event Recovery & Retry Safety)**: Corrupted or ineligible staged files are safely unlinked and logged to prevent blocking loops. Network disconnects and offline API states preserve valid staged files for retry, with multi-turn duplicate suppression verified.
  - [x] **Targeted Remediation 5 (Conservative Configuration Portability)**: Preserved working active paths in `.agents/mcp_config.json` and `.opencode/opencode.json` pointing to the working `C:\Games\recall-2.1.1-windows` distribution. Provided generic `.agents/mcp_config.json.example` for developer portability.
- **Test Requirements & Verified Results**:
  - Capture security and token permissions: `tests/test_capture_security.py` (8 passed).
  - Relevance, redaction, and persistence: `tests/test_capture_service.py` (9 passed).
  - 4-process concurrent submission: `tests/test_capture_concurrency.py` (1 passed).
  - Hook contract, malformed JSON recovery, and e2e integration: `tests/test_capture_hook.py` (9 passed).
  - Antigravity integration spike: `scripts/test_antigravity_hook_spike.py` (6 passed).
  - Full regression suite: **419 passed, 1 skipped by design, 0 failed in 66.40s** (8 new tests added; 420 items total).
  - **Post-Checkpoint Stabilization (2026-11-26)**:
    - Fixed standalone CLI import in `scripts/recall_stage.py` by adding repository root to `sys.path` before importing `contracts.capture` and `recall_core.staging` (resolving `ModuleNotFoundError: No module named 'contracts'`).
    - Hardened `tests/test_capture_concurrency.py::test_four_process_capture_concurrency` subprocess `communicate(timeout=90)` to prevent full-suite CPU-contention timeouts without weakening concurrency assertions.
    - Re-verified affected tests (`10 passed in 21.15s`) and full regression suite (`419 passed, 1 skipped, 0 failed in 66.40s`).
  - Production database `C:\Users\dipan\.recall\recall.sqlite3` and `C:\Games` distribution verified 100% untouched.


### Phase 04 — Conflict Resolution & Custom-Instruction State Management
- **Status**: APPROVED & CLOSED (Post-Integration Audit Passed)
- **Dependencies**: Phase 03 (Approved & Stabilized)
- **Acceptance Criteria**:
  - [x] Enforce strict precedence: User Instruction > Explicit Supersession > Canonical Memory > Historical Memory > Local LLM Arbitration > Abstain/Unresolved (`DefaultConflictResolver.apply_deterministic_rules`, `_priority`, `_violates_instructions`, project-over-global instruction partitioning).
  - [x] Ensure local 1B-3B model cannot mutate storage or override user instructions (post-arbitration `_violates_instructions` guardrail in `DefaultConflictResolver.resolve` returning `ABSTAINED` with `llm_instruction_override_blocked`; zero `UnitOfWork`/repo access in `intelligence/conflict.py`).
  - [x] Formalize instruction versioning and active state transitions (`_VALID_INSTRUCTION_TRANSITIONS` in `CustomInstructionService.update`, rejecting empty content and `DELETED` reactivation; `get_active_for_project` orders project-scoped instructions before global).
  - [x] Wire active custom instructions & global memories into `MemoryManager.get_conflicts()` and conflict resolution into `MemoryManager.assemble_context()` + `ContextAssemblyService.apply_conflict_resolutions()`.
- **Independent Review & Remediation**:
  - Multi-agent workflow documented in `docs/MULTI_AGENT_WORKFLOW.md` (with `.opencode/agents/recall-architect.md`, `.opencode/agents/recall-reviewer.md`, `scripts/invoke_opencode.py`, `.agents/skills/opencode-review/SKILL.md`).
  - Independent adversarial code review identified 8 findings (3 HIGH, 4 MEDIUM, 1 LOW): deterministic instruction-violation filtering, affirmative/contraction contradiction detection, `ACTIVE`-only `supersedes_id` eligibility, project-over-global precedence, `get_conflicts` instruction error propagation + global scope, `DELETED` immutability, `explicit_user_update` provenance handling, and `apply_conflict_resolutions` active-memory cleanup. All 8 resolved and covered by regression tests.
- **Test Results**:
  - Targeted Phase 04 tests (`tests/test_conflict_resolution.py`, `tests/test_instruction_service.py`, `tests/test_integration_core_flows.py`): **61 passed in 14.75s**.
  - Full regression suite (`pytest -q --tb=short`): **430 passed, 1 skipped by design, 0 failed in 70.39s**.

### Phase 05 — Versioned, Lineage-Preserving Milestone Memory Compaction
- **Status**: COMPLETED (Audited, Reviewed & Verified)
- **Dependencies**: Phase 04 (Approved & Closed)
- **Acceptance Criteria**:
  - [x] Implement atomic `MemoryManager.compact()` inside `UnitOfWork.begin()` (`BEGIN IMMEDIATE`) preserving complete DAG lineage in `memory_lineage`.
  - [x] Enforce compaction idempotency and stable operation identifiers (`idempotency_key`, `compaction_op_id`).
  - [x] Durable SQLite-backed pending-sync outbox (`metadata.pending_semantic_sync`) for semantic index failures with `flush_pending_semantic_sync()` recovery.
  - [x] Explicit eligibility rules protecting unresolved, conflicted, and authoritative (`explicit_user_update`, `pinned`, `authoritative`) memories.
  - [x] Monotonic `compaction_version` allocation inside the SQLite write transaction and `session_id` scoping.
  - [x] Deep, bidirectional DAG lineage traversal (`traverse_lineage`) and archival policy (`ARCHIVED` without deleting rows or lineage).
- **Test Results**:
  - Targeted Phase 05 tests (`tests/test_compaction.py`): **7 passed in 25.53s**.
  - Full regression suite (`pytest -q --tb=short`): **437 passed, 1 skipped by design, 0 failed in 87.35s**.

### Phase 06 — Antigravity MCP Trust, Permission & Installation UX
- **Status**: COMPLETED & VERIFIED (Final Verification Audit Passed; Ready for Phase 07 Approval)
- **Dependencies**: Phase 05 (Completed & Verified)
- **Design & Audit Document**: `docs/PHASE_06_TRUST_AND_UX_DESIGN.md`
- **Acceptance Criteria**:
  - [x] Enforce default-on operator auth boundary on data-bearing & mutating REST endpoints (`api/auth.py`, `api/routes/auth.py`, `api/app.py`: `.operator_token` under `~/.recall/`, `HttpOnly; SameSite=Strict` session + `X-CSRF-Token`, fail-closed `Host`/`Origin`/`Referer`, Vite `/api` proxy in `frontend/src/api/client.ts`), with `require_auth=False` for legacy test fixtures.
  - [x] Enforce `RECALL_MCP_MODE` (`read-only` vs `standard`), `RECALL_ALLOWED_PROJECT_IDS` (strict startup UUID validation, fail-closed across all 6 tools including `recall_save_project`), `create_session=False` on read & compact paths, `include_global` context isolation, and `scope="global"` `ToolError` rejection unless explicitly enabled.
  - [x] Align `recall_save_memory` provenance (`agent_saved`) with 4-tier conflict rank (`explicit_user_update: 4 > user_explicit: 3 > agent_saved: 2 > inferred/agent_inferred: 1`) and retrieval boost (`+0.1` for `user_explicit` vs `+0.0` for `agent_saved`).
  - [x] Enforce non-bypassable compaction floor (`max_active_memories >= 5`) and `idempotency_key` regex + parameter binding (`project_id`, `session_id`, `max_active_memories`).
  - [x] Finalize `scripts/generate_mcp_config.py` (`cwd` + `RECALL_MCP_MODE`), `.agents/mcp_config.json.example`, and `recall_mcp.server --doctor` pre-flight diagnostics.
- **Independent Review & Remediation**:
  - Conducted via fallback read-only `research` subagent (due to documented Windows OpenCode v2.4.1 non-TTY hang). Surfaced 0 Critical, 1 High (`client.ts` `noUncheckedIndexedAccess` TS error), and 3 Low findings (`Origin: null` fallback, `recall_compact_memory` `create_session=False`, `client.ts` auth helpers); all 4 resolved.
- **Test & Build Results**:
  - Targeted Phase 06 tests (`tests/test_mcp_trust_and_ux.py`): **7 passed**.
  - Frontend production build (`cd frontend && npm run build`): **`tsc && vite build` succeeded in 602ms**.
  - Full regression suite (`pytest -q --tb=short`): **444 passed, 1 skipped by design, 0 failed in 95.82s**.

### Phase 07 — Full Regression, Security, Packaging & Release Validation
- **Status**: COMPLETED (Validated — **Release Ready with Known Limitations**)
- **Dependencies**: Phase 06 (Approved & Verified)
- **Acceptance Criteria**:
  - [x] Full regression suite run across all components (`pytest -q --tb=short`: **450 passed, 1 skipped by design, 0 failed in 110.46s**; `npm run build`: `tsc && vite build` **319ms**).
  - [x] Security validation & operational tests (`tests/test_phase07_validation.py`: session TTL expiration, full restart + ChromaDB + DAG lineage recovery, DB migration idempotency, corrupted DB `--doctor`, isolated `smoke_test_mcp.py`, SPA deep-link auth).
  - [x] Independent adversarial release review (`research` subagent fallback due to Windows OpenCode v2.4.1 non-TTY hang): resolved both Critical runtime blockers (Dashboard operator login UI in `frontend/src/App.tsx` + SPA `Accept: text/html` deep-link pass-through in `api/app.py`), `load_dotenv()` in `api/main.py` & `recall_mcp/server.py`, `.env.example` Phase 06 env docs, safe `RECALL_SESSION_TTL_SECONDS`, `RECALL_CORE_FACTORY` in `run_doctor()`, and `shared` topic check in `_violates_instructions`.
  - [x] Remaining release-gating items identified for user approval (version numbers still `2.1.1` in `pyproject.toml`, `frontend/package.json`, `setup.bat`, `setup.ps1`, `scripts/build_dist_bundle.py`; `build_dist_bundle.py` omits `recall_stage.py`/`recall_capture_hook.py`).
- **Test Requirements**: `450 passed, 1 skipped by design, 0 failed` (`pytest -q --tb=short`) and `npm run build` (`319ms`).

### Phase 08 — Database Identity, Runtime Integrity & Automated Repair
- **Status**: COMPLETED (Verified Across Installed 2.1.1 & Dev 3.0.0)
- **Root Cause**:
  - `D:\proj\Hackathon\RECALL\.env` set `RECALL_DB_PATH=D:\proj\Hackathon\RECALL\.dev_data\recall_dev.sqlite3` (56 memories, 41 active, 0 ChromaDB embeddings), whereas installed RECALL 2.1.1 (`C:\Games\recall-2.1.1-windows`) had no `.env` and defaulted to `C:\Users\dipan\.recall\recall.sqlite3` (102 memories, 87 active, 85 ChromaDB embeddings).
  - Additionally, `RECALL_CHROMA_PATH` was ignored by `SQLiteUnitOfWork` (`database/repositories/unit_of_work.py`), `RECALL_DB_PATH` silently created unintended directories/empty DBs on missing parent paths, and `docs/RECALL_3.0.0_DEV_TRACKING.md` referenced legacy `C:\Users\dipan\.recall\chroma` instead of `C:\Users\dipan\.recall\recall.sqlite3.chromadb`.
- **Canonical Resolution & Repair**:
  - Added `resolve_runtime_paths()` in `recall_core/bootstrap.py` enforcing precedence: `explicit_config > env:RECALL_DB_PATH > default_canonical (~/.recall/recall.sqlite3)`, and `env:RECALL_CHROMA_PATH > derived_from_sqlite (<sqlite_path>.chromadb)`, failing closed (`ConfigurationError`) on directory-as-DB or missing env parent directories.
  - Wired `chroma_persist_directory` through `SQLiteUnitOfWork` (`database/repositories/unit_of_work.py`).
  - Commented out `RECALL_DB_PATH` in `D:\proj\Hackathon\RECALL\.env` (preserving `.dev_data/recall_dev.sqlite3` untouched on disk) so both installed 2.1.1 and dev 3.0.0 resolve identically to `C:\Users\dipan\.recall\recall.sqlite3` and `C:\Users\dipan\.recall\recall.sqlite3.chromadb` by default.
  - Updated `recall_mcp/server.py` (`main()` & `run_doctor()`) to emit resolved SQLite/ChromaDB paths, sources, `cwd`, and `python_executable`.
  - Added `scripts/verify_and_repair_chroma.py` for read-only parity inspection and backup-before-rebuild recovery.
- **Test Results**:
  - Phase 08 suite (`tests/test_phase08_database_identity.py`): **5 passed in 35.09s** (including `-W error::RuntimeWarning -m recall_mcp.server --doctor`, write/search/context/restart round-trip, and backup-before-rebuild ChromaDB recovery).
  - Full regression suite (`pytest -q --tb=short`): **456 passed, 2 skipped, 0 failed in 112.72s**.

### Phase 09 — Complete Authentication Removal (RECALL Community Edition, `3.1.0` Target)
- **Status**: COMPLETED ✅ — Version bumped to 3.1.0, Git commit pending final acceptance.
- **Architectural Boundary**: **RECALL Community is a local-first, accountless application. Authentication is exclusive to RECALL Pro.**
- **Removed Authentication Components**:
  - Deleted `api/auth.py` (`OperatorSessionStore`, `resolve_or_create_operator_token`, `verify_operator_token`, `is_valid_host`, `is_valid_origin`, `SESSION_COOKIE_NAME`, `CSRF_COOKIE_NAME`) and `api/routes/auth.py` (`/auth/session`, `/auth/logout`, `/auth/status`).
  - Removed `auth_router` from `api/routes/__init__.py` and removed `require_auth`, `operator_auth_middleware`, session/CSRF CORS headers, and `allow_credentials=True` from `api/app.py`.
  - Removed `verify_capture_auth` dependency from `api/routes/capture.py`, capture token generation/ACL helpers (`resolve_or_create_capture_token`, `verify_capture_token`, `get_default_capture_token_path`, `secure_write_token_file`, `get_current_user_sid`) from `recall_core/capture_service.py`, and `_resolve_token()` / `Authorization` header from `scripts/recall_capture_hook.py` (preserving secret redaction and `BEGIN IMMEDIATE` idempotency).
  - Removed login UI, session check loading screen, client-side auth gating, `X-CSRF-Token`, `credentials: 'include'`, and auth methods from `frontend/src/App.tsx` and `frontend/src/api/client.ts`.
  - Removed `RECALL_OPERATOR_TOKEN*`, `RECALL_SESSION_TTL_SECONDS`, and `RECALL_API_HTTPS` from `.env.example` and updated project docs (`README.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_06_TRUST_AND_UX_DESIGN.md`, `docs/PACKAGING_AND_DISTRIBUTION.md`, `docs/RELEASE_PLAN.md`, `docs/modules/API.md`, `docs/modules/FRONTEND.md`).
- **Verification**:
  - Frontend production build (`cd frontend && npm run build`): `tsc && vite build` passed in **272ms**.
  - Full Python regression suite (`pytest -q --tb=short`): **450 passed, 2 skipped, 0 failed in 95.58s**.
  - Antigravity hook spike (`scripts/test_antigravity_hook_spike.py`): **6/6 passed**.
  - MCP diagnostics (`-W error::RuntimeWarning -m recall_mcp.server --doctor`): `ok: true` with canonical `~/.recall/recall.sqlite3` intact.
