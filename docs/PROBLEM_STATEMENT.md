# RECALL — Problem Statement

## 1. Problem

AI coding agents are highly capable inside a single working context, but their usefulness degrades when project work spans multiple sessions. Important decisions, implementation history, constraints, debugging discoveries, and user preferences are often left behind in previous conversations.

A project therefore develops a **context continuity problem**:

> The coding agent can see the current repository, but it does not reliably remember why the repository is in its current state, which explicit user instructions should continue to govern the work, or how a human can inspect and control that persistent context.

This creates repeated explanations, duplicated debugging, contradictory decisions, loss of project-specific knowledge, and unnecessary context-window usage.

## 2. Why Existing Conversation Context Is Not Enough

Conversation history is not the same thing as useful persistent memory.

A practical memory system for coding work must be able to:

- preserve raw historical evidence;
- distinguish durable knowledge from transient conversation;
- retrieve relevant historical knowledge at the time it is needed;
- preserve relationships between raw material and derived summaries;
- survive new agent sessions;
- resolve contradictory historical context safely;
- preserve explicit user-authored instructions;
- let the user create, view, update, and delete those instructions;
- remain recoverable if a semantic index is lost or rebuilt;
- provide a human-facing dashboard for inspection and control.

Simply storing previous prompts or creating a vector database of chat messages does not fully solve this problem.

## 3. RECALL's Objective

RECALL provides a persistent memory layer for AI coding agents so that an agent can carry forward useful project context across sessions without requiring the user to manually restate the entire history.

The objective is not to remember everything. The objective is to remember and retrieve **what matters**, while also respecting explicit user-authored instructions.

## 4. Target Scenario

A developer works on a software project over many sessions.

Session A establishes an architectural decision and records why it was made.

Session B implements a feature based on that decision.

Session C occurs days later. The agent encounters code whose rationale is not obvious from the source alone.

Without persistent memory, the developer must reconstruct the history manually.

With RECALL, the agent can retrieve the relevant prior memory, understand the decision and its lineage, resolve conflicting stale context when necessary, and continue work with less repeated explanation.

Separately, the developer may have durable personal or project-specific preferences such as:

> “Prefer simple Python modules over introducing a framework unless there is a concrete requirement.”

The user must be able to save such an instruction explicitly and manage it later rather than relying on conversation-derived memory.

## 5. Locked Solution Direction

RECALL is implemented as an **OpenCode enhancement / MCP-compatible persistent memory layer**.

The locked architecture is:

```text
                   ┌────────────────────────────┐
                   │       Client Layer         │
                   │                            │
                   │ OpenCode / MCP / /recall   │
                   │ Web Dashboard / Chat UI    │
                   └────────────┬───────────────┘
                                │
                       MCP / HTTP-JSON
                                ▼
                   ┌────────────────────────────┐
                   │       RECALL Core          │
                   │          Python            │
                   └────────────┬───────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         ┌──────────┐      ┌──────────┐      ┌───────────┐
         │  SQLite  │      │ ChromaDB │      │ Local     │
         │ canonical│─────▶│ derived  │      │ 1B–3B LLM │
         │ truth    │      │ semantic │      │ arbitration│
         └──────────┘      └──────────┘      └───────────┘
```

### Architectural meaning

- **OpenCode** remains the coding-agent host and execution environment.
- **RECALL MCP Server** exposes memory and instruction operations through the MCP/plugin boundary.
- **SQLite** stores canonical session/message/response data, memory lineage, and user-authored custom instructions.
- **ChromaDB** provides semantic retrieval over derived/embedded memory representations.
- **Local 1B–3B LLM** resolves residual ambiguity between conflicting historical memories but is not authoritative storage.
- ChromaDB and the LLM are both replaceable/derived components; SQLite remains canonical.

## 6. User-Managed Custom Instructions

The problem statement requires a direct user-controlled memory/instruction surface. RECALL therefore exposes a dedicated command family conceptually including:

```text
/recall compact
/recall update-context
/recall custom-instructions
/recall ...
```

`/recall custom-instructions` must allow the user to:

1. **See/List** current custom instructions.
2. **Create** a new custom instruction.
3. **Update** an existing custom instruction.
4. **Delete** an existing custom instruction.

These instructions are stored as a separate canonical data domain in SQLite. They are not merely vector memories.

Custom instructions may support at least two scopes:

- **Global personal** — applies across projects.
- **Project** — applies only to the selected project.

The active instruction set is loaded directly from SQLite during context assembly. Optional vector indexing can improve search/discovery, but correctness must never depend on it.

Explicit user instructions have higher authority than inferred historical memory.

## 7. Human Dashboard Requirement

The approved product includes a lightweight web dashboard with a ChatGPT-like interaction model. It is a client for RECALL rather than a separate memory engine.

The dashboard must expose, at minimum:

- Ask/Chat with RECALL;
- memory exploration and provenance;
- conflict inspection;
- custom instruction create/view/update/delete;
- basic project/session/index state.

All mutations go through RECALL's application/domain services.

## 8. Core Engineering Challenge

The central problem is therefore not merely storage. It is the design of a reliable memory lifecycle and policy layer:

```text
Conversation data
      ↓
   capture
      ↓
 canonical persistence
      ↓
 memory extraction / compression
      ↓
 semantic indexing
      ↓
 relevance retrieval
      ↓
 conflict detection
      ↓
 deterministic resolution
      ↓
 local 1B–3B arbitration when needed
      ↓
 custom-instruction merge
      ↓
 context returned to agent
```

The system must preserve provenance so that derived memories can be traced back to the source information that produced them, while explicit user instructions remain independently manageable and authoritative.

## 9. Success Criteria

A successful RECALL implementation should demonstrate that:

1. information from an earlier coding session can persist after the session ends;
2. a later session can retrieve relevant information without manually replaying the entire history;
3. retrieved information remains tied to its source/lineage;
4. conflicting memories are resolved using explicit metadata first and local-model arbitration only when necessary;
5. the semantic index can be rebuilt from the canonical store;
6. losing or disabling ChromaDB does not destroy canonical memory or custom instructions;
7. the user can invoke `/recall custom-instructions` and see, create, update, and delete instructions;
8. the integration remains usable through MCP;
9. the web dashboard provides the required human control and inspection surface.

## 10. Non-Goals

RECALL is not intended to be:

- a general-purpose personal knowledge-management application;
- a standalone chat application;
- a replacement for the coding agent;
- a GUI-first desktop application;
- a vector-database-only memory store;
- a replacement for version control or source code documentation;
- an autonomous policy engine that can override explicit user instructions;
- a general-purpose chat platform unrelated to memory.

## 11. Product Principle

**The codebase tells the agent what the system is. RECALL helps the agent remember why it became that way, what the user explicitly wants, and which historical context is still valid.**
