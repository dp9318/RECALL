# RECALL — Module Ownership and Boundaries

This document defines responsibilities by work stream, not by person.

## Frontend / Dashboard

### Owns

- React application;
- Tailwind CSS styling;
- chat-like dashboard UI;
- memory explorer UI;
- conflict center UI;
- custom instruction UI;
- project/session navigation;
- API client and presentation state.

### Does Not Own

- SQLite schema;
- ChromaDB access;
- memory business rules;
- conflict arbitration;
- direct MCP internals.

## Database / Persistence

### Owns

- SQLite schema and migrations;
- repository implementations;
- canonical persistence;
- lineage storage;
- custom-instruction persistence;
- ChromaDB indexing adapter;
- rebuild/synchronization utilities.

### Does Not Own

- UI behavior;
- conflict policy;
- dashboard state management;
- OpenCode command semantics.

## Core Memory Manager

### Owns

- application orchestration;
- memory lifecycle;
- update/compaction flows;
- custom instruction service orchestration;
- context assembly;
- service-level contracts;
- MCP/API delegation into core services.

### Does Not Own

- raw SQL implementation;
- React implementation;
- model-specific reasoning prompt internals.

## Retrieval / Conflict Intelligence

### Owns

- retrieval strategies;
- ranking;
- conflict detection;
- deterministic conflict rules;
- candidate packaging;
- local LLM and cloud-overflow resolver adapters;
- resolver output validation;
- abstention behavior.

### Does Not Own

- canonical persistence;
- UI;
- overall command routing.

## Integration / Architecture

### Owns

- cross-module contract review;
- architecture documentation;
- integration branch coordination;
- API/MCP end-to-end wiring;
- CI and final integration validation;
- ADR approval flow.

## Shared Rule

No module may bypass another module's canonical boundary simply because direct access is faster.
