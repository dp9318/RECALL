# RECALL — Release Planning & Target Version Specifications

## 1. Overview & Objective

This document pins the target release versions and outlines the verification checklist for the upcoming major RECALL release. It audits all independent subsystem versions across the codebase, records the rationale for version increments according to Semantic Versioning (SemVer 2.0.0), and documents backward-compatibility guarantees for the HTTP API.

> [!NOTE]
> Per release planning governance, this document records target versions and verification requirements in advance. No production files, packages, or configurations are mutated, nor are Git tags created or published in this step.

---

## 2. Version Target Registry

| Subsystem / Layer | Current Reported Version | Target Release Version | SemVer Increment Type | Status / Representation |
| :--- | :---: | :---: | :---: | :--- |
| **Application Release** | `1.0.1` | **`2.0.0`** | **Major** | Monorepo system-level release, user documentation, and product baseline |
| **HTTP API (FastAPI REST)** | `1.0.0` | **`1.1.0`** | **Minor** | Modular HTTP API endpoints, OpenAPI specification, and `/health` probe |
| **Frontend Web Dashboard** | `1.0.1` | `2.0.0` | Major (Aligned) | React 19 + Tailwind CSS v4 dashboard client (`frontend/package.json`) |
| **Python Core Engine** | `0.1.0` | `0.1.0` (or `2.0.0`) | Unchanged / Independent | Canonical Python distribution (`pyproject.toml` `recall-core`) |
| **MCP Server Adapter** | Unversioned | `1.0.0` / Inherited | Initial / Aligned | FastMCP stdio interface (`recall_mcp.server`) |
| **Database Schema** | `2` | `2` | Unchanged | Canonical SQLite schema version (`schema_version` migration level) |

---

## 3. Rationale for Target Versions

### 3.1 Application Release: `1.0.1` → `2.0.0` (Major Bump)

A major version bump for the overall RECALL platform is justified by extensive, fundamental architectural paradigm shifts and breaking internal re-organizations:

1. **Monorepo Architecture & Package Consolidation (ADR 0002, ADR 0003)**:
   - Complete restructuring from nested `core/recall_core/` legacy paths to root-level canonical packages (`recall_core`, `api`, `recall_mcp`, `database`, `intelligence`).
   - Deprecation and complete retirement of legacy `core/` compatibility delegation shims and consolidation of the test suite into a single root `tests/` tree.
2. **Retirement of Legacy Desktop Direction**:
   - Complete architectural shift away from the former Qt/QML/PySide6 desktop concepts in favor of the modern Web Dashboard client.
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

## 5. Metadata Audit & Inconsistency Analysis

1. **Application vs. Frontend vs. Package Inconsistency**:
   - `README.md` and `frontend/src/components/layout/Sidebar.tsx` report `v1.0.1`.
   - `frontend/package.json` specifies `"version": "1.0.1"`.
   - Root `pyproject.toml` declares `version = "0.1.0"` under package name `recall-core`.
   - *Resolution for Release:* Update `README.md`, `frontend/package.json`, and `Sidebar.tsx` to `2.0.0`. Evaluate aligning `pyproject.toml` or documenting `recall-core` as an independently versioned core Python package.
2. **Hardcoded API Version Inconsistency**:
   - `api/app.py` specifies `version="1.0.0"` in `FastAPI(title="RECALL HTTP API", version="1.0.0")`.
   - `api/routes/health.py` hardcodes `"api_version": "1.0.0"` in the health payload dictionary.
   - `frontend/src/api/mockClient.ts` hardcodes `api_version: '1.0.0'`.
   - `tests/test_integration_phase_c.py` explicitly tests `assert res_healthz.json()["api_version"] == "1.0.0"`.
   - *Resolution for Release:* Establish a single authoritative API version constant (e.g. `api.__version__ = "1.1.0"`) shared by `app.py`, `health.py`, and the test suite.
3. **Unversioned MCP Server**:
   - `recall_mcp/server.py` initializes `FastMCP("RECALL")` without an explicit version parameter.
   - *Resolution for Release:* Pass explicit server version (e.g. `version="1.0.0"` or matching application `2.0.0`) when initializing `FastMCP`.

---

## 6. Pre-Release Verification Checklist

Before tagging or cutting the `2.0.0` / `1.1.0` release, the following automated and manual gates must pass:

- [ ] **Consolidated Pytest Suite**:
  ```bash
  pytest -q
  ```
  *Ensure all unit, contract, repository, and integration tests pass with zero regressions.*
- [ ] **Integration Test Health Check Assertion**:
  Update `tests/test_integration_phase_c.py` line 90 to assert `api_version == "1.1.0"` when the version constant is bumped.
- [ ] **Frontend Production Build & Typecheck**:
  ```bash
  cd frontend
  npm run build
  ```
  *Ensure TypeScript compiles cleanly (`tsc`) and Vite generates the production bundle without errors.*
- [ ] **OpenAPI Metadata Verification**:
  Query `GET /openapi.json` from the running API service and confirm that:
  - `info.version` equals `"1.1.0"`.
  - All new endpoints (`DELETE /projects/{id}`, `POST /projects`, `POST /sessions`) are present in `paths`.
- [ ] **Health Endpoint Contract Verification**:
  Query `GET /health` and `GET /healthz` and verify:
  - `api_version` returns `"1.1.0"`.
  - `status` returns `"healthy"`.
  - `database_connected` and `chromadb_connected` return `true`.
- [ ] **MCP Server Diagnostic & Tool Smoke Test**:
  ```bash
  python scripts/smoke_test_mcp.py
  ```
  *Confirm all 8 FastMCP tools register and respond through stdio.*
- [ ] **Database Integrity Verification**:
  Execute read-only `PRAGMA integrity_check` on the canonical SQLite database to verify zero corrupt B-trees or broken foreign keys.
