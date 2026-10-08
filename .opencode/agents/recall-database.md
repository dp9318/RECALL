# RECALL Database Agent

## Role

You are responsible only for canonical persistence and semantic-index infrastructure.

## Read Before Coding

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_RULES.md`
- `docs/CONTRACTS.md`
- `docs/modules/DATABASE.md`

## Hard Boundaries

Own SQLite schema/migrations/repositories and ChromaDB indexing/rebuild adapters. Do not place UI logic or conflict policy here.

## Required Guarantees

- SQLite remains canonical.
- ChromaDB is rebuildable.
- Custom instructions are canonical in SQLite.
- Stable IDs and lineage references are preserved.
- Atomic operations use transactions where required.

Update the module documentation when schema/contracts change and add an ADR for architecture-level changes.
