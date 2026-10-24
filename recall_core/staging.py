"""Structured event staging module for RECALL automatic memory capture.

Provides a reliable, validated producer interface for staging eligible events
(decisions, conventions, architecture patterns, task outcomes) into a local
staging file (.pending_capture.json) to be ingested by the Antigravity lifecycle
hook or background capture runner.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple
from uuid import UUID

from contracts.capture import ELIGIBLE_CAPTURE_CATEGORIES
from recall_core.capture_service import MAX_CONTENT_LENGTH, MIN_CONTENT_LENGTH


def get_default_staging_path(workspace_path: Optional[Path] = None) -> Path:
    """Return the canonical staging file path for a workspace or RECALL repository."""
    if workspace_path is not None:
        return (workspace_path / ".agents" / ".pending_capture.json").resolve()

    repo_root = Path(__file__).resolve().parent.parent
    return (repo_root / ".agents" / ".pending_capture.json").resolve()


def stage_capture_event(
    content: str,
    event_category: str,
    project_name: Optional[str] = None,
    project_id: Optional[UUID] = None,
    session_id: Optional[UUID] = None,
    idempotency_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    workspace_path: Optional[Path] = None,
) -> Path:
    """Validate and stage an eligible capture event to disk atomically.

    Raises:
        ValueError: If category is ineligible, content is empty, or length limits are violated.
    """
    raw_content = (content or "").strip()
    if not raw_content:
        raise ValueError("Content cannot be empty or whitespace")

    category = event_category.strip().lower()
    if category not in ELIGIBLE_CAPTURE_CATEGORIES:
        raise ValueError(
            f"Ineligible event category '{category}'. Must be one of: {sorted(ELIGIBLE_CAPTURE_CATEGORIES)}"
        )

    if len(raw_content) < MIN_CONTENT_LENGTH:
        raise ValueError(
            f"Content length ({len(raw_content)}) is below minimum threshold ({MIN_CONTENT_LENGTH})"
        )

    if len(raw_content) > MAX_CONTENT_LENGTH:
        raise ValueError(
            f"Content length ({len(raw_content)}) exceeds maximum allowed ({MAX_CONTENT_LENGTH})"
        )

    payload = {
        "event_category": category,
        "content": raw_content,
        "project_name": project_name.strip() if project_name and project_name.strip() else None,
        "project_id": str(project_id) if project_id else None,
        "session_id": str(session_id) if session_id else None,
        "idempotency_key": idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None,
        "metadata": metadata or {},
        "staged_at": datetime.now(timezone.utc).isoformat(),
    }

    target_path = get_default_staging_path(workspace_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via temporary file in same directory
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(target_path.parent),
        prefix=".capture_stage_",
        suffix=".tmp",
    )
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_name, str(target_path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return target_path


def get_staged_capture_event(
    workspace_path: Optional[Path] = None,
) -> Optional[Tuple[Path, dict[str, Any]]]:
    """Find and read a staged capture event if present."""
    candidates = []
    if workspace_path is not None:
        candidates.append(workspace_path / ".agents" / ".pending_capture.json")
        candidates.append(workspace_path / ".dev_data" / ".pending_capture.json")

    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / ".agents" / ".pending_capture.json")
    candidates.append(repo_root / ".dev_data" / ".pending_capture.json")

    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return candidate.resolve(), data
            except Exception:
                pass

    return None


def clear_staged_capture_event(workspace_path: Optional[Path] = None) -> bool:
    """Clear staged capture event files if present."""
    found = False
    candidates = []
    if workspace_path is not None:
        candidates.append(workspace_path / ".agents" / ".pending_capture.json")
        candidates.append(workspace_path / ".dev_data" / ".pending_capture.json")

    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / ".agents" / ".pending_capture.json")
    candidates.append(repo_root / ".dev_data" / ".pending_capture.json")

    for candidate in candidates:
        if candidate.is_file():
            try:
                candidate.unlink(missing_ok=True)
                found = True
            except OSError:
                pass

    return found
