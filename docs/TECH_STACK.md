# RECALL — Technology Stack

## Core / Backend

- Python
- MCP server/tooling for OpenCode integration
- HTTP/JSON API for the dashboard; FastAPI is the preferred implementation
- SQLite for canonical persistence
- ChromaDB for derived semantic retrieval
- local 1B–3B LLM runtime behind a narrow resolver adapter (runtime/model configurable)

## Frontend

- HTML
- React
- Tailwind CSS
- JavaScript/JSX
- Vite is the preferred frontend build/dev tool

The frontend must communicate with the backend through the RECALL HTTP/JSON API.

## Testing

- Python unit/integration tests for core, repositories, APIs, MCP, and resolver
- React component tests for key dashboard behavior
- API contract tests for frontend/backend boundaries

## Tooling

- Git
- GitHub
- OpenCode

## Storage Model

### SQLite

Canonical records and relationships.

### ChromaDB

Derived embeddings/index only. It may be recreated from SQLite.

### Local LLM

Only used for bounded conflict arbitration when deterministic logic cannot safely resolve the candidate set.

## Dependency Discipline

Prefer small, focused dependencies. Do not add another primary database or another memory index unless a documented architecture change is approved.
