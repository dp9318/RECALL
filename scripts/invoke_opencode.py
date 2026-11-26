#!/usr/bin/env python3
"""Invoke OpenCode CLI non-interactively for independent architecture analysis or code review."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_FREE_MODEL = "opencode/deepseek-v4.1-flash-free"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Invoke OpenCode CLI subagent for RECALL independent analysis or review."
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="OpenCode agent name (e.g. recall-architect, recall-reviewer).",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Prompt to send to the OpenCode agent.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_FREE_MODEL,
        help=f"Model in provider/model format (default: {DEFAULT_FREE_MODEL}).",
    )
    parser.add_argument(
        "--cwd",
        default=str(Path(__file__).resolve().parent.parent),
        help="Working directory (use a separate git worktree path for parallel work).",
    )
    parser.add_argument(
        "--worktree",
        default=None,
        help="Optional OpenCode --worktree name for isolated execution.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout in seconds (default: 180).",
    )
    args = parser.parse_args()

    opencode_bin = shutil.which("opencode") or shutil.which("opencode.ps1") or "opencode"
    cmd = [
        opencode_bin,
        "run",
        "--standalone",
        "--auto",
        "--agent",
        args.agent,
        "--model",
        args.model,
        "--archived",
    ]
    if args.worktree:
        cmd.extend(["--worktree", args.worktree])
    cmd.append(args.prompt)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=args.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.kill()
        proc.communicate()
        sys.stderr.write(f"OpenCode invocation timed out after {args.timeout}s.\n")
        return 124

    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
