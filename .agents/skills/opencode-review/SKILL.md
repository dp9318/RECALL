---
name: opencode-review
description: Invoke OpenCode CLI subagents (recall-architect, recall-reviewer) from Antigravity for independent architecture analysis and code review.
---

# OpenCode Independent Analysis & Review

Use this skill when Antigravity (Gemini 4 Hydrogen) needs independent architectural feedback or an adversarial code review from OpenCode CLI.

## Commands

Run via `scripts/invoke_opencode.py` (uses free model `opencode/deepseek-v4.1-flash-free` by default and `--archived` to avoid polluting interactive sessions):

- **Architecture Analysis**:
  ```powershell
  python scripts/invoke_opencode.py --agent recall-architect --prompt "Analyze <target> against RECALL invariants."
  ```
- **Independent Code Review**:
  ```powershell
  python scripts/invoke_opencode.py --agent recall-reviewer --prompt "Review git diff for <scope>."
  ```

## Isolation Rules

1. `recall-architect` and `recall-reviewer` are read-only subagents.
2. Never allow two agents to write to the same working tree concurrently; use `git worktree add` or `--worktree` for any parallel implementation.
3. Never modify `.agents/mcp_config.json`, `.opencode/opencode.json`, `.dev_data/`, or `~/.recall/`.
