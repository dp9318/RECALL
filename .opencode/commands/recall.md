---
description: Operate the RECALL persistent memory layer and its managed commands
---

The user invoked `/recall $ARGUMENTS`.

Operations currently backed by the configured RECALL MCP server:

- `search <query>` — call `recall_search` to retrieve relevant persistent
  memories.
- `get-context` — call `recall_get_context` to assemble project context and
  return its active memories and instructions.
- `save-memory` — call `recall_save_memory` to persist a user-authored project
  memory.
- `update-context` — call `recall_update_context` to persist an explicit
  project or global context update.
- `compact` — call `recall_compact` to compact a project's memories.
- `custom-instructions` — use `recall_list_custom_instructions`,
  `recall_create_custom_instruction`, `recall_update_custom_instruction`, or
  `recall_delete_custom_instruction`.

Rules:

1. Use the corresponding `recall_*` MCP tool for each supported operation.
2. Require a selected project for project memory operations; context updates may omit project scope for global context.
3. Custom instructions support `global` and `project` scope. Project-scoped creation requires the selected project.
4. Do not bypass RECALL Core to edit SQLite or ChromaDB directly.
5. Treat SQLite as canonical and ChromaDB as derived.
6. Treat explicit custom instructions as higher authority than inferred memories.
7. Do not simulate successful persistence when a backend operation failed.
8. Preserve source/lineage identifiers in results when available.
9. Allow unresolved conflict results; do not fabricate certainty.
