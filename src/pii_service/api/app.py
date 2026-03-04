"""FastAPI application setup and configuration."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

from ..api.middleware import (
    AuthenticationMiddleware,
    RequestLoggingMiddleware,
    setup_cors,
)
from ..api.endpoints import router, set_dependencies
from ..core.policy_loader import PolicyLoader
from ..core.token_store import TokenStore
from ..core.structured_tokenizer import StructuredTokenizer
from ..core.unstructured_tokenizer import UnstructuredTokenizer


logger = structlog.get_logger(__name__)


def create_app(
    policy_loader: PolicyLoader,
    token_store: TokenStore,
    structured_tokenizer: StructuredTokenizer,
    unstructured_tokenizer: UnstructuredTokenizer,
) -> FastAPI:
    """
    Create and configure FastAPI application with dependencies.
    
    Args:
        policy_loader: PolicyLoader instance
        token_store: TokenStore instance
        structured_tokenizer: StructuredTokenizer instance
        unstructured_tokenizer: UnstructuredTokenizer instance
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="PII Anonymization Service",
        version="1.0.0",
        description="High-performance tokenization and de-tokenization service for PII data",
    )

    # Set dependencies for endpoints
    set_dependencies(
        policy_loader=policy_loader,
        structured_tokenizer=structured_tokenizer,
        unstructured_tokenizer=unstructured_tokenizer,
        token_store=token_store,
    )

    # Setup CORS
    setup_cors(app)

    # Add request logging middleware (first, so it wraps everything)
    app.add_middleware(RequestLoggingMiddleware)

    # Add authentication middleware
    app.add_middleware(AuthenticationMiddleware)

    # Include API router
    app.include_router(router)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Handle unhandled exceptions globally.
        
        Args:
            request: FastAPI request
            exc: Exception that was raised
            
        Returns:
            JSON error response
        """
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(exc),
            },
        )

    return app
