#!/usr/bin/env python3
"""Verify SQLite-to-ChromaDB index consistency and optionally repair with backup."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager, resolve_runtime_paths


def inspect_consistency(sqlite_path: Path, chroma_path: Path) -> dict[str, Any]:
    """Inspect active SQLite IDs vs ChromaDB embedding IDs in read-only mode."""
    result: dict[str, Any] = {
        "sqlite_path": str(sqlite_path),
        "chroma_path": str(chroma_path),
        "sqlite_active_count": 0,
        "chroma_embedding_count": 0,
        "missing_in_chroma": [],
        "stale_in_chroma": [],
        "consistent": False,
    }
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        active_ids = {
            row[0]
            for row in conn.execute(
                "SELECT memory_id FROM memories WHERE status = ?", ("active",)
            ).fetchall()
        }
    finally:
        conn.close()

    chroma_db = chroma_path / "chroma.sqlite3"
    chroma_ids: set[str] = set()
    if chroma_db.is_file():
        c_conn = sqlite3.connect(f"file:{chroma_db}?mode=ro", uri=True)
        try:
            chroma_ids = {
                row[0] for row in c_conn.execute("SELECT embedding_id FROM embeddings").fetchall()
            }
        finally:
            c_conn.close()

    missing = sorted(active_ids - chroma_ids)
    stale = sorted(chroma_ids - active_ids)
    result["sqlite_active_count"] = len(active_ids)
    result["chroma_embedding_count"] = len(chroma_ids)
    result["missing_in_chroma"] = missing
    result["stale_in_chroma"] = stale
    result["consistent"] = not missing and not stale
    return result


def repair_with_backup(sqlite_path: Path, chroma_path: Path) -> dict[str, Any]:
    """Create a recoverable backup of ChromaDB and rebuild from canonical active SQLite records."""
    backup_path: Path | None = None
    if chroma_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = chroma_path.with_name(f"{chroma_path.name}.backup_{ts}")
        shutil.copytree(chroma_path, backup_path)

    manager = create_memory_manager(DatabaseConfig.from_path(sqlite_path))
    try:
        rebuild_res = manager.rebuild_semantic_index()
        if not rebuild_res.success:
            raise RuntimeError(rebuild_res.error or "Semantic index rebuild failed")
        post = inspect_consistency(sqlite_path, chroma_path)
        post["backup_path"] = str(backup_path) if backup_path else None
        post["rebuilt_count"] = rebuild_res.value
        return post
    finally:
        manager.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or repair RECALL SQLite-to-ChromaDB consistency.")
    parser.add_argument("--db", type=str, default=None, help="Optional explicit SQLite DB path.")
    parser.add_argument("--repair", action="store_true", help="Backup existing ChromaDB and rebuild from SQLite.")
    args = parser.parse_args()

    cfg = DatabaseConfig.from_path(args.db) if args.db else None
    resolved = resolve_runtime_paths(cfg)
    if args.repair:
        report = repair_with_backup(resolved.sqlite_path, resolved.chroma_path)
    else:
        report = inspect_consistency(resolved.sqlite_path, resolved.chroma_path)
    print(json.dumps(report, indent=2))
    return 0 if report.get("consistent") else 1


if __name__ == "__main__":
    raise SystemExit(main())
