# RECALL — Cross-Module Contracts

The project should prefer explicit contracts between modules so multiple contributors can work independently.

## Memory Contract

A memory should expose at minimum:

- stable `memory_id`;
- project/scope;
- memory type;
- content/claim;
- status;
- timestamps;
- provenance/source reference;
- lineage/supersession metadata.

## Custom Instruction Contract

A custom instruction should expose at minimum:

- stable `instruction_id`;
- scope (`global` or `project`);
- optional `project_id`;
- instruction content;
- active status;
- created/updated timestamps;
- version/audit metadata where supported.

## Conflict Result Contract

The conflict resolver should return a structured result containing enough information to distinguish:

- resolved;
- partially resolved;
- unresolved/abstained;
- preferred candidates;
- superseded/conflicting candidates;
- confidence where available;
- evidence identifiers;
- resolution reason;
- whether a model was used and the selected provider when available.

## API Contract

The dashboard consumes RECALL capabilities through a stable HTTP/JSON interface. The implemented frontend-facing contract is:

```text
GET    /health
GET    /projects
GET    /memories
GET    /memories/{id}
POST   /memories
PATCH  /memories/{id}
DELETE /memories/{id}
POST   /context/query
POST   /context/compact
GET    /custom-instructions
POST   /custom-instructions
PATCH  /custom-instructions/{id}
DELETE /custom-instructions/{id}
GET    /conflicts
GET    /sessions
GET    /stats
```

### Frontend-facing HTTP API behavior

- The API is served by the RECALL core application and is not a separate business-logic implementation.
- Requests are validated at the HTTP boundary before Core operations are invoked.
- All write operations persist canonical state in SQLite and optionally update the derived ChromaDB index as best-effort metadata synchronization.
- Route responses return JSON payloads shaped to the dashboard TypeScript contracts under `frontend/src/types`.
- Error responses use standard HTTP status codes with a JSON detail message.
- Project and session scoping is validated against canonical repositories before execution.
- Compaction preserves lineage and is rejected when lineage preservation is disabled or invalid.

The route names and field shapes above are the contract used by the dashboard client. Any change to these public names or schemas requires deliberate contract updates and corresponding frontend compatibility checks.

## MCP Contract

The MCP layer exposes the OpenCode operations using thin adapters over Core.
Its current public tools are:

- `recall_search`, `recall_get_context`, and `recall_save_memory`;
- `recall_update_context` and `recall_compact`;
- `recall_list_custom_instructions`, `recall_create_custom_instruction`,
  `recall_update_custom_instruction`, and `recall_delete_custom_instruction`.

Inputs map to existing Core request models, and outputs serialize existing
public DTOs/results. MCP handlers must not implement persistence, retrieval,
context assembly, compaction, or instruction business logic. Exact input
properties, defaults, scope rules, output shapes, and errors are documented in
[`modules/MCP.md`](./modules/MCP.md). Changes to these public names or shapes
require deliberate contract updates.
