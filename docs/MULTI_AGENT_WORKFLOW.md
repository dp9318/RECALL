# RECALL v3.0.0 — Multi-Agent Development Workflow

## 1. Roles & Responsibilities

| Role | Agent / Tool | Responsibility |
| :--- | :--- | :--- |
| **Primary Orchestrator** | **Gemini 4 Hydrogen (Antigravity)** | Task decomposition, RECALL MCP coordination, implementation integration, conflict/review resolution, final verification, and checkpointing. |
| **Architecture Analyst** | **OpenCode CLI (`--agent recall-architect`)** | Read-only pre-implementation architecture review against `AGENTS.md`, contracts, and RECALL invariants. |
| **Independent Reviewer** | **OpenCode CLI (`--agent recall-reviewer`)** | Read-only post-implementation adversarial diff review (correctness, security, encapsulation, test coverage). |

### Model Selection
- OpenCode invocations default to the free model `opencode/deepseek-v4.1-flash-free` via `scripts/invoke_opencode.py` (with `--archived` so scripted runs stay out of interactive session history).

### Evaluation of Additional Tools (Aider & Goose)
- **Aider (`aider.exe`)** and **Goose (`goose.exe`)** are installed on the machine, but **not** added to the RECALL workflow:
  - OpenCode v2.4.1 already provides native `--agent` specialization, `--worktree` isolation, `--format json`, free model access (`opencode/deepseek-v4.1-flash-free`), and RECALL MCP integration (`.opencode/opencode.json`).
  - Introducing Aider or Goose would duplicate OpenCode's CLI subagent and worktree capabilities while adding configuration surface without measurable benefit.

---

## 2. Git Worktree & Isolation Rules

1. **No Concurrent Shared-Tree Edits**: Agents must never modify the same working tree concurrently.
2. **Parallel Implementation**: Create a dedicated Git worktree per parallel task:
   ```powershell
   git worktree add ..\RECALL-phase04 -b feat/phase04-conflict-resolution dev/recall-3.0.0
   ```
   After tests pass, merge/cherry-pick into `dev/recall-3.0.0` and remove the worktree (`git worktree remove ..\RECALL-phase04`).
3. **Preserved State**:
   - `.agents/mcp_config.json` and `.opencode/opencode.json` remain untouched (pointing to the working RECALL 2.1.1 MCP server).
   - `.dev_data/` remains isolated for development; `~/.recall/` (production) is never touched.

---

## 3. How to Invoke OpenCode from Antigravity

- **Skill**: `.agents/skills/opencode-review/SKILL.md`
- **Wrapper**: `scripts/invoke_opencode.py`

```powershell
# Independent architecture analysis
python scripts/invoke_opencode.py --agent recall-architect --prompt "Audit Phase 04 design..."

# Independent code review
python scripts/invoke_opencode.py --agent recall-reviewer --prompt "Review Phase 04 git diff..."
```

### Known Windows Environment Note
- `opencode v2.4.1` (`opencode run`) spawns `serve --stdio --port 0` and can block in non-TTY Windows subprocesses. `scripts/invoke_opencode.py` uses `stdin=subprocess.DEVNULL` and `taskkill /F /T /PID` on timeout so hung child processes never leak. If OpenCode CLI times out in a non-TTY session, Antigravity falls back to its isolated read-only `research` subagent for independent adversarial review.
