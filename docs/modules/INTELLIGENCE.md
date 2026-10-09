# RECALL — Retrieval and Conflict Intelligence Module Contract

## Goal

Provide retrieval ranking and safe conflict resolution, with a bounded local 1B–3B model used only when deterministic logic is insufficient.

## Retrieval

Support:

- project-aware filtering;
- keyword/structured retrieval;
- semantic retrieval from ChromaDB using the local Sentence Transformers
  model `sentence-transformers/all-MiniLM-L6-v2` by default;
- result ranking;
- bounded candidate sets;
- provenance preservation.

The provider is configured with `RECALL_EMBEDDING_PROVIDER`,
`RECALL_EMBEDDING_MODEL`, and `RECALL_EMBEDDING_DEVICE`. Defaults are
`sentence-transformers`, `sentence-transformers/all-MiniLM-L6-v2`, and `cpu`.
The model loads lazily and runs locally; its first use may need to download the
model files. Install the `core[semantic]` extra. Provider, model, and vector
dimension must match for document and query embeddings. A missing provider,
model, or Chroma index is reported as an error; semantic requests do not
silently fall back to keyword search.

If the model changes, call `MemoryManager.rebuild_semantic_index()` using the
configured Core factory. The explicit rebuild replaces a collection with a
different recorded model identity and re-embeds active canonical memories from
SQLite. SQLite remains authoritative if indexing or rebuilding fails.

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
