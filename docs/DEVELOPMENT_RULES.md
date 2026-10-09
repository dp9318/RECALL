# RECALL — Development Rules

## 1. Architecture First

Do not silently change the locked architecture. Architectural changes require an ADR and updates to the affected docs.

## 2. Separation of Concerns

```text
Client adapters
    ↓
Application/domain services
    ↓
Repositories and adapters
    ↓
SQLite / ChromaDB / local model runtime
```

Keep business logic out of HTTP routes, MCP handlers, and React components.

## 3. SQLite Rules

- Canonical truth lives in SQLite.
- Use explicit schema and migrations.
- Use transactions for atomic multi-step changes.
- Preserve lineage and provenance.

## 4. ChromaDB Rules

- Derived only.
- Store canonical IDs in metadata.
- Never rely on vector-only data for correctness.
- Support rebuild/synchronization.

## 5. Custom Instructions

- Must support list/view, create, update, delete.
- Must support global and project scope.
- Must be canonical in SQLite.
- Must never be silently overwritten by automatic memory extraction.
- Deletion/inactivation is canonical first; vector cleanup is derived follow-up.

## 6. Conflict Rules

1. detect candidate conflicts;
2. validate scope/status;
3. prefer explicit user updates;
4. prefer current valid state;
5. use local LLM only for residual ambiguity; use an explicitly configured cloud API only if the local context window is exceeded;
6. validate output;
7. permit abstention.

## 7. Frontend Rules

- No direct database access.
- No duplicate memory policy.
- No conflict-model calls directly from React.
- All domain actions go through API contracts.
- Handle loading, empty, error, and partial states explicitly.

## 8. Testing

Meaningful changes need tests at the appropriate layer. Regression priorities:

- persistence;
- lineage;
- retrieval;
- index rebuild;
- custom-instruction CRUD and scope;
- precedence;
- conflict resolution and abstention;
- MCP/API contracts;
- dashboard core flows.

## 9. Logging

Log lifecycle and failure information without unnecessarily exposing private/custom instruction content.

## 10. Git

- No direct work on protected `main`.
- Use focused feature branches.
- Open pull requests against `integration/recall`.
- Keep commits small and explain intent.
- Do not commit local databases, caches, embeddings, or secrets.

## 11. Documentation

Module behavior changes must update the appropriate module doc. Architecture changes must update the architecture docs and add an ADR.

## 12. Definition of Done

A feature is complete only when implementation, tests, docs, and integration behavior agree.
