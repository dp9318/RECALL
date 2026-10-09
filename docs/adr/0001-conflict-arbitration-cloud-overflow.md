# ADR 0001 — Conflict Arbitration Cloud Overflow Fallback

## Status

Proposed for Dipankar review.

## Context

The approved conflict lifecycle uses deterministic precedence first, then
local-model arbitration for residual ambiguity. The local model must not write
canonical memory state. A strict local context limit can prevent arbitration
even when a cloud model could process the bounded evidence.

Cloud APIs do not share interchangeable credentials or request formats. The
repository had no concrete local runtime adapter or cloud adapter.

## Decision

- Keep SQLite as canonical memory state and conflict arbitration advisory.
- Use Ollama as the default local arbitration adapter.
- Support native OpenAI, Anthropic, and Google Gemini APIs as optional cloud
  overflow adapters.
- Use cloud arbitration only when Ollama reports that its context window was
  exceeded and a cloud provider, model, and API key are explicitly configured.
- Send only complete evidence packages up to 16,000 characters; do not truncate
  evidence, and skip model arbitration when the package exceeds this bound.
- Do not send evidence to cloud for local connection, model, or response errors.
- Validate model outcomes and candidate identifiers before returning them.
- Do not persist conflict decisions or apply suggested memory status or lineage
  changes automatically.
- Keep conflict detection and arbitration explicitly invoked; do not trigger
  resolution automatically during memory create/update or context assembly.

## Alternatives Considered

- Local-only arbitration: preserves the prior runtime boundary but cannot
  recover from a local context-window limit.
- Cloud fallback on any local error: would disclose evidence more broadly and
  obscure local runtime failures.
- One OpenAI-compatible wire adapter: does not support native Anthropic or
  Gemini APIs and cannot use their API keys interchangeably.
- Persist/apply model decisions: requires a reviewed conflict lifecycle,
  persistence contract, and user acceptance workflow not currently defined.

## Consequences

- Local operation remains the default; Ollama and the selected model must be
  installed separately.
- Cloud fallback is opt-in and transmits bounded memory evidence to the
  configured vendor only on a typed local context-window overflow.
- Each supported cloud provider requires its own native request/response
  adapter and API key.
- Arbitrary cloud APIs are not automatically compatible. New vendors require
  an adapter and tests.
- Conflict outcomes remain recommendations. A separate approved design is
  required before persisting or applying them.

## Configuration

- `RECALL_LOCAL_LLM_MODEL`, `RECALL_LOCAL_LLM_BASE_URL`,
  `RECALL_LOCAL_LLM_TIMEOUT`
- `RECALL_CONFLICT_CLOUD_PROVIDER`, `RECALL_CONFLICT_CLOUD_MODEL`,
  `RECALL_CONFLICT_CLOUD_API_KEY`
- Optional `RECALL_CONFLICT_CLOUD_BASE_URL`,
  `RECALL_CONFLICT_CLOUD_TIMEOUT`
