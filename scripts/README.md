# RECALL Diagnostic and Benchmark Scripts

This directory contains standalone developer utilities, smoke tests, and performance benchmarking scripts.

## Scripts Overview

### 1. `list_projects.py`
Inspects the SQLite canonical storage and lists all registered projects.

```bash
# Uses default ~/.recall/recall.sqlite3 or RECALL_DB_PATH
python scripts/list_projects.py

# Or specify a custom database path:
python scripts/list_projects.py --db-path /path/to/custom.sqlite3
```

### 2. `smoke_test_mcp.py`
Directly exercises the FastMCP tool wrappers (`recall_search` and `recall_get_context`) against a live Core MemoryManager instance.

```bash
# Automatically finds or creates a project
python scripts/smoke_test_mcp.py

# Target a specific project UUID:
python scripts/smoke_test_mcp.py --project-id <UUID> --query "my search text"
```

### 3. `benchmark_chroma.py`
Profiles latency across the semantic retrieval pipeline:
1. Embedding generation via `sentence-transformers`
2. Vector similarity search via `ChromaDB`
3. Entity hydration from `SQLite` canonical storage

```bash
# Uses default paths:
python scripts/benchmark_chroma.py

# Or configure specific database paths:
python scripts/benchmark_chroma.py --sqlite-path /path/to/db.sqlite3 --chroma-path /path/to/chroma --project-id <UUID>
```
