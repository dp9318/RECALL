# RECALL Intelligence Agent

## Role

You are responsible for retrieval, ranking, conflict detection, deterministic conflict resolution, and the local 1B–3B arbitration adapter.

## Read Before Coding

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_RULES.md`
- `docs/CONTRACTS.md`
- `docs/modules/INTELLIGENCE.md`

## Hard Boundaries

The resolver is not a source of truth. Never allow the model to directly write/delete canonical records or override explicit custom instructions.

## Resolution Strategy

Deterministic rules first. Local model only for bounded ambiguity. Validate structured output. Support abstention.

Keep the model behind a narrow interface so the runtime/model can change without affecting the core.
