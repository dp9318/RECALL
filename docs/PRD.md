# RECALL — Product Requirements Document

## 1. Product Summary

RECALL is a persistent memory engine for AI coding agents, delivered as an OpenCode-oriented enhancement with an MCP-compatible Python memory server.

Its purpose is to preserve durable project context across coding sessions, retrieve relevant context when the agent needs it, resolve conflicting historical context, and let the user explicitly manage personal custom instructions.

## 2. Product Goals

### Primary goals

- Persist useful coding-session knowledge across sessions.
- Retrieve relevant historical context using semantic search.
- Preserve raw evidence and memory lineage.
- Resolve conflicting memories without treating the resolver model as authoritative.
- Keep the canonical data recoverable independently of the semantic index.
- Give the user explicit control over custom personal instructions.
- Integrate cleanly with an AI coding agent through MCP and `/recall ...` commands.

### Secondary goals

- Reduce repeated user explanations.
- Reduce irrelevant context replay.
- Provide a foundation for memory compression and lifecycle management.
- Make the memory layer testable independently of client presentation.
- Provide a small web dashboard for human inspection and control of RECALL.

## 3. Users

### Primary user

A developer using an AI coding agent for a project over multiple sessions.

### Secondary user

A project maintainer or engineer evaluating whether persistent agent memory is accurate, recoverable, and useful.

## 4. Core Use Cases

### UC-01 — Persist a session

At the end of or during a coding interaction, relevant raw session information is stored in the canonical ledger.

### UC-02 — Remember a decision

An architectural, implementation, or project-level decision is retained as durable memory with provenance.

### UC-03 — Retrieve relevant history

A later coding session asks for context related to the current task. RECALL returns the most relevant memories.

### UC-04 — Trace derived memory

A compressed or semantic memory can be traced back to its parent source records.

### UC-05 — Resolve conflicting context

When multiple memories disagree, RECALL first applies deterministic validity/supersession rules and then may invoke a local 1B–3B model to arbitrate remaining ambiguity.

### UC-06 — Manage custom instructions

The user invokes `/recall custom-instructions` and can see, create, update, and delete persistent custom instructions.

### UC-07 — Rebuild semantic memory

If the ChromaDB index is deleted or corrupted, it can be regenerated from SQLite without losing canonical data.

### UC-08 — Continue without semantic index

The system should fail gracefully when semantic indexing is temporarily unavailable rather than silently claiming that memory was saved when it was not.

### UC-09 — Use the RECALL dashboard

A developer opens the web dashboard to ask RECALL questions, inspect memory provenance, review conflicts, and manage custom instructions through a ChatGPT-like human interface.

## 5. Functional Requirements

### FR-01 Persistence

RECALL shall store raw session-related information in SQLite.

### FR-02 Memory Identity

Each durable memory record shall have a stable identity and metadata sufficient to understand its origin and scope.

### FR-03 Lineage

Derived memories shall maintain a relationship to their source records.

### FR-04 Semantic Retrieval

RECALL shall support semantic retrieval using ChromaDB as a derived index.

### FR-05 Relevance

Retrieval shall support ranking/filtering so that irrelevant historical information is not blindly inserted into the agent context.

### FR-06 Project Scope

Memory shall be scoped so that context from unrelated projects is not accidentally mixed.

### FR-07 MCP Integration

Memory and custom-instruction operations needed by the agent shall be available through MCP-compatible interfaces.

### FR-08 Recovery

The semantic index shall be rebuildable from the canonical SQLite data.

### FR-09 Observability

Failures in capture, indexing, retrieval, instruction management, conflict resolution, and rebuild operations shall be observable through explicit errors/logging.

### FR-10 Custom Instructions

RECALL shall maintain a canonical store of user-authored custom instructions separate from automatically derived memory.

### FR-11 Custom Instruction CRUD

Through `/recall custom-instructions`, the user shall be able to:

- see/list current instructions;
- create a new instruction;
- update an existing instruction;
- delete an existing instruction.

### FR-12 Instruction Scope

Custom instructions shall support at least global personal scope and project scope.

### FR-13 Instruction Authority

Explicit user-authored instructions shall be treated as higher-authority policy than inferred historical memories. The conflict resolver must not silently rewrite or delete them.

### FR-14 Conflict Arbitration

When retrieved historical memories remain contradictory after deterministic resolution, RECALL may invoke a local 1B–3B LLM to produce a structured arbitration result with evidence references.

### FR-15 Resolver Abstention

The resolver shall support an unresolved/abstain outcome when available evidence is insufficient.

### FR-16 Slash Command Surface

The RECALL integration shall expose a command family conceptually including:

```text
/recall compact
/recall update-context
/recall custom-instructions
/recall ...
```

The command names may evolve, but `custom-instructions` is a required user-facing management surface.

### FR-17 Dashboard

RECALL shall provide a web dashboard client that can:

- send queries to RECALL;
- display context and provenance;
- explore memories;
- inspect conflicts and resolutions;
- manage custom instructions through create/view/update/delete flows;
- display basic project/session/index status.

The dashboard shall use the RECALL application/API layer and shall not access SQLite or ChromaDB directly.

## 6. Custom Instruction Requirements

A custom instruction is persistent user-authored text that RECALL should apply when constructing context or guiding agent behavior.

Each instruction should have, at minimum:

- stable ID;
- scope;
- content;
- active/inactive state;
- timestamps;
- version/update metadata.

The management flow should let the user identify an instruction, edit its content, save the new version, or delete it.

Deletion must be explicit and must affect the canonical record. No vector-index entry may keep a deleted instruction authoritative.

## 7. Non-Functional Requirements

### Reliability

Canonical memory and custom instructions must not depend on the continued existence of the vector index or LLM.

### Maintainability

Core memory logic, custom-instruction logic, conflict arbitration, MCP transport, and storage adapters must remain separated.

### Determinism

Memory transformations should be reproducible enough to support debugging and rebuild workflows.

### Performance

Retrieval and conflict resolution should operate on bounded candidate sets rather than large historical transcripts. The local resolver should be small enough for practical local execution.

### Extensibility

Future storage/indexing/resolver implementations should be replaceable behind clear interfaces without rewriting memory semantics.

## 8. MVP Scope

The MVP should demonstrate:

1. session/message persistence;
2. memory extraction or registration;
3. semantic indexing;
4. semantic retrieval;
5. source/parent lineage;
6. MCP access;
7. ChromaDB rebuild from SQLite;
8. conflict detection and a local 1B–3B resolver path;
9. `/recall custom-instructions` with create/read/update/delete behavior;
10. a functional web dashboard with the minimum human-control views.

## 9. Out of Scope for MVP

- polished desktop GUI;
- multi-user cloud synchronization;
- distributed deployment;
- billing/account management;
- broad personal-assistant memory unrelated to software projects;
- replacing OpenCode's coding capabilities;
- training or fine-tuning a dedicated LLM.

## 10. Success Metrics

The prototype should be judged by whether it can answer, reliably and with provenance:

> “What important information from previous sessions is relevant to what I am doing now?”

and whether the user can explicitly manage the persistent instructions that should guide future sessions.

A successful demo should show a memory written in one session being correctly retrieved in a later session, conflicting stale context being handled safely, and custom instructions being created, viewed, updated, and deleted through `/recall custom-instructions`.
