# RECALL — Release Planning & Target Version Specifications

## 1. Overview & Objective

This document pins the target release versions and outlines the verification checklist for the RECALL platform releases. It audits independent subsystem versions across the codebase, records the rationale for version increments according to Semantic Versioning (SemVer 2.0.0), and documents backward-compatibility guarantees for the HTTP API and application surfaces.

> [!NOTE]
> Per release planning governance, this document records target versions and verification requirements in advance. No production tags or releases are published in this step.

---

## 2. Version Target Registry

| Subsystem / Layer | Historical Baseline | Previous Milestone | Target Release Version | SemVer Increment Type | Status / Representation |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Application Release** | `1.0.1` | `2.1.0` | **`2.1.1`** | **Patch** | Monorepo system-level release: Minor UI fixes |
| **HTTP API (FastAPI REST)** | `1.0.0` | `1.0.0` | **`1.1.0`** | **Minor** | Modular HTTP API endpoints, OpenAPI specification, and `/health` probe |
| **Frontend Web Dashboard** | `1.0.1` | `2.1.0` | **`2.1.1`** | **Patch (Aligned)** | React 19 + Tailwind CSS v4 dashboard client (`frontend/package.json`) |
| **Python Core Engine** | `0.1.0` | `2.1.0` | **`2.1.1`** | **Aligned** | Canonical Python distribution (`pyproject.toml` `recall-core`) |
| **MCP Server Adapter** | Unversioned | `1.0.0` | **`1.0.0`** | **Initial** | FastMCP stdio interface (`recall_mcp.server`) |
| **Database Schema** | `2` | `2` | **`2`** | **Unchanged** | Canonical SQLite schema version (`schema_version` migration level) |

---

## 3. Rationale for Target Versions

### 3.1 Historical Milestone: Application Release `1.0.1` → `2.0.0` (Major Bump)

A major version bump for the overall RECALL platform was established for the fundamental architectural paradigm shifts and internal re-organizations:

1. **Monorepo Architecture & Package Consolidation (ADR 0002, ADR 0003)**:
   - Restructuring from nested `core/recall_core/` legacy paths to root-level canonical packages (`recall_core`, `api`, `recall_mcp`, `database`, `intelligence`).
   - Deprecation and complete retirement of legacy `core/` compatibility delegation shims and consolidation of the test suite into a single root `tests/` tree.
2. **Retirement of Legacy Desktop Direction**:
   - Complete architectural shift away from former Qt/QML/PySide6 desktop concepts in favor of the modern Web Dashboard client.
3. **Introduction of Agentic FastMCP Surface**:
   - Full implementation of the FastMCP stdio protocol adapter exposing 8 canonical `/recall` tools directly to OpenCode and AI coding agents.
4. **Canonical Database Migration Level 2**:
   - Consolidated SQLite schema enforcing foreign-key cascade deletions, memory lineage tracking, and partial unique indexes for active project-scoped custom instructions.

### 3.2 HTTP API: `1.0.0` → `1.1.0` (Minor Bump)

A minor version bump for the HTTP/JSON REST API is justified because significant new functionality and endpoints were introduced in a **strictly backward-compatible** manner:

1. **Additive REST Endpoints**:
   - `DELETE /projects/{project_id}`: Hard deletion of project namespace with cascaded entity cleanup (returns `204 No Content` / `404 Not Found`).
   - `DELETE /custom-instructions/{instruction_id}`: Formalized soft deletion of custom instructions with `204 No Content` on success and `404 Not Found` if missing or previously deleted.
   - `POST /projects`: Programmatic project namespace creation with validation.
   - `POST /sessions`: Programmatic session creation and idempotency retrieval.
2. **Lineage Graph Serialization**:
   - Memory serialization helpers in `api/serializers.py` now dynamically populate `superseded_by` and `related_memories` via `MemoryManager.get_memory_lineage()`, unlocking complete lineage graph exploration without altering existing fields.
3. **Query & Mutation Enhancements**:
   - `GET /memories`: Added support for `status="deleted"` and `status="all"` filters.
   - `PATCH /memories/{id}`: Added dedicated parsing for `importance` (0–100 integer) and `tags` (string array) stored safely into metadata.
4. **Preservation of Preexisting Contracts**:
   - Zero preexisting endpoints were removed or renamed.
   - All response schemas remain forward-compatible supersets of the `1.0.0` contracts defined in `docs/CONTRACTS.md`.

### 3.3 Application Milestone: `2.0.0` → `2.1.0` (Minor Bump)

A minor version bump to `2.1.0` captures the cold-start search latency optimization and architectural resilience improvements:

1. **Cache-First Model Initialization**:
   - In `intelligence/embeddings.py`, `SentenceTransformer` loads with `local_files_only=True` first, avoiding synchronous network roundtrips to Hugging Face Hub when weights exist locally.
2. **Configurable MCP Startup Warmup**:
   - Controlled via `RECALL_MCP_WARMUP` (defaulting to enabled: `true`, `1`, `yes`). Executes an explicit dummy forward pass on startup, shifting PyTorch kernel allocation out of the agent request cycle.
   - Can be explicitly disabled (`RECALL_MCP_WARMUP=false`) for instant 38 ms process startup when cold search latency is acceptable.
3. **Search Cold-Start Latency Reduction**:
   - Initial `recall_search` execution dropped from **4,195.77 ms to 45.04 ms** (a **93.2x speedup** on first user interaction).
   - MCP process startup-to-ready time remains under 250 ms (233.7 ms with full warmup vs. 38.5 ms without warmup).
4. **Steady-State Warm Query Characterization**:
   - Benchmark distribution across 30 continuous runs shows warm queries executing consistently in **17.57 ms to 26.77 ms** (median **21.34 ms**, min **17.57 ms**).
   - Query time is dominated by PyTorch CPU vector inference (15–24 ms), with SQLite candidate retrieval (0.17 ms) and ChromaDB collection lookup (2.20 ms) scaling sub-linearly.
5. **Narrowed Exception Recovery & Error Integrity**:
   - Inner fallback strictly targets cache-miss and corruption exceptions: `cache_errors = (OSError, ValueError, CorruptedCacheException, EntryNotFoundError, SafetensorsParsingError)`.
   - If local cache is corrupted, online fallback self-heals by downloading clean assets from Hugging Face Hub.
   - In offline environments, fallback surfaces actionable error messages without masking underlying causes.
   - Hardware or runtime defects (`RuntimeError`, `TypeError`, `MemoryError`) bypass fallback and surface directly.
6. **MCP Stdio Protocol Protection**:
   - Warmup routines are wrapped in `with contextlib.redirect_stdout(sys.stderr):`.
   - Zero bytes leak to `sys.stdout`, guaranteeing that FastMCP JSON-RPC transport framing is never corrupted by third-party library progress bars or logging.
7. **Regression Test Suite**:
   - 8 new deterministic unit tests in `tests/test_semantic_retrieval.py` and `tests/test_mcp_bootstrap.py` covering cache hits, cache misses, corruption recovery, unexpected error bypass, warmup execution, `RECALL_MCP_WARMUP=false`, and stdio isolation.
8. **Runtime Regression Audit & Windows Distribution Fixes (v2.1.0 Distribution Audit)**:
   - **Windows CMD Batch Launcher Escape (`start_api.bat`)**: Escaped `&` as `^&` in line 13 (`Starting RECALL HTTP REST API ^& Web Dashboard`), eliminating the CMD command-splitting parse error: `'Web' is not recognized as an internal or external command`.
   - **MCP `runpy` `RuntimeWarning` Elimination**: Converted eager import of `create_server` in `recall_mcp/__init__.py` to PEP 562 lazy attribute loading via `__getattr__("create_server")`, eliminating `<frozen runpy>:128: RuntimeWarning: 'recall_mcp.server' found in sys.modules`. Added `recall_mcp/__main__.py` CLI alias for `python -m recall_mcp`.
   - **ChromaDB Disconnection Verification**: Verified that ChromaDB persistent vector index (`~/.recall/recall.sqlite3.chromadb`) remained 100% connected, healthy, and populated (32 active memories, cosine space). Clarified that the alleged disconnection was an operator suspicion triggered by stderr warmup logs and the `runpy` warning.
   - **HTTP API Dual-Mounting & SPA 404 Guard**: In `api/app.py`, mounted modular routers both at root (`/health`, `/projects`) and with `prefix="/api"` (`/api/health`, `/api/projects`) for reverse-proxy compatibility. Guarded SPA fallback routing so requests beginning with `api/` return strict `404 Not Found` JSON rather than fallback HTML.
   - **Frontend Dev Proxy & Environment Auto-Detection**: In `frontend/vite.config.ts`, added `rewrite: (path) => path.replace(/^\/api/, '')`. In `frontend/src/api/client.ts`, updated `API_BASE_URL` to auto-detect dev mode (`http://localhost:8080`) vs. production mode (`""` same-origin relative), honoring explicit `VITE_API_BASE_URL` overrides.

### 3.4 Application Milestone: `2.1.0` → `2.1.1` (Patch Bump — Minor UI fixes)

A patch bump to `2.1.1` captures UI fixes, canonical logo branding unification, and clean distribution packaging:

1. **Canonical Logo Integration**:
   - Adopted `frontend/src/assets/RECALL-logo-3.svg` as the single authoritative logo across the application.
   - Removed the legacy generic circular placeholder icon from the sidebar.
   - Created the shared `<RecallLogo>` component with responsive size presets (`xs`, `sm`, `md`, `lg`, `xl`) and optional wordmark.
2. **Favicon & Browser Metadata**:
   - Replaced default Vite icon with the official RECALL emblem (`favicon.svg`, `favicon.ico`, `favicon-32x32.png`, `apple-touch-icon.png`).
   - Updated `frontend/index.html` metadata and verified HTTP serving.
3. **Distribution Packaging Optimization**:
   - Updated `scripts/build_dist_bundle.py` to package `recall-2.1.1-windows.zip`.
   - Included `frontend/public/` in the distribution bundle to ensure standalone and development asset parity.

---

## 4. Backward Compatibility Assessment

| Contract Area | Change Type | Compatibility Finding | Impact on Existing Clients |
| :--- | :---: | :---: | :--- |
| **Existing Endpoints** | Unchanged | **Compatible** | All `1.0.0` routes retain identical paths, HTTP verbs, and parameter names |
| **New Endpoints** | Additive | **Compatible** | New routes (`DELETE /projects/{id}`, `POST /projects`, etc.) do not conflict with existing callers |
| **Query Parameters** | Additive | **Compatible** | New filters (`status="all"`, `status="deleted"`) default to prior behavior when omitted |
| **Response Payloads** | Additive | **Compatible** | Additive fields (`superseded_by`, `related_memories`, `total`) are ignored by naive clients |
| **Error Formats** | Standardized | **Compatible** | Standard HTTP status codes (400, 404, 409, 500) with JSON `{"detail": "..."}` payloads preserved |
| **UI-Only Changes** | Presentation | **Isolated** | Tailwind CSS v4 styling and component adjustments are strictly isolated from the REST API contract |

**Conclusion:** The HTTP API changes strictly fulfill the SemVer definition of a MINOR increment (new backward-compatible functionality). No breaking changes exist that would require an API major bump to `2.0.0`.

---

## 5. Metadata Alignment Summary

1. **Application & Frontend Alignment (`2.1.1`)**:
   - `README.md` reports `v2.1.1`.
   - `frontend/src/components/layout/Sidebar.tsx` reports `v2.1.1`.
   - `frontend/package.json` specifies `"version": "2.1.1"`.
   - `frontend/package-lock.json` synchronized at `"version": "2.1.1"`.
   - Root `pyproject.toml` declares `version = "2.1.1"`.
   - `docs/PACKAGING_AND_DISTRIBUTION.md` records `2.1.1`.
2. **HTTP API Version Alignment (`1.1.0`)**:
   - `api/__init__.py` declares `__version__ = "1.1.0"` and `API_VERSION = "1.1.0"`.
   - `api/app.py` specifies `version="1.1.0"` in `FastAPI(...)`.
   - `api/routes/health.py` reports `"api_version": "1.1.0"`.
   - `frontend/src/api/mockClient.ts` aligns mock health with `api_version: '1.1.0'`.
   - `tests/test_integration_phase_c.py` verifies `api_version == "1.1.0"`.
3. **MCP Server Alignment (`1.0.0`)**:
   - `recall_mcp/server.py` implements the FastMCP stdio interface exposing all 8 canonical `/recall` tools.
4. **Canonical Database Schema (`2`)**:
   - SQLite migration level remains at `schema_version = 2`.

---

## 6. Pre-Release Verification Checklist

Before tagging or cutting the `2.1.1` / `1.1.0` release, the following automated and manual gates must pass:

- [x] **Consolidated Pytest Suite**:
  ```bash
  pytest -q
  ```
  *Ensure all 377 unit, contract, repository, and integration tests pass with zero regressions.*
- [x] **Integration Test Health Check Assertion**:
  `tests/test_integration_phase_c.py` line 90 asserts `api_version == "1.1.0"`.
- [x] **Frontend Production Build & Typecheck**:
  ```bash
  cd frontend
  npm run build
  ```
  *Ensure TypeScript compiles cleanly (`tsc`) and Vite generates the production bundle without errors.*
- [x] **OpenAPI Metadata Verification**:
  FastAPI application reports `version="1.1.0"` and OpenAPI schema documents all routes.
- [x] **Health Endpoint Contract Verification**:
  `GET /health` and `GET /healthz` return `api_version: "1.1.0"`.
- [x] **MCP Server Diagnostic & Stdout Protocol Isolation**:
  Confirm that warmup output never reaches `sys.stdout` and that FastMCP registers all tools.
- [x] **Database Integrity Verification**:
  Verified canonical SQLite database row counts (49 memories, 2 projects, 3 instructions) and schema version 2 intact.
