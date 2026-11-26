"""Operator authentication, session lifecycle, and request origin/host validation for RECALL HTTP API."""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request

from recall_core.capture_service import secure_write_token_file

SESSION_COOKIE_NAME = "recall_operator_session"
CSRF_COOKIE_NAME = "recall_csrf_token"
DEFAULT_SESSION_TTL_SECONDS = 28_800  # 8 hours

_ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def get_default_operator_token_path() -> Path:
    """Return the operator token path outside workspace repositories."""
    override = os.environ.get("RECALL_OPERATOR_TOKEN_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".recall" / ".operator_token"


def resolve_or_create_operator_token(token_path: Optional[Path] = None) -> str:
    """Load the operator token from env or user-scoped token file, creating one with strict ACLs if absent."""
    env_token = os.environ.get("RECALL_OPERATOR_TOKEN", "").strip()
    if env_token:
        return env_token

    path = token_path or get_default_operator_token_path()
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content

    token = secrets.token_urlsafe(32)
    secure_write_token_file(path, token)
    return token


def verify_operator_token(provided: str, expected: str) -> bool:
    """Constant-time comparison for operator tokens."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


@dataclass
class OperatorSession:
    session_id: str
    csrf_token: str
    expires_at: float


class OperatorSessionStore:
    """Thread-safe in-memory operator session store with expiration and revocation."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._sessions: dict[str, OperatorSession] = {}

    def create_session(self, ttl_seconds: Optional[int] = None) -> OperatorSession:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl_seconds
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        session = OperatorSession(
            session_id=session_id,
            csrf_token=csrf_token,
            expires_at=time.monotonic() + max(ttl, 1),
        )
        with self._lock:
            self._purge_expired_locked()
            self._sessions[session_id] = session
        return session

    def get_valid_session(self, session_id: Optional[str]) -> Optional[OperatorSession]:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if time.monotonic() >= session.expires_at:
                del self._sessions[session_id]
                return None
            return session

    def revoke_session(self, session_id: Optional[str]) -> bool:
        if not session_id:
            return False
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, sess in self._sessions.items() if now >= sess.expires_at]
        for sid in expired:
            del self._sessions[sid]


def is_valid_host(host_header: Optional[str], *, allow_testserver: bool = False) -> bool:
    """Validate Host header to prevent DNS-rebinding attacks against localhost."""
    if not host_header:
        return False
    raw = host_header.strip().lower()
    if raw.startswith("["):
        hostname = raw.split("]", 1)[0] + "]"
    else:
        hostname = raw.split(":", 1)[0]
    allowed = set(_ALLOWED_LOOPBACK_HOSTS)
    if allow_testserver:
        allowed.add("testserver")
    return hostname in allowed


def _extract_origin_tuple(url_value: Optional[str]) -> Optional[tuple[str, str]]:
    if not url_value:
        return None
    try:
        parsed = urlparse(url_value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return (parsed.scheme.lower(), parsed.netloc.lower())


def is_valid_origin(request: Request, allowed_origins: set[str]) -> bool:
    """Fail-closed Origin/Referer validation for cookie-authenticated mutations."""
    origin_header = request.headers.get("origin")
    if origin_header is not None:
        candidate = _extract_origin_tuple(origin_header)
    else:
        candidate = _extract_origin_tuple(request.headers.get("referer"))
    if candidate is None:
        return False

    allowed_tuples: set[tuple[str, str]] = set()
    for origin in allowed_origins:
        t = _extract_origin_tuple(origin)
        if t is not None:
            allowed_tuples.add(t)

    host = request.headers.get("host")
    if host:
        scheme = request.url.scheme.lower() or "http"
        allowed_tuples.add((scheme, host.strip().lower()))

    return candidate in allowed_tuples


def normalize_api_path(path: str) -> str:
    """Normalize both root and /api-prefixed paths for uniform auth checks."""
    if path == "/api":
        return "/"
    if path.startswith("/api/"):
        return path[4:]
    return path
