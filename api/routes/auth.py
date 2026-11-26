"""Operator authentication routes for Dashboard session lifecycle."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response

from api.auth import (
    CSRF_COOKIE_NAME,
    DEFAULT_SESSION_TTL_SECONDS,
    OperatorSessionStore,
    SESSION_COOKIE_NAME,
    is_valid_origin,
    resolve_or_create_operator_token,
    verify_operator_token,
)

router = APIRouter(tags=["auth"])


def _is_https_mode() -> bool:
    return os.getenv("RECALL_API_HTTPS", "false").lower() in ("true", "1", "yes")


@router.post("/auth/session")
def create_operator_session(
    request: Request,
    response: Response,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Authenticate an operator token and issue an HttpOnly session cookie + CSRF token."""
    provided = ""
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.split("Bearer ", 1)[1].strip()
    elif isinstance(payload, dict) and isinstance(payload.get("token"), str):
        provided = payload["token"].strip()

    expected = resolve_or_create_operator_token()
    if not verify_operator_token(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid operator authentication token")

    store: OperatorSessionStore = request.app.state.session_store
    try:
        ttl = max(int(os.getenv("RECALL_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))), 1)
    except ValueError:
        ttl = DEFAULT_SESSION_TTL_SECONDS
    session = store.create_session(ttl_seconds=ttl)
    secure_cookie = _is_https_mode()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        samesite="strict",
        secure=secure_cookie,
        path="/",
        max_age=ttl,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=session.csrf_token,
        httponly=False,
        samesite="strict",
        secure=secure_cookie,
        path="/",
        max_age=ttl,
    )
    return {"authenticated": True, "expires_in_seconds": ttl}


@router.post("/auth/logout")
def logout_operator_session(request: Request, response: Response) -> dict[str, Any]:
    """Revoke the active operator session and clear cookies."""
    store: OperatorSessionStore = request.app.state.session_store
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        allowed_origins = set(getattr(request.app.state, "allowed_origins", set()))
        if not is_valid_origin(request, allowed_origins):
            raise HTTPException(status_code=403, detail="Invalid or missing Origin")
        session = store.get_valid_session(session_id)
        if session is not None:
            csrf_header = request.headers.get("x-csrf-token", "")
            if not csrf_header or not hmac.compare_digest(csrf_header, session.csrf_token):
                raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")
        store.revoke_session(session_id)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/auth/status")
def get_auth_status(request: Request) -> dict[str, Any]:
    """Return whether the current request holds a valid operator session."""
    require_auth = bool(getattr(request.app.state, "require_auth", True))
    store: OperatorSessionStore = request.app.state.session_store
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = store.get_valid_session(session_id) is not None
    return {"authenticated": authenticated, "auth_required": require_auth}
