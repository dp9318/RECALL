---
description: Operate the RECALL persistent memory layer and its managed commands
---

The user invoked `/recall $ARGUMENTS`.

Supported operations include:

- `compact` — compact eligible context while preserving canonical history and lineage.
- `update-context` — persist explicit durable project context.
- `custom-instructions` — list/view, create, update, and delete user-authored custom instructions.
- `search <query>` — retrieve relevant persistent memories.
- `list` — list managed memories or other supported records.
- `delete <id>` — delete/deactivate the explicitly identified managed record.
- `stats` — show supported memory/index/session statistics.

Rules:

1. Use RECALL core/domain operations; never bypass them to edit SQLite or ChromaDB directly.
2. Treat SQLite as canonical and ChromaDB as derived.
3. Treat explicit custom instructions as higher authority than inferred memories.
4. For ambiguous custom-instruction update/delete requests, list current instructions first and request clarification rather than guessing.
5. If a requested capability is not implemented, report that honestly.
6. Do not simulate successful persistence when a backend operation failed.
7. Preserve source/lineage identifiers in results when available.
8. Allow unresolved conflict results; do not fabricate certainty.
