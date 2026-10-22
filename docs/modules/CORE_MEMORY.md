# RECALL — Core Memory Manager Module Contract

## 1. Goal

Implement the central domain application behavior of RECALL, encapsulating all persistence, retrieval, conflict resolution, instruction precedence, and context assembly behind an authoritative public facade: `MemoryManager`.

---

## 2. Architectural Responsibilities

The Core module (`recall_core/`) sits between client adapters (`api/`, `recall_mcp/`) and persistence/intelligence infrastructure:

```text
       Client Adapters (api/, recall_mcp/)
                      ↓
           recall_core.MemoryManager
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
ContextAssembly  Instruction    ConflictResolver
        │             │             │
        └─────────────┼─────────────┘
                      ▼
            SQLiteUnitOfWork
        ┌─────────────┴─────────────┐
        ▼                           ▼
SQLite Repositories       ChromaDB Semantic Index
```

### Public Facade Operations (`MemoryManager`):
1. **Memory Lifecycle**:
   - `create_memory(request: MemoryCreateRequest) -> Result[Memory]`
   - `get_memory(memory_id: UUID) -> Result[Optional[Memory]]`
   - `update_memory(memory_id: UUID, request: MemoryUpdateRequest) -> Result[Optional[Memory]]`
   - `delete_memory(memory_id: UUID) -> Result[bool]` (soft-delete with Chroma vector cleanup)
   - `get_memory_lineage(memory_id: UUID) -> Result[list[MemoryLineage]]`
   - `search_memories(params: MemorySearchParams) -> Result[list[Memory]]`
   - `search_memories_paginated(params: MemorySearchParams) -> Result[PaginatedResult[Memory]]`
2. **Project & Session Lifecycle**:
   - `create_project`, `get_project`, `list_projects_paginated`, `delete_project` (cascades)
   - `create_session`, `get_session`, `list_sessions_paginated`
   - `get_project_memory_count`, `get_project_session_count`, `get_session_memory_count`
3. **Retrieval & Context Assembly**:
   - `retrieve(request: RetrievalRequest) -> Result[RetrievalResult]`
   - `assemble_context(request: ContextAssemblyRequest) -> Result[AssembledContext]`
   - `compact(request: CompactRequest) -> Result[CompactResult]`
4. **Custom Instructions**:
   - Delegated to `CustomInstructionService`: `create_instruction`, `get_instruction`, `update_instruction`, `delete_instruction`, `list_instructions`, `get_active_instructions`
5. **Conflict Resolution & Semantic Maintenance**:
   - `detect_and_resolve_conflicts(project_id: Optional[UUID]) -> Result[Optional[ConflictResolutionResult]]`
   - `rebuild_semantic_index() -> Result[int]` (rebuilds ChromaDB from active SQLite rows)
   - `get_stats(project_id: Optional[UUID]) -> Result[dict]`

---

## 3. Authority & Precedence Enforcement

The Core enforces an absolute authority hierarchy during context retrieval and conflict arbitration:

```text
Explicit user custom instruction
        ↓
Explicit user update / supersession
        ↓
Current valid canonical memory
        ↓
Older historical memory
        ↓
Local 1B–3B model arbitration for residual ambiguity
        ↓
Unresolved / abstain
```

- **Deterministic First**: Precedence rules are evaluated deterministically before any model invocation.
- **Model Invariant**: Local LLM is strictly advisory. Neither local nor cloud models can directly mutate canonical storage or override user instructions.
- **Non-Hallucination**: When ambiguity remains unresolvable, the system returns `unresolved` rather than fabricating certainty.

---

## 4. Encapsulation & Client Invariant

Client surfaces (`api/` and `recall_mcp/`) must strictly interact with `MemoryManager`. Direct access to private attributes (`_uow`) or underlying repository classes is strictly prohibited and continuously enforced via AST regression tests.
