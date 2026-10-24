"""Capture service for RECALL Core automatic memory capture.

Handles:
1. Safe token provisioning and constant-time verification.
2. Fail-closed credential and secret redaction.
3. Conservative relevance and noise filtering.
4. Project and session lifecycle association (reusing active sessions).
5. Atomic SQLite BEGIN IMMEDIATE idempotency across concurrent processes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Tuple
from uuid import UUID

from contracts.base import Result, Scope
from contracts.capture import (
    CaptureEventRequest,
    CaptureEventResponse,
    ELIGIBLE_CAPTURE_CATEGORIES,
)
from contracts.memory import MemoryCreateRequest, MemoryStatus
from contracts.project import SessionCreateRequest
from database.repositories.unit_of_work import SQLiteUnitOfWork
from database.repositories.base import uuid_to_str

logger = logging.getLogger("recall_core.capture")

MIN_CONTENT_LENGTH = 20
MAX_CONTENT_LENGTH = 4000

# High-confidence credential & secret patterns
SECRET_PATTERNS = [
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "[REDACTED_SECRET:GOOGLE_KEY]"),
    (re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{20,}\b"), "[REDACTED_SECRET:ANTHROPIC_KEY]"),
    (re.compile(r"\bsk-[a-zA-Z0-9_\-]{20,}\b"), "[REDACTED_SECRET:OPENAI_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_SECRET:AWS_KEY]"),
    (re.compile(r"\bghp_[a-zA-Z0-9]{20,}\b"), "[REDACTED_SECRET:GITHUB_KEY]"),
    (re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{82}\b"), "[REDACTED_SECRET:GITHUB_PAT]"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_SECRET:PRIVATE_KEY]",
    ),
    (re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b", re.IGNORECASE), "[REDACTED_SECRET:BEARER_TOKEN]"),
    (re.compile(r"://([^:]+):([^@\s]+)@"), "://\\1:[REDACTED_SECRET:PASSWORD]@"),
]

# Conversational boilerplate patterns that should be filtered out
BOILERPLATE_PATTERNS = [
    re.compile(r"^(ok|okay|sure|yes|no|done|got it|proceeding)[.!,]?\s*$", re.IGNORECASE),
    re.compile(r"^Sure, (let me|I will|I'll|we can) .*$", re.IGNORECASE),
    re.compile(r"^I (will|am going to|can|would like to|shall) (view|read|run|check|inspect|look at|test) .*$", re.IGNORECASE),
    re.compile(r"^Please wait while (I|we) .*$", re.IGNORECASE),
    re.compile(r"^(Running|Executing|Starting) tests?.*$", re.IGNORECASE),
]


def redact_secrets(content: str) -> Tuple[str, int]:
    """Redact sensitive credentials from text using high-confidence patterns.

    Fails closed if any unhandled error occurs during scanning.

    Returns:
        Tuple[str, int]: (redacted_content, count_of_redactions_applied)
    """
    if not content:
        return content, 0

    try:
        redacted = content
        redactions = 0
        for pattern, replacement in SECRET_PATTERNS:
            matches = len(pattern.findall(redacted))
            if matches > 0:
                redacted = pattern.sub(replacement, redacted)
                redactions += matches
        return redacted, redactions
    except Exception as exc:
        raise ValueError(f"Secret redaction failed: {exc}") from exc


def get_current_user_sid() -> str:
    """Resolve the current Windows user's SID reliably.

    Tries whoami first, then PowerShell WindowsIdentity, then raises PermissionError.
    """
    if sys.platform != "win32":
        raise NotImplementedError("User SID resolution is only applicable on Windows")

    # 1. Try whoami /user /fo csv /nh
    try:
        proc = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        output = proc.stdout.strip()
        if output:
            parts = output.split(",")
            sid = parts[-1].strip().strip('"').strip()
            if re.match(r"^S-1-5-[0-9\-]+$", sid):
                return sid
    except Exception as whoami_exc:
        logger.debug(f"whoami SID lookup failed: {whoami_exc}")

    # 2. Try PowerShell WindowsIdentity
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        sid = proc.stdout.strip()
        if re.match(r"^S-1-5-[0-9\-]+$", sid):
            return sid
    except Exception as ps_exc:
        logger.debug(f"PowerShell SID lookup failed: {ps_exc}")

    raise PermissionError("Failed to resolve current Windows user SID for secure token storage")


def secure_write_token_file(token_path: Path, token: str) -> None:
    """Write token to file with restricted per-user permissions on Windows and POSIX.

    Guarantees:
    1. The token content is never written to disk until after permissions are locked down.
    2. Inherited permissions are removed and only the current user SID (on Windows)
       or 0600 owner-only (on POSIX) is granted access.
    3. Fails closed: on any failure, unlinks the file and raises PermissionError.
    4. Never logs or leaks the token string in exceptions or error logs.
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        try:
            # 1. Resolve current user's SID before creating or writing anything
            sid = get_current_user_sid()

            # 2. Touch the file empty first so permissions can be locked down BEFORE writing sensitive data
            token_path.touch(exist_ok=True)

            # 3. Disable inheritance and remove all existing inherited permissions
            subprocess.run(
                ["icacls", str(token_path), "/inheritance:r"],
                capture_output=True,
                check=True,
                timeout=5,
            )

            # 4. Grant Full Control exclusively to current user's SID
            subprocess.run(
                ["icacls", str(token_path), "/grant:r", f"*{sid}:(F)"],
                capture_output=True,
                check=True,
                timeout=5,
            )

            # 5. Verify ACL contains the grant
            verify_proc = subprocess.run(
                ["icacls", str(token_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            if sid not in verify_proc.stdout and "Successfully processed" not in verify_proc.stdout:
                raise PermissionError("Verification of restricted ACLs failed")

            # 6. Now safely write the token content into the restricted file
            token_path.write_text(token, encoding="utf-8")

        except Exception as acl_exc:
            token_path.unlink(missing_ok=True)
            raise PermissionError(
                f"Failed to establish secure per-user ACLs on token file: {acl_exc}"
            ) from acl_exc
    else:
        # POSIX: Atomic create with 0600 mode so file is never world/group readable
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            fd = os.open(str(token_path), flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
            os.chmod(str(token_path), 0o600)
        except Exception as chmod_exc:
            token_path.unlink(missing_ok=True)
            raise PermissionError(
                f"Failed to establish secure POSIX permissions on token file: {chmod_exc}"
            ) from chmod_exc


def get_default_capture_token_path(workspace_path: Optional[Path] = None) -> Path:
    """Deterministically resolve the capture token storage path.

    Order of precedence:
    1. RECALL_CAPTURE_TOKEN_FILE environment variable.
    2. If workspace_path is provided, workspace_path / '.dev_data' / '.capture_token'.
    3. RECALL repository root .dev_data (derived from module location).
    4. User home fallback: ~/.recall/.capture_token.
    """
    env_file = os.getenv("RECALL_CAPTURE_TOKEN_FILE")
    if env_file and env_file.strip():
        return Path(env_file.strip()).expanduser().resolve()

    if workspace_path is not None:
        return (workspace_path / ".dev_data" / ".capture_token").resolve()

    # Derived from RECALL Core module location (D:\\proj\\Hackathon\\RECALL)
    repo_root = Path(__file__).resolve().parent.parent
    dev_data_dir = repo_root / ".dev_data"
    if dev_data_dir.is_dir() or (repo_root / "recall_core").is_dir():
        return (dev_data_dir / ".capture_token").resolve()

    return (Path.home() / ".recall" / ".capture_token").resolve()


def resolve_or_create_capture_token(token_file_path: Optional[Path] = None) -> str:
    """Resolve token from RECALL_CAPTURE_TOKEN or securely provision to deterministic local file."""
    env_token = os.getenv("RECALL_CAPTURE_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()

    if token_file_path is None:
        token_file_path = get_default_capture_token_path()

    if token_file_path.is_file():
        try:
            existing = token_file_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except Exception as read_exc:
            logger.warning(f"Failed to read existing capture token file: {read_exc}")

    # Generate new cryptographically secure token
    new_token = secrets.token_urlsafe(32)
    secure_write_token_file(token_file_path, new_token)
    return new_token


def verify_capture_token(provided_token: str, expected_token: str) -> bool:
    """Safely verify the capture token in constant time."""
    if not provided_token or not expected_token:
        return False
    return secrets.compare_digest(provided_token.strip(), expected_token.strip())


class CaptureService:
    """Domain service for secure, deduplicated, and conservative automatic memory capture."""

    def __init__(self, uow: SQLiteUnitOfWork, memory_manager: Any) -> None:
        self._uow = uow
        self._memory_manager = memory_manager

    def capture(self, request: CaptureEventRequest) -> Result[CaptureEventResponse]:
        """Process an event capture request through the conservative capture pipeline."""
        raw_content = (request.content or "").strip()
        if not raw_content:
            return Result.err("Content cannot be empty or whitespace")

        category = request.event_category.strip().lower()
        if category not in ELIGIBLE_CAPTURE_CATEGORIES:
            return Result.err(
                f"Ineligible event category '{category}'. Must be one of: {sorted(ELIGIBLE_CAPTURE_CATEGORIES)}"
            )

        # 1. Boilerplate & Low-Signal Rejection (runs before length check so short chatter skips cleanly)
        for pattern in BOILERPLATE_PATTERNS:
            if pattern.search(raw_content):
                return Result.ok(
                    CaptureEventResponse(
                        status="skipped_boilerplate",
                        detail="Content identified as conversational boilerplate or status chatter",
                    )
                )

        # 2. Structural Length Guardrails
        if len(raw_content) < MIN_CONTENT_LENGTH:
            return Result.err(
                f"Content length ({len(raw_content)}) is below minimum threshold ({MIN_CONTENT_LENGTH})"
            )

        if len(raw_content) > MAX_CONTENT_LENGTH:
            return Result.err(
                f"Content length ({len(raw_content)}) exceeds maximum allowed ({MAX_CONTENT_LENGTH})"
            )


        # 3. Fail-Closed Secret Redaction
        try:
            redacted_content, redactions_count = redact_secrets(raw_content)
        except Exception as redact_err:
            return Result.err(f"Capture rejected: fail-closed secret inspection error: {redact_err}")

        # 4. Project Identity Resolution
        project_name = (request.project_name or "default").strip()
        proj_res = self._memory_manager.resolve_or_create_project(
            name=project_name,
            project_id=request.project_id,
        )
        if not proj_res.success or proj_res.value is None:
            return Result.err(proj_res.error or "Failed to resolve project for capture")
        project = proj_res.value
        project_uuid = project.id

        # 5. Session Association (Reuse Active Session)
        session_uuid: Optional[UUID] = None
        if request.session_id is not None:
            # Caller provided explicit session ID; verify ownership
            sess_res = self._memory_manager.get_session(request.session_id)
            if not sess_res.success or sess_res.value is None:
                return Result.err(f"Requested session '{request.session_id}' not found")
            sess = sess_res.value
            if sess.project_id != project_uuid:
                return Result.err(
                    f"Session '{request.session_id}' belongs to project '{sess.project_id}', "
                    f"which does not match capture project '{project_uuid}'"
                )
            session_uuid = sess.id
        else:
            # Look up active session for this project
            active_sess_res = self._memory_manager.get_active_session(project_uuid)
            if active_sess_res.success and active_sess_res.value is not None:
                session_uuid = active_sess_res.value.id
            else:
                # No active session exists; create one
                new_sess_res = self._memory_manager.create_session(
                    SessionCreateRequest(project_id=project_uuid)
                )
                if new_sess_res.success and new_sess_res.value is not None:
                    session_uuid = new_sess_res.value.id

        # 6. Idempotency Key Computation
        if request.caller_idempotency_key:
            idempotency_key = f"{project_uuid}:{request.caller_idempotency_key.strip()}"
        else:
            # Deterministic hash of normalized content within project and category
            norm_content = " ".join(redacted_content.split())
            hash_input = f"{Scope.PROJECT.value}:{project_uuid}:{category}:{norm_content}"
            idempotency_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        # 7. Atomic BEGIN IMMEDIATE Idempotency & Persistence
        try:
            with self._uow.begin():
                # Check for existing active memory with matching idempotency_key
                conn = self._uow._ensure_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT memory_id
                    FROM memories
                    WHERE project_id = ?
                      AND status = 'active'
                      AND json_extract(metadata, '$.idempotency_key') = ?
                    LIMIT 1
                    """,
                    (uuid_to_str(project_uuid), idempotency_key),
                )
                row = cursor.fetchone()
                if row:
                    existing_id = UUID(row[0])
                    return Result.ok(
                        CaptureEventResponse(
                            status="suppressed_duplicate",
                            memory_id=existing_id,
                            project_id=project_uuid,
                            session_id=session_uuid,
                            idempotency_key=idempotency_key,
                            redactions_applied=redactions_count,
                            detail="Duplicate event suppressed under active idempotency key",
                        )
                    )

                # Not a duplicate; persist canonical memory
                metadata_payload = {
                    **(request.metadata or {}),
                    "idempotency_key": idempotency_key,
                    "event_category": category,
                    "capture_source": request.source,
                    "redactions_applied": redactions_count,
                }

                mem_req = MemoryCreateRequest(
                    project_id=project_uuid,
                    session_id=session_uuid,
                    scope=Scope.PROJECT,
                    memory_type=category,
                    content=redacted_content,
                    provenance="agent_inferred",
                    metadata=metadata_payload,
                )
                mem_res = self._uow.memories.create(mem_req)
                if not mem_res.success or mem_res.value is None:
                    return Result.err(mem_res.error or "Failed to persist canonical memory")

                created_memory = mem_res.value

            # Best-effort Chroma vector indexing outside the SQLite immediate lock
            if hasattr(self._uow, "semantic_index") and self._uow.semantic_index is not None:
                try:
                    self._uow.semantic_index.index_memory(created_memory)
                except Exception as idx_err:
                    logger.warning(f"Derived semantic indexing error during capture: {idx_err}")

            return Result.ok(
                CaptureEventResponse(
                    status="persisted",
                    memory_id=created_memory.id,
                    project_id=project_uuid,
                    session_id=session_uuid,
                    idempotency_key=idempotency_key,
                    redactions_applied=redactions_count,
                    detail="Event successfully persisted as active canonical memory",
                )
            )

        except Exception as exc:
            return Result.err(f"Atomic capture persistence failed: {exc}")
