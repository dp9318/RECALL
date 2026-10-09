# RECALL — Technology Stack

## Core / Backend

- Python
- MCP server/tooling for OpenCode integration
- HTTP/JSON API for the dashboard; FastAPI is the preferred implementation
- SQLite for canonical persistence
- ChromaDB for derived semantic retrieval
- Sentence Transformers with `sentence-transformers/all-MiniLM-L6-v2` as the
  default local embedding provider/model (CPU by default)
- local 1B–3B LLM runtime behind a narrow resolver adapter (Ollama by default; runtime/model configurable)
- optional native API adapters for OpenAI, Anthropic, and Google Gemini, used only on local context-window overflow when explicitly configured

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

### Conflict arbitration models

The local LLM is used for bounded conflict arbitration when deterministic logic cannot safely resolve the candidate set. Cloud services are an opt-in overflow fallback, not a general fallback for local service errors. Conflict evidence is sent to a cloud API only when the provider, model, and API key are configured and local arbitration reports context-window overflow.

## Dependency Discipline

Prefer small, focused dependencies. Do not add another primary database or another memory index unless a documented architecture change is approved.
