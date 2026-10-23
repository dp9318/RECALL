"""OpenCode MCP adapter for RECALL Core."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from recall_mcp.server import create_server

__all__ = ["create_server"]


def __getattr__(name: str) -> Any:
    if name == "create_server":
        from recall_mcp.server import create_server

        return create_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)
