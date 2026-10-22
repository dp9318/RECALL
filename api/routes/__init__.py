"""Route registration and router aggregation for the RECALL HTTP API."""

from __future__ import annotations

from .conflicts import router as conflicts_router
from .context import router as context_router
from .health import router as health_router
from .instructions import router as instructions_router
from .memories import router as memories_router
from .projects import router as projects_router
from .sessions import router as sessions_router
from .stats import router as stats_router

__all__ = [
    "health_router",
    "projects_router",
    "memories_router",
    "sessions_router",
    "instructions_router",
    "conflicts_router",
    "stats_router",
    "context_router",
]
