# OpenCode Implementation Instruction: DATABASE / PERSISTENCE Module

## Mission

Implement the RECALL Database/Persistence module per the locked architecture. SQLite is the canonical source of truth. ChromaDB is a derived semantic index that must be rebuildable from SQLite. The module must expose clean repository interfaces to the rest of the system.

---

## Step 1: Inspect and Read All Contracts

Before writing any code, read and internalize these documents:

- `AGENTS.md` (project instructions)
- `docs/ARCHITECTURE.md` (system architecture)
- `docs/PRD.md` (product requirements)
- `docs/DESIGN.md` (product/interaction design)
- `docs/TECH_STACK.md` (technology stack)
- `docs/DEVELOPMENT_RULES.md` (development rules)
- `docs/CONTRACTS.md` (cross-module contracts)
- `docs/MODULE_OWNERSHIP.md` (module boundaries)
- `docs/modules/DATABASE.md` (database module contract)
- `docs/REPOSITORY_LAYOUT.md` (repository structure)

**Critical**: Understand that you own `database/` directory. You do NOT own UI behavior, conflict policy, dashboard state, or OpenCode command semantics.

---

## Step 2: Create the Database Module Structure

Create the following directory structure under `database/`:

```
database/
├── __init__.py
├── config.py              # Database configuration
├── connection.py          # SQLite connection management
├── migrations/
│   ├── __init__.py
│   ├── manager.py         # Migration runner
│   └── versions/          # Individual migration files
├── schema/
│   ├── __init__.py
│   ├── ddl.py             # CREATE TABLE statements
│   └── indexes.py         # Index definitions
├── repositories/
│   ├── __init__.py
│   ├── base.py            # Base repository interface
│   ├── project_repo.py
│   ├── session_repo.py
│   ├── message_repo.py
│   ├── memory_repo.py
│   ├── memory_lineage_repo.py
│   ├── custom_instruction_repo.py
│   └── metadata_repo.py
├── chroma/
│   ├── __init__.py
│   ├── client.py          # ChromaDB client wrapper
│   ├── indexer.py         # Indexing operations
│   ├── rebuild.py         # Full rebuild from SQLite
│   └── health.py          # Health/status reporting
├── contracts.py           # Shared DTOs for this module
└── exceptions.py          # Module-specific exceptions
```

---

## Step 3: Implement SQLite Schema (DDL)

Create `database/schema/ddl.py` with complete schema covering ALL required domains:

### Required Tables

1. **projects**
   - `project_id` (PK, stable UUID)
   - `name`, `description`
   - `created_at`, `updated_at`
   - `status` (active/archived)

2. **sessions**
   - `session_id` (PK, stable UUID)
   - `project_id` (FK)
   - `started_at`, `ended_at`
   - `status` (active/completed/abandoned)
   - `metadata` (JSON)

3. **messages / events**
   - `event_id` (PK, stable UUID)
   - `session_id` (FK)
   - `sequence` (ordering)
   - `role` (user/assistant/system/tool)
   - `content` (text)
   - `metadata` (JSON)
   - `created_at`

4. **memories**
   - `memory_id` (PK, stable UUID)
   - `project_id` (FK, nullable for global)
   - `session_id` (FK, nullable)
   - `memory_type` (fact/decision/preference/context/etc.)
   - `content` (text)
   - `status` (active/superseded/archived/deleted)
   - `provenance` (source: user/explicit/extracted/inferred)
   - `confidence` (0.0-1.0)
   - `created_at`, `updated_at`
   - `valid_from`, `valid_until` (temporal validity)

5. **memory_lineage / supersession**
   - `lineage_id` (PK)
   - `supersedes_memory_id` (FK)
   - `superseded_by_memory_id` (FK)
   - `reason` (explicit_user_update/auto_compaction/conflict_resolution/etc.)
   - `created_at`
   - Supports full version chain traversal

6. **custom_instructions** (FIRST-CLASS - per PRD/Architecture)
   - `instruction_id` (PK, stable UUID)
   - `scope` (ENUM: 'global', 'project')
   - `project_id` (FK, NULL when global)
   - `content` (text)
   - `active` (boolean)
   - `version` (integer, increments on update)
   - `created_at`, `updated_at`
   - `created_by` (user identifier)
   - `metadata` (JSON for future extensibility)
   - **Unique constraint**: (scope, project_id) when active=true for project scope

7. **index_metadata** (for ChromaDB sync tracking)
   - `record_type` (memory/custom_instruction)
   - `record_id` (FK to canonical)
   - `chroma_id` (ChromaDB document ID)
   - `indexed_at`
   - `embedding_model` (model identifier)
   - `content_hash` (for change detection)

### Requirements

- Use explicit foreign keys with `ON DELETE CASCADE` / `SET NULL` where appropriate
- Add indexes for common lookups: project_id, session_id, memory_type, status, scope, active
- Use transactions for atomic multi-step changes
- All IDs: stable UUIDs (generate in application, not DB)
- Timestamps: UTC ISO8601 with timezone
- Status fields: use CHECK constraints for valid values

---

## Step 4: Implement Migrations

Create `database/migrations/manager.py` with:

- Migration version tracking table (`schema_version`)
- Up-only migrations (no down migrations needed for MVP)
- Each migration: version number, description, SQL
- Idempotent execution (safe to re-run)
- Transaction per migration

Initial migration (`001_initial_schema.sql`): All tables from Step 3.

Future migrations go in `database/migrations/versions/`.

---

## Step 5: Implement Connection Management

Create `database/connection.py`:

- `DatabaseConfig` dataclass (path, pragmas, timeout)
- `get_connection()` context manager
- `initialize_database(config)` - runs migrations on first connect
- Connection pooling if needed (SQLite: single writer, multiple readers)
- Pragmas: `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`

---

## Step 6: Implement Repository Interfaces

Create `database/repositories/base.py` with abstract base:

```python
class Repository(Protocol):
    def create(self, entity) -> Entity: ...
    def get(self, id) -> Optional[Entity]: ...
    def update(self, entity) -> Entity: ...
    def delete(self, id) -> bool: ...
    def list(self, filters) -> List[Entity]: ...
```

Implement concrete repositories in each `*_repo.py`:

- **ProjectRepository**: CRUD + list by status
- **SessionRepository**: CRUD + list by project, active session lookup
- **MessageRepository**: append, get by session, range queries
- **MemoryRepository**: CRUD + list by project/type/status + temporal queries
- **MemoryLineageRepository**: add_supersession, get_chain, get_superseded_by
- **CustomInstructionRepository**: 
  - CRUD (create, get, update, delete)
  - `list_active(scope, project_id=None)` - returns active instructions in precedence order
  - `get_by_scope(scope, project_id)` 
  - `deactivate(instruction_id)` - soft delete (active=false)
  - `activate(instruction_id)` - with mutual exclusion for project scope
- **MetadataRepository**: index tracking for ChromaDB sync

**Key rule**: Repositories expose domain objects, not raw rows. No SQL in callers.

---

## Step 7: Implement ChromaDB Infrastructure (Derived Layer Only)

Create `database/chroma/`:

### `client.py`
- Wrapper around `chromadb.Client`
- Collection management (one collection per record type or unified)
- Connection config (path, host/port for client-server mode)

### `indexer.py`
- `index_memory(memory: Memory, embedding: List[float])` - upsert
- `index_custom_instruction(instruction: CustomInstruction, embedding: List[float])` - upsert
- `remove_memory(memory_id)` - delete by canonical ID
- `remove_custom_instruction(instruction_id)` - delete by canonical ID
- Store canonical IDs in metadata: `{"canonical_id": "...", "record_type": "memory|instruction"}`

### `rebuild.py`
- `rebuild_all()` - full rebuild from SQLite
  - Query all active memories + custom instructions from repositories
  - Generate embeddings (delegate to intelligence module via callback/interface)
  - Bulk upsert to ChromaDB
  - Update `index_metadata` table
- `rebuild_incremental(since_timestamp)` - optional optimization
- Must be callable independently (CLI, API, startup)

### `health.py`
- `get_status()` - returns: indexed_count, last_rebuild, embedding_model, errors
- `verify_integrity()` - sample check: canonical IDs exist in SQLite

**Critical**: ChromaDB never decides correctness. It only accelerates semantic search. All canonical operations go through SQLite repositories.

---

## Step 8: Define Module Contracts

Create `database/contracts.py` with Pydantic models matching `docs/CONTRACTS.md`:

```python
class MemoryContract(BaseModel):
    memory_id: UUID
    project_id: Optional[UUID]
    memory_type: str
    content: str
    status: Literal["active", "superseded", "archived", "deleted"]
    provenance: str
    confidence: float
    created_at: datetime
    updated_at: datetime
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]

class CustomInstructionContract(BaseModel):
    instruction_id: UUID
    scope: Literal["global", "project"]
    project_id: Optional[UUID]
    content: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: str
```

---

## Step 9: Write Tests

Create tests in `tests/database/`:

### Unit Tests (per repository)
- `test_project_repo.py`
- `test_session_repo.py`
- `test_memory_repo.py`
- `test_memory_lineage_repo.py`
- `test_custom_instruction_repo.py` - **CRITICAL**: test CRUD, scope precedence, mutual exclusion
- `test_metadata_repo.py`

### Integration Tests
- `test_migrations.py` - apply all migrations, verify schema
- `test_transactions.py` - multi-step atomic operations
- `test_chroma_rebuild.py` - rebuild from SQLite, verify counts match
- `test_chroma_sync.py` - index/update/remove operations

### Contract Tests
- `test_contracts.py` - verify repository returns match contract schemas

### Test Requirements
- Use temporary SQLite databases (file or `:memory:`)
- Use temporary ChromaDB directories
- Test foreign key enforcement
- Test cascade behavior
- Test unique constraint on active project-scoped custom instructions
- Test lineage chain traversal

---

## Step 10: Update Documentation

After implementation, update:

- `docs/modules/DATABASE.md` - document actual schema, repositories, ChromaDB utilities
- Add migration history to `docs/modules/DATABASE.md`
- If any contract changed, update `docs/CONTRACTS.md` and note in commit message

---

## Step 11: Verify Integration Requirements

Before reporting complete, verify:

1. **Core Memory Manager** can import and use repositories:
   ```python
   from database.repositories import MemoryRepository, CustomInstructionRepository
   ```

2. **Retrieval/Conflict modules** can use ChromaDB indexer via interface:
   ```python
   from database.chroma import Indexer, Rebuilder
   ```

3. **API/MCP adapters** can call repository methods without knowing SQL

4. **No raw SQL** escapes the `database/` module

5. **Custom instructions** support:
   - List/view (with scope filtering)
   - Create (global + project scope)
   - Update (version increment)
   - Delete (soft delete via active=false)
   - Precedence: global < project (project overrides)

6. **ChromaDB rebuild** works from fresh SQLite:
   - `python -m database.chroma.rebuild` works standalone

---

## CRITICAL RULES - DO NOT VIOLATE

| Rule | Enforcement |
|------|-------------|
| SQLite is canonical truth | All writes go through repositories; ChromaDB only receives derived data |
| ChromaDB rebuildable | `rebuild_all()` uses ONLY repository queries, never ChromaDB state |
| Custom instructions first-class | Full CRUD + scope in SQLite; never auto-overwritten |
| No cross-module bleeding | Repositories return contracts, not ORM models; no SQL in core/intelligence/api |
| No commits | **DO NOT COMMIT OR PUSH ANY CHANGES** |

---

## Reporting Requirements

When implementation and tests pass, STOP and report:

1. **Files created/changed** (list with paths)
2. **Schema/interface changes** (DDL, repository methods, contract models)
3. **Test results** (which tests pass, coverage notes)
4. **Integration requirements** (what other modules need to consume)
5. **Any cross-module contract issues** discovered (STOP and report these rather than silently changing)

---

## Final Reminder

**DO NOT COMMIT OR PUSH ANY CHANGES.**

Stop after implementation and testing and report the files changed, schema/interface changes, tests/results, and any integration requirements. The work must be reviewed and approved by Dipankar before any commit is made.