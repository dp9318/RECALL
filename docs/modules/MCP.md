# RECALL MCP / OpenCode Integration

## Implemented tools

The stdio MCP adapter in `recall_mcp/` delegates to an explicitly injected
`core.recall_core.MemoryManager`:

| Tool | Core operation |
| --- | --- |
| `recall_search` | `MemoryManager.retrieve(RetrievalRequest(...))` |
| `recall_get_context` | `MemoryManager.assemble_context(ContextAssemblyRequest(...))` |
| `recall_save_memory` | `MemoryManager.create_memory(MemoryCreateRequest(...))` |

Each tool requires a project UUID; an optional session UUID is checked against
that project's session by Core before use. Search and context results contain
the existing memory contracts, including IDs, status, scope, timestamps, and
provenance. Scores are omitted because the current Core retrieval contract does
not return per-memory scores. Invalid inputs and failed Core operations are MCP
tool errors, not success-shaped fallback data.

The adapter does not implement storage, retrieval, or conflict policy. It does
not expose conflict-resolution tools because there is not yet a complete safe
Core operation that selects and persists a conflict resolution.

## Current implementation status and blocker

The repository currently has Core orchestration and a default retrieval
implementation, plus SQLite connection/schema/migration utilities. It does not
have concrete implementations of the project, session, memory, custom
instruction, semantic-index repositories, or Unit of Work. Consequently this
checkout has no real Core composition factory, so it cannot provide durable
save/search/context flows end-to-end. The MCP server deliberately requires a
real factory and refuses to start without one; it never substitutes sample or
in-memory records.

Once a concrete composition exists, expose a callable that constructs and
returns `MemoryManager`, then point `RECALL_CORE_FACTORY` at it in
`package.module:factory` form. The returned manager owns its real repositories
and services. Do not place SQL, ChromaDB calls, or another memory store in the
factory or MCP handlers.

## Install and run

From the repository root, create/activate a virtual environment as appropriate
for the environment, then install the editable project and optional MCP/test
dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "core[mcp,test]"
```

`recall-mcp` runs the local MCP server over stdio. It requires
`RECALL_CORE_FACTORY` to name the application-owned factory described above:

```bash
export RECALL_CORE_FACTORY="your_application.bootstrap:create_memory_manager"
recall-mcp
```

The factory value above is a placeholder, not an included RECALL module: no
concrete storage composition currently exists in this repository. Until one is
provided, startup exits with an explicit diagnostic. Do not configure OpenCode
to point at a guessed database path or claim persistence has been initialized.

## OpenCode configuration

OpenCode supports local MCP servers using a `type: "local"` configuration with
a command array and optional environment map. After a real Core factory is
available, add the following to the project `opencode.json` (substitute the
actual absolute interpreter path and factory import path):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "recall": {
      "type": "local",
      "command": ["/absolute/path/to/RECALL/.venv/bin/recall-mcp"],
      "environment": {
        "RECALL_CORE_FACTORY": "your_application.bootstrap:create_memory_manager"
      },
      "enabled": true
    }
  }
}
```

Use the interpreter/entry point installed by the environment where
`core[mcp]` was installed. Restart OpenCode after changing its config; the
`recall_search`, `recall_get_context`, and `recall_save_memory` tools should
then appear in its MCP tool list. If they do not, check that the command is
executable in the activated environment and inspect OpenCode's MCP startup
diagnostics. The MCP server uses stdio, so it must not print application output
to stdout.

After the real Core composition is in place, verify the flow with these tools:

1. Call `recall_save_memory` with the selected `project_id` and content.
2. Call `recall_search` with the same project and a matching query.
3. Call `recall_get_context` with the same project and inspect memory provenance
   and custom instructions.

The current repository cannot complete this end-to-end flow until concrete
repositories/Unit of Work and their composition are implemented. Automated
adapter tests use mocked Core boundaries and are not persistence integration
tests.

## Validation

```bash
python -m pytest core/tests -q
```

This repository also has a top-level `tests/test_contracts.py` and
`core/tests/test_contracts.py` with the same import name; running pytest over
the entire repository currently causes a collection import mismatch. The
documented Core test command avoids that pre-existing collection issue.
