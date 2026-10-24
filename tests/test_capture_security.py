"""Tests for RECALL automatic capture authentication and token security."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from recall_core.bootstrap import create_memory_manager
from database.config import DatabaseConfig
from tests.test_mcp_bootstrap import _TestSemanticIndex
from recall_core.capture_service import (
    resolve_or_create_capture_token,
    secure_write_token_file,
    verify_capture_token,
)


@pytest.fixture
def capture_client(tmp_path, monkeypatch):
    """Provide a TestClient with isolated DB and capture token."""
    db_path = tmp_path / "capture_sec_test.sqlite3"
    token_path = tmp_path / ".capture_token"
    test_token = "secure_test_token_abcdef1234567890"

    monkeypatch.setenv("RECALL_CAPTURE_TOKEN", test_token)

    core = create_memory_manager(
        DatabaseConfig.from_path(db_path),
        semantic_index=_TestSemanticIndex(),
    )
    app = create_app(core)
    client = TestClient(app)
    return client, test_token, core


def test_capture_endpoint_requires_auth(capture_client):
    client, valid_token, _ = capture_client

    payload = {
        "content": "Decided to enforce atomic BEGIN IMMEDIATE for cross-process idempotency.",
        "event_category": "decision",
        "project_name": "SecurityTestProj",
    }

    # 1. Missing Authorization header
    resp_missing = client.post("/api/capture", json=payload)
    assert resp_missing.status_code == 401
    assert "Missing capture authentication token" in resp_missing.json()["detail"]

    # 2. Invalid Bearer token
    resp_invalid = client.post(
        "/api/capture",
        json=payload,
        headers={"Authorization": "Bearer wrong_token_value"},
    )
    assert resp_invalid.status_code == 401
    assert "Invalid capture authentication token" in resp_invalid.json()["detail"]

    # 3. Valid Bearer token
    resp_valid = client.post(
        "/api/capture",
        json=payload,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert data["status"] == "persisted"
    assert data["memory_id"] is not None


def test_capture_endpoint_accepts_x_header(capture_client):
    client, valid_token, _ = capture_client

    payload = {
        "content": "All timestamps must be offset-aware UTC datetimes.",
        "event_category": "convention",
        "project_name": "SecurityTestProj",
    }

    resp = client.post(
        "/api/capture",
        json=payload,
        headers={"X-Recall-Capture-Token": valid_token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "persisted"


def test_constant_time_token_verification():
    expected = "super_secret_token_123456"
    assert verify_capture_token(expected, expected) is True
    assert verify_capture_token(expected + "x", expected) is False
    assert verify_capture_token("", expected) is False
    assert verify_capture_token(expected, "") is False


def test_token_file_secure_permissions(tmp_path):
    token_file = tmp_path / "sub" / ".capture_token"
    token_val = "generated_secret_token_999"

    secure_write_token_file(token_file, token_val)
    assert token_file.is_file()
    assert token_file.read_text(encoding="utf-8") == token_val

    if sys.platform == "win32":
        # Check that icacls reports the file has no inherited permissions
        res = subprocess.run(["icacls", str(token_file)], capture_output=True, text=True)
        assert res.returncode == 0
        # Should contain username or No permissions inherited
        assert "(F)" in res.stdout or "(I)" not in res.stdout


def test_fail_closed_if_secure_permissions_fail(tmp_path):
    token_file = tmp_path / ".capture_token"

    # Simulate an error applying ACLs
    with patch("subprocess.run", side_effect=OSError("icacls failed")):
        with pytest.raises(PermissionError) as exc_info:
            secure_write_token_file(token_file, "token_that_should_fail")

    # File must be removed if secure permissions could not be established
    assert not token_file.exists()
    # Token must not be leaked in exception message
    assert "token_that_should_fail" not in str(exc_info.value)


def test_get_current_user_sid_on_windows():
    if sys.platform != "win32":
        pytest.skip("Windows only test")

    from recall_core.capture_service import get_current_user_sid
    import re

    sid = get_current_user_sid()
    assert isinstance(sid, str)
    assert re.match(r"^S-1-5-[0-9\-]+$", sid), f"Invalid Windows SID format: {sid}"


def test_sid_failure_fails_closed(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Windows only test")

    token_file = tmp_path / ".capture_token"
    with patch("recall_core.capture_service.get_current_user_sid", side_effect=PermissionError("SID failed")):
        with pytest.raises(PermissionError) as exc_info:
            secure_write_token_file(token_file, "secret_test_token_val")

    assert not token_file.exists()
    assert "secret_test_token_val" not in str(exc_info.value)


def test_deterministic_token_path_resolution(tmp_path, monkeypatch):
    """Verify API and hook resolve the exact same token path regardless of CWD."""
    from recall_core.capture_service import get_default_capture_token_path
    from scripts.recall_capture_hook import _resolve_token

    monkeypatch.delenv("RECALL_CAPTURE_TOKEN", raising=False)
    monkeypatch.delenv("RECALL_CAPTURE_TOKEN_FILE", raising=False)

    # 1. Custom token file path via RECALL_CAPTURE_TOKEN_FILE
    explicit_file = tmp_path / "explicit_token.txt"
    explicit_file.write_text("explicit_token_12345", encoding="utf-8")
    monkeypatch.setenv("RECALL_CAPTURE_TOKEN_FILE", str(explicit_file))

    resolved_api_path = get_default_capture_token_path()
    assert resolved_api_path == explicit_file.resolve()

    resolved_hook_token = _resolve_token(workspace_path=tmp_path)
    assert resolved_hook_token == "explicit_token_12345"

    # 2. Check resolution across varying CWDs without env vars
    monkeypatch.delenv("RECALL_CAPTURE_TOKEN_FILE", raising=False)
    repo_token_path = get_default_capture_token_path()

    # Changing CWD must NOT change the resolved path
    orig_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        cwd_changed_path = get_default_capture_token_path()
        assert cwd_changed_path == repo_token_path, "Token path must remain deterministic across different CWDs"
    finally:
        os.chdir(orig_cwd)
