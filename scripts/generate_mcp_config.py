"""Generate client-specific MCP configuration with resolved local paths.

Usage:
    python scripts/generate_mcp_config.py [--output <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def generate_config(output_file: Path | None = None) -> dict[str, dict]:
    repo_root = Path(__file__).resolve().parent.parent
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"

    if not venv_python.exists():
        python_cmd = sys.executable
    else:
        python_cmd = str(venv_python.resolve())

    # Format 1: Standard mcpServers (Antigravity, Cursor, Claude Desktop)
    standard_config = {
        "mcpServers": {
            "recall": {
                "command": python_cmd,
                "args": ["-m", "recall_mcp.server"],
                "env": {
                    "RECALL_MCP_WARMUP": "true"
                }
            }
        }
    }

    # Format 2: OpenCode format (.opencode/opencode.json)
    opencode_config = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "recall": {
                "type": "local",
                "command": [python_cmd, "-m", "recall_mcp.server"],
                "environment": {
                    "RECALL_MCP_WARMUP": "true"
                },
                "enabled": True
            }
        }
    }

    combined = {
        "instructions": (
            "Ready-to-use configuration for your AI coding agents. "
            "Copy the relevant snippet into your agent's MCP settings file."
        ),
        "standard_mcpServers_format (Cursor, Claude Desktop, Antigravity)": standard_config,
        "opencode_format (.opencode/opencode.json)": opencode_config,
    }

    target = output_file or (repo_root / "mcp_config.local.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    print(f"[INFO] Generated client MCP configuration at: {target}")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local MCP client configuration")
    parser.add_argument("--output", help="Custom output JSON path")
    args = parser.parse_args()

    out_path = Path(args.output).resolve() if args.output else None
    generate_config(out_path)


if __name__ == "__main__":
    main()
