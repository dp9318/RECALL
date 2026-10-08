# RECALL — Repository Layout Plan

The implementation may evolve, but the intended module boundaries are:

```text
RECALL/
├── .opencode/
│   ├── agents/
│   └── commands/
├── core/                # central memory manager and application services
├── database/            # SQLite + ChromaDB adapters
├── intelligence/        # retrieval, ranking, conflict logic, LLM adapter
├── api/                 # HTTP/JSON API adapters
├── mcp/                 # OpenCode/MCP adapter
├── frontend/            # React + Tailwind dashboard
├── contracts/           # shared DTOs/interfaces/schemas
├── tests/
├── docs/
└── AGENTS.md
```

Directory boundaries are more important than the exact package names. Do not create cross-cutting modules that bypass the documented contracts simply to reduce file count.
