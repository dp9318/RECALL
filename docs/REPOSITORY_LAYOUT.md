# RECALL — Repository Layout

The current verified repository structure and module boundaries:

```text
RECALL/
├── .agents/                 # Antigravity IDE workspace MCP configuration
├── .opencode/               # Agent configuration and slash commands
├── recall_core/             # Central domain orchestration facade (MemoryManager)
├── api/                     # Modular FastAPI HTTP/JSON REST service
│   ├── app.py               # Application factory & CORS middleware
│   ├── dependencies.py      # Dependency injection providers
│   ├── serializers.py       # Entity and lineage serializers
│   ├── main.py              # Uvicorn entry point
│   └── routes/              # Modular endpoint routers
├── recall_mcp/              # FastMCP stdio server (9 agent tools)
├── database/                # SQLite canonical persistence & ChromaDB semantic index
│   ├── connection.py        # WAL thread-safe connection manager
│   ├── repositories/        # UnitOfWork and entity repositories
│   └── migrations/          # Schema migrations engine
├── intelligence/            # Lexical/semantic retrieval and conflict arbitration
├── contracts/               # Shared dataclasses, enums, and schemas
├── frontend/                # React 19 + Tailwind CSS v4 web dashboard
├── tests/                   # Consolidated test suite (unit, integration, contracts, repositories)
├── scripts/                 # Diagnostic, benchmark, and smoke test utilities
├── readme_src/              # README diagrams and UI screenshots
├── docs/                    # Architecture, ADRs, and module contracts
│   ├── adr/                 # Architecture Decision Records (ADR 0001, ADR 0002, ADR 0003)
│   ├── archive/             # Historical sprint instructions
│   └── modules/             # Module specifications (API, CORE, DATABASE, etc.)
├── pyproject.toml           # Authoritative PEP 621 packaging & console scripts
├── pytest.ini               # Pytest configuration
├── .env.example             # Sanitized environment configuration template
├── AGENT.md                 # Intentional compatibility pointer to AGENTS.md
├── AGENTS.md                # Authoritative OpenCode project rules & boundaries
└── README.md                # Project documentation and quickstart
```

Directory boundaries define encapsulation. Client surfaces (`recall_mcp`, `api`, `frontend`) must interact with canonical domain storage exclusively through the `MemoryManager` facade and must never bypass documented contracts.
