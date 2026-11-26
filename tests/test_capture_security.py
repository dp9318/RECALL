"""Tests for RECALL accountless capture endpoint validation and secret redaction."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager
from recall_core.capture_service import redact_secrets
from tests.test_mcp_bootstrap import _TestSemanticIndex


@pytest.fixture
def capture_client(tmp_path):
    """Provide an accountless TestClient with an isolated DB."""
    db_path = tmp_path / "capture_accountless_test.sqlite3"
    core = create_memory_manager(
        DatabaseConfig.from_path(db_path),
        semantic_index=_TestSemanticIndex(),
    )
    app = create_app(core)
    client = TestClient(app)
    try:
        yield client, core
    finally:
        core.close()


def test_capture_endpoint_accepts_accountless_requests_without_headers(capture_client):
    client, _ = capture_client

    payload = {
        "content": "Decided to enforce atomic BEGIN IMMEDIATE for cross-process idempotency.",
        "event_category": "decision",
        "project_name": "AccountlessCaptureProj",
    }

    resp = client.post("/api/capture", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "persisted"
    assert data["memory_id"] is not None


def test_capture_endpoint_redacts_secrets_and_validates_payload(capture_client):
    client, core = capture_client

    # Secret redaction still runs without authentication tokens
    secret_payload = {
        "content": "Architecture note: never hardcode sk-abcdefghijklmnopqrstuvwxyz123456 in configs.",
        "event_category": "architecture",
        "project_name": "AccountlessCaptureProj",
    }
    resp = client.post("/api/capture", json=secret_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "persisted"
    assert data["redactions_applied"] >= 1

    saved = core.get_memory(data["memory_id"])
    assert saved.success and saved.value is not None
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in saved.value.content
    assert "[REDACTED_SECRET:OPENAI_KEY]" in saved.value.content

    # Ineligible category still fails validation (422)
    invalid_resp = client.post(
        "/api/capture",
        json={
            "content": "Valid length content with an ineligible category value.",
            "event_category": "casual_chat",
            "project_name": "AccountlessCaptureProj",
        },
    )
    assert invalid_resp.status_code == 422


def test_redact_secrets_masks_credentials():
    redacted, count = redact_secrets("Use Bearer abcdefghijklmnopqrstuvwxyz1234567890 for external relay")
    assert count == 1
    assert "[REDACTED_SECRET:BEARER_TOKEN]" in redacted
