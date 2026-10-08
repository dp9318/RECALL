# RECALL — Team Development and Git Workflow

## Goal

Allow multiple contributors and coding agents to develop independent modules in parallel while keeping integration controlled and predictable.

## Repository Model

Use one monorepo.

### Protected Branch

```text
main
```

This branch should contain only reviewed, integrated work.

### Integration Branch

```text
integration/recall
```

This is the shared staging branch for completed module work.

### Feature Branches

Use a branch per work stream, for example:

```text
feature/frontend-<short-name>
feature/database-<short-name>
feature/core-<short-name>
feature/intelligence-<short-name>
```

## Merge Flow

```text
feature branch
     ↓ pull request
integration/recall
     ↓ integration tests / demo
main
```

Do not ask all contributors to work against the same source files unnecessarily.

## Module Boundaries

### Frontend Module

Owns the dashboard UI under the frontend directory and its API client/presentation code.

Must not directly access persistence or model runtimes.

### Database Module

Owns SQLite schema, migrations, repositories, and ChromaDB persistence/index adapters.

Must expose contracts that the core can consume.

### Core Memory Module

Owns memory lifecycle orchestration, context assembly, command/service behavior, and integration of the contracts.

### Intelligence Module

Owns retrieval/ranking helpers, conflict detection, deterministic resolution rules, and the local LLM arbitration adapter.

## Shared Contracts

Shared data structures and API contracts live under `contracts/` or the documented equivalent. Changes to shared contracts should be coordinated and kept backward-compatible where practical.

## Agent Documentation

Each module has an OpenCode agent instruction file. A module agent must read:

1. root `AGENTS.md`;
2. the module document;
3. shared contracts;
4. the architecture and development rules relevant to the change.

The module agent should update its module documentation when interfaces or behavior materially change.

## Integration Protocol

Before opening a PR:

1. run module tests;
2. run contract tests touching changed interfaces;
3. rebase/merge current integration branch as appropriate;
4. document assumptions or unresolved integration points;
5. include any migration/API changes in the PR description.

The integration owner should merge modules in dependency order where practical:

1. contracts;
2. database/persistence;
3. retrieval/conflict services;
4. core orchestration;
5. API/MCP adapters;
6. dashboard integration.

## Why This Works

Each work stream can be developed with mocks or interfaces when another module is incomplete. The integration branch catches cross-module incompatibilities before changes reach `main`.
