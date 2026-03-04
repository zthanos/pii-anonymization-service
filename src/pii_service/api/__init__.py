"""API layer for REST and gRPC endpoints."""

from .app import create_app
from .endpoints import router, set_dependencies
from .middleware import (
    AuthenticationMiddleware,
    RequestLoggingMiddleware,
    setup_cors,
)

__all__ = [
    "create_app",
    "router",
    "set_dependencies",
    "AuthenticationMiddleware",
    "RequestLoggingMiddleware",
    "setup_cors",
]
