# RECALL MCP / OpenCode Integration

## Public tools

The stdio MCP adapter in `recall_mcp/` delegates to an explicitly injected
`core.recall_core.MemoryManager`. All nine tools return structured JSON data;
invalid inputs, missing records, and failed Core operations are MCP tool
errors.

| Tool | Core operation | Inputs | Structured output |
| --- | --- | --- | --- |
| `recall_search` | `MemoryManager.retrieve(RetrievalRequest(...))` | `query: string`, `project_id: UUID`, optional `session_id: UUID`, `limit: int` (1–50, default 10) | `query`, `project_id`, `session_id`, `total_found`, `memories[]` |
| `recall_get_context` | `MemoryManager.assemble_context(ContextAssemblyRequest(...))` | `project_id: UUID`, optional `session_id: UUID`, optional `query: string`, `limit: int` (1–50, default 10), `include_historical: bool` (default false) | Serialized `AssembledContext` |
| `recall_save_memory` | `MemoryManager.create_memory(MemoryCreateRequest(...))` | `content: string`, `project_id: UUID`, optional `session_id: UUID`, `memory_type: string` (default `general`) | `memory`, `metadata` |
| `recall_update_context` | `MemoryManager.update_context(UpdateContextRequest(...))` | `content: string`, optional `project_id: UUID`, optional `session_id: UUID`, `memory_type: string` (default `context_update`), `provenance: string` (default `user_explicit`) | `memory_id`, `success`, `error` |
| `recall_compact` | `MemoryManager.compact(CompactRequest(...))` | `project_id: UUID`, optional `session_id: UUID`, `preserve_lineage: true` (default true; false is rejected because lineage is mandatory), `max_active_memories: positive int` (default 50) | `compacted_count`, `superseded_count`, `archived_count`, `preserved_count`, `errors[]` |
| `recall_list_custom_instructions` | `MemoryManager.list_instructions(CustomInstructionListParams(...))` | optional `scope` (`global`/`project`), optional `project_id: UUID`, optional `status` (`active`/`inactive`/`deleted`), `limit: int` (1–50, default 50), `offset: non-negative int` (default 0) | `instructions[]`, `count` (number in returned page) |
| `recall_create_custom_instruction` | `MemoryManager.create_instruction(CustomInstructionCreateRequest(...))` | `content: string`, `scope` (`global`/`project`, default `global`), optional `project_id: UUID` for project scope, optional `metadata: object` | `instruction` |
| `recall_update_custom_instruction` | `MemoryManager.update_instruction(id, CustomInstructionUpdateRequest(...))` | `instruction_id: UUID`; at least one of optional `content: string`, `status` (`active`/`inactive`/`deleted`), `metadata: object` | `instruction` |
| `recall_delete_custom_instruction` | `MemoryManager.delete_instruction(id)` | `instruction_id: UUID` | `instruction_id`, `deleted: true` |

Memory and instruction objects serialize existing public dataclass fields:
IDs, scope, content, status, timestamps, provenance/version, metadata, and
supported lineage fields. UUIDs become strings, enums become their values,
and timestamps use ISO 8601. Search scores are omitted because the Core
retrieval contract has no per-memory score field.

Search, save, context, and compaction require an existing project UUID. Any
supplied session must exist and belong to that project; it provides Core
session context but does not make context assembly or compaction
session-exclusive. Project context includes active project memories and active
global memories, excluding other projects. Context assembly includes active
global and matching project instructions.

Context update permits project or global scope; a session requires a project.
Core assigns `Scope.PROJECT` when `project_id` is supplied and `Scope.GLOBAL`
otherwise, and persists its existing `explicit_update` metadata. Compaction
selects the oldest active project memories above the configured cap and
replaces the selected group with one active summary. Each source remains in
SQLite as superseded history and has a canonical `memory_lineage` relationship
to the summary. `preserve_lineage` remains in the request for compatibility,
but only `true` is accepted: the PRD requires canonical history and lineage to
be retained, so disabling lineage is unsupported. A successful compaction
does not exceed the configured active-memory cap; a repeated request at or
below the cap creates no additional summary. `preserved_count` reports the
active-memory count after the operation, including the generated summary.

Instruction creation defaults to global scope; project scope requires an
existing `project_id`, while global scope rejects one. Listing uses the filters
supported by `CustomInstructionListParams`; project filtering is literal and
does not implicitly include global instructions. Context assembly is the
operation that combines global and project instructions. Instruction updates
may change content, status, and metadata, but not scope/project association.
Delete uses Core's existing deactivation behavior. Empty results return
`{"instructions": [], "count": 0}`. Compaction preserves Core's `errors[]`
for partial operation failures.

Text inputs are trimmed and validated; memory/context content is limited to
10,000 characters, queries to 1,000, memory types to 64, and provenance to
128. Instruction list page size is limited to 50. The adapter does not
implement persistence, retrieval, instruction, compaction, or conflict
business logic. It exposes no conflict-resolution tool; conflict resolution
remains advisory and outside this interface.

## Composition and persistence

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
composition by default. `RECALL_CORE_FACTORY` is optional; set it only when an
application needs to override that composition with its own zero-argument
factory.

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
a command array and optional environment map. Add the following to the project
`opencode.json`, substituting the actual absolute path to the installed
`recall-mcp` entry point:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "recall": {
      "type": "local",
      "command": ["/absolute/path/to/RECALL/.venv/bin/recall-mcp"],
      "enabled": true
    }
  }
}
```

The default Core composition needs no application-supplied factory. If an
application override is needed, add an `"environment"` map containing
`"RECALL_CORE_FACTORY": "package.module:factory"`; the factory path must refer
to an importable application factory returning a `MemoryManager`. Use the
entry point installed by the environment where `core[mcp]` and
`core[semantic]` were installed. Restart OpenCode after changing its config;
all nine tools in the table above should appear in its MCP tool list. If they
do not, check that the command is executable in the activated environment and
inspect OpenCode's MCP startup diagnostics. The MCP server uses stdio, so it
must not print application output to stdout.

Verify the flow with these tools:

1. Call `recall_save_memory` with the selected `project_id` and content.
2. Call `recall_search` with the same project and a matching query.
3. Call `recall_get_context` with the same project and inspect memory provenance
   and custom instructions.
4. Call `recall_update_context` or `recall_compact` for Core context lifecycle.
5. Use the four custom-instruction tools to list and manage instructions within
   their supported scope.

These setup instructions and the MCP SDK integration tests do not establish
that the OpenCode host itself has been launched or tested. Validate the
connection from OpenCode's own MCP tool list and diagnostics in the target
environment.

The built-in composition supports SQLite-backed memory persistence and local
semantic search/context flows when the semantic extra and model are available.
Automated adapter tests also exercise dependency injection with mocked Core
boundaries.

## Validation

```bash
python -m pytest core/tests -q
pytest -q
```

The first command runs the Core suite; the second runs the full repository
suite, including MCP protocol and composition tests. These test commands do
not substitute for an OpenCode-host integration test.
