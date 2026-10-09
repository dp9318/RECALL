# RECALL Implementation Audit

**Date:** 2026-10-09
**Audited branch:** `feature/mcp-opencode`
**Starting commit:** `7dcf479339bb867433324d69f3724ff6d54a9eca`

This status is based on the checked-out code and tests, not on this document's
previous revision.

## Component status

| Component | Current implementation | Status |
| --- | --- | --- |
| Shared contracts | DTOs and result types under `contracts/` | Implemented |
| Core orchestration | `MemoryManager`, context assembly, custom-instruction service | Implemented; depends on injected repositories/services |
| Database setup | SQLite connection, DDL, migrations | Utilities implemented |
| SQLite repositories / Unit of Work | Abstract contracts in `database/repositories.py`; no concrete adapters | Missing; no canonical persistence composition |
| Semantic index | Abstract `SemanticIndexRepository`; no ChromaDB adapter | Missing |
| Retrieval | `DefaultRetrievalService` supports structured and semantic-index delegation and ranking | Implemented, but requires repositories; semantic hits require an index |
| Embeddings | `DefaultEmbeddingService` uses a deterministic bag-of-words vector | Implemented baseline, not a semantic model |
| Conflict detection/resolution | Default detector, deterministic resolver, optional LLM adapter, abstention | Implemented; no production local-model adapter configured |
| MCP adapter | `recall_mcp.server` exposes search, context assembly, and save through injected Core | Implemented; requires an application-supplied Core factory |
| OpenCode MCP config | Documented local stdio configuration | Not verified against a running OpenCode client in this environment |
| REST API | No API routes found | Missing |

## MCP integration details

The MCP tools delegate to `MemoryManager.retrieve`,
`MemoryManager.assemble_context`, and `MemoryManager.create_memory`. They require
a project UUID, verify an optional session belongs to that project, and return
Core contract data including scope and provenance. Adapter tests exercise MCP
tool discovery and requests through the SDK's in-memory client/server protocol.

There is no concrete repository/Unit of Work implementation or Core
composition/bootstrap in this checkout. Therefore the MCP adapter cannot start
with a usable Core until an application provides a factory that returns a real
`MemoryManager`. The adapter intentionally does not supply an in-memory demo or
claim that saved memories persist.

See [the MCP module guide](modules/MCP.md) for installation, OpenCode
configuration, tool details, and setup limitations.

## Test evidence and limitations

The Core test suite, including mocked MCP adapter tests, passes with:

```bash
python -m pytest core/tests -q
```

The adapter tests use mocked Core boundaries; they are not database or semantic
retrieval integration tests. There is no verified SQLite close/reopen flow,
ChromaDB rebuild, real-embedding retrieval, configured local-model arbitration,
or OpenCode-connected save/search/context flow.

Running pytest over the repository root currently fails collection because
`tests/test_contracts.py` and `core/tests/test_contracts.py` import under the
same module name. The module-level Core test command avoids that pre-existing
collection collision.

## Remaining integration blockers

1. Implement concrete SQLite repositories and a Unit of Work, then provide a
   Core composition factory.
2. Implement a ChromaDB semantic index adapter and rebuild/health integration.
3. Configure and validate an optional local-model adapter if LLM arbitration is
   required.
4. Add the dashboard HTTP/JSON API.
5. Run the MCP server against the real composition and verify OpenCode
   discovery and save → search → context end-to-end.
