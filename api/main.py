"""Executable entry point for the RECALL HTTP API server."""

from __future__ import annotations

import os
import uvicorn

from api.app import app


def main() -> None:
    """Run the dashboard API on the configured host and port."""
    host = os.getenv("RECALL_API_HOST", "0.0.0.0")
    port = int(os.getenv("RECALL_API_PORT", "8080"))
    reload = os.getenv("RECALL_API_RELOAD", "false").lower() in ("true", "1", "yes")
    if reload:
        uvicorn.run("api.app:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
