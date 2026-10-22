"""Build script to create the clean RECALL 2.1.0 Windows distribution bundle and ZIP archive.

Usage:
    python scripts/build_dist_bundle.py
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path


def build_bundle() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = repo_root / "dist"
    bundle_name = "recall-2.1.0-windows"
    bundle_dir = dist_dir / bundle_name
    zip_path = dist_dir / f"{bundle_name}.zip"

    print(f"[1/5] Preparing distribution directories under {dist_dir}...")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if zip_path.exists():
        zip_path.unlink()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 1. Top-level files to copy
    top_level_files = [
        "pyproject.toml",
        "requirements.txt",
        ".env.example",
        "mcp_config.example.json",
        "setup.bat",
        "setup.ps1",
        "start_api.bat",
        "start_mcp.bat",
        "LICENSE",
    ]

    print("[2/5] Copying application source packages and configuration...")
    for filename in top_level_files:
        src = repo_root / filename
        if src.exists():
            shutil.copy2(src, bundle_dir / filename)

    # 2. Python packages
    packages = [
        "recall_core",
        "database",
        "intelligence",
        "contracts",
        "api",
        "recall_mcp",
    ]

    def ignore_patterns(path: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in ("__pycache__", ".pytest_cache", ".venv", "node_modules", ".git"):
                ignored.add(name)
            elif name.endswith((".pyc", ".pyo", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".log")):
                ignored.add(name)
        return ignored

    for pkg in packages:
        src_pkg = repo_root / pkg
        dest_pkg = bundle_dir / pkg
        shutil.copytree(src_pkg, dest_pkg, ignore=ignore_patterns)

    # 3. Scripts
    scripts_dest = bundle_dir / "scripts"
    scripts_dest.mkdir(parents=True, exist_ok=True)
    for script in ["smoke_test_mcp.py", "generate_mcp_config.py", "list_projects.py", "benchmark_chroma.py", "README.md"]:
        src_script = repo_root / "scripts" / script
        if src_script.exists():
            shutil.copy2(src_script, scripts_dest / script)

    # 4. Frontend (including pre-built dist/ and sources, excluding node_modules)
    print("[3/5] Packaging frontend distribution assets and build sources...")
    frontend_src = repo_root / "frontend"
    frontend_dest = bundle_dir / "frontend"
    frontend_dest.mkdir(parents=True, exist_ok=True)

    # Copy frontend dist
    if (frontend_src / "dist").exists():
        shutil.copytree(frontend_src / "dist", frontend_dest / "dist", ignore=ignore_patterns)

    # Copy frontend src and build manifests
    if (frontend_src / "src").exists():
        shutil.copytree(frontend_src / "src", frontend_dest / "src", ignore=ignore_patterns)

    for item in ["package.json", "package-lock.json", "vite.config.ts", "tsconfig.json", "index.html"]:
        f_item = frontend_src / item
        if f_item.exists():
            shutil.copy2(f_item, frontend_dest / item)

    # 5. Docs (core architecture and release documentation)
    docs_dest = bundle_dir / "docs"
    docs_dest.mkdir(parents=True, exist_ok=True)
    for doc in ["RELEASE_PLAN.md", "PACKAGING_AND_DISTRIBUTION.md", "ARCHITECTURE.md", "CONTRACTS.md"]:
        doc_src = repo_root / "docs" / doc
        if doc_src.exists():
            shutil.copy2(doc_src, docs_dest / doc)

    # 6. Dedicated Distribution README
    bundle_readme = """# RECALL v2.1.0 — Windows Distribution Package

Persistent memory engine for AI coding agents.

This distribution package provides a self-contained installation of RECALL Local for Windows,
including the FastAPI REST backend, pre-built Web Dashboard, and FastMCP stdio agent server.

---

## ⚡ Quick Start on Windows

### 1. Prerequisites
- **Windows 10 or 11 (64-bit)**
- **Python 3.11 or 3.12 (64-bit)** installed and added to your system `PATH` (https://www.python.org/downloads/)
- **Standard User Privileges:** Administrator privileges are **NOT** required.
- Optional: **Node.js 18+** (only if you wish to modify frontend sources and run live Vite dev server)

### 2. Run Setup
Open the extracted directory in Windows Explorer or Command Prompt:
- **Batch (Default):** Double-click `setup.bat` (or run `setup.bat` in Command Prompt).
- **PowerShell:** Run `.\\setup.ps1`.
  *(If PowerShell execution policy blocks the script, run: `powershell -ExecutionPolicy Bypass -File .\\setup.ps1`)*

The setup script runs entirely in user space and will automatically:
1. Detect Python 3.11 or 3.12 on system `PATH`.
2. Create an isolated virtual environment in `.venv\\`.
3. Install runtime dependencies (`fastapi`, `uvicorn`, `python-dotenv`, `mcp`, `chromadb`, `sentence-transformers`) with fallback linking.
4. Run an initial isolated smoke test in `%TEMP%` to verify database migrations and FastMCP tools without modifying your live user data.
5. Auto-generate `mcp_config.local.json` in this directory with your machine's exact resolved paths.

---

## 🚀 Running RECALL Services

### 1. Start the Web Dashboard & HTTP API Server
Double-click `start_api.bat` (or execute `.venv\\Scripts\\python.exe -m api.main`).
- **Web Dashboard:** `http://localhost:8080/` (Pre-compiled production assets served directly from FastAPI — no Node.js required!)
- **Interactive Swagger Documentation:** `http://localhost:8080/docs`
- **Health Liveness Probe:** `http://localhost:8080/health` (reports `api_version: "1.1.0"`)

### 2. Connect AI Coding Agents via MCP
RECALL includes a built-in FastMCP stdio server exposing 8 canonical `/recall` tools.
During setup, `mcp_config.local.json` was automatically generated with your exact machine paths.

**Option A (Auto-Generated - Recommended):**
Open `mcp_config.local.json` and copy the ready-to-use snippet for your agent:
- **Google Antigravity:** `.agents/mcp_config.json` (workspace root or `%USERPROFILE%\\.gemini\\config\\mcp_config.json`)
- **Cursor:** `.cursor/mcp.json` or `%USERPROFILE%\\.cursor\\mcp.json`
- **Claude Desktop:** `%APPDATA%\\Claude\\claude_desktop_config.json`
- **OpenCode:** `.opencode/opencode.json` in workspace root

**Option B (Manual):**
- Standard format (Google Antigravity, Cursor, Claude Desktop):
```json
{
  "mcpServers": {
    "recall": {
      "command": "<PATH_TO_RECALL>\\\\.venv\\\\Scripts\\\\python.exe",
      "args": ["-m", "recall_mcp.server"],
      "env": {
        "RECALL_MCP_WARMUP": "true"
      }
    }
  }
}
```
- OpenCode format (`.opencode/opencode.json`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "recall": {
      "type": "local",
      "command": ["<PATH_TO_RECALL>\\\\.venv\\\\Scripts\\\\python.exe", "-m", "recall_mcp.server"],
      "environment": {
        "RECALL_MCP_WARMUP": "true"
      },
      "enabled": true
    }
  }
}
```
*(Replace `<PATH_TO_RECALL>` with the directory where this package was extracted, e.g. `C:\\\\Users\\\\username\\\\RECALL`)*

---

## 📦 Data Storage & Privacy

RECALL isolates all user data outside the application directory:
- **Canonical Storage:** `%USERPROFILE%\\.recall\\recall.sqlite3` (SQLite schema version 2, WAL mode)
- **Derived Semantic Index:** `%USERPROFILE%\\.recall\\recall.sqlite3.chromadb\\`
- **Database Backups:** `%USERPROFILE%\\.recall\\backups\\`
- **Model Weights Cache:** `%USERPROFILE%\\.cache\\huggingface\\hub\\`

No code or user memories are transmitted to external cloud services unless explicitly configured.

---

## 🌐 SentenceTransformer & Offline Behavior

1. **First-Run Download:**
   The default embedding model (`sentence-transformers/all-MiniLM-L6-v2`, ~90 MB) is downloaded
   automatically on the first semantic search or warmup if internet access is available.
2. **Subsequent Warm Runs:**
   Once cached, RECALL uses cache-first loading (`local_files_only=True`) and never initiates
   outbound network requests.
3. **Air-Gapped / Offline Environments:**
   To deploy offline without internet access, copy the folder:
   `%USERPROFILE%\\.cache\\huggingface\\hub\\models--sentence-transformers--all-MiniLM-L6-v2`
   from an online machine to the target machine's `%USERPROFILE%\\.cache\\huggingface\\hub\\` directory.
   RECALL will operate completely offline with zero network connectivity.
4. **Behavior when Model is Unavailable:**
   If offline and no model cache exists, RECALL returns an actionable error explaining that model
   files were not found locally. Canonical SQLite memory creation, updates, and structured retrieval
   continue to function without interruption.

---

## 🛠️ Troubleshooting

- **Python not recognized:** Ensure Python 3.11+ is installed and checked "Add Python to PATH".
- **PowerShell execution policy error:** Run `powershell -ExecutionPolicy Bypass -File .\\setup.ps1` or use `setup.bat`.
- **Administrator privileges:** RECALL does not require administrator privileges. All operations occur in user-writable paths.
- **MCP transport timeout / warmup:** By default, `RECALL_MCP_WARMUP=true` warms up the model in ~200 ms.
  To disable warmup for instant process start, set `RECALL_MCP_WARMUP=false`.
- **Port 8080 already in use:** Set `RECALL_API_PORT=8081` in `.env` or system environment.
- **Windows long paths error:** Enable long paths via `git config --system core.longpaths true`.

---

## 📄 License & Version
- Application Version: `2.1.0`
- HTTP API Version: `1.1.0`
- License: MIT
"""
    with open(bundle_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(bundle_readme)

    # 7. Create ZIP archive
    print(f"[4/5] Compressing {bundle_dir} into {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for root, _, files in os.walk(bundle_dir):
            for file in files:
                file_path = Path(root) / file
                archive_name = file_path.relative_to(dist_dir)
                zipf.write(file_path, archive_name)

    # 8. Report statistics
    total_files = sum(len(files) for _, _, files in os.walk(bundle_dir))
    uncompressed_bytes = sum(
        (Path(root) / file).stat().st_size
        for root, _, files in os.walk(bundle_dir)
        for file in files
    )
    zip_bytes = zip_path.stat().st_size

    print("[5/5] Distribution bundle successfully created!")
    print(f"       Artifact Path:      {zip_path}")
    print(f"       Bundle Directory:   {bundle_dir}")
    print(f"       Total Files:        {total_files}")
    print(f"       Uncompressed Size:  {uncompressed_bytes / 1024 / 1024:.2f} MB")
    print(f"       Compressed Size:    {zip_bytes / 1024 / 1024:.2f} MB")

    return zip_path


if __name__ == "__main__":
    build_bundle()
