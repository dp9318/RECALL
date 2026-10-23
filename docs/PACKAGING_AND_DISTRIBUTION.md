# RECALL — Packaging, Distribution, and Recovery Specification

This document details the current distribution architecture, canonical data storage locations, backup/recovery protocols, and the Windows deployment roadmap for RECALL Local.

---

## 1. Current Packaging Architecture

RECALL uses a standard **PEP 621** monorepo packaging configuration governed by the root `pyproject.toml`.

### 1.1 Python Package (`recall-core`)
- **Build System:** `setuptools>=61.0` and `wheel`
- **Package Name:** `recall-core`
- **Current Version:** `2.1.1` (Core package)
- **Included Packages:** `recall_core*`, `api*`, `contracts*`, `database*`, `intelligence*`, `recall_mcp*`
- **Console Script Entry Points:**
  ```toml
  [project.scripts]
  recall-mcp = "recall_mcp.server:main"
  recall-api = "api.main:main"
  ```

### 1.2 Frontend Distribution (`frontend/`)
- **Framework:** React 19 + TypeScript + Vite + Tailwind CSS v4
- **Manifest:** `frontend/package.json` (`version: 2.1.1`)
- **Build Output:** Compiled static assets output to `frontend/dist/` (`index.html`, minified JS/CSS chunks).
- **Serving Strategy:**
  - In development: Served via Vite dev server at `http://localhost:5173` with proxy rewrites (`/api/*` -> `http://localhost:8080/*`).
  - In production: Served directly by FastAPI mounted at root `/` and `/assets` with SPA client routing fallback and strict API 404 guards via `api/app.py`.

---

## 2. Canonical Data Storage & File Layout

All persistent runtime state is isolated to the user's home directory under `~/.recall/`:

```text
~/.recall/
├── recall.sqlite3              # Canonical SQLite database (schema version 2, WAL mode)
├── recall.sqlite3-wal          # Active Write-Ahead Log sidecar
├── recall.sqlite3-shm          # Shared memory index for WAL
├── recall.sqlite3.chromadb/    # Derived ChromaDB persistent vector index
│   ├── chroma.sqlite3          # ChromaDB collection metadata
│   └── <uuid>/                 # HNSW binary vector indices
└── backups/                    # Online timestamped database backups
    └── recall_backup_YYYYMMDD_HHMMSS.sqlite3
```

### Path Resolution Invariants
- By default, `RECALL_DB_PATH` is unset and resolves dynamically to:
  `pathlib.Path.home() / ".recall" / "recall.sqlite3"`
- When `RECALL_DB_PATH` is explicitly provided, the database and derived Chroma directory automatically orient relative to the custom path.

---

## 3. Backup, Verification, and Disaster Recovery

### 3.1 Online Database Backup Protocol
RECALL implements an online, non-blocking backup mechanism using Python's native `sqlite3.Connection.backup()` API:

```python
import sqlite3
from pathlib import Path

source_path = Path.home() / ".recall" / "recall.sqlite3"
backup_path = Path.home() / ".recall" / "backups" / "recall_backup_YYYYMMDD_HHMMSS.sqlite3"

# Open source strictly in read-only mode to prevent write contention
source_conn = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
dest_conn = sqlite3.connect(backup_path)

# Execute streaming page-by-page backup
source_conn.backup(dest_conn, pages=100)

dest_conn.close()
source_conn.close()
```

**Key Safety Properties:**
- Operates concurrently with active readers and writers without taking exclusive database locks.
- Automatically folds pending uncheckpointed WAL frames into the backup file, producing a standalone, fully compacted SQLite database.
- The backup passes `PRAGMA integrity_check` independently of WAL sidecars.

### 3.2 Restoring from Backup
To restore a prior database snapshot:
1. Stop all running RECALL instances (`recall-api`, `recall-mcp`, Web Dashboard).
2. Archive the existing `~/.recall/recall.sqlite3` and remove stale `-wal` and `-shm` sidecars.
3. Copy the selected backup snapshot to `~/.recall/recall.sqlite3`.
4. Rebuild the derived ChromaDB index:
   ```bash
   python -c "from recall_core.bootstrap import create_memory_manager; m = create_memory_manager(); m.rebuild_semantic_index(); m.close()"
   ```
5. Restart RECALL services.

---

## 4. Upgrade & Uninstall Safety

### 4.1 Schema Migration Idempotency
- Canonical schema level is tracked in table `schema_version`.
- Migrations in `database/migrations/` apply sequentially within atomic SQLite transactions.
- Running migration checks on an already-migrated database is a safe, zero-mutation no-op.

### 4.2 Uninstall Invariant
- Removing Python virtual environments (`.venv/`) or the source tree **never** touches or deletes the user's persistent context in `~/.recall/`.
- User memories and custom instructions remain intact across reinstalls and Python environment refreshes.

---

## 5. Windows Distribution Architecture & Roadmap

### 5.1 Implemented in v2.1.0 / v2.1.1: Portable Windows Distribution Archive
RECALL provides a self-contained portable Windows distribution (`recall-2.1.1-windows.zip` generated via `scripts/build_dist_bundle.py`):
1. **Zero-Node User Runtime**: Pre-compiled production frontend (`frontend/dist`) is served directly by FastAPI on port 8080 (`start_api.bat`). End users need only Python 3.11/3.12 (standard user privileges; Administrator not required).
2. **Automated User-Space Setup (`setup.bat` / `setup.ps1`)**: Creates an isolated `.venv`, upgrades pip, installs runtime dependencies with verified fallback linking, and executes an isolated smoke test in `%TEMP%` protecting live storage.
3. **Automatic Client MCP Configuration (`scripts/generate_mcp_config.py`)**: Resolves absolute python paths and emits ready-to-copy snippets in `mcp_config.local.json` for OpenCode, Cursor, Google Antigravity, and Claude Desktop.
4. **Resilient Launchers**: `start_api.bat` and `start_mcp.bat` provide double-clickable or CMD launchers with clean error reporting.

### 5.2 Upcoming Enhancements
1. **Self-Contained Executables**: Package `recall-api` and `recall-mcp` using PyInstaller into standalone Windows binaries (`recall-api.exe`, `recall-mcp.exe`).
2. **Windows Background Service**: Lightweight system-tray runner or NSSM service wrapper to manage daemon lifecycle on user logon.
3. **Automated Backup Schedule**: Scheduled daily background backup trigger with rolling 7-day retention in `~/.recall/backups/`.
