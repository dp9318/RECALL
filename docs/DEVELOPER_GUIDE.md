# RECALL — Developer & Operations Guide

This guide provides practical instructions for setting up the local development environment, executing client surfaces, running the test suite, and troubleshooting common operational issues.

---

## 1. Prerequisites

- **Python**: Version `3.11` or `3.12` (with `venv` and `pip`)
- **Node.js**: Version `18.0.0+` or `20.0.0+` (with `npm`)
- **Operating System**: Windows 10/11, macOS, or Linux
- **Optional Local LLM**: [Ollama](https://ollama.com/) running locally with model `qwen2.5:3b` for bounded conflict arbitration

---

## 2. Environment Setup

### 2.1 Clone & Virtual Environment

```bash
# Clone the repository
git clone <repository-url> RECALL
cd RECALL

# Create a Python virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (cmd):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

### 2.2 Install Python Dependencies

Install RECALL in editable mode with all optional feature sets:

```bash
# Install core engine, test tools, MCP protocol, and semantic dependencies:
pip install -e ".[test,mcp,semantic]"
```

This registers the CLI console scripts:
- `recall-api`: Starts the modular FastAPI REST server.
- `recall-mcp`: Starts the FastMCP stdio server for coding agents.

### 2.3 Configure Environment Variables

Copy the provided sanitized template:

```bash
cp .env.example .env
```

Key variables configured in `.env`:
- `RECALL_API_HOST`: Defaults to `0.0.0.0`
- `RECALL_API_PORT`: Defaults to `8080`
- `RECALL_DB_PATH`: Path to custom SQLite database (defaults to `~/.recall/recall.sqlite3`)
- `RECALL_CORS_ORIGINS`: Comma-separated allowed origins (e.g. `http://localhost:5173`)
- `RECALL_API_RELOAD`: Set to `true` to enable Uvicorn hot reloading during development

### 2.4 Setup Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

---

## 3. Running Client Surfaces

### 3.1 Running the HTTP REST API

```bash
# Using the console script:
recall-api

# Or directly with Python:
python -m api.main

# With hot-reloading (development):
uvicorn api.app:app --host 0.0.0.0 --port 8080 --reload
```

- API Base URL: `http://localhost:8080`
- Interactive OpenAPI Docs: `http://localhost:8080/docs`
- Health Probe: `http://localhost:8080/health`

### 3.2 Running the FastMCP Server (Agent Surface)

```bash
# Using the console script:
recall-mcp

# Or via Python module:
python -m recall_mcp.server
```

When connected to an AI agent (such as OpenCode or Antigravity), communication occurs via standard JSON-RPC over `stdin` and `stdout`. Diagnostic logs are routed to `stderr` to prevent protocol corruption.

### 3.3 Running the React Web Dashboard

```bash
cd frontend
npm run dev
```

- Local Dev URL: `http://localhost:5173`
- The frontend connects to the backend API at `http://localhost:8080` by default.

---

## 4. Testing & Verification

### 4.1 Running the Consolidated Pytest Suite

```bash
# Run all tests with short progress output:
pytest -q

# Run specific test modules:
pytest tests/test_database_repositories.py -v
pytest tests/test_http_api.py -v
pytest tests/test_mcp_server.py -v
pytest tests/test_integration_phase_b.py -v
pytest tests/test_integration_phase_c.py -v
```

> [!IMPORTANT]
> **Isolated Test Invariant**: All test fixtures in `tests/conftest.py` instantiate ephemeral in-memory databases (`DatabaseConfig.in_memory()`) or isolated temporary directory databases. Tests **never** mutate the live user database at `~/.recall/recall.sqlite3`.

### 4.2 Architecture Boundary Regression Tests

To ensure the client surfaces do not bypass the `MemoryManager` facade, automated Abstract Syntax Tree (AST) regression tests run as part of the test suite:
- `test_api_package_has_zero_uow_access`
- `test_api_module_has_zero_uow_access`

These verify that no file in `api/` imports or references private UnitOfWork (`_uow`) attributes or repository classes directly.

### 4.3 Running the Frontend Build & Typecheck

```bash
cd frontend
npm run build
```

This executes `tsc` (strict TypeScript validation) followed by `vite build`. It must compile with zero errors before any commit or release.

### 4.4 Diagnostic Scripts (`scripts/`)

- **MCP Smoke Test:** Tests FastMCP tool registration and end-to-end SQLite + ChromaDB operations:
  ```bash
  python scripts/smoke_test_mcp.py
  ```
- **List SQLite Projects:** Quick read-only inspection of projects in the canonical database:
  ```bash
  python scripts/list_projects.py
  ```
- **ChromaDB Latency Benchmark:** Benchmarks embedding and query speeds:
  ```bash
  python scripts/benchmark_chroma.py
  ```

---

## 5. Troubleshooting & Common Pitfalls

### 5.1 Initial HuggingFace Download Delay
**Symptom:** The first invocation of `recall_search` or `scripts/smoke_test_mcp.py` hangs for 10–20 seconds.  
**Cause:** SentenceTransformers downloads the model weights (`sentence-transformers/all-MiniLM-L6-v2`) on first run into `~/.cache/huggingface/hub/`.  
**Resolution:** This is a one-time operation. Subsequent runs load the cached weights locally in under 20ms.

### 5.2 SQLite WAL Locking & Busy Timeout
**Symptom:** `sqlite3.OperationalError: database is locked`.  
**Cause:** Concurrent multi-process writes without WAL checkpointing or long-running exclusive locks.  
**Resolution:** RECALL configures WAL mode (`PRAGMA journal_mode=WAL`) and `busy_timeout=5000ms`. Ensure long-running transactions commit or close their connection contexts promptly.

### 5.3 Stale ChromaDB Cache across Processes
**Symptom:** A memory created via HTTP API is not immediately visible in an already-running MCP search.  
**Cause:** ChromaDB's in-memory index cache is local to each process.  
**Resolution:** The Chroma client will reload on next query. For full consistency, use `MemoryManager.rebuild_semantic_index()`.
