---
description: Use the RECALL memory layer and its supported command operations
---
You are operating on the RECALL_V2 project.

The user invoked `/recall $ARGUMENTS`.

Interpret the first token of `$ARGUMENTS` as the requested RECALL operation. Supported operations include:

- `compact` — compact/summarize eligible project context while preserving canonical history and lineage.
- `update-context` — persist or update durable project context based on the user's explicit request.
- `custom-instructions` — manage user-authored custom instructions. This operation must support view/list, create, update, and delete.
- `search <query>` — retrieve relevant persistent memories for the current project/context.
- `list` — list relevant memories or managed records using the available RECALL tools.
- `delete <id>` — delete/deactivate the explicitly identified managed record using the RECALL domain operation.
- `stats` — show RECALL memory/index/usage status if supported.

Rules:

1. Use the RECALL MCP/domain operations exposed by the project. Do not bypass the RECALL core to edit SQLite or ChromaDB directly.
2. If the requested operation is not implemented, say so clearly; do not simulate a successful memory operation.
3. For `custom-instructions`, preserve explicit user ownership and scope. List existing instructions before an update/delete when the identifier is ambiguous.
4. User-authored custom instructions are higher authority than inferred historical memory.
5. ChromaDB is derived state. SQLite is canonical.
6. Never let the local 1B–3B resolver silently override an explicit custom instruction.
7. If a conflict cannot be safely resolved from canonical evidence and deterministic rules, preserve an unresolved result rather than inventing certainty.
8. When returning memory, include source/lineage identifiers when available.
9. Keep responses concise and operational. Report what was actually performed, not what was intended.
10. If `$ARGUMENTS` is empty or ambiguous, show the supported `/recall` operations and ask for the missing operation only when necessary.
