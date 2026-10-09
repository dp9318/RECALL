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

## Current implementation status and composition requirement

The repository includes concrete SQLite repositories for projects, sessions,
memories, and custom instructions, plus a SQLite Unit of Work. Core provides
`create_memory_manager` for the default composition. It initializes SQLite,
composes the local Sentence Transformers embedding function and Chroma semantic
index, and returns a `MemoryManager`. With no override, the CLI database is
stored at `~/.recall/recall.sqlite3`; its derived Chroma data is stored beside
that database. Applications can pass an explicit `DatabaseConfig` to this
factory when composing Core themselves.

Install the semantic dependencies along with MCP:

```bash
python -m pip install -e "core[mcp,semantic]"
```

The default embedding configuration is
`RECALL_EMBEDDING_PROVIDER=sentence-transformers`,
`RECALL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`, and
`RECALL_EMBEDDING_DEVICE=cpu`. Model files are loaded lazily and may be
downloaded on first semantic use. If the provider or model is unavailable, MCP
reports a semantic retrieval error; it does not claim a keyword result is
semantic. Structured-only retrieval remains available to callers that
explicitly disable semantic retrieval.

To reindex after changing the model, stop clients that write memories, create
the manager using the new embedding configuration, and call
`manager.rebuild_semantic_index()`. This explicit operation rebuilds the
derived Chroma collection from active SQLite memories. Always close the
manager afterward.

The factory should compose the existing repositories and services rather than
implementing their logic itself. Do not place SQL, ChromaDB calls, or another
memory store in the MCP handlers.

## Install and run

From the repository root, create/activate a virtual environment as appropriate
for the environment, then install the editable project and optional MCP/test
dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "core[mcp,semantic,test]"
```

`recall-mcp` runs the local MCP server over stdio and uses the built-in Core
composition by default. Set `RECALL_CORE_FACTORY` only when an application
needs to override that composition with its own zero-argument factory:

```bash
export RECALL_CORE_FACTORY="your_application.bootstrap:create_memory_manager"
recall-mcp
```

The factory value above is a placeholder, not an included RECALL module. If
the override is set, it must import successfully, return a `MemoryManager`, and
manage any configuration needed by its composition. Without an override, MCP
uses the default per-user SQLite database location described above. The
manager is closed when the MCP server exits.

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

Verify the flow with these tools:

1. Call `recall_save_memory` with the selected `project_id` and content.
2. Call `recall_search` with the same project and a matching query.
3. Call `recall_get_context` with the same project and inspect memory provenance
   and custom instructions.

The built-in composition supports SQLite-backed memory persistence and local
semantic search/context flows when the semantic extra and model are available.
Automated adapter tests also exercise dependency injection with mocked Core
boundaries.

## Validation

```bash
python -m pytest core/tests -q
```

This repository also has a top-level `tests/test_contracts.py` and
`core/tests/test_contracts.py` with the same import name; running pytest over
the entire repository currently causes a collection import mismatch. The
documented Core test command avoids that pre-existing collection issue.
