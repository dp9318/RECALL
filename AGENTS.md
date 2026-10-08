# RECALL — Project Instructions for OpenCode

## Mission

RECALL is a persistent memory engine for AI coding agents. Its purpose is to preserve useful project context across sessions, retrieve relevant history, manage explicit user-authored custom instructions, detect and resolve conflicting historical context, and expose the resulting context through both an agent-facing OpenCode integration and a human-facing web dashboard.

RECALL is the memory system. It is not the coding agent itself, and it is not a general-purpose chatbot.

## Read First

Before non-trivial implementation, read:

1. `docs/PROBLEM_STATEMENT.md`
2. `docs/PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DESIGN.md`
5. `docs/TECH_STACK.md`
6. `docs/DEVELOPMENT_RULES.md`
7. `docs/TEAM_WORKFLOW.md`
8. the relevant module document in `docs/modules/`

If working from the architecture image, read `docs/ARCHITECTURE_REFERENCE.md`. The written documents are authoritative when the image is incomplete or ambiguous.

## Locked Architecture

```text
                          CLIENT SURFACES
        ┌────────────────────────┬─────────────────────────┐
        │                        │                         │
        │ OpenCode + MCP         │ Web Dashboard           │
        │ /recall commands       │ React + Tailwind CSS   │
        │                        │ HTTP/JSON              │
        └──────────────┬─────────┴──────────────┬──────────┘
                       │                        │
                       └────────────┬───────────┘
                                    ▼
                         ┌─────────────────────────┐
                         │       RECALL CORE       │
                         │        Python           │
                         │                         │
                         │ command/API adapters    │
                         │ memory lifecycle        │
                         │ retrieval               │
                         │ instructions            │
                         │ conflict handling       │
                         │ context assembly        │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
              ┌──────────┐      ┌──────────┐       ┌────────────┐
              │ SQLite   │─────▶│ ChromaDB │       │ Local      │
              │ canonical│     │ derived  │       │ LLM 1B–3B │
              │ truth     │     │ index    │       │ arbitration│
              └──────────┘      └──────────┘       └────────────┘
```

## Non-Negotiable Rules

- SQLite is the canonical source of truth for sessions, messages/events, memories, lineage, projects, and custom instructions.
- ChromaDB is derived semantic state. It must be rebuildable from SQLite.
- The local 1B–3B model is a bounded conflict-arbitration component. It is not canonical memory and cannot directly mutate canonical storage.
- Explicit user-authored custom instructions have higher authority than inferred historical memory.
- `/recall custom-instructions` must support view/list, create, update, and delete.
- Custom instructions must support at least global/personal scope and project scope.
- The dashboard must never read or write SQLite or ChromaDB directly.
- The OpenCode integration must use MCP and the `/recall` command family; it must not duplicate core memory logic.
- The dashboard is a client of RECALL, not a second memory engine.
- The RECALL core must remain usable without the dashboard.
- Do not introduce a second primary database.
- Do not reintroduce the previous Qt/QML/PySide6 desktop direction.
- Do not let the local LLM override explicit user instructions.
- When ambiguity remains, RECALL may return an unresolved result instead of fabricating certainty.

## Client Surfaces

### OpenCode

Use the `/recall` command family and MCP operations for agent-facing memory workflows. Typical operations include:

```text
/recall compact
/recall update-context
/recall custom-instructions
/recall search <query>
/recall list
/recall delete <id>
/recall stats
```

### Web Dashboard

The dashboard is a ChatGPT-style human control surface, implemented with React and Tailwind CSS. MVP areas:

- Chat / Ask RECALL
- Memory Explorer
- Conflict Center
- Custom Instructions
- Session / usage overview
- Project/context selector

It may present conversation-style responses, but RECALL itself remains a memory engine. General-purpose response generation is not the responsibility of the mandatory 1B–3B conflict model.

## Memory Authority

```text
Explicit user custom instruction
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

## Development Rule

Every module must be independently testable behind a clear contract. Keep implementation ownership separated by module directory. Shared contracts must be changed deliberately and documented when they change.

For architectural changes, update the relevant documentation and add an ADR under `docs/adr/` before or with implementation.
