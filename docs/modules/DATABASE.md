# RECALL — Database and Persistence Module Contract

## 1. Goal

Provide reliable canonical persistence in SQLite and a synchronized, 100% rebuildable derived vector index in ChromaDB.

---

## 2. Canonical SQLite Storage

SQLite is the sole authoritative store of record for RECALL. All entities, relationships, lineage graphs, and custom instructions originate and persist in SQLite.

### 2.1 Table Inventory & Schema Versioning (Schema Level 2)

Defined in `database/schema/ddl.py` and managed by `database/migrations/`:

| Table Name | Primary Key | Responsibilities & Invariants |
| :--- | :--- | :--- |
| `schema_version` | `version` (INT) | Migration audit log (`version`, `description`, `applied_at`). Current level: **2**. |
| `projects` | `project_id` (TEXT/UUID) | Isolated project namespaces (`name`, `description`, `status`, `metadata`). |
| `sessions` | `session_id` (TEXT/UUID) | Coding sessions tied to a project (`FOREIGN KEY (project_id) REFERENCES projects ON DELETE CASCADE`). |
| `memories` | `memory_id` (TEXT/UUID) | Durable knowledge claims (`scope`, `memory_type`, `content`, `status`, `provenance`, `supersedes_id`, `metadata`). Cascades on project delete. |
| `memory_lineage` | `lineage_id` (TEXT/UUID) | Directed acyclic graph recording predecessor/successor relationships (`parent_id`, `child_id`, `relationship`, `reason`). Cascades on memory delete. |
| `custom_instructions` | `instruction_id` (TEXT/UUID) | User-authored governing instructions (`scope`, `project_id`, `content`, `status`, `version`, `metadata`). |
| `memory_index_metadata` | `record_id` (TEXT/UUID) | Reserved for vector indexing provenance. |
| `instruction_index_metadata` | `record_id` (TEXT/UUID) | Reserved for vector indexing provenance. |

### 2.2 Relational & Deletion Semantics

1. **Foreign Key Cascade Deletion**:
   - `PRAGMA foreign_keys = ON` is enforced across all connections.
   - Deleting a project via `ProjectRepository.delete()` executes a **hard delete** (`DELETE FROM projects WHERE project_id = ?`).
   - SQLite automatically cascades deletion to all child sessions, project-scoped memories, project instructions, and lineage records.
2. **Soft Deletion for Memories & Instructions**:
   - Memories: Deleted via `UPDATE memories SET status = 'deleted', updated_at = ? WHERE memory_id = ?`. Standard queries (`search()`) exclude soft-deleted rows by default.
   - Custom Instructions: Deleted via `UPDATE custom_instructions SET status = 'deleted', updated_at = ? WHERE instruction_id = ?`. Standard listings filter `status != 'deleted'`.
3. **Scope CHECK Constraints**:
   - Both `memories` and `custom_instructions` enforce the invariant:
     `((scope = 'global' AND project_id IS NULL) OR (scope = 'project' AND project_id IS NOT NULL))`
4. **Partial Unique Index**:
   - SQLite partial unique index `idx_custom_instructions_unique_active_project` guarantees at most one active project-scoped instruction per project.

---

## 3. Concurrency & Connection Architecture

Managed in `database/connection.py`:

- **WAL Mode**: Initialized with `PRAGMA journal_mode = WAL` and `PRAGMA synchronous = NORMAL (2)`, enabling concurrent non-blocking readers alongside an active writer.
- **Busy Timeout**: Configured with `PRAGMA busy_timeout = 5000` to prevent immediate busy errors under write contention.
- **Thread Safety**: `ThreadSafeConnection` wraps the SQLite connection using a re-entrant lock (`threading.RLock()`), serializing queries within a process without requiring connection pooling.

---

## 4. Derived ChromaDB Semantic Index

Implemented in `database/repositories/semantic_index_repo.py`:

- **Derived State Invariant**: ChromaDB is an unauthoritative, derived index. Vector data is stored strictly to accelerate semantic similarity retrieval.
- **Selective Indexing**: Only memories with `status = 'active'` are vector-indexed. Historical (superseded/archived/deleted) memories are removed from ChromaDB to maintain semantic precision.
- **Complete Rebuildability**: At any time, `MemoryManager.rebuild_semantic_index()` can wipe and repopulate the vector index from active SQLite rows.
- **Fault Tolerance**: If vector indexing fails during memory creation or update, the canonical SQLite transaction is committed safely, and an indexing warning is surfaced.
