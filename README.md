# RECALL — Persistent Memory Engine for AI Coding Agents

RECALL is a local, persistent memory engine designed for AI coding agents. Its purpose is to preserve useful project context across development sessions, retrieve relevant historical context, manage explicit user-authored custom instructions, detect and arbitrate conflicting memories, and expose unified context through both an **MCP server** for agent-integrated IDEs and a **Web Dashboard** for developers.

RECALL is the memory engine itself — not a standalone chatbot or a coding agent. It acts as the persistent cognitive layer that makes any coding agent smarter over time.

---

## 🏗️ Architecture & Memory Hierarchy

RECALL uses a layered architecture with explicit authority rules:

```text
                          CLIENT SURFACES
        ┌────────────────────────┬─────────────────────────┐
        │                        │                         │
        │ OpenCode / Antigravity │ Web Dashboard           │
        │ Cursor / Claude (MCP)  │ React + Tailwind CSS    │
        │ /recall commands       │ HTTP / JSON API         │
        └──────────────┬─────────┴──────────────┬──────────┘
                       │                        │
                       └────────────┬───────────┘
                                    ▼
                         ┌─────────────────────────┐
                         │       RECALL CORE       │
                         │    (Python FastMCP/API) │
                         │                         │
                         │ memory lifecycle        │
                         │ retrieval & compaction  │
                         │ custom instructions     │
                         │ conflict arbitration    │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
              ┌──────────┐      ┌──────────┐       ┌────────────┐
              │  SQLite  │─────▶│ ChromaDB │       │ Local LLM  │
              │canonical │      │ derived  │       │ bounded    │
              │ truth    │      │ index    │       │ arbitration│
              └──────────┘      └──────────┘       └────────────┘
```

### Memory Authority Rules

When conflicts arise, RECALL enforces strict authority ordering:
1. **Explicit user custom instructions** (`Scope.GLOBAL` / `Scope.PROJECT`)
2. **Explicit user updates / supersessions**
3. **Current valid canonical memories**
4. **Older historical memories**
5. **Local 1B–3B LLM arbitration** (for ambiguous conflict resolution)
6. **Unresolved / Abstain** (returns unresolved state instead of fabricating certainty)

- **SQLite** is the canonical source of truth for sessions, events, memories, lineage, projects, and custom instructions (persisted in `~/.recall/recall.sqlite3`).
- **ChromaDB** is a derived semantic index that can always be fully rebuilt from SQLite.
- The **Web Dashboard** interacts strictly through the HTTP REST API and never mutates SQLite or ChromaDB directly.

---

## 🚀 Quick Start: Running Backend & Frontend

### Prerequisites

- **Python 3.11+**
- **Node.js 18+ & npm**

### 1. Environment Setup

From the repository root (`d:\proj\Hackathon\RECALL`):

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# Install dependencies (core, MCP adapter, and semantic index):
pip install -e "core[mcp,semantic]"
```

---

### 2. Run the Backend API

The backend provides the HTTP REST API for the frontend dashboard and external integrations.

* **Directory:** Root repository directory (`RECALL`)
* **Terminal Commands:**

```powershell
# In Windows PowerShell (or your activated terminal):
cd d:\proj\Hackathon\RECALL
python -m core.recall_core.api
```

*(Alternative with hot-reload or custom host/port):*
```powershell
uvicorn core.recall_core.api:app --host 0.0.0.0 --port 8080 --reload
```
or using the installed CLI entry point:
```powershell
recall-api
```

* **Default URL:** `http://localhost:8080`
* **Health Check:** `http://localhost:8080/health`

---

### 3. Run the Frontend Dashboard

The frontend is a modern ChatGPT-style management interface built with **React**, **TypeScript**, and **Tailwind CSS**. It allows developers to inspect memories, manage custom instructions, review conflicts, and simulate context queries.

* **Directory:** `frontend` directory (`d:\proj\Hackathon\RECALL\frontend`)
* **Terminal Commands:**

```powershell
cd d:\proj\Hackathon\RECALL\frontend

# Install dependencies (first time only):
npm install

# Start Vite development server:
npm run dev
```

* **Default URL:** `http://localhost:5173`
* **API Proxy:** The Vite development server automatically proxies `/api` calls to `http://localhost:8080`.

---

## 🔌 Configuring RECALL MCP in Agent-Integrated IDEs

RECALL includes a standard **Model Context Protocol (MCP)** server (`recall_mcp.server`) operating over `stdio`. It exposes 9 structured tools to your AI agent:

| Tool | Purpose |
| --- | --- |
| `recall_search` | Search memories across project scope with semantic/keyword matching |
| `recall_get_context` | Assemble active project memories and matching custom instructions |
| `recall_save_memory` | Save a new memory with canonical SQLite persistence |
| `recall_update_context` | Persist an explicit context update for a project or global scope |
| `recall_compact` | Summarize older memories above the active cap while preserving lineage |
| `recall_list_custom_instructions` | List custom instructions filtered by scope, project, or status |
| `recall_create_custom_instruction` | Create user instructions (global or project scoped) |
| `recall_update_custom_instruction` | Update instruction content or status |
| `recall_delete_custom_instruction` | Soft-delete / deactivate a custom instruction |

---

### A. Google Antigravity

To register RECALL in **Google Antigravity**:

1. Open your workspace customization or global settings:
   - Workspace level: `.agents/mcp_config.json` (inside your project root)
   - Or Global level: `<GlobalCustomizationsRoot>/mcp_config.json`
2. Add the `recall` server configuration:

```json
{
  "mcpServers": {
    "recall": {
      "command": "python",
      "args": ["-m", "recall_mcp.server"],
      "cwd": "d:/proj/Hackathon/RECALL"
    }
  }
}
```

> [!TIP]
> If using a virtual environment, set `"command"` to the absolute path of Python in your `.venv` (e.g., `d:/proj/Hackathon/RECALL/.venv/Scripts/python.exe`).

---

### B. Cursor

To configure in **Cursor**:

**Method 1: Via Cursor Settings UI**
1. Open **Cursor Settings** -> **Features** -> **MCP**.
2. Click **+ Add New MCP Server**.
3. Fill in the details:
   - **Name:** `recall`
   - **Type:** `command`
   - **Command:** `python -m recall_mcp.server` (or `.venv/Scripts/python.exe -m recall_mcp.server`)
   - **Working Directory:** `d:/proj/Hackathon/RECALL`

**Method 2: Via `~/.cursor/mcp.json` or Workspace `.cursor/mcp.json`**
```json
{
  "mcpServers": {
    "recall": {
      "command": "python",
      "args": ["-m", "recall_mcp.server"],
      "cwd": "d:/proj/Hackathon/RECALL"
    }
  }
}
```

---

### C. OpenCode

In your workspace's `.opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "recall": {
      "type": "local",
      "command": ["python", "-m", "recall_mcp.server"],
      "cwd": "d:/proj/Hackathon/RECALL",
      "enabled": true
    }
  }
}
```

---

### D. Claude Desktop / VS Code (Cline / Roo-Code)

In `claude_desktop_config.json` (or your extension's MCP configuration):

```json
{
  "mcpServers": {
    "recall": {
      "command": "python",
      "args": ["-m", "recall_mcp.server"],
      "cwd": "d:/proj/Hackathon/RECALL"
    }
  }
}
```

---

## 🧪 Testing and Verification

To verify your environment and run automated test suites:

```bash
# Run core unit and integration tests:
python -m pytest core/tests -q

# Run full repository test suite (contracts, database, intelligence, MCP):
pytest -q
```

---

## 📚 Project Documentation

For in-depth specifications and guidelines:
- [Problem Statement](file:///d:/proj/Hackathon/RECALL/docs/PROBLEM_STATEMENT.md)
- [Product Requirements Document (PRD)](file:///d:/proj/Hackathon/RECALL/docs/PRD.md)
- [Architecture Specifications](file:///d:/proj/Hackathon/RECALL/docs/ARCHITECTURE.md)
- [MCP Adapter Documentation](file:///d:/proj/Hackathon/RECALL/docs/modules/MCP.md)
- [Team Workflow & Contributing](file:///d:/proj/Hackathon/RECALL/docs/TEAM_WORKFLOW.md)
