# RECALL Core Memory Manager

The Core Memory Manager is the orchestration layer of RECALL, a persistent memory engine for AI coding agents.

## Repository layout

```text
RECALL/
├── contracts/             # Shared DTOs and service contracts
├── database/              # Persistence and semantic-index repository interfaces
├── intelligence/          # Retrieval and conflict-resolution services
├── core/
│   ├── recall_core/        # Memory manager and context orchestration
│   ├── tests/              # Core tests and fixtures
│   ├── pyproject.toml
│   └── README.md
└── docs/                   # Architecture and module ownership
```

The `contracts`, `database`, and `intelligence` packages intentionally live beside `core`; keep these boundaries stable so parallel integrations can depend on shared contracts.

## Installation

Run from the repository root:

```bash
python -m pip install -e "core[test,mcp]"
```

## Running tests

Run from the repository root:

```bash
python -m pytest core/tests -v
```

See [the MCP module setup guide](../docs/modules/MCP.md) for OpenCode configuration,
Core factory requirements, and current integration limitations.

## Core components

- **MemoryManager**: orchestrates memory operations, retrieval, conflict resolution, and context assembly.
- **CustomInstructionService**: manages global and project-scoped user instructions.
- **ContextAssemblyService**: assembles context from projects, sessions, memories, and retrieval.
- **Contracts**: shared data-transfer objects across core and integrations.
- **Database interfaces**: canonical persistence and derived semantic-index boundaries.
- **Intelligence services**: retrieval and conflict resolution, including optional bounded model arbitration.

## Key behaviors

- Memory lifecycle management and retrieval delegation.
- Global and project-scoped custom instructions.
- Explicit instructions and canonical state remain authoritative.
- Semantic index is derived and rebuildable; canonical persistence takes precedence.
- `/recall compact` preserves history and lineage.
- `/recall update-context` records explicit durable updates.
- Statistics and health reporting.
