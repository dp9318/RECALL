# RECALL — Development Rules

## 1. Architecture First

The following are locked unless explicitly changed and documented:

- OpenCode is the agent host.
- Python MCP server is the integration layer.
- SQLite is canonical source of truth.
- ChromaDB is the derived semantic index.
- User custom instructions are a separate canonical domain in SQLite.
- A local 1B–3B LLM may arbitrate unresolved memory conflicts but is never authoritative.
- RECALL core is not dashboard-dependent; a web dashboard is a required human client, not the core engine.

## 2. Separation of Concerns

Keep these concerns independent:

```text
MCP / command transport
        ↓
application / memory services
        ├── instruction service
        ├── retrieval service
        └── conflict resolver
        ↓
repositories / storage adapters
        ├── SQLite
        └── ChromaDB
```

Do not place business rules directly inside MCP handlers when they belong in domain services.

## 3. Database Rules

### SQLite

- Every important persistent fact must have a canonical representation here.
- User custom instructions must have canonical relational records here.
- Prefer explicit relational structures for relationships and lineage.
- Use transactions for logically atomic operations.
- Make schema changes through controlled migrations or equivalent versioned mechanisms.

### ChromaDB

- Treat it as derived state.
- Store stable references back to canonical memory/instruction IDs where applicable.
- Do not make application correctness depend on an unrecoverable vector-only record.

## 4. Custom Instruction Rules

- `/recall custom-instructions` must support create, list/show, update, and delete.
- User-authored instructions must never be silently overwritten by automatic memory extraction or the conflict LLM.
- Prefer versioning or audit metadata for updates when practical.
- Deletion must change canonical SQLite state first; any index cleanup is a derived follow-up.
- Support at least global personal and project scopes.
- Load active instructions directly from SQLite for correctness.

## 5. Lineage Rules

Whenever a memory is summarized, compressed, merged, or otherwise derived:

- create a stable derived-memory identity;
- record its parent/source relationship;
- preserve enough metadata to understand its origin;
- never overwrite the only copy of the underlying evidence merely to save space.

## 6. Retrieval Rules

Retrieval must be:

- project-aware;
- relevance-oriented;
- bounded in result size;
- provenance-aware;
- checked for active/superseded conflicts.

Do not return an entire historical transcript when a few memories answer the query.

## 7. Conflict Resolution Rules

The conflict path must be staged:

1. validate candidate identity and scope;
2. prefer explicit user updates/supersession;
3. prefer current valid records over stale records;
4. invoke the local 1B–3B model only when ambiguity remains;
5. validate the model's structured output;
6. allow an unresolved/abstain result.

The local LLM must never directly mutate SQLite or delete canonical evidence.

## 8. Error Handling

Never silently convert a persistence/indexing/resolution failure into success.

A partial operation must be distinguishable from a fully successful operation.

Use typed/domain-level errors where practical so MCP can expose actionable failures.

## 9. Dashboard Rules

- Treat the dashboard as a client of RECALL, not as a parallel memory engine.
- Never access SQLite or ChromaDB directly from the dashboard.
- Never duplicate retrieval, memory extraction, custom-instruction policy, or conflict arbitration in frontend code.
- Use the RECALL application/domain API for all reads and writes.
- Show provenance and status where the domain API provides it; do not invent source attribution.
- Keep the dashboard ChatGPT-like in interaction style but focused on RECALL memory operations, not general-purpose chat behavior.
- Keep the dashboard optional to the core runtime: RECALL must remain usable through OpenCode/MCP without the dashboard.

## 10. Testing Rules

Every meaningful feature should have tests at the appropriate level.

Minimum regression areas:

- SQLite persistence;
- memory lineage;
- retrieval;
- ChromaDB synchronization;
- rebuild;
- MCP schemas/contracts;
- custom-instruction CRUD and scope isolation;
- conflict detection;
- deterministic resolution precedence;
- resolver output validation and abstention;
- failure recovery.

Tests should prove behavior rather than implementation trivia.

## 11. Code Quality

Prefer:

- small focused modules;
- explicit names;
- predictable data flow;
- typed boundaries;
- simple dependency direction;
- minimal global state.

Avoid premature abstractions, speculative plugin systems, and framework-heavy architecture.

## 12. Configuration and Secrets

Never commit secrets, API keys, personal credentials, or machine-specific paths.

Use environment/configuration mechanisms and document required variables.

Do not log custom instruction content unnecessarily if it may contain sensitive personal preferences or data.

## 13. Logging

Logs should help diagnose:

- session capture;
- memory creation;
- indexing;
- retrieval;
- conflict detection/resolution;
- custom instruction create/update/delete;
- rebuilds;
- failures.

Do not log sensitive content unnecessarily.

## 14. Git Discipline

Prefer focused commits with clear intent.

A change that alters architecture should update the relevant documentation in the same change.

Do not commit generated databases, local caches, embeddings, or machine-specific runtime artifacts unless explicitly required.

## 15. Dependency Discipline

Add a dependency only when it solves a concrete problem.

The local LLM runtime must be justified by the conflict-resolution requirement and kept behind a narrow adapter.

Before introducing a second persistence system, ask whether the requirement can be satisfied by SQLite + ChromaDB under the existing architecture.

## 16. Change Protocol

For an architectural change:

1. state the problem;
2. document the proposed decision;
3. update the relevant architecture/PRD documents;
4. implement the change;
5. add or update tests;
6. verify rebuild/recovery implications;
7. verify custom-instruction and conflict-precedence implications.

## 17. Definition of Done

A RECALL feature is done when:

- implementation exists;
- tests cover the important behavior;
- error paths are considered;
- canonical data remains recoverable;
- documentation matches the implementation;
- no locked architecture decision was accidentally violated;
- user-authored instructions remain under explicit user control.

## 18. Required `/recall custom-instructions` Capability

The command is not optional polish. It is a functional requirement.

At minimum the implementation must make it possible for the user to:

```text
/recall custom-instructions
    ↓
see current instructions
    ↓
create / update / delete
```

The command may use sub-prompts, menus, identifiers, or arguments internally, but the four lifecycle operations must be available and testable.
