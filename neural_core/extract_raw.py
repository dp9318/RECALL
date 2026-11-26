"""Standalone read-only SQLite data exporter for RECALL Neural Core (Phase 1).

Connects to the canonical RECALL SQLite database using URI `mode=ro`,
exports non-deleted canonical records to `neural_core/data/raw/`,
applies fail-closed secret redaction, and validates all exported JSON/JSONL files.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import pathname2url

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recall_core.capture_service import redact_secrets  # noqa: E402

DEFAULT_DB_PATH = Path(r"C:\Users\dipan\.recall\recall.sqlite3")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "neural_core" / "data" / "raw"

OUTPUT_FILENAMES = (
    "memories.jsonl",
    "projects.json",
    "sessions.json",
    "lineage.json",
    "custom_instructions.json",
    "extraction_report.json",
)


def _redact_value(value: Any) -> tuple[Any, int]:
    """Recursively redact secrets from strings, lists, and dicts."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        total = 0
        out = []
        for item in value:
            redacted_item, count = _redact_value(item)
            total += count
            out.append(redacted_item)
        return out, total
    if isinstance(value, dict):
        total = 0
        out: dict[str, Any] = {}
        for k, v in value.items():
            redacted_val, count = _redact_value(v)
            total += count
            out[str(k)] = redacted_val
        return out, total
    return value, 0


def _parse_metadata(raw_value: Any) -> tuple[Any, bool, bool]:
    """Parse JSON metadata without losing original values.

    Returns:
        (parsed_or_raw_value, is_missing, is_invalid_json)
    """
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return {}, True, False
    if isinstance(raw_value, dict):
        return raw_value, len(raw_value) == 0, False
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            is_missing = isinstance(parsed, dict) and len(parsed) == 0
            return parsed, is_missing, False
        except json.JSONDecodeError:
            return raw_value, False, True
    return raw_value, False, True


def _open_readonly_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open SQLite strictly in read-only URI mode."""
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite database not found: {resolved}")
    uri = f"file:{pathname2url(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _check_no_overwrite(output_dir: Path, force: bool) -> None:
    """Refuse to overwrite existing export files unless --force is explicitly passed."""
    existing = [output_dir / name for name in OUTPUT_FILENAMES if (output_dir / name).exists()]
    if existing and not force:
        joined = ", ".join(str(p) for p in existing)
        raise FileExistsError(
            f"Refusing to overwrite existing export files without --force: {joined}"
        )


def _validate_exports(output_dir: Path) -> dict[str, int]:
    """Read back and validate JSON/JSONL syntax of all exported files."""
    validated: dict[str, int] = {}
    for name in OUTPUT_FILENAMES:
        path = output_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing expected export file: {path}")
        if name.endswith(".jsonl"):
            line_count = 0
            with path.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    stripped = line.strip()
                    if not stripped:
                        raise ValueError(f"Empty line {idx} in {path}")
                    json.loads(stripped)
                    line_count += 1
            validated[name] = line_count
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            validated[name] = len(data) if isinstance(data, list) else 1
    return validated


def extract_dataset(
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Extract canonical RECALL records in read-only mode and write validated exports."""
    _check_no_overwrite(output_dir, force=force)
    output_dir.mkdir(parents=True, exist_ok=True)

    missing_metadata_counts: Counter[str] = Counter()
    invalid_json_counts: Counter[str] = Counter()
    redaction_counts: Counter[str] = Counter()

    memory_status_counts: Counter[str] = Counter()
    instruction_status_counts: Counter[str] = Counter()
    project_status_counts: Counter[str] = Counter()
    session_status_counts: Counter[str] = Counter()

    excluded_deleted_memories = 0
    excluded_deleted_instructions = 0

    conn = _open_readonly_sqlite(db_path)
    try:
        # 1. Projects
        projects_out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM projects ORDER BY created_at ASC"):
            d = dict(row)
            project_status_counts[str(d.get("status", "unknown"))] += 1
            meta, is_missing, is_invalid = _parse_metadata(d.get("metadata"))
            if is_missing:
                missing_metadata_counts["projects"] += 1
            if is_invalid:
                invalid_json_counts["projects"] += 1
            redacted_meta, r_meta = _redact_value(meta)
            redacted_name, r_name = _redact_value(d.get("name"))
            redacted_desc, r_desc = _redact_value(d.get("description"))
            redaction_counts["projects"] += r_meta + r_name + r_desc

            projects_out.append({
                "project_id": d["project_id"],
                "name": redacted_name,
                "description": redacted_desc,
                "status": d["status"],
                "metadata": redacted_meta,
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
            })

        # 2. Sessions
        sessions_out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM sessions ORDER BY started_at ASC"):
            d = dict(row)
            session_status_counts[str(d.get("status", "unknown"))] += 1
            meta, is_missing, is_invalid = _parse_metadata(d.get("metadata"))
            if is_missing:
                missing_metadata_counts["sessions"] += 1
            if is_invalid:
                invalid_json_counts["sessions"] += 1
            redacted_meta, r_meta = _redact_value(meta)
            redaction_counts["sessions"] += r_meta

            sessions_out.append({
                "session_id": d["session_id"],
                "project_id": d["project_id"],
                "started_at": d["started_at"],
                "ended_at": d["ended_at"],
                "status": d["status"],
                "metadata": redacted_meta,
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
            })

        # 3. Memories (exclude status == 'deleted' from export, retain active/superseded/archived)
        memories_out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM memories ORDER BY created_at ASC"):
            d = dict(row)
            status = str(d.get("status", "unknown"))
            memory_status_counts[status] += 1
            if status == "deleted":
                excluded_deleted_memories += 1
                continue

            meta, is_missing, is_invalid = _parse_metadata(d.get("metadata"))
            if is_missing:
                missing_metadata_counts["memories"] += 1
            if is_invalid:
                invalid_json_counts["memories"] += 1

            redacted_content, r_content = _redact_value(d.get("content"))
            redacted_meta, r_meta = _redact_value(meta)
            redaction_counts["memories"] += r_content + r_meta

            memories_out.append({
                "memory_id": d["memory_id"],
                "project_id": d["project_id"],
                "session_id": d["session_id"],
                "scope": d["scope"],
                "memory_type": d["memory_type"],
                "content": redacted_content,
                "status": status,
                "provenance": d["provenance"],
                "supersedes_id": d["supersedes_id"],
                "valid_from": d["valid_from"],
                "valid_until": d["valid_until"],
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
                "metadata": redacted_meta,
            })

        # 4. Memory Lineage
        lineage_out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM memory_lineage ORDER BY created_at ASC"):
            d = dict(row)
            redacted_reason, r_reason = _redact_value(d.get("reason"))
            redaction_counts["memory_lineage"] += r_reason
            lineage_out.append({
                "lineage_id": d["lineage_id"],
                "parent_id": d["parent_id"],
                "child_id": d["child_id"],
                "relationship": d["relationship"],
                "reason": redacted_reason,
                "created_at": d["created_at"],
            })

        # 5. Custom Instructions (exclude status == 'deleted' from export, retain active/inactive)
        instructions_out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM custom_instructions ORDER BY created_at ASC"):
            d = dict(row)
            status = str(d.get("status", "unknown"))
            instruction_status_counts[status] += 1
            if status == "deleted":
                excluded_deleted_instructions += 1
                continue

            meta, is_missing, is_invalid = _parse_metadata(d.get("metadata"))
            if is_missing:
                missing_metadata_counts["custom_instructions"] += 1
            if is_invalid:
                invalid_json_counts["custom_instructions"] += 1

            redacted_content, r_content = _redact_value(d.get("content"))
            redacted_meta, r_meta = _redact_value(meta)
            redaction_counts["custom_instructions"] += r_content + r_meta

            instructions_out.append({
                "instruction_id": d["instruction_id"],
                "scope": d["scope"],
                "project_id": d["project_id"],
                "content": redacted_content,
                "status": status,
                "version": d["version"],
                "metadata": redacted_meta,
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
            })
    finally:
        conn.close()

    # Write export files
    with (output_dir / "memories.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for item in memories_out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    (output_dir / "projects.json").write_text(
        json.dumps(projects_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "sessions.json").write_text(
        json.dumps(sessions_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "lineage.json").write_text(
        json.dumps(lineage_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "custom_instructions.json").write_text(
        json.dumps(instructions_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report: dict[str, Any] = {
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_database": str(db_path.expanduser().resolve()),
        "sqlite_open_mode": "ro",
        "output_directory": str(output_dir.resolve()),
        "exported_counts": {
            "memories": len(memories_out),
            "projects": len(projects_out),
            "sessions": len(sessions_out),
            "lineage": len(lineage_out),
            "custom_instructions": len(instructions_out),
        },
        "excluded_deleted_counts": {
            "memories": excluded_deleted_memories,
            "custom_instructions": excluded_deleted_instructions,
        },
        "row_counts_by_status": {
            "memories": dict(memory_status_counts),
            "custom_instructions": dict(instruction_status_counts),
            "projects": dict(project_status_counts),
            "sessions": dict(session_status_counts),
        },
        "missing_metadata": dict(missing_metadata_counts),
        "invalid_json": dict(invalid_json_counts),
        "redaction_counts": dict(redaction_counts),
        "total_redactions": sum(redaction_counts.values()),
    }

    (output_dir / "extraction_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    validated_files = _validate_exports(output_dir)
    report["validated_files"] = validated_files
    (output_dir / "extraction_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only RECALL SQLite dataset exporter for Neural Core."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to RECALL SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly allow overwriting existing export files.",
    )
    args = parser.parse_args()
    report = extract_dataset(args.db_path, args.output_dir, force=args.force)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
