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

The dashboard should be able to consume domain capabilities through a stable HTTP/JSON interface. Suggested endpoints:

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

Exact route names may evolve; the domain capability must remain stable.

## MCP Contract

The MCP layer should expose equivalent core capabilities needed by OpenCode. MCP handlers should remain thin adapters over core services.
