"""Executable entry point for the RECALL HTTP API server."""

from __future__ import annotations

import os
import uvicorn

from api.app import app


def main() -> None:
    """Run the dashboard API on the configured host and port.

    Defaults to 127.0.0.1 (loopback) for local operator security. Explicit
    network binding (e.g. 0.0.0.0) via RECALL_API_HOST requires appropriate
    network security controls (firewall, VPN, reverse proxy with TLS/auth).
    """
    host = os.getenv("RECALL_API_HOST", "127.0.0.1")
    port = int(os.getenv("RECALL_API_PORT", "8080"))
    reload = os.getenv("RECALL_API_RELOAD", "false").lower() in ("true", "1", "yes")
    if reload:
        uvicorn.run("api.app:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
