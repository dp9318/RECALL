# RECALL — Core Memory Manager Module Contract

## Goal

Implement the central application behavior of RECALL and orchestrate persistence, retrieval, conflict resolution, instructions, and context assembly.

## Responsibilities

- capture durable context;
- update project context;
- compact eligible context;
- retrieve memory candidates;
- invoke conflict services;
- load active custom instructions;
- assemble prioritized context;
- expose service-level operations to MCP and HTTP adapters.

## Precedence

The core must enforce:

```text
Explicit user instruction
    > explicit user update/supersession
    > current canonical memory
    > historical memory
    > unresolved/arbitrated historical candidate
```

## Custom Instructions

Provide a domain service for:

- list;
- create;
- update;
- delete/deactivate;
- scope filtering;
- active-state lookup.

## Context Assembly

The assembled result should carry enough provenance for clients to explain where important context came from.

## Boundary

The core depends on repository and intelligence contracts. It does not depend on React and should not contain direct UI logic.
