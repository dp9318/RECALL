"""Utility script to list all projects registered in a RECALL SQLite database.

Usage:
    python scripts/list_projects.py [--db-path /path/to/recall.sqlite3]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="List projects in RECALL database")
    parser.add_argument(
        "--db-path",
        default=os.getenv("RECALL_DB_PATH", str(Path.home() / ".recall" / "recall.sqlite3")),
        help="Path to SQLite database file",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database file not found at: {db_path}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT project_id, name, description, created_at FROM projects ORDER BY created_at DESC")
        rows = cursor.fetchall()
        if not rows:
            print(f"No projects found in {db_path}")
            return
        print(f"Found {len(rows)} project(s) in {db_path}:")
        for row in rows:
            desc = f" - {row['description']}" if row['description'] else ""
            print(f"  ID: {row['project_id']} | Name: {row['name']}{desc}")
        conn.close()
    except sqlite3.Error as exc:
        print(f"SQLite error reading {db_path}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
