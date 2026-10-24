"""Fail-safe Antigravity lifecycle hook runner for RECALL automatic capture.

Complies strictly with the Antigravity hook specification in:
builtin/skills/agy-customizations/docs/hooks.md

- Receives JSON metadata on stdin (camelCase).
- Never reads or uploads transcriptPath contents.
- Captures only narrowly defined, explicitly eligible structured events from a staged file.
- Emits the exact required stdout JSON for PostInvocation or Stop.
- Never exits non-zero; never blocks or halts the agent workflow on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ELIGIBLE_CATEGORIES = {"decision", "convention", "architecture", "task_outcome"}
DEFAULT_API_URL = "http://127.0.0.1:8080/api/capture"
CONNECT_TIMEOUT_SECONDS = 2.0


def _resolve_token(workspace_path: Path | None) -> str | None:
    """Resolve the local capture token from environment or deterministic local storage."""
    token = os.getenv("RECALL_CAPTURE_TOKEN")
    if token and token.strip():
        return token.strip()

    env_file = os.getenv("RECALL_CAPTURE_TOKEN_FILE")
    if env_file and env_file.strip():
        candidate = Path(env_file.strip()).expanduser().resolve()
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    # Check dev workspace token file
    if workspace_path:
        dev_token_file = (workspace_path / ".dev_data" / ".capture_token").resolve()
        if dev_token_file.is_file():
            try:
                return dev_token_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    # Check repository root dev token file
    repo_root = Path(__file__).resolve().parent.parent
    repo_dev_token = (repo_root / ".dev_data" / ".capture_token").resolve()
    if repo_dev_token.is_file():
        try:
            return repo_dev_token.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Check user home token file
    home_token_file = (Path.home() / ".recall" / ".capture_token").resolve()
    if home_token_file.is_file():
        try:
            return home_token_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return None


def _get_staged_event_file(workspace_path: Path) -> Path | None:
    """Find a staged structured capture event file if one exists."""
    candidates = [
        workspace_path / ".agents" / ".pending_capture.json",
        workspace_path / ".dev_data" / ".pending_capture.json",
    ]
    repo_root = Path(__file__).resolve().parent.parent
    if repo_root != workspace_path:
        candidates.append(repo_root / ".agents" / ".pending_capture.json")
        candidates.append(repo_root / ".dev_data" / ".pending_capture.json")

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def run_hook(event_type: str) -> None:
    """Execute the hook runner, guaranteeing valid stdout JSON and exit code 0."""
    # Determine the exact required stdout JSON response
    if event_type == "stop":
        stdout_response = json.dumps({"decision": "allow"})
    else:  # post-invocation
        stdout_response = json.dumps({"injectSteps": []})

    try:
        # Read metadata from stdin if available (up to 64KB)
        stdin_data: dict[str, Any] = {}
        if not sys.stdin.isatty():
            try:
                raw_stdin = sys.stdin.read(65536)
                if raw_stdin.strip():
                    stdin_data = json.loads(raw_stdin)
            except Exception as stdin_exc:
                sys.stderr.write(f"[RECALL-HOOK] Warning: could not parse stdin metadata: {stdin_exc}\n")

        # Resolve workspace directory
        workspace_paths = stdin_data.get("workspacePaths") or []
        workspace_dir = Path(workspace_paths[0]) if workspace_paths else Path.cwd()

        # Check for a staged structured event file
        staged_file = _get_staged_event_file(workspace_dir)
        if not staged_file:
            # No eligible structured event staged; return immediately
            return

        # Read and validate the staged event
        try:
            raw_event = json.loads(staged_file.read_text(encoding="utf-8"))
            if not isinstance(raw_event, dict):
                raise ValueError("Staged event is not a JSON object")
        except Exception as read_exc:
            sys.stderr.write(f"[RECALL-HOOK] Warning: removing corrupted staged event: {read_exc}\n")
            try:
                staged_file.unlink(missing_ok=True)
            except Exception:
                pass
            return

        category = raw_event.get("event_category")
        content = raw_event.get("content", "")
        if category not in ELIGIBLE_CATEGORIES or not isinstance(content, str) or not content.strip():
            # Ineligible or malformed event; remove and skip
            sys.stderr.write(
                f"[RECALL-HOOK] Warning: removing ineligible staged event (category={category}, content_type={type(content).__name__})\n"
            )
            try:
                staged_file.unlink(missing_ok=True)
            except Exception:
                pass
            return

        # Resolve authentication token
        token = _resolve_token(workspace_dir)
        if not token:
            sys.stderr.write("[RECALL-HOOK] Warning: no capture token available, skipping capture\n")
            return

        # Build capture request payload
        api_url = os.getenv("RECALL_API_URL", DEFAULT_API_URL)
        payload = {
            "project_name": raw_event.get("project_name") or workspace_dir.name,
            "project_id": raw_event.get("project_id"),
            "session_id": raw_event.get("session_id"),
            "event_category": category,
            "content": content.strip(),
            "source": f"antigravity_hook:{event_type}",
            "caller_idempotency_key": raw_event.get("idempotency_key"),
            "metadata": raw_event.get("metadata", {}),
        }

        # Send HTTP request to local API
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT_SECONDS) as resp:
                if resp.status in (200, 201):
                    # Successfully captured or suppressed duplicate
                    staged_file.unlink(missing_ok=True)
                else:
                    sys.stderr.write(f"[RECALL-HOOK] Warning: API returned HTTP {resp.status}\n")
                    if 400 <= resp.status < 500:
                        # Client error (invalid payload); clean up malformed staged file
                        staged_file.unlink(missing_ok=True)
        except urllib.error.HTTPError as http_err:
            sys.stderr.write(f"[RECALL-HOOK] Warning: API HTTP error {http_err.code}: {http_err.reason}\n")
            if 400 <= http_err.code < 500:
                # Permanent client rejection (e.g. 400 bad request, 422 unprocessable); remove to avoid infinite loop
                staged_file.unlink(missing_ok=True)
        except urllib.error.URLError as url_err:
            # API is offline or slow; do not delete file, preserve for retry
            sys.stderr.write(f"[RECALL-HOOK] Warning: API request failed (non-blocking, preserved for retry): {url_err}\n")
        except Exception as post_exc:
            sys.stderr.write(f"[RECALL-HOOK] Warning: capture dispatch error: {post_exc}\n")

    except Exception as top_exc:
        sys.stderr.write(f"[RECALL-HOOK] Warning: unhandled hook exception: {top_exc}\n")
    finally:
        # Guarantees exact valid JSON on stdout exactly once and clean exit code 0
        sys.stdout.write(stdout_response + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity lifecycle hook runner for RECALL")
    parser.add_argument(
        "--event",
        choices=["post-invocation", "stop"],
        default="post-invocation",
        help="Antigravity hook event type (default: post-invocation)",
    )
    args = parser.parse_args()
    run_hook(args.event)


if __name__ == "__main__":
    main()
