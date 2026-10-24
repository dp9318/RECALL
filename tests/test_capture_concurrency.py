"""Four-process concurrency tests for RECALL atomic capture idempotency."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path


def test_four_process_capture_concurrency(tmp_path):
    from database.config import DatabaseConfig
    from database.connection import initialize_database

    db_path = str(tmp_path / "concurrent_capture_test.sqlite3")
    initialize_database(DatabaseConfig.from_path(db_path))
    project_name = "ConcurrentCaptureProject"
    content = "Architecture decision: Enforce atomic BEGIN IMMEDIATE on SQLite for multi-process capture idempotency."

    worker_code = """
import sys
from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager
from contracts.capture import CaptureEventRequest

db_path = sys.argv[1]
project_name = sys.argv[2]
content = sys.argv[3]

core = create_memory_manager(DatabaseConfig.from_path(db_path))
try:
    req = CaptureEventRequest(
        project_name=project_name,
        event_category="decision",
        content=content,
        source="concurrency_worker",
    )
    res = core.capture_memory(req)
    if res.success and res.value:
        print(f"STATUS:{res.value.status}")
        print(f"MEMORY_ID:{res.value.memory_id}")
    else:
        print(f"ERROR:{res.error}")
        sys.exit(1)
finally:
    core.close()
"""

    # Spawn 4 independent OS processes simultaneously
    processes = []
    for _ in range(4):
        p = subprocess.Popen(
            [sys.executable, "-c", worker_code, db_path, project_name, content],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(p)

    outputs = []
    for p in processes:
        stdout, stderr = p.communicate(timeout=30)
        assert p.returncode == 0, f"Worker process failed with code {p.returncode}: {stderr}\nStdout: {stdout}"
        outputs.append(stdout)

    memory_ids = set()
    statuses = []

    for out in outputs:
        for line in out.strip().splitlines():
            if line.startswith("MEMORY_ID:"):
                memory_ids.add(line.split(":", 1)[1].strip())
            elif line.startswith("STATUS:"):
                statuses.append(line.split(":", 1)[1].strip())

    # All 4 processes must report the exact same canonical memory ID
    assert len(memory_ids) == 1, f"Expected 1 canonical memory ID across all processes, got: {memory_ids}"
    canonical_id = memory_ids.pop()

    # One process persisted, the other three suppressed duplicates
    assert "persisted" in statuses
    assert statuses.count("persisted") == 1, f"Expected exactly 1 'persisted' status, got: {statuses}"
    assert statuses.count("suppressed_duplicate") == 3, f"Expected 3 'suppressed_duplicate' statuses, got: {statuses}"

    # Verify directly in SQLite that exactly one row exists
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT memory_id, content FROM memories WHERE content = ?", (content,))
        rows = cursor.fetchall()
        assert len(rows) == 1, f"Expected exactly 1 row in SQLite database, found: {rows}"
        assert rows[0][0] == canonical_id
    finally:
        conn.close()
