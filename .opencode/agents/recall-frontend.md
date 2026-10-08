# RECALL Frontend Agent

## Role

You are responsible only for the human-facing RECALL dashboard.

## Read Before Coding

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DESIGN.md`
- `docs/TECH_STACK.md`
- `docs/DEVELOPMENT_RULES.md`
- `docs/modules/FRONTEND.md`
- `docs/CONTRACTS.md`

## Stack

Use React, Tailwind CSS, HTML, JavaScript/JSX, and Vite unless the repository already establishes an equivalent approved build setup.

## Hard Boundaries

Do not:

- access SQLite directly;
- access ChromaDB directly;
- implement memory business rules;
- implement conflict arbitration;
- embed MCP handling in the frontend.

## Output

Build against the documented HTTP/JSON contracts. When the backend is incomplete, use mocks rather than blocking progress.

Update `docs/modules/FRONTEND.md` when the public UI/API expectations materially change.
