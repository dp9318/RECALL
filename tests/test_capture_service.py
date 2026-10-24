"""Comprehensive tests for RECALL CaptureService relevance, redaction, and persistence."""

from __future__ import annotations

from uuid import uuid4
import pytest

from contracts.base import Scope
from contracts.capture import CaptureEventRequest, CaptureEventResponse
from contracts.retrieval import RetrievalRequest, ContextAssemblyRequest
from database.config import DatabaseConfig
from recall_core.bootstrap import create_memory_manager
from recall_core.capture_service import redact_secrets
from tests.test_mcp_bootstrap import _TestSemanticIndex


@pytest.fixture
def capture_manager(tmp_path):
    """Provide an isolated MemoryManager instance."""
    db_path = tmp_path / "capture_service_test.sqlite3"
    core = create_memory_manager(
        DatabaseConfig.from_path(db_path),
        semantic_index=_TestSemanticIndex(),
    )
    yield core
    core.close()


# --- Secret Redaction Tests ---

def test_secret_redaction_patterns():
    # OpenAI key
    text1, count1 = redact_secrets("Configured sk-1234567890abcdef1234567890 in settings.")
    assert "[REDACTED_SECRET:OPENAI_KEY]" in text1
    assert "sk-" not in text1
    assert count1 == 1

    # Anthropic key
    text2, count2 = redact_secrets("Anthropic key is sk-ant-api03-abcdef1234567890abcdef for model.")
    assert "[REDACTED_SECRET:ANTHROPIC_KEY]" in text2
    assert count2 == 1

    # AWS key
    text3, count3 = redact_secrets("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE in config.")
    assert "[REDACTED_SECRET:AWS_KEY]" in text3
    assert count3 == 1

    # GitHub token
    text4, count4 = redact_secrets("Token is ghp_1234567890abcdef1234567890abcdef123456 in header.")
    assert "[REDACTED_SECRET:GITHUB_KEY]" in text4
    assert count4 == 1

    # Private key block
    key_block = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    text5, count5 = redact_secrets(f"Loaded server key: {key_block}")
    assert "[REDACTED_SECRET:PRIVATE_KEY]" in text5
    assert "BEGIN RSA" not in text5
    assert count5 == 1

    # Bearer token
    text6, count6 = redact_secrets("Authorization: Bearer my_secret_token_1234567890")
    assert "[REDACTED_SECRET:BEARER_TOKEN]" in text6
    assert count6 == 1

    # Password in URI
    text7, count7 = redact_secrets("Database connected at postgres://admin:super_secret_pw@localhost:5432/recall")
    assert "[REDACTED_SECRET:PASSWORD]" in text7
    assert "super_secret_pw" not in text7
    assert count7 == 1


# --- Category and Relevance Filter Tests ---

def test_capture_eligible_categories(capture_manager):
    for cat in ["decision", "convention", "architecture", "task_outcome"]:
        req = CaptureEventRequest(
            content=f"Substantive durable context for eligible category {cat} in project.",
            event_category=cat,
            project_name="CategoryTestProject",
        )
        res = capture_manager.capture_memory(req)
        assert res.success is True
        assert res.value.status == "persisted"
        assert res.value.memory_id is not None


def test_capture_ineligible_category_rejected(capture_manager):
    req = CaptureEventRequest(
        content="This should be rejected because arbitrary is not an allowed category.",
        event_category="arbitrary_tag",
        project_name="CategoryTestProject",
    )
    res = capture_manager.capture_memory(req)
    assert res.success is False
    assert "Ineligible event category" in res.error


def test_capture_length_guardrails(capture_manager):
    # Below minimum
    req_short = CaptureEventRequest(
        content="Too short",
        event_category="decision",
        project_name="CategoryTestProject",
    )
    res_short = capture_manager.capture_memory(req_short)
    assert res_short.success is False
    assert "below minimum threshold" in res_short.error

    # Above maximum
    req_long = CaptureEventRequest(
        content="X" * 4001,
        event_category="decision",
        project_name="CategoryTestProject",
    )
    res_long = capture_manager.capture_memory(req_long)
    assert res_long.success is False
    assert "exceeds maximum allowed" in res_long.error


def test_capture_boilerplate_chatter_skipped(capture_manager):
    for boilerplate in [
        "Sure, let me help you with that right away.",
        "I will view the file to check its contents.",
        "Please wait while I run the tests for you.",
        "Running tests now.",
    ]:
        req = CaptureEventRequest(
            content=boilerplate,
            event_category="decision",
            project_name="CategoryTestProject",
        )
        res = capture_manager.capture_memory(req)
        assert res.success is True
        assert res.value.status == "skipped_boilerplate"
        assert res.value.memory_id is None


# --- Session Reuse and Association Tests ---

def test_capture_reuses_active_session(capture_manager):
    project_name = "SessionReuseProject"

    req1 = CaptureEventRequest(
        content="First milestone decision recorded during ongoing active session.",
        event_category="decision",
        project_name=project_name,
    )
    res1 = capture_manager.capture_memory(req1)
    assert res1.success is True
    session_id_1 = res1.value.session_id
    assert session_id_1 is not None

    req2 = CaptureEventRequest(
        content="Second architectural milestone recorded in the exact same active session.",
        event_category="architecture",
        project_name=project_name,
    )
    res2 = capture_manager.capture_memory(req2)
    assert res2.success is True
    session_id_2 = res2.value.session_id

    # Active session must be reused across events
    assert session_id_1 == session_id_2


def test_capture_rejects_foreign_project_session(capture_manager):
    # Create project A and project B
    proj_a = capture_manager.resolve_or_create_project("ProjectA").value
    proj_b = capture_manager.resolve_or_create_project("ProjectB").value

    # Create session on project A
    sess_a = capture_manager.create_session(
        from_contract := __import__("contracts.project", fromlist=["SessionCreateRequest"]).SessionCreateRequest(project_id=proj_a.id)
    ).value

    # Attempt to capture into Project B using Project A's session ID
    req = CaptureEventRequest(
        content="Attempting cross-project session association should fail securely.",
        event_category="decision",
        project_name="ProjectB",
        session_id=sess_a.id,
    )
    res = capture_manager.capture_memory(req)
    assert res.success is False
    assert "does not match capture project" in res.error


# --- Idempotency & Duplicate Suppression Tests ---

def test_sequential_duplicate_suppression(capture_manager):
    project_name = "IdempotencyProject"
    content = "Decided to enforce SQLite immediate locking across all concurrent processes."

    req1 = CaptureEventRequest(
        content=content,
        event_category="decision",
        project_name=project_name,
    )
    res1 = capture_manager.capture_memory(req1)
    assert res1.success is True
    assert res1.value.status == "persisted"
    canonical_id = res1.value.memory_id

    # Submit identical content again
    req2 = CaptureEventRequest(
        content=f"  {content}  ",  # with whitespace variation
        event_category="decision",
        project_name=project_name,
    )
    res2 = capture_manager.capture_memory(req2)
    assert res2.success is True
    assert res2.value.status == "suppressed_duplicate"
    # Returns existing canonical memory ID
    assert res2.value.memory_id == canonical_id


# --- Retrieval Integration Tests ---

def test_captured_memory_is_retrievable_and_assembled(capture_manager):
    project_name = "RetrievalProject"
    content = "Architecture rule: All domain models must be defined as dataclasses in contracts."

    req = CaptureEventRequest(
        content=content,
        event_category="convention",
        project_name=project_name,
    )
    res = capture_manager.capture_memory(req)
    assert res.success is True
    project_id = res.value.project_id
    memory_id = res.value.memory_id

    # 1. Search via retrieve()
    search_res = capture_manager.retrieve(
        RetrievalRequest(
            query="Architecture rule domain models",
            project_id=project_id,
            limit=10,
        )
    )
    assert search_res.success is True
    found_ids = [m.id for m in search_res.value.memories]
    assert memory_id in found_ids
    captured_mem = next(m for m in search_res.value.memories if m.id == memory_id)
    assert captured_mem.provenance == "agent_inferred"

    # 2. Assemble context via assemble_context()
    ctx_res = capture_manager.assemble_context(
        ContextAssemblyRequest(project_id=project_id)
    )
    assert ctx_res.success is True
    ctx_mem_ids = [m.id for m in ctx_res.value.active_memories]
    assert memory_id in ctx_mem_ids
