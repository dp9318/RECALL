"""Unit and integration tests for the Antigravity recall capture hook runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest


def run_hook_proc(event_type: str, stdin_content: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    import os
    hook_script = Path(__file__).resolve().parent.parent / "scripts" / "recall_capture_hook.py"
    cmd = [sys.executable, str(hook_script), "--event", event_type]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged_env,
    )
    stdout, stderr = p.communicate(input=stdin_content, timeout=5)
    return p.returncode, stdout, stderr


def test_hook_post_invocation_stdout_contract():
    code, out, err = run_hook_proc("post-invocation", "")
    assert code == 0
    parsed = json.loads(out.strip())
    assert parsed == {"injectSteps": []}


def test_hook_stop_stdout_contract():
    code, out, err = run_hook_proc("stop", "")
    assert code == 0
    parsed = json.loads(out.strip())
    assert parsed == {"decision": "allow"}


def test_hook_absorbs_corrupted_stdin():
    code, out, err = run_hook_proc("post-invocation", "CORRUPTED_NON_JSON")
    assert code == 0
    parsed = json.loads(out.strip())
    assert parsed == {"injectSteps": []}


def test_hook_offline_api_exits_zero(tmp_path):
    staged_dir = tmp_path / ".agents"
    staged_dir.mkdir(parents=True)
    staged_file = staged_dir / ".pending_capture.json"
    staged_file.write_text(
        json.dumps({
            "event_category": "decision",
            "content": "Valid decision content that should not block on offline API.",
        }),
        encoding="utf-8",
    )

    env = {
        "RECALL_API_URL": "http://127.0.0.1:59998/api/capture",
        "RECALL_CAPTURE_TOKEN": "test_tok",
    }
    stdin_data = json.dumps({"workspacePaths": [str(tmp_path)]})

    code, out, err = run_hook_proc("post-invocation", stdin_data, env=env)
    assert code == 0
    parsed = json.loads(out.strip())
    assert parsed == {"injectSteps": []}
    assert staged_file.exists()  # Kept for retry


def test_hook_recovers_from_malformed_staged_json(tmp_path):
    staged_dir = tmp_path / ".agents"
    staged_dir.mkdir(parents=True)
    staged_file = staged_dir / ".pending_capture.json"
    staged_file.write_text("{corrupted_json: missing_quotes", encoding="utf-8")

    stdin_data = json.dumps({"workspacePaths": [str(tmp_path)]})
    code, out, err = run_hook_proc("post-invocation", stdin_data)
    assert code == 0
    assert json.loads(out.strip()) == {"injectSteps": []}
    assert "removing corrupted staged event" in err
    # Must be unlinked so it doesn't block future turns
    assert not staged_file.exists()


def test_hook_removes_ineligible_event(tmp_path):
    staged_dir = tmp_path / ".agents"
    staged_dir.mkdir(parents=True)
    staged_file = staged_dir / ".pending_capture.json"
    staged_file.write_text(
        json.dumps({
            "event_category": "casual_chat",
            "content": "This is casual chatter that is not an eligible category.",
        }),
        encoding="utf-8",
    )

    stdin_data = json.dumps({"workspacePaths": [str(tmp_path)]})
    code, out, err = run_hook_proc("post-invocation", stdin_data)
    assert code == 0
    assert json.loads(out.strip()) == {"injectSteps": []}
    assert "removing ineligible staged event" in err
    assert not staged_file.exists()


def test_hook_removes_missing_content_event(tmp_path):
    staged_dir = tmp_path / ".agents"
    staged_dir.mkdir(parents=True)
    staged_file = staged_dir / ".pending_capture.json"
    staged_file.write_text(
        json.dumps({
            "event_category": "decision",
            "content": "   ",
        }),
        encoding="utf-8",
    )

    stdin_data = json.dumps({"workspacePaths": [str(tmp_path)]})
    code, out, err = run_hook_proc("post-invocation", stdin_data)
    assert code == 0
    assert not staged_file.exists()


def test_staging_module_and_cli_producer(tmp_path):
    """Verify the structured staging producer module and CLI utility."""
    from recall_core.staging import (
        clear_staged_capture_event,
        get_staged_capture_event,
        stage_capture_event,
    )

    # 1. Validation failure: category ineligible
    with pytest.raises(ValueError, match="Ineligible event category"):
        stage_capture_event(
            content="Valid content string exceeding minimum threshold",
            event_category="invalid_cat",
            workspace_path=tmp_path,
        )

    # 2. Validation failure: content too short
    with pytest.raises(ValueError, match="below minimum threshold"):
        stage_capture_event(
            content="Too short",
            event_category="decision",
            workspace_path=tmp_path,
        )

    # 3. Successful staging
    staged_path = stage_capture_event(
        content="Architecture decision: Adopt SQLite-first persistence for canonical memories.",
        event_category="architecture",
        project_name="StagingTestProject",
        workspace_path=tmp_path,
    )
    assert staged_path.is_file()

    # 4. Read back staged event
    retrieved = get_staged_capture_event(tmp_path)
    assert retrieved is not None
    path, data = retrieved
    assert path == staged_path.resolve()
    assert data["event_category"] == "architecture"
    assert "SQLite-first" in data["content"]

    # 5. Clear staged event
    cleared = clear_staged_capture_event(tmp_path)
    assert cleared is True
    assert not staged_path.exists()

    # 6. Test CLI producer script
    stage_cli = Path(__file__).resolve().parent.parent / "scripts" / "recall_stage.py"
    cli_proc = subprocess.run(
        [
            sys.executable,
            str(stage_cli),
            "--category",
            "convention",
            "--content",
            "Coding convention: All function signatures must include return type hints.",
            "--project",
            "CliTestProj",
            "--workspace",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert cli_proc.returncode == 0
    cli_out = json.loads(cli_proc.stdout.strip())
    assert cli_out["status"] == "staged"
    assert staged_path.is_file()


def test_end_to_end_staging_hook_and_ingestion(tmp_path, monkeypatch):
    """End-to-end test: Producer stages event -> Hook executes -> API ingests -> Memory persisted."""
    import socket
    import threading
    import time
    import uvicorn
    from api.app import create_app
    from database.config import DatabaseConfig
    from recall_core.bootstrap import create_memory_manager
    from tests.test_mcp_bootstrap import _TestSemanticIndex
    from recall_core.staging import stage_capture_event

    db_path = tmp_path / "e2e_capture.sqlite3"
    token = "test_e2e_token_777888999"
    monkeypatch.setenv("RECALL_CAPTURE_TOKEN", token)

    core = create_memory_manager(
        DatabaseConfig.from_path(db_path),
        semantic_index=_TestSemanticIndex(),
    )
    app = create_app(core)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server startup
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)

    try:
        # 1. Stage an eligible event using the producer
        content = "Architecture decision: Adopt SQLite-first persistence for canonical memories."
        staged_file = stage_capture_event(
            content=content,
            event_category="decision",
            project_name="E2ETestProject",
            workspace_path=tmp_path,
        )
        assert staged_file.is_file()

        # 2. Execute hook runner with workspace path in stdin
        env = {
            "RECALL_API_URL": f"http://127.0.0.1:{port}/api/capture",
            "RECALL_CAPTURE_TOKEN": token,
        }
        stdin_data = json.dumps({"workspacePaths": [str(tmp_path)]})
        code, out, err = run_hook_proc("post-invocation", stdin_data, env=env)
        assert code == 0
        assert json.loads(out.strip()) == {"injectSteps": []}

        # 3. Verify staged file was cleanly consumed
        assert not staged_file.exists()

        # 4. Verify canonical memory was persisted into SQLite database
        proj_res = core.get_project_by_name("E2ETestProject")
        assert proj_res.success and proj_res.value is not None
        proj_id = proj_res.value.id

        mems_res = core._uow.memories.get_active_for_project(proj_id)
        assert mems_res.success and mems_res.value is not None
        assert len(mems_res.value) == 1
        persisted_mem = mems_res.value[0]
        assert persisted_mem.content == content
        assert persisted_mem.memory_type == "decision"
        assert persisted_mem.provenance == "agent_inferred"

        # 5. Test duplicate suppression on retry/re-staging
        staged_again = stage_capture_event(
            content=content,
            event_category="decision",
            project_name="E2ETestProject",
            workspace_path=tmp_path,
        )
        assert staged_again.is_file()

        code2, out2, err2 = run_hook_proc("post-invocation", stdin_data, env=env)
        assert code2 == 0
        assert not staged_again.exists()

        # Still only 1 memory in database (duplicate suppressed!)
        mems_res2 = core._uow.memories.get_active_for_project(proj_id)
        assert len(mems_res2.value) == 1

    finally:
        server.should_exit = True
        core.close()
