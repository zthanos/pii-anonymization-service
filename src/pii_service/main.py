"""Main entry point for the PII Anonymization Service."""

import asyncio
import signal
import sys
import structlog
import uvicorn

from .config import settings
from .core.policy_loader import PolicyLoader
from .core.token_store import TokenStore
from .core.crypto_engine import CryptoEngine
from .core.structured_tokenizer import StructuredTokenizer
from .core.unstructured_tokenizer import UnstructuredTokenizer
from .core.llm_client import LLMClient
from .api.app import create_app
from .api.grpc_server import create_grpc_server, start_grpc_server, stop_grpc_server
from .utils.logging import setup_logging

logger = structlog.get_logger(__name__)

# Global references for graceful shutdown
grpc_server = None
shutdown_event = asyncio.Event()


async def initialize_components():
    """
    Initialize all service components.

    Returns:
        Tuple of (policy_loader, token_store, structured_tokenizer, unstructured_tokenizer)
    """
    logger.info("initializing_components")

    # Initialize PolicyLoader and load policy
    logger.info("loading_policy", path=settings.POLICY_PATH)
    policy_loader = PolicyLoader()
    await policy_loader.load_policy(settings.POLICY_PATH)
    logger.info("policy_loaded", version=policy_loader.policy.version)

    # Initialize TokenStore with Redis connection pool
    logger.info("initializing_token_store", redis_url=settings.REDIS_URL)
    token_store = TokenStore(
        redis_url=settings.REDIS_URL,
        pool_size=settings.REDIS_POOL_SIZE,
    )
    logger.info("token_store_initialized")

    # Initialize CryptoEngine
    crypto_engine = CryptoEngine()
    logger.info("crypto_engine_initialized")

    # Initialize LLMClient
    llm_client = LLMClient(
        base_url=settings.OPENAI_BASE_URL,
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )
    logger.info("llm_client_initialized")

    # Initialize StructuredTokenizer
    structured_tokenizer = StructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
    )
    logger.info("structured_tokenizer_initialized")

    # Initialize UnstructuredTokenizer
    unstructured_tokenizer = UnstructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
        llm_client=llm_client,
    )
    logger.info("unstructured_tokenizer_initialized")

    logger.info("components_initialized")

    return policy_loader, token_store, structured_tokenizer, unstructured_tokenizer


async def start_fastapi_server(app, host: str = "0.0.0.0", port: int = 8000):
    """
    Start the FastAPI server.

    Args:
        app: FastAPI application instance
        host: Host to bind to
        port: Port to bind to
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,  # Use our structlog configuration
        ssl_keyfile=settings.SSL_KEYFILE,
        ssl_certfile=settings.SSL_CERTFILE,
        ssl_ca_certs=settings.SSL_CA_CERTS,
    )
    server = uvicorn.Server(config)

    logger.info("fastapi_server_starting", host=host, port=port)

    # Run until shutdown event is set
    await server.serve()


async def run_servers():
    """
    Run both FastAPI and gRPC servers concurrently.
    """
    global grpc_server

    try:
        # Initialize components
        (
            policy_loader,
            token_store,
            structured_tokenizer,
            unstructured_tokenizer,
        ) = await initialize_components()

        # Create FastAPI app with dependencies
        app = create_app(
            policy_loader=policy_loader,
            token_store=token_store,
            structured_tokenizer=structured_tokenizer,
            unstructured_tokenizer=unstructured_tokenizer,
        )

        # Create gRPC server
        grpc_server = await create_grpc_server(
            structured_tokenizer=structured_tokenizer,
            port=settings.GRPC_PORT,
            max_workers=settings.GRPC_MAX_WORKERS,
            max_concurrent_requests=settings.GRPC_MAX_CONCURRENT_REQUESTS,
            batch_size=settings.GRPC_BATCH_SIZE,
            ssl_keyfile=settings.SSL_KEYFILE,
            ssl_certfile=settings.SSL_CERTFILE,
            ssl_ca_certs=settings.SSL_CA_CERTS,
        )

        # Start gRPC server
        await start_grpc_server(grpc_server)

        # Start FastAPI server (this will block until shutdown)
        await start_fastapi_server(app, host="0.0.0.0", port=settings.HTTP_PORT)

    except Exception as e:
        logger.error("server_startup_error", error=str(e), exc_info=True)
        raise


def handle_shutdown_signal(signum, frame):
    """
    Handle shutdown signals (SIGTERM, SIGINT).

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_event.set()


async def shutdown():
    """
    Perform graceful shutdown of all services.
    """
    global grpc_server

    logger.info("shutting_down")

    # Stop gRPC server
    if grpc_server:
        await stop_grpc_server(grpc_server, grace_period=5.0)

    logger.info("shutdown_complete")


def main():
    """
    Main entry point for the service.
    """
    # Configure logging
    setup_logging(log_level=settings.LOG_LEVEL)

    logger.info(
        "service_starting",
        http_port=settings.HTTP_PORT,
        grpc_port=settings.GRPC_PORT,
        policy_path=settings.POLICY_PATH,
    )

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

    # Run the servers
    try:
        asyncio.run(run_servers())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error("service_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Perform cleanup
        asyncio.run(shutdown())


if __name__ == "__main__":
    main()
