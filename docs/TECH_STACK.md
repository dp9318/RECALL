# RECALL — Technology Stack

## 1. Core Stack

| Layer | Technology | Role |
|---|---|---|
| Coding-agent host | OpenCode | Agent runtime / integration and test environment |
| Integration protocol | MCP | Boundary between OpenCode and RECALL |
| Application language | Python | Memory engine and MCP server |
| Canonical storage | SQLite | Raw/source-of-truth ledger + user custom instructions |
| Semantic index | ChromaDB | Embedding-based and compressed-memory retrieval |
| Conflict resolver | Local 1B–3B LLM | Bounded arbitration of unresolved memory conflicts |
| Human client | Web dashboard | Chat-like UI for memory inspection/control |
| Dashboard API boundary | HTTP/JSON | Domain/application API consumed by the dashboard |

## 2. Architectural Role of Each Technology

### OpenCode

Provides the coding-agent environment in which RECALL is exercised and integrated.

### Python

Implements memory lifecycle logic, custom-instruction management, storage orchestration, retrieval logic, conflict arbitration orchestration, and the MCP server.

### MCP

Provides a clean tool boundary so the coding agent can use memory and instruction operations without depending directly on internal databases.

### SQLite

Provides durable, local, transactional canonical storage for project history, memory lineage, and explicit custom instructions.

### ChromaDB

Provides semantic indexing and similarity retrieval over derived memory representations. It is rebuildable.

### Local 1B–3B LLM

Provides a lightweight local decision layer for unresolved contradictions. It should be selected for reliable instruction following, structured output, low latency, and local resource requirements rather than general chat capability.

The exact model and runtime remain implementation decisions until benchmarked against RECALL-specific conflict cases.

## 3. Supporting Tooling

The implementation may use standard Python engineering tooling such as:

- virtual environments / dependency management;
- pytest for automated tests;
- type checking and linting where beneficial;
- Git for version control.

The exact tooling is implementation-level and may evolve without changing the architecture.

## 4. Technology Constraints

The core MVP should avoid adding infrastructure without a concrete requirement.

In particular, the following are **not core dependencies** of RECALL_V2:

- Qt/QML;
- PySide6;
- a frontend framework chosen before the dashboard implementation;
- Django;
- a separate backend service that duplicates the RECALL core;
- a second primary database.

These technologies may appear in experiments outside the core memory engine, but they must not become hidden architectural requirements.

## 5. Storage Strategy

SQLite is authoritative.

ChromaDB is rebuildable.

The local LLM is stateless from the architecture's perspective: it reasons over supplied evidence and does not own persistent memory.

Therefore:

```text
SQLite
  ↓ source of truth
  ├── application reads
  ├── custom-instruction management
  └── rebuild / indexing pipeline
            ↓
         ChromaDB

SQLite + bounded evidence
            ↓
      local 1B–3B LLM
            ↓
       structured decision
```

## 6. Embeddings

RECALL should use an embedding model/provider compatible with the chosen ChromaDB integration. The embedding implementation is intentionally abstracted so that the semantic index can evolve without changing the canonical storage model.

Embedding configuration, model choice, and dimensions should be centralized rather than scattered through the codebase.

## 7. Local LLM Runtime

The conflict resolver should run locally where practical. Candidate runtimes may evolve (for example, a local inference runtime that can load a 1B–3B model), but the architecture only requires a stable abstraction such as:

```text
ConflictResolver
    -> resolve(conflict_set)
    -> structured result
```

The resolver must support timeout/error handling and an explicit abstain state.

## 8. Dashboard and Application API

The dashboard is required for the MVP, but its frontend framework is not yet architecturally locked.

The dashboard should consume a thin HTTP/JSON application API implemented as part of the RECALL core/service boundary. The API should expose domain operations rather than raw database endpoints.

The frontend must not connect directly to SQLite, ChromaDB, or the resolver runtime.

## 9. Custom Instruction Storage

Custom instructions are primarily a SQLite concern. A conceptual schema may include:

```text
custom_instructions
--------------------
id
scope_type            # global | project
scope_id              # null for global, project identifier otherwise
content
active
version
created_at
updated_at
```

A separate `custom_instruction_versions` table is optional but recommended if the product needs audit/history.

## 10. Deployment Model

The first target is a local developer environment where OpenCode and the RECALL MCP server can access local persistent storage and a local 1B–3B resolver model.

The architecture should not assume cloud hosting or a multi-user deployment.

## 11. Versioning Principle

Pin or constrain dependency versions according to the project environment, but avoid coupling architecture documents to patch-level versions unless a specific version is itself an architectural requirement.
