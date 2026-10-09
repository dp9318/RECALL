# RECALL — Product Requirements Document

## Product Goal

Build a reliable persistent context engine for AI coding agents, with both an agent-facing OpenCode interface and a human-facing web dashboard.

## Users

- Developers using OpenCode who want persistent project memory.
- Project collaborators who need to inspect or correct stored context.
- Users who want persistent personal/project instructions that survive sessions.

## MVP Functional Areas

### 1. Persistent Memory

- capture durable project/session information;
- create and update memory records;
- preserve memory type, project, timestamps, provenance, and lineage;
- retain historical versions or supersession relationships where applicable.

### 2. Retrieval

- structured/project-aware retrieval;
- semantic search through ChromaDB;
- canonical lookup through SQLite;
- source and lineage visibility;
- bounded result sets.

### 3. Context Update and Compaction

`/recall update-context` must persist an explicit durable context update.

`/recall compact` must reduce active context while retaining canonical history and lineage.

### 4. Custom Instructions

`/recall custom-instructions` must support:

- list/view;
- create;
- update;
- delete.

Instructions must support:

- global/personal scope;
- project scope;
- active/inactive lifecycle;
- explicit user ownership.

### 5. Conflict Resolution

The resolver must use staged resolution:

1. identify conflicting candidates;
2. validate scope and canonical status;
3. apply deterministic precedence;
4. invoke the local 1B–3B model only if ambiguity remains;
5. use an explicitly configured cloud provider only if the local model reports that its context window was exceeded;
6. validate structured model output;
7. allow an unresolved/abstain result.

### 6. OpenCode Integration

Expose core capabilities through MCP and the `/recall` command family.

### 7. Web Dashboard

The dashboard must provide:

- Chat / Ask RECALL;
- Memory Explorer;
- Conflict Center;
- Custom Instructions manager;
- session/usage overview;
- project/context selector.

The dashboard is a client and must use the RECALL API.

## Non-Goals

- replacing OpenCode as the coding agent;
- building a general-purpose chatbot as the primary product;
- making ChromaDB the canonical database;
- automatic destructive deletion of historical evidence;
- allowing the local LLM to author authoritative memory directly;
- creating a second desktop application.

## MVP Quality Requirements

- deterministic canonical persistence;
- rebuildable semantic index;
- provenance-aware retrieval;
- testable custom-instruction CRUD;
- safe conflict abstention;
- API contracts for dashboard and MCP;
- focused observability for failures.
