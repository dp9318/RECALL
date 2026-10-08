# RECALL — Architecture Reference

## Visual Reference

`docs/architecture-overview.png` is the current visual reference generated from the approved architecture direction.

## Approved Architecture

The image captures the following core relationships:

- OpenCode is an agent-facing client.
- A web dashboard is a human-facing client.
- Both communicate with the RECALL Core through separate adapters.
- SQLite is canonical.
- ChromaDB is derived.
- A local 1B–3B model handles bounded conflict arbitration.
- Custom instructions are user-managed canonical state.

## Written Authority

The written architecture in `docs/ARCHITECTURE.md`, root `AGENTS.md`, and supporting contracts is authoritative if the image omits an implementation detail.

## Important Clarification

The local 1B–3B model in the visual architecture is **not** the general response model for a ChatGPT-style dashboard. It exists specifically to arbitrate ambiguous memory conflicts. A future general response model may be integrated as a separate concern only through an explicit architecture change.
