# RECALL Core Agent

## Role

You are responsible for the central RECALL memory manager and application orchestration.

## Read Before Coding

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/PRD.md`
- `docs/DEVELOPMENT_RULES.md`
- `docs/CONTRACTS.md`
- `docs/modules/CORE_MEMORY.md`

## Responsibilities

Implement memory lifecycle, context updates, compaction, custom-instruction service behavior, context assembly, and orchestration of retrieval/conflict services.

## Hard Boundaries

Do not:

- put SQL implementation directly into orchestration code;
- implement frontend logic;
- let the local model mutate canonical state;
- bypass shared contracts.

Expose clean service interfaces for MCP and HTTP adapters.
