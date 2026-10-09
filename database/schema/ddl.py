"""SQLite DDL statements for RECALL schema."""

from __future__ import annotations

CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE
);
"""

CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT,
    session_id TEXT,
    scope TEXT NOT NULL DEFAULT 'global' CHECK (scope IN ('global', 'project')),
    memory_type TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'archived', 'deleted')),
    provenance TEXT,
    supersedes_id TEXT,
    valid_from TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE SET NULL,
    FOREIGN KEY (supersedes_id) REFERENCES memories (memory_id) ON DELETE SET NULL,
    CHECK (
        (scope = 'global' AND project_id IS NULL) OR
        (scope = 'project' AND project_id IS NOT NULL)
    )
);
"""

CREATE_MEMORY_LINEAGE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_lineage (
    lineage_id TEXT PRIMARY KEY,
    parent_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'supersedes',
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES memories (memory_id) ON DELETE CASCADE,
    FOREIGN KEY (child_id) REFERENCES memories (memory_id) ON DELETE CASCADE,
    UNIQUE (parent_id, child_id)
);
"""

CREATE_CUSTOM_INSTRUCTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS custom_instructions (
    instruction_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project')),
    project_id TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'deleted')),
    version INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
    CHECK (
        (scope = 'global' AND project_id IS NULL) OR
        (scope = 'project' AND project_id IS NOT NULL)
    )
);
"""

CREATE_MEMORY_INDEX_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS memory_index_metadata (
    record_id TEXT PRIMARY KEY,
    chroma_id TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    embedding_model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES memories (memory_id) ON DELETE CASCADE
);
"""

CREATE_INSTRUCTION_INDEX_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS instruction_index_metadata (
    record_id TEXT PRIMARY KEY,
    chroma_id TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    embedding_model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES custom_instructions (instruction_id) ON DELETE CASCADE
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions (project_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions (status);",
    "CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories (project_id);",
    "CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories (session_id);",
    "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories (scope);",
    "CREATE INDEX IF NOT EXISTS idx_memories_status ON memories (status);",
    "CREATE INDEX IF NOT EXISTS idx_memories_memory_type ON memories (memory_type);",
    "CREATE INDEX IF NOT EXISTS idx_memories_supersedes_id ON memories (supersedes_id);",
    "CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);",
    "CREATE INDEX IF NOT EXISTS idx_memories_valid_from ON memories (valid_from);",
    "CREATE INDEX IF NOT EXISTS idx_memory_lineage_parent_id ON memory_lineage (parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_memory_lineage_child_id ON memory_lineage (child_id);",
    "CREATE INDEX IF NOT EXISTS idx_custom_instructions_scope ON custom_instructions (scope);",
    "CREATE INDEX IF NOT EXISTS idx_custom_instructions_project_id ON custom_instructions (project_id);",
    "CREATE INDEX IF NOT EXISTS idx_custom_instructions_status ON custom_instructions (status);",
    "CREATE INDEX IF NOT EXISTS idx_custom_instructions_active_project ON custom_instructions (project_id) WHERE scope = 'project' AND status = 'active';",
    "CREATE INDEX IF NOT EXISTS idx_custom_instructions_active_global ON custom_instructions (instruction_id) WHERE scope = 'global' AND status = 'active';",
    "CREATE INDEX IF NOT EXISTS idx_memory_index_metadata_chroma_id ON memory_index_metadata (chroma_id);",
    "CREATE INDEX IF NOT EXISTS idx_instruction_index_metadata_chroma_id ON instruction_index_metadata (chroma_id);",
]

ALL_TABLES = [
    CREATE_SCHEMA_VERSION_TABLE,
    CREATE_PROJECTS_TABLE,
    CREATE_SESSIONS_TABLE,
    CREATE_MEMORIES_TABLE,
    CREATE_MEMORY_LINEAGE_TABLE,
    CREATE_CUSTOM_INSTRUCTIONS_TABLE,
    CREATE_MEMORY_INDEX_METADATA_TABLE,
    CREATE_INSTRUCTION_INDEX_METADATA_TABLE,
]

SCHEMA_VERSION = 1