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

Store embeddings and metadata with references to canonical IDs. ChromaDB must
be rebuildable from SQLite. Memory documents and queries use the same explicit
Sentence Transformers embedding function. Collection metadata records the
provider and model; a mismatch is rejected during normal retrieval and can
only be replaced by an explicit canonical rebuild. The local Chroma directory
is derived from the configured SQLite database path.

`MemoryManager.rebuild_semantic_index()` pages through active canonical SQLite
memories and rebuilds the vector collection. This is the supported reindex
path after changing the embedding model. Index failures do not change canonical
memory writes, and semantic queries surface the error rather than returning
keyword results as if they were semantic.

## Required Utilities

- index/update a canonical record;
- remove/deactivate derived entries when appropriate;
- rebuild the semantic index from canonical state;
- report index health/status.

## Boundary

Expose repository interfaces to the core. Do not make higher layers depend on raw SQL or ChromaDB implementation details.
