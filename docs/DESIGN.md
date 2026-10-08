# RECALL — System Design

## 1. Design Principles

RECALL follows seven core principles:

1. **Remember selectively.** Useful memory is more important than maximum memory volume.
2. **Keep evidence.** Derived memory must remain traceable to source records.
3. **Separate truth from retrieval.** SQLite is canonical; ChromaDB is derived.
4. **Respect user authorship.** Explicit custom instructions are canonical user intent, not inferred memory.
5. **Use small-model arbitration safely.** The 1B–3B LLM resolves ambiguity only from bounded evidence and can abstain.
6. **Keep the agent boundary clean.** MCP separates OpenCode from internal implementation details.
7. **Design for recovery.** A broken semantic index must be repairable.
8. **Keep clients thin.** OpenCode and the dashboard consume RECALL capabilities; they do not duplicate the memory engine.

## 2. Logical Modules

```text
recall/
├── mcp/                 # MCP transport, command mapping, schemas
├── core/                # memory semantics and orchestration
├── instructions/        # custom-instruction CRUD and policy
├── storage/             # SQLite repositories / persistence
├── index/               # ChromaDB adapter and indexing
├── retrieval/           # candidate retrieval + ranking/filtering
├── resolver/            # deterministic conflict checks + LLM arbitration
├── memory/              # extraction, compression, lineage
├── models/              # domain models / DTOs
├── config/              # configuration
└── tests/
```

The actual repository layout may differ, but these responsibilities should remain separable.

## 3. Client Surfaces

### OpenCode Client

The OpenCode side exposes RECALL through MCP plus the `/recall ...` command surface. It is optimized for agent-driven context retrieval and memory management during coding work.

### Web Dashboard

The dashboard is a human-facing client with a ChatGPT-like interaction model. It should include:

- **Ask / Chat** — ask RECALL for relevant project context and inspect the returned evidence.
- **Memory Explorer** — search, filter, inspect, and manage memories where permitted.
- **Conflict Center** — inspect conflict sets, resolutions, evidence, and unresolved cases.
- **Custom Instructions** — view, create, update, and delete global/project instructions.
- **Overview / Stats** — show project/session counts, memory counts, index status, and recent activity.

The dashboard calls a domain/application API. UI components should never contain SQL queries, embedding logic, or direct LLM conflict arbitration.

## 4. Domain Concepts

### Project

A logical project boundary used to isolate memory.

### Session

A coding-agent interaction period associated with a project.

### Event / Message

A raw piece of session history captured for canonical persistence.

### Memory

A durable, reusable knowledge representation derived from one or more canonical records.

### Memory lineage

The relationship connecting a derived memory to the records from which it was produced.

### Semantic document

A searchable representation of memory intended for the vector index.

### Custom instruction

An explicitly user-authored persistent rule or preference that should influence future RECALL context assembly and/or coding-agent behavior.

### Conflict

A set of memories whose claims cannot all be simultaneously treated as the current applicable context.

### Resolution

A structured decision describing which claims are active, superseded, compatible, or unresolved, with evidence IDs.

## 5. Canonical Data Model

Conceptually:

```text
Project
  │
  ├── Session
  │     │
  │     └── Event / Message
  │             │
  │             └── Memory
  │                  │
  │                  └── Derived semantic document
  │
  └── Project-scoped Custom Instruction

Global Personal Custom Instruction
```

A memory may have multiple parents when it summarizes or combines multiple source records.

The concrete relational schema should make relationships explicit rather than hiding them inside unstructured JSON.

## 6. Canonical Data Domains

The SQLite schema should distinguish at least:

```text
projects
sessions
events/messages
memories
memory_lineage
custom_instructions
custom_instruction_versions (optional but recommended)
```

A `custom_instructions` record should contain enough fields to support ID, scope, content, state, timestamps, and versioning. A separate version table is recommended if edit history is valuable.

## 7. Memory Record Requirements

A memory record should be able to answer:

- What is this memory?
- Which project does it belong to?
- When was it created or observed?
- What kind of memory is it?
- What source records produced it?
- Is it still valid/active?
- Where can its semantic representation be found?

## 8. Custom Instruction Requirements

A custom instruction should answer:

- What is the instruction?
- Is it global or project-scoped?
- Is it active?
- When was it created/updated?
- What is its current version?
- Can it be identified unambiguously for update/delete?

The user must own its lifecycle. Automatic memory extraction may reference an instruction, but must not mutate it.

### `/recall custom-instructions` interaction model

The command should resolve to an interactive management flow similar to:

```text
/recall custom-instructions
          │
          ▼
   show current instructions
          │
     ┌────┼────┬────────┐
     ▼    ▼    ▼        ▼
   create view update   delete
          │    │        │
          └────┴────────┘
                 │
                 ▼
          SQLite canonical
```

The UI/command syntax can evolve, but the underlying operations must remain explicit and testable.

## 9. MCP / Command Design

MCP operations should be domain-oriented. A minimal conceptual set is:

- `memory_store` — persist/register memory or a memory-worthy event;
- `memory_search` — retrieve relevant memories;
- `memory_get` — fetch a specific memory and its provenance;
- `memory_rebuild` — rebuild the semantic index from canonical data;
- `memory_status` — report store/index health;
- `custom_instruction_list` — list active/custom instructions in scope;
- `custom_instruction_create` — create one;
- `custom_instruction_update` — update one;
- `custom_instruction_delete` — delete one;
- `context_resolve` — resolve a bounded set of conflicting candidate memories when deterministic rules cannot decide.

The OpenCode-facing command family can compose these domain operations into user-friendly commands such as:

```text
/recall compact
/recall update-context
/recall custom-instructions
/recall ...
```

Exact tool names may change during implementation, but each operation should have a stable contract and narrow responsibility.

## 10. Retrieval Design

A retrieval request should contain enough information to establish scope and intent, such as:

- project identity;
- query text;
- optional session identity;
- optional limits/filters.

Candidate generation happens through semantic search. Candidate records should then be validated against canonical storage and filtered/ranked using available metadata.

The final result should favor a small number of high-value memories over a large number of weak matches.

Applicable custom instructions should be loaded from canonical storage and merged into context separately, with higher policy priority than inferred historical memory.

## 11. Conflict Resolution Design

Conflict handling uses a staged pipeline:

```text
candidates
   ↓
canonical validation
   ↓
status / recency / supersession checks
   ↓
clear winner? ── yes ──► resolved
   │
   no
   ↓
bounded evidence package
   ↓
local 1B–3B LLM
   ↓
structured JSON-like result
   ├── resolved
   ├── partially_resolved
   └── unresolved
```

The resolver input should contain only the claims necessary to judge the conflict, plus metadata such as timestamps, memory IDs, scope, and explicit supersession markers.

The resolver output should include at minimum:

- status;
- preferred/active claims;
- superseded/conflicting claims;
- confidence or rationale fields appropriate to the implementation;
- evidence IDs.

The LLM must not directly mutate SQLite. A domain service validates its output before any state transition.

## 12. Conflict Priority

When claims disagree, use this priority order:

```text
Explicit user instruction
        ↓
Explicit user update / supersession
        ↓
Current valid canonical memory
        ↓
Older historical memory
        ↓
Local LLM arbitration for residual ambiguity
        ↓
Unresolved / abstain
```

This ordering prevents an inferred memory or small local model from silently overriding direct user intent.

## 13. Memory Compression Design

Compression is a transformation, not a replacement for source history.

```text
source A ─┐
source B ─┼──► derived memory C
source C ─┘
```

Memory C retains parent references to A/B/C as applicable.

This makes compression reversible in the sense that the underlying evidence remains available even when the compact representation is used for retrieval.

## 14. Indexing Design

Indexing should be treated as an asynchronous-like derived step even if implemented synchronously at first:

```text
canonical write → index update
```

The system must be able to represent the state where the first succeeds and the second fails.

A rebuild mechanism closes that consistency gap.

For custom instructions, direct SQLite reads are authoritative. If instructions are also indexed, indexing is optional derived state only.

## 15. Configuration

Configuration should define, at minimum:

- SQLite location;
- ChromaDB persistence location;
- project/scope configuration as needed;
- embedding/index configuration;
- local resolver model/runtime configuration;
- logging level.

Configuration must not hard-code machine-specific absolute paths.

## 16. Observability

The system should make it possible to answer:

- Was the memory written to SQLite?
- Was indexing attempted?
- Did indexing succeed?
- Which memory ID was returned?
- Which source records produced it?
- Why was a retrieved result selected?
- Was a conflict detected?
- Did deterministic rules resolve it?
- Was the local resolver invoked?
- What evidence IDs supported the resolution?
- Was a custom instruction created, updated, or deleted successfully?
- Is the semantic index out of date?

Use structured logs or equivalent machine-readable diagnostics where practical.
