"""FastAPI application factory and middleware configuration for RECALL."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
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


def create_app(memory_manager: MemoryManager | None = None) -> FastAPI:
    """Build and configure the FastAPI application bound to a RECALL MemoryManager.

    Args:
        memory_manager: Optional explicitly constructed MemoryManager instance.
            If None, dependencies fall back to singleton application state or
            lazy instantiation via `api.dependencies.get_manager`.

    Returns:
        FastAPI: Fully configured ASGI application with CORS middleware, state,
        and all modular routers mounted.
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
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.memory_manager = memory_manager

    # Register modular routers
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(memories_router)
    app.include_router(sessions_router)
    app.include_router(instructions_router)
    app.include_router(conflicts_router)
    app.include_router(stats_router)
    app.include_router(context_router)

    return app


app = create_app()
