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
  - Full regression suite: **419 passed, 1 skipped by design, 0 failed in 60.64s** (8 new tests added; 420 items total).
  - Production database `C:\Users\dipan\.recall\recall.sqlite3` and `C:\Games` distribution verified 100% untouched.


### Phase 04 — Conflict Resolution & Custom-Instruction State Management
- **Status**: QUEUED
- **Dependencies**: Phase 03
- **Acceptance Criteria**:
  - [ ] Enforce strict precedence: User Instruction > Explicit Supersession > Canonical Memory > Historical Memory > Local LLM Arbitration > Abstain/Unresolved.
  - [ ] Ensure local 1B-3B model cannot mutate storage or override user instructions.
  - [ ] Formalize instruction versioning and active state transitions.
- **Test Requirements**: Conflict simulation test suite covering contradictory instructions, historical supersessions, and model abstention.

### Phase 05 — Versioned, Lineage-Preserving Milestone Memory Compaction
- **Status**: QUEUED
- **Dependencies**: Phase 04
- **Acceptance Criteria**:
  - [ ] Implement `recall_compact_memory` preserving complete DAG lineage in `memory_lineage`.
  - [ ] Never hard-delete source memories during compaction (mark consolidated/archived with parent-child links).
  - [ ] Generate auditable summary nodes with version tags.
- **Test Requirements**: Compaction round-trip tests verifying source memory retrieval via lineage graph.

### Phase 06 — Antigravity MCP Trust, Permission & Installation UX
- **Status**: QUEUED
- **Dependencies**: Phase 05
- **Acceptance Criteria**:
  - [ ] Finalize production MCP registration schema, tool metadata, and instructions.
  - [ ] Provide seamless setup scripts and configuration guides for Antigravity, OpenCode, and Cursor.
  - [ ] Validate stdio protocol integrity and warm-up latency optimizations.
- **Test Requirements**: End-to-end client connection tests with mock and real Antigravity IDE sessions.

### Phase 07 — Full Regression, Security, Packaging & Release Validation
- **Status**: QUEUED
- **Dependencies**: Phase 06
- **Acceptance Criteria**:
  - [ ] Full regression suite run across all components (Core, Database, Intelligence, MCP, API, Frontend).
  - [ ] Security audit: process isolation, permission boundaries, read-only guarantees.
  - [ ] Windows packaging and distribution readiness review.
  - [ ] Final release approval presentation to Dipankar.
- **Test Requirements**: 100% passing automated test suite with coverage reports and packaging smoke tests.
