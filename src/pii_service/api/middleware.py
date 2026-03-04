"""FastAPI middleware for authentication and request logging."""

import time
import uuid
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
import structlog

from ..config import settings


logger = structlog.get_logger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate Bearer tokens for API authentication."""

    # Endpoints that don't require authentication
    SKIP_AUTH_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        """
        Validate Bearer token for all requests except health and metrics.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response from next handler or 401 error
        """
        # Skip authentication for health and metrics endpoints
        if request.url.path in self.SKIP_AUTH_PATHS:
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing Authorization header"}
            )

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid Authorization header format. Expected 'Bearer <token>'"}
            )

        # Extract API key (token)
        api_key = auth_header[7:]  # Remove "Bearer " prefix

        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Empty API key"}
            )

        # Validate API key if configured
        if settings.API_KEY and api_key != settings.API_KEY:
            logger.warning(
                "invalid_api_key_attempt",
                client_ip=request.client.host if request.client else None,
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid API key"}
            )

        # Extract client_id from API key for rate limiting
        # Use the first 8 characters as client_id
        client_id = api_key[:8] if len(api_key) >= 8 else api_key

        # Store client_id in request state for use in endpoints
        request.state.client_id = client_id
        request.state.api_key = api_key

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests with structured data."""

    async def dispatch(self, request: Request, call_next):
        """
        Log request start and completion with timing.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response with X-Request-ID header
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Store request_id in request state
        request.state.request_id = request_id

        # Bind request_id to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Log request start
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        # Track request timing
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log request completion
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_seconds=duration,
            )

            # Add request_id to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate duration
            duration = time.time() - start_time

            # Log request error
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_seconds=duration,
                error=str(e),
                exc_info=True,
            )

            # Re-raise exception
            raise

        finally:
            # Clear structlog context
            structlog.contextvars.clear_contextvars()


def setup_cors(app) -> None:
    """
    Configure CORS middleware.
    
    Args:
        app: FastAPI application
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify allowed origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
