"""RECALL HTTP API package."""

__version__ = "1.1.0"
API_VERSION = __version__

from .app import app, create_app

__all__ = ["app", "create_app", "API_VERSION", "__version__"]

