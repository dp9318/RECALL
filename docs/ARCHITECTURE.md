# RECALL — System Architecture

## 1. Overview

RECALL is a persistent memory engine implemented as a Python core/service. It has two client surfaces:

1. OpenCode integration through MCP and `/recall` commands.
2. A web dashboard using React + Tailwind CSS and a JSON/HTTP application API.

Both surfaces invoke the same core application services.

## 2. High-Level Architecture

```text
                      ┌─────────────────────────────┐
                      │        CLIENT SURFACES      │
                      │                             │
                      │ OpenCode / MCP / /recall    │
                      │ React + Tailwind Dashboard  │
                      └──────────────┬──────────────┘
                                     │
                         MCP         │       HTTP/JSON
                           │         │           │
                           └─────────┴───────────┘
                                     ▼
                      ┌─────────────────────────────┐
                      │         RECALL CORE         │
                      │           Python            │
                      │                             │
                      │ Command / API adapters     │
                      │ Memory Manager              │
                      │ Retrieval                   │
                      │ Custom Instructions         │
                      │ Conflict Detection         │
                      │ Conflict Resolution         │
                      │ Context Assembly            │
                      └──────────────┬──────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌──────────┐     ┌───────────┐    ┌────────────┐
              │ SQLite   │────▶│ ChromaDB  │    │ Local      │
              │ canonical│     │ derived   │    │ LLM 1B–3B │
              │ truth     │     │ semantic  │    │ arbitration│
              └──────────┘     └───────────┘    └────────────┘
```

## 3. Core Components

### 3.1 Client Adapters

**MCP adapter** exposes agent-facing operations to OpenCode.

**HTTP/JSON API** exposes human-facing operations to the web dashboard.

Both adapters delegate to the same application services.

### 3.2 Memory Manager

Owns memory lifecycle orchestration:

- capture/persist;
- retrieval request handling;
- updates and supersession;
- compaction;
- lineage preservation;
- context assembly.

### 3.3 Custom Instruction Service

Owns user-authored instruction lifecycle and precedence.

Canonical records live in SQLite. Active instructions are loaded from SQLite for correctness.

### 3.4 Retrieval Layer

Combines:

- structured/keyword retrieval from canonical storage;
- semantic retrieval from ChromaDB;
- ranking and project/scope filtering.

### 3.5 Conflict Layer

Performs:

- conflict detection;
- deterministic precedence rules;
- bounded candidate packaging;
- local-model arbitration when needed;
- validation and abstention.

### 3.6 Context Assembly

Combines:

1. active custom instructions;
2. current valid canonical memories;
3. resolved historical memories;
4. project/session context;
5. provenance metadata.

## 4. Canonical Storage

SQLite owns:

- projects;
- sessions;
- messages/events;
- memories;
- memory lineage/supersession;
- custom instructions;
- lifecycle metadata.

ChromaDB stores embeddings and metadata that reference canonical IDs. It is disposable and rebuildable.

## 5. Conflict Authority

```text
User custom instruction
        ↓
Explicit user update/supersession
        ↓
Current canonical memory
        ↓
Older memory
        ↓
Local LLM arbitration
        ↓
Unresolved/abstain
```

The local LLM never directly writes authoritative state.

## 6. Dashboard Boundary

The dashboard interacts only with the RECALL API. It does not know database schemas and does not implement memory rules.

```text
Dashboard
   ↓
HTTP/JSON API
   ↓
RECALL Core
   ↓
repositories / services
   ↓
SQLite + ChromaDB + resolver adapter
```

## 7. Failure Behavior

- ChromaDB unavailable: canonical operations still work; semantic retrieval may be degraded.
- Local LLM unavailable: deterministic conflict rules still run; unresolved conflicts may be returned.
- Dashboard unavailable: OpenCode/MCP continues to function.
- MCP unavailable: dashboard/API still works.
- Index corruption: rebuild ChromaDB from SQLite.
