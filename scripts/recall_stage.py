#!/usr/bin/env python3
"""CLI utility to stage an eligible capture event for RECALL automatic ingestion.

Usage:
    python scripts/recall_stage.py --category decision --content "Use SQLite WAL mode"
    python scripts/recall_stage.py --category convention --content "Always use UTC timestamps" --project "MyProject"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from contracts.capture import ELIGIBLE_CAPTURE_CATEGORIES
from recall_core.staging import stage_capture_event


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage an eligible capture event into .pending_capture.json for RECALL ingestion."
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=sorted(ELIGIBLE_CAPTURE_CATEGORIES),
        help=f"Eligible capture category: {sorted(ELIGIBLE_CAPTURE_CATEGORIES)}",
    )
    parser.add_argument(
        "--content",
        required=True,
        type=str,
        help="Capture content (must be between 20 and 4000 characters).",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Optional project name for the capture event.",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        default=None,
        help="Optional project UUID.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional session UUID.",
    )
    parser.add_argument(
        "--idempotency-key",
        type=str,
        default=None,
        help="Optional custom idempotency key.",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Optional workspace root directory (defaults to current repository root).",
    )

    args = parser.parse_args()

    project_uuid = None
    if args.project_id:
        try:
            project_uuid = UUID(args.project_id.strip())
        except ValueError:
            sys.stderr.write(f"Error: Invalid project UUID '{args.project_id}'\n")
            sys.exit(1)

    session_uuid = None
    if args.session_id:
        try:
            session_uuid = UUID(args.session_id.strip())
        except ValueError:
            sys.stderr.write(f"Error: Invalid session UUID '{args.session_id}'\n")
            sys.exit(1)

    workspace_path = Path(args.workspace).resolve() if args.workspace else None

    try:
        staged_path = stage_capture_event(
            content=args.content,
            event_category=args.category,
            project_name=args.project,
            project_id=project_uuid,
            session_id=session_uuid,
            idempotency_key=args.idempotency_key,
            workspace_path=workspace_path,
        )
        output = {
            "status": "staged",
            "file": str(staged_path),
            "category": args.category,
            "content_preview": args.content[:80] + ("..." if len(args.content) > 80 else ""),
        }
        print(json.dumps(output, indent=2))
    except Exception as exc:
        sys.stderr.write(f"Error staging capture event: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
