# ADR 0003 — Canonical Package and Test Consolidation

## Status

Accepted.

## Context

In ADR 0002, the core package was promoted from nested `core/recall_core/` to top-level `recall_core/`, and the monolithic HTTP API was decomposed into top-level `api/`. To prevent breaking tests and legacy workflows during the transition, thin backward-compatibility re-export shims were retained under `core/recall_core/`, alongside the older unit test suite in `core/tests/`.

Following the complete verification of the restructured runtime surfaces (`recall_mcp`, `api`, `frontend`), an audit of the repository revealed:
1. `core/recall_core/` contained 0% distinct business logic and functioned exclusively as pure delegation shims.
2. All production entry points (`recall_mcp/server.py`, `api/app.py`, `api/routes/`) already imported directly from top-level `recall_core` and `api`.
3. Having parallel test trees (`core/tests/` and `tests/`) fragmented test execution, complicated fixture sharing (`conftest.py`), and created ambiguity over test discovery.
4. Continuing to maintain legacy shims created long-term maintenance overhead and potential import confusion for developers and agent workflows.

## Decision

1. **Migrate Internal Consumers**: Update all internal tests, scripts (`scripts/smoke_test_mcp.py`), and documentation to import exclusively from canonical `recall_core` and `api`.
2. **Consolidate Test Suite**: Move all test modules from `core/tests/` to root `tests/`, merge root test fixtures into `tests/conftest.py`, and configure `pytest.ini` with `testpaths = tests`.
3. **Retire Compatibility Shims**: Safely remove `core/recall_core/`, `core/__init__.py`, and obsolete `core/` scaffolding.
4. **Update Packaging**: Remove `core*` from `tool.setuptools.packages.find.include` in `pyproject.toml`, leaving only canonical packages (`recall_core*`, `api*`, `contracts*`, `database*`, `intelligence*`, `recall_mcp*`).

## Consequences

- Exactly one authoritative, top-level implementation exists for every architectural subsystem:
  - `recall_core/`: Domain facade orchestration (`MemoryManager`, `create_memory_manager`).
  - `api/`: Modular FastAPI HTTP/REST application.
  - `recall_mcp/`: FastMCP stdio server for AI coding agents.
  - `database/`: SQLite canonical persistence and ChromaDB semantic index.
  - `intelligence/`: Hybrid retrieval, embeddings, and LLM conflict arbitration.
  - `contracts/`: Shared DTOs and type schemas.
  - `frontend/`: React 19 + Tailwind CSS v4 dashboard.
  - `tests/`: Single consolidated test suite covering all units and integration flows.
- Legacy `core.recall_core` import paths are fully retired.
- Test discovery is unified into a single root `pytest` invocation without path collisions.
