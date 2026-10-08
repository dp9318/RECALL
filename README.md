# RECALL

RECALL is a persistent memory engine for AI coding agents.

It provides two client surfaces over one core:

- **OpenCode integration** through MCP and `/recall` commands.
- **Web dashboard** built with React and Tailwind CSS for humans to inspect and manage memory.

Core storage and intelligence:

- **SQLite** — canonical source of truth.
- **ChromaDB** — derived semantic index.
- **Local 1B–3B LLM** — bounded arbitration for ambiguous memory conflicts.

The project is organized as a modular monorepo so multiple developers/agents can implement independent modules through Git branches and shared contracts.

Read `docs/ARCHITECTURE.md`, `docs/TEAM_WORKFLOW.md`, and `docs/MODULE_OWNERSHIP.md` before contributing.
