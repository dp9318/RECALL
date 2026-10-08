# RECALL — Database and Persistence Module Contract

## Goal

Provide reliable canonical persistence and a rebuildable semantic index.

## SQLite Domains

At minimum model:

- projects;
- sessions;
- messages/events;
- memories;
- memory lineage/supersession;
- custom instructions;
- lifecycle/index metadata as needed.

## Requirements

- migrations/versioning;
- transactions for atomic changes;
- foreign-key relationships where appropriate;
- indexes for common lookups;
- stable identifiers;
- timestamps and status fields;
- provenance and lineage.

## Custom Instructions

Canonical fields should support:

- instruction ID;
- scope;
- project ID when scoped;
- content;
- active/deleted status;
- timestamps;
- version/audit metadata.

## ChromaDB

Store embeddings and metadata with references to canonical IDs. ChromaDB must be rebuildable from SQLite.

## Required Utilities

- index/update a canonical record;
- remove/deactivate derived entries when appropriate;
- rebuild the semantic index from canonical state;
- report index health/status.

## Boundary

Expose repository interfaces to the core. Do not make higher layers depend on raw SQL or ChromaDB implementation details.
