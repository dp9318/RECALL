# RECALL — Retrieval and Conflict Intelligence Module Contract

## Goal

Provide retrieval ranking and safe conflict resolution, with a bounded local 1B–3B model used only when deterministic logic is insufficient.

## Retrieval

Support:

- project-aware filtering;
- keyword/structured retrieval;
- semantic retrieval from ChromaDB;
- result ranking;
- bounded candidate sets;
- provenance preservation.

## Conflict Detection

Detect when candidate memories disagree on the same topic/entity/decision and are simultaneously plausible for the current scope.

## Deterministic Resolution

Before calling the local model, apply:

1. explicit user update/supersession;
2. current active status;
3. project scope over unrelated scope where appropriate;
4. timestamps/versions as supporting evidence;
5. provenance quality.

Do not treat recency as absolute authority when explicit user state disagrees.

## Local LLM Arbitration

The local model receives only a bounded evidence package. It must output structured data validated by code.

Possible outcomes:

- resolved;
- partially resolved;
- unresolved/abstain.

It must not:

- directly modify SQLite;
- delete canonical evidence;
- override custom instructions;
- invent evidence identifiers.

## Runtime

The model runtime and exact 1B–3B model are configurable. Keep the resolver behind a narrow adapter so the model can be changed without redesigning the core.
