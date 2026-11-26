"""FastAPI application factory and middleware configuration for RECALL."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.auth import (
    OperatorSessionStore,
    SESSION_COOKIE_NAME,
    is_valid_host,
    is_valid_origin,
    normalize_api_path,
    resolve_or_create_operator_token,
    verify_operator_token,
)
from api.routes import (
    auth_router,
    capture_router,
    conflicts_router,
    context_router,
    health_router,
    instructions_router,
    memories_router,
    projects_router,
    sessions_router,
    stats_router,
)
from recall_core.memory_manager import MemoryManager


def create_app(memory_manager: MemoryManager | None = None, *, require_auth: bool = True) -> FastAPI:
    """Build and configure the FastAPI application bound to a RECALL MemoryManager.

    Args:
        memory_manager: Optional explicitly constructed MemoryManager instance.
            If None, dependencies fall back to singleton application state or
            lazy instantiation via `api.dependencies.get_manager`.

    Returns:
        FastAPI: Fully configured ASGI application with CORS middleware, state,
        all modular routers mounted, and production frontend served at root.
    """
    app = FastAPI(title="RECALL HTTP API", version="1.1.0")

    cors_origins = [
        origin.strip()
        for origin in os.getenv("RECALL_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if not cors_origins:
        cors_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Recall-Capture-Token"],
    )

    app.state.memory_manager = memory_manager
    app.state.require_auth = require_auth
    app.state.allowed_origins = set(cors_origins)
    app.state.session_store = OperatorSessionStore()

    _public_paths = {
        "/",
        "/health",
        "/healthz",
        "/auth/session",
        "/auth/status",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    _spa_routes = {"/overview", "/chat", "/memories", "/conflicts", "/instructions", "/settings"}
    _public_prefixes = ("/assets/", "/favicon", "/apple-touch-icon")

    @app.middleware("http")
    async def operator_auth_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        allow_testserver = (
            not require_auth
            or "PYTEST_CURRENT_TEST" in os.environ
            or os.getenv("RECALL_API_ALLOW_TESTSERVER", "").lower() in ("true", "1", "yes")
        )
        if not is_valid_host(request.headers.get("host"), allow_testserver=allow_testserver):
            return JSONResponse(status_code=403, content={"detail": "Invalid Host header"})

        norm_path = normalize_api_path(request.url.path)
        accept_header = request.headers.get("accept", "").lower()
        is_browser_spa_nav = (
            request.method == "GET"
            and not request.url.path.startswith("/api/")
            and norm_path in _spa_routes
            and "text/html" in accept_header
        )
        if norm_path in _public_paths or norm_path.startswith(_public_prefixes) or norm_path == "/capture" or is_browser_spa_nav:
            return await call_next(request)

        if not require_auth:
            return await call_next(request)

        # Operator Bearer token auth (non-browser CLI/automation)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header.split("Bearer ", 1)[1].strip()
            expected = resolve_or_create_operator_token()
            if not verify_operator_token(provided, expected):
                return JSONResponse(status_code=401, content={"detail": "Invalid operator token"})
            return await call_next(request)

        # Operator session cookie auth (browser Dashboard)
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        session = app.state.session_store.get_valid_session(session_id)
        if session is None:
            return JSONResponse(status_code=401, content={"detail": "Operator authentication required"})

        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            if not is_valid_origin(request, app.state.allowed_origins):
                return JSONResponse(status_code=403, content={"detail": "Invalid or missing Origin"})
            csrf_header = request.headers.get("x-csrf-token", "")
            if not csrf_header or not hmac.compare_digest(csrf_header, session.csrf_token):
                return JSONResponse(status_code=403, content={"detail": "Invalid or missing CSRF token"})

        return await call_next(request)

    # Register modular API routers (mounted at root and with /api prefix for proxy compatibility)
    routers = [
        auth_router,
        health_router,
        projects_router,
        memories_router,
        sessions_router,
        instructions_router,
        conflicts_router,
        stats_router,
        context_router,
        capture_router,
    ]
    for router in routers:
        app.include_router(router)
        app.include_router(router, prefix="/api")

    # Mount pre-built production frontend if available
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir() and (frontend_dist / "index.html").is_file():
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend_assets")

        @app.get("/", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(frontend_dist / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail="API route not found")
            if full_path:
                candidate = (frontend_dist / full_path).resolve()
                if candidate.is_file() and str(candidate).startswith(str(frontend_dist.resolve())):
                    return FileResponse(str(candidate))
            return FileResponse(str(frontend_dist / "index.html"))

    return app


app = create_app()

