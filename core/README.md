# RECALL Core Memory Manager

The Core Memory Manager is the central orchestration layer of the RECALL persistent memory engine.

## Structure

```
core/
├── core/                 # Python package (core implementation)
│   ├── __init__.py
│   ├── exceptions.py
│   ├── instruction_service.py
│   ├── context_assembly.py
│   └── memory_manager.py
├── contracts/            # Shared DTOs and interfaces
├── database/             # Repository interfaces
├── intelligence/         # Retrieval and conflict resolution interfaces
├── tests/                # Unit tests
├── pyproject.toml
└── README.md
```

## Installation

```bash
pip install -e .[test]
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Core Components

- **MemoryManager**: Central orchestration for memory operations, retrieval, conflict resolution, and context assembly
- **CustomInstructionService**: CRUD operations for user-authored custom instructions with scope filtering
- **ContextAssemblyService**: Assembles context from projects, sessions, memories, instructions, and conflict resolutions
- **Contracts**: Shared DTOs for memory, instructions, projects, conflicts, and retrieval
- **Database Interfaces**: Repository interfaces for projects, sessions, memories, instructions, and semantic index
- **Intelligence Interfaces**: Retrieval service, conflict detection, and conflict resolution service interfaces

## Key Features

- Memory lifecycle management (create, read, update, delete, search)
- Custom instruction management with global/project scope
- Retrieval delegation (structured + semantic)
- Conflict resolution delegation (deterministic rules + LLM arbitration)
- Context assembly with precedence enforcement (explicit instructions > inferred memories)
- `/recall compact` - context compaction preserving lineage
- `/recall update-context` - explicit durable context updates
- Statistics and monitoring