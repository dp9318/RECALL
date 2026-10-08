# RECALL_V2 — OpenCode Project Instructions

## Mission

RECALL_V2 is a persistent memory engine for AI coding agents. It helps an agent retain useful project context across sessions, retrieve relevant history, manage explicit user-authored custom instructions, and safely resolve conflicting historical context.

RECALL is **not** the coding agent itself. OpenCode is the primary agent host/integration target.

RECALL exposes two first-class client surfaces:

1. **OpenCode integration** — MCP + `/recall ...` command surface for agent-driven use.
2. **Web dashboard** — a ChatGPT-like human-facing client for inspecting memory, asking RECALL questions, managing custom instructions, and reviewing conflicts.

Both clients use the same RECALL core. Neither client owns canonical memory.

## Read Before Coding

For any non-trivial change, read the relevant documents in this order:

1. `docs/PROBLEM_STATEMENT.md`
2. `docs/PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DESIGN.md`
5. `docs/TECH_STACK.md`
6. `docs/DEVELOPMENT_RULES.md`
7. `docs/ARCHITECTURE_REFERENCE.md` when the visual architecture or dashboard boundary is relevant

The image `docs/architecture-overview.png` is a visual reference. The written architecture is authoritative where the image is incomplete or ambiguous.

## Locked Architecture

```text
                        ┌───────────────────────────┐
                        │     CLIENT INTERFACES     │
                        │                           │
                        │ OpenCode + MCP + /recall │
                        │ Web Dashboard / Chat UI   │
                        └────────────┬──────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                        MCP               HTTP/JSON
                          │                     │
                          └──────────┬──────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │      RECALL CORE        │
                        │        Python           │
                        │                         │
                        │ commands / API          │
                        │ memory lifecycle        │
                        │ retrieval               │
                        │ instruction management  │
                        │ conflict resolution     │
                        │ context assembly        │
                        └────────────┬────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
           ┌──────────┐       ┌────────────┐      ┌─────────────┐
           │  SQLite  │       │  ChromaDB  │      │ Local 1B–3B │
           │ canonical│──────▶│ semantic / │      │ conflict    │
           │ source   │       │ derived idx│      │ arbitration │
           └──────────┘       └────────────┘      └─────────────┘
```

### Non-negotiable rules

- SQLite is the **canonical source of truth** for sessions, events/messages, memories, lineage, and custom instructions.
- ChromaDB is a **derived semantic index**. It must be rebuildable from SQLite.
- The local 1B–3B model is a **bounded conflict-arbitration component**, not a database, not a memory source of truth, and not a policy authority.
- The local LLM cannot directly mutate canonical state.
- Explicit user custom instructions outrank inferred historical memory.
- Custom instructions are a separate canonical domain with explicit CRUD lifecycle.
- The dashboard must never write directly to SQLite or ChromaDB.
- The dashboard talks to the RECALL core through a domain/application API; do not duplicate memory business logic in the frontend.
- The OpenCode integration talks to RECALL through MCP and the `/recall` command surface.
- The core must not depend on the dashboard being present.
- Do not reintroduce the old Qt/QML/PySide6 desktop architecture into RECALL.
- Do not add another primary database.

## User-Facing RECALL Surface

The command family is conceptually:

```text
/recall compact
/recall update-context
/recall custom-instructions
/recall search <query>
/recall list
/recall delete <id>
/recall stats
```

The exact set may evolve, but `/recall custom-instructions` is mandatory and must support:

- list/view;
- create;
- update;
- delete.

Do not fabricate results if the corresponding RECALL tool/API is unavailable.

## Custom Instructions

Treat custom instructions as explicit user-owned state:

```text
create → persist in SQLite → version/update → apply during context assembly → delete/deactivate explicitly
```

Support at least:

- global/personal scope;
- project scope.

A stale ChromaDB vector must never keep a deleted or inactive instruction authoritative.

## Memory Lifecycle

```text
capture
  → canonical persist
  → derive/compress
  → semantic index
  → retrieve
  → detect conflicts
  → deterministic resolution
  → bounded LLM arbitration if needed
  → apply custom instructions
  → assemble context
  → return through MCP/API
```

Preserve parent/child lineage for derived memories.

## Conflict Priority

When context conflicts, prefer:

```text
Explicit user instruction
        ↓
Explicit user update / supersession
        ↓
Current valid canonical memory
        ↓
Older historical memory
        ↓
Local 1B–3B arbitration for residual ambiguity
        ↓
Unresolved / abstain
```

Never force an uncertain answer merely to avoid returning an unresolved state.

## Dashboard Rules

The dashboard is a **human control and inspection surface**, not a second memory engine.

Expected MVP areas:

- Chat / Ask RECALL
- Memory Explorer
- Conflict Center
- Custom Instructions
- Session / usage overview
- Project/context selector

The dashboard must be able to expose provenance and state where practical, especially:

- memory IDs;
- source/lineage;
- conflict status;
- custom instruction scope and status;
- whether a result came from canonical or derived data.

Keep it visually similar in interaction model to a ChatGPT-style client, but do not pretend it is a generic chatbot. The product identity is RECALL and the UI exists to control and inspect persistent memory.

## Development Discipline

Before changing a locked architecture decision, update the architecture documents first and obtain explicit approval.

For new features:

1. identify the domain capability;
2. add/modify a core service or API contract;
3. expose it to MCP and/or dashboard as required;
4. test canonical persistence and failure behavior;
5. verify that the dashboard/OpenCode client does not bypass the core.

For dashboard work, do not implement direct DB queries, ad-hoc memory rules, or LLM conflict logic in the frontend.

For memory work, prioritize correctness and provenance over retrieval recall at any cost.

For resolver work, use deterministic rules first and call the local model only on bounded ambiguous candidate sets.

## Verification

At minimum, new behavior should have focused tests for:

- persistence and retrieval;
- lineage;
- SQLite → ChromaDB rebuild;
- custom instruction CRUD and scope isolation;
- instruction precedence;
- conflict resolution and abstention;
- MCP contracts;
- dashboard API contracts and core integration.

Do not mark a feature complete based only on a successful happy-path demo.
