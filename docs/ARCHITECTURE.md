# RECALL — Architecture

## 1. Architectural Intent

RECALL is a persistent memory subsystem for AI coding agents. It sits beside the coding agent rather than replacing it.

The architecture deliberately separates:

- agent integration;
- memory semantics;
- canonical persistence;
- semantic indexing;
- user-authored instructions;
- conflict resolution.

## 2. System Context

RECALL has two first-class clients: an OpenCode integration for agent-driven use and a web dashboard for human inspection/control.

```text
                           Developer / User
                                │
                ┌──────────────┴──────────────┐
                │                             │
                ▼                             ▼
        ┌─────────────────┐          ┌────────────────────┐
        │     OpenCode    │          │   RECALL Dashboard │
        │  coding agent   │          │  Chat-like web UI  │
        └────────┬────────┘          └─────────┬──────────┘
                 │ MCP                         │ HTTP/JSON
                 └──────────────┬──────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │     RECALL Core         │
                    │        Python           │
                    ├─────────────────────────┤
                    │ command/API layer       │
                    │ memory lifecycle        │
                    │ retrieval               │
                    │ instructions            │
                    │ conflict resolution     │
                    │ context assembly        │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
     │    SQLite    │     │  ChromaDB    │     │ Local 1B–3B  │
     │  canonical   │────▶│   derived    │     │   conflict   │
     │ source truth │     │ semantic idx │     │  arbitration │
     └──────────────┘     └──────────────┘     └──────────────┘
```

The dashboard is an interface only. It does not become a second memory engine, second source of truth, or separate business-logic implementation.

## 3. Component Responsibilities

### 3.1 OpenCode

OpenCode is the coding-agent host used to exercise and integrate RECALL.

Responsibilities:

- interact with the user;
- inspect and modify the codebase;
- invoke RECALL through the plugin/MCP boundary;
- consume retrieved context and applicable custom instructions.

OpenCode does not own RECALL's canonical memory database.

### 3.2 RECALL Dashboard

The dashboard is the human-facing control plane for RECALL. It is intentionally similar in interaction model to a ChatGPT wrapper but is centered on memory inspection and control.

Responsibilities:

- send natural-language queries to RECALL;
- show retrieved context and provenance;
- inspect memory records and lineage;
- inspect unresolved/resolved conflicts;
- create, view, update, and delete custom instructions;
- expose project/session and basic usage state.

The dashboard communicates through a domain/application API exposed by RECALL. It must not connect directly to SQLite or ChromaDB and must not implement its own conflict-resolution policy.

### 3.3 RECALL MCP Server

The Python MCP server is the integration boundary.

Responsibilities:

- expose memory operations as MCP-compatible tools/resources where appropriate;
- expose the `/recall ...` command surface through the OpenCode integration;
- validate inputs;
- invoke memory, instruction, retrieval, and conflict-resolution services;
- return structured results and errors;
- keep transport concerns separate from storage logic.

### 3.4 Memory Core

The memory core owns memory semantics.

Responsibilities:

- normalize incoming records;
- decide or accept which data becomes durable memory;
- create derived/compressed memory;
- preserve lineage;
- apply project/session scope;
- orchestrate persistence and retrieval.

### 3.5 Custom Instruction Service

User-authored custom instructions are a first-class domain object, separate from automatically derived memory.

Responsibilities:

- create a custom instruction;
- list/show the user's applicable instructions;
- update an existing instruction;
- delete an instruction;
- validate scope and instruction metadata;
- supply active instructions to the context assembly pipeline.

Custom instructions are explicit user intent. They must not be silently rewritten by memory extraction, compression, or the conflict-resolution model.

### 3.6 Conflict Resolution Service

The resolver handles situations where retrieved memories contain contradictory claims or competing versions of the same context.

Resolution policy is layered:

1. deterministic metadata/recency/validity rules;
2. explicit user-authored custom instructions and explicit updates;
3. the local 1B–3B LLM only when ambiguity remains.

The resolver receives bounded evidence, not the entire database, and returns a structured decision with evidence IDs.

The model is an **arbitration component, not a source of truth**. It cannot directly mutate canonical memory.

### 3.7 SQLite

SQLite is the canonical source-of-truth ledger.

Typical canonical information includes:

- projects/scopes;
- sessions;
- messages or events;
- responses/tool outcomes where retained;
- derived memory records;
- parent/child lineage;
- custom instructions;
- instruction versions/status;
- metadata required to reproduce or rebuild derived indexes.

Exact schema may evolve, but canonical data must remain recoverable independently of ChromaDB.

### 3.8 ChromaDB

ChromaDB is the semantic/derived index.

It may store:

- embeddings;
- searchable semantic documents;
- derived memory representations;
- optional searchable projections of custom instructions;
- identifiers that map back to SQLite records.

Custom instructions should normally be loaded directly from SQLite because they are small, explicit, and high-priority. ChromaDB must never be required to recover the user's instructions.

### 3.9 Local 1B–3B LLM

A small local LLM is used only for conflict arbitration when deterministic rules cannot safely resolve competing context.

Responsibilities:

- compare a bounded set of conflicting claims;
- identify which claims are compatible, superseded, or unresolved;
- produce a structured resolution with evidence references;
- abstain when the evidence is insufficient.

The model must not:

- invent new facts;
- directly write to SQLite;
- overwrite user-authored custom instructions;
- become a second source of truth.

## 4. Data Ownership

```text
SQLite = canonical truth
ChromaDB = derived semantic projection
LLM = bounded arbitration only
Custom instructions = explicit user-owned canonical data
```

A ChromaDB record or LLM output without a valid canonical identity/evidence chain must not be treated as authoritative memory.

## 5. Canonical Data Domains

RECALL should conceptually distinguish at least four domains:

```text
Canonical SQLite
├── Raw session/event data
├── Derived/semantic memory records + lineage
├── User custom instructions
└── Instruction/version metadata
```

This separation is important because automatically derived memory and explicit user instructions have different authority and lifecycle rules.

## 6. Memory Lifecycle

```text
Raw agent interaction
        ↓
      Capture
        ↓
    Normalize
        ↓
 SQLite canonical write
        ↓
 Memory extraction / compression
        ↓
 Parent-child lineage recorded
        ↓
 Semantic representation created
        ↓
 ChromaDB index
        ↓
 Later query
        ↓
 Candidate retrieval
        ↓
 Scope + relevance filtering/ranking
        ↓
 Conflict detection
        ↓
 Deterministic resolution
        ↓
  unresolved? ── yes ──► local 1B–3B resolver
        │                         ↓
        └──────────────────► structured resolution
                                  ↓
                         context assembly
                                  ↓
                         MCP response to OpenCode
```

Custom instructions enter context assembly through a separate path:

```text
/recall custom-instructions
        │
        ├── create
        ├── show/list
        ├── update
        └── delete
                │
                ▼
        SQLite canonical store
                │
                ▼
        Active instruction set
                │
                ▼
        Context assembly
```

## 7. Retrieval Architecture

Retrieval should be two-layered conceptually:

1. **Semantic candidate generation** using ChromaDB.
2. **Canonical validation and contextualization** using SQLite.

After candidate generation, RECALL checks for contradictory claims and active supersession. The resolver must prefer explicit user updates and current valid records over stale historical memories.

A useful retrieval result should expose enough identity/provenance for the agent to understand where the memory came from.

## 8. Conflict Resolution Architecture

The conflict resolver should follow this pipeline:

```text
retrieved candidates
        ↓
canonical validation
        ↓
duplicate / contradiction detection
        ↓
explicit validity + supersession checks
        ↓
clear winner? ── yes ──► accept
        │
        no
        ↓
local 1B–3B LLM arbitration
        ↓
structured result
        ├── resolved
        ├── partially resolved
        └── unresolved / abstain
```

The model prompt must include only the claims and metadata necessary for the decision. Every model decision should reference the evidence IDs that justified it.

## 9. Custom Instruction Model

A custom instruction is a user-authored persistent rule that tells RECALL and/or the coding agent how to behave for that user. Examples include coding preferences, response conventions, architectural preferences, or project-specific working rules.

Conceptually:

```text
CustomInstruction
├── instruction_id
├── scope (global or project)
├── content
├── active/inactive status
├── created_at
├── updated_at
└── version metadata
```

The initial deployment may be single-user, so a separate account system is not required. The schema should still preserve enough identity/scope information to support global personal instructions and project-scoped instructions.

### `/recall custom-instructions` behavior

The command is an interactive management surface. At minimum, the user must be able to:

- **see/list** all applicable custom instructions;
- **create** a new instruction;
- **update** an existing instruction;
- **delete** an existing instruction.

A successful update or delete changes the canonical SQLite record immediately. Any derived semantic representation should be refreshed or invalidated afterward.

The command must never hide existing instructions merely because they conflict with retrieved memory. The user owns them.

## 10. Memory Hierarchy

RECALL may maintain multiple representations of the same knowledge:

```text
Parent/source records
       │
       ├── child / extracted memory
       │
       ├── compressed summary
       │
       └── semantic index representation
```

Custom instructions are outside this derived hierarchy: they are explicit canonical policy data.

## 11. Failure Boundaries

### ChromaDB unavailable

The system should report semantic-index unavailability explicitly. Canonical memory and custom instructions remain intact in SQLite.

### SQLite unavailable

Memory persistence, custom-instruction management, and authoritative retrieval cannot be trusted. The system must fail loudly rather than silently pretending memory or instruction changes were stored.

### Local resolver unavailable

If deterministic rules cannot resolve a conflict and the local 1B–3B model is unavailable, return an explicit unresolved result with the conflicting evidence rather than guessing.

### Partial indexing

A successful SQLite write followed by a failed ChromaDB update represents a recoverable indexing inconsistency, not loss of canonical memory. Reindex/rebuild should repair it.

## 12. Rebuild Model

A rebuild should conceptually follow:

```text
SQLite canonical records
        ↓
filter eligible derived memories
        ↓
recreate semantic representations
        ↓
populate ChromaDB
        ↓
validate identity/lineage mapping
```

Custom instructions do not depend on rebuild for correctness. If they are indexed for optional search, the projection can be regenerated from SQLite.

## 13. Security and Isolation

Memory should be scoped to the project/session identity available to the integration layer.

Custom instructions should support at least:

- global personal scope;
- project scope.

Project-scoped instructions must not leak into another project.

Credentials, secrets, and raw sensitive values should not be embedded into long-lived semantic memory unless explicitly required and handled by a defined policy.

## 14. Architectural Constraints

The core system must not depend on:

- Qt/QML/PySide6 GUI code;
- a web frontend;
- Django as a required application server;
- a second database competing with SQLite as source of truth.

Additional infrastructure may be introduced later only when justified by a concrete requirement.
