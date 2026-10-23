# RECALL — Technical Documentation Index

Welcome to the RECALL developer documentation. This directory contains the authoritative technical specifications, architectural contracts, operational guides, and decision records for the RECALL persistent memory engine.

---

## 🗺️ Documentation Directory Map

```text
docs/
├── README.md                     # This document — navigation index & reading order
├── PROBLEM_STATEMENT.md          # Core mission, agent memory deficit, and boundaries
├── PRD.md                        # Product Requirements Document & functional specs
├── ARCHITECTURE.md               # System architecture, layering, and failure modes
├── ARCHITECTURE_REFERENCE.md     # Textual reference clarifying the visual architecture
├── DESIGN.md                     # Detailed engine design & algorithmic flows
├── CONTRACTS.md                  # Strict cross-module contracts (API, MCP, DTOs)
├── DEVELOPMENT_RULES.md          # Absolute system invariants & architectural rules
├── DEVELOPER_GUIDE.md            # Setup, execution, testing, debugging, and commands
├── PACKAGING_AND_DISTRIBUTION.md # Packaging state, data paths, backup/restore, roadmap
├── RELEASE_PLAN.md               # 2.1.1 release targets, SemVer rationale, verification
├── REPOSITORY_LAYOUT.md          # Monorepo directory structure & package boundaries
├── MODULE_OWNERSHIP.md           # Module ownership boundaries for parallel work
├── TECH_STACK.md                 # Language, framework, database, and library matrix
├── TEAM_WORKFLOW.md              # Git branching, review protocol, and PR flow
├── adr/                          # Architectural Decision Records
│   ├── README.md                 # ADR index and status overview
│   ├── 0001-conflict-arbitration-cloud-overflow.md
│   ├── 0002-package-flattening-and-modular-api.md
│   └── 0003-canonical-package-and-test-consolidation.md
└── modules/                      # Subsystem-specific deep-dive specifications
    ├── API.md                    # Modular FastAPI REST service & route contracts
    ├── CORE_MEMORY.md            # Domain orchestration facade & lifecycle contracts
    ├── DATABASE.md               # SQLite canonical persistence & ChromaDB vector index
    ├── FRONTEND.md               # React 19 + Tailwind CSS v4 dashboard client
    ├── INTELLIGENCE.md           # Hybrid retrieval, embeddings & conflict arbitration
    └── MCP.md                    # FastMCP stdio server & OpenCode agent tools
```

---

## 📖 Recommended Reading Order

### For New Developers & Coding Agents
1. [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) — Why RECALL exists and what it is *not*.
2. [PRD.md](PRD.md) — Functional requirements, capabilities, and non-goals.
3. [ARCHITECTURE.md](ARCHITECTURE.md) — The locked dual-surface architecture and storage boundaries.
4. [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) — Mandatory invariants (SQLite canonical truth, encapsulation).
5. [CONTRACTS.md](CONTRACTS.md) — Public interfaces between core, database, API, and MCP.
6. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — Local installation, running services, and test commands.

### For Subsystem Contributors
- **Agent Integration Engineers:** Read [modules/MCP.md](modules/MCP.md) and [CONTRACTS.md](CONTRACTS.md).
- **Backend & Core Engineers:** Read [modules/CORE_MEMORY.md](modules/CORE_MEMORY.md), [modules/DATABASE.md](modules/DATABASE.md), and [modules/INTELLIGENCE.md](modules/INTELLIGENCE.md).
- **REST API & Web Engineers:** Read [modules/API.md](modules/API.md) and [modules/FRONTEND.md](modules/FRONTEND.md).
- **Release & Ops Engineers:** Read [RELEASE_PLAN.md](RELEASE_PLAN.md) and [PACKAGING_AND_DISTRIBUTION.md](PACKAGING_AND_DISTRIBUTION.md).

---

## 🏛️ Locked Architecture Summary

RECALL operates on a strict **dual-surface, single-core** model:

```text
                          CLIENT SURFACES
        ┌────────────────────────┬─────────────────────────┐
        │                        │                         │
        │ OpenCode + MCP         │ Web Dashboard           │
        │ /recall commands       │ React + Tailwind CSS    │
        │ stdio JSON-RPC         │ HTTP/JSON REST          │
        └──────────────┬─────────┴──────────────┬──────────┘
                       │                        │
                       └────────────┬───────────┘
                                    ▼
                         ┌─────────────────────────┐
                         │       RECALL CORE       │
                         │      (recall_core)      │
                         │                         │
                         │ MemoryManager facade    │
                         │ Retrieval orchestration │
                         │ Custom instructions     │
                         │ Context assembly        │
                         │ Conflict detection      │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
              ┌──────────┐      ┌──────────┐       ┌────────────┐
              │ SQLite   │─────▶│ ChromaDB │       │ Local      │
              │ canonical│      │ derived  │       │ LLM 1B–3B  │
              │ truth    │      │ index    │       │ arbitration│
              └──────────┘      └──────────┘       └────────────┘
```

### Core Invariants:
1. **SQLite Canonical Truth:** SQLite (`~/.recall/recall.sqlite3`) is the sole authoritative store.
2. **Derived Vector State:** ChromaDB is derived and 100% rebuildable via `MemoryManager.rebuild_semantic_index()`.
3. **Strict Encapsulation:** Client surfaces interact strictly via `MemoryManager`. Direct access to `_uow` or repositories from external packages is forbidden.
4. **Instruction Precedence:** User-authored custom instructions outrank historical memories and LLM decisions.
5. **Non-Hallucination:** Ambiguous contradictions abstain or report `unresolved` rather than fabricating certainty.
