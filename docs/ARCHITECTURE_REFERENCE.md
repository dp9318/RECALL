# RECALL_V2 — Architecture Reference and Alignment

## Visual Reference

The file `docs/architecture-overview.png` is the architecture image reviewed in the current project context.

It correctly captures the core ideas already approved:

- OpenCode as the AI coding-agent host;
- RECALL as a Python MCP/service layer;
- SQLite as canonical source of truth;
- ChromaDB as a derived semantic index;
- a local 1B–3B LLM for bounded conflict resolution;
- explicit custom-instruction management;
- retrieval → conflict resolution → context assembly.

## Approved Update: Human Dashboard

The architecture is now approved with one additional first-class client surface that the original image does not show completely:

```text
                 ┌──────────────────────────────┐
                 │        CLIENT SURFACES       │
                 │                              │
                 │ OpenCode / MCP / /recall     │
                 │ Web Dashboard / Chat-like UI │
                 └──────────────┬───────────────┘
                                │
                      ┌─────────┴─────────┐
                      │                   │
                     MCP              HTTP/JSON
                      │                   │
                      └─────────┬─────────┘
                                ▼
                     ┌──────────────────────┐
                     │      RECALL CORE     │
                     │       Python         │
                     └──────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         ┌─────────┐       ┌──────────┐     ┌──────────┐
         │ SQLite  │       │ ChromaDB │     │ Local    │
         │ truth   │──────▶│ derived  │     │ 1B–3B    │
         │         │       │ index    │     │ resolver  │
         └─────────┘       └──────────┘     └──────────┘
```

The dashboard is intentionally **not** another backend or another data store. It is a human-facing client similar in interaction style to a ChatGPT wrapper.

## Dashboard Scope

The MVP dashboard should provide:

- Chat / Ask RECALL;
- Memory Explorer;
- Conflict Center;
- Custom Instructions management;
- Session/usage overview;
- project/context selection.

All dashboard mutations go through RECALL domain/API services.

## Authority

When the image and written project documents disagree, the written documents and `AGENTS.md` are authoritative. The image is a visual communication aid, not a source of schema truth.
