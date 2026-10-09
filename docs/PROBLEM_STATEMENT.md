# RECALL — Problem Statement

## Problem

AI coding agents are effective within a single working context, but useful project knowledge often disappears across sessions. Decisions, constraints, implementation details, user preferences, and previous mistakes must be repeatedly re-explained.

A useful persistent memory layer must do more than store transcripts. It must distinguish current information from stale information, preserve lineage, retrieve relevant context, support explicit user control, and handle conflicting memories safely.

## Required Capabilities

RECALL must:

1. persist useful project/session context across agent sessions;
2. retrieve relevant memories for a current task;
3. preserve source and lineage information for derived memories;
4. compact or summarize context without destroying canonical evidence;
5. detect and resolve conflicting memories;
6. use a small local 1B–3B LLM for bounded ambiguous conflict arbitration, with an explicitly configured cloud API fallback only when the local context window is exceeded;
7. let users explicitly create, view, update, and delete personal custom instructions;
8. support global/personal and project-scoped custom instructions;
9. expose memory operations to OpenCode through MCP and `/recall` commands;
10. provide a web dashboard where humans can inspect, query, and manage RECALL;
11. keep canonical state recoverable even when the semantic index or model is unavailable.

## User Control Requirement

The user must be able to invoke:

```text
/recall custom-instructions
```

and perform all four lifecycle operations:

```text
view/list
create
update
 delete
```

The dashboard must offer equivalent functionality through a visual interface.

## Architecture Constraint

SQLite is canonical. ChromaDB is derived. The local LLM is an arbitration component. Neither frontend nor OpenCode may bypass the RECALL core to directly edit storage.

## Success Condition

A project should be able to continue across sessions with relevant durable context, while the user can understand where important context came from, correct it, remove it, and explicitly define instructions that take precedence over inferred historical memory.
