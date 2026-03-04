"""gRPC server setup and configuration."""

import structlog
from concurrent import futures
from typing import Optional

import grpc

from ..proto import add_StructuredAnonymizerServicer_to_server
from .grpc_servicer import StructuredAnonymizerServicerImpl
from ..core.structured_tokenizer import StructuredTokenizer

logger = structlog.get_logger(__name__)

# Maximum message size: 100MB
MAX_MESSAGE_LENGTH = 100 * 1024 * 1024


async def create_grpc_server(
    structured_tokenizer: StructuredTokenizer,
    port: int = 50051,
    max_workers: int = 50,
    max_concurrent_requests: int = 1000,
    batch_size: int = 50,
    ssl_keyfile: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
    ssl_ca_certs: Optional[str] = None,
) -> grpc.aio.Server:
    """
    Create and configure an async gRPC server.

    Args:
        structured_tokenizer: Tokenizer for structured data operations
        port: Port to listen on (default: 50051)
        max_workers: Maximum number of worker threads (default: 50)
        max_concurrent_requests: Maximum concurrent requests per stream (default: 1000)
        batch_size: Number of records to batch together (default: 50)
        ssl_keyfile: Path to SSL private key file (optional)
        ssl_certfile: Path to SSL certificate file (optional)
        ssl_ca_certs: Path to SSL CA certificates file (optional)

    Returns:
        Configured gRPC server instance
    """
    # Create async gRPC server
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.max_send_message_length", MAX_MESSAGE_LENGTH),
            ("grpc.max_receive_message_length", MAX_MESSAGE_LENGTH),
            # Enable keepalive for long-running streams
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.http2.max_pings_without_data", 0),
            # Increase concurrent streams
            ("grpc.max_concurrent_streams", 1000),
            # Optimize for throughput
            ("grpc.http2.min_time_between_pings_ms", 10000),
            ("grpc.http2.max_ping_strikes", 2),
        ],
    )

    # Add servicer to server with concurrency limit
    servicer = StructuredAnonymizerServicerImpl(
        structured_tokenizer,
        max_concurrent=max_concurrent_requests,
        batch_size=batch_size
    )
    add_StructuredAnonymizerServicer_to_server(servicer, server)

    # Configure TLS if certificates provided
    if ssl_keyfile and ssl_certfile:
        logger.info("grpc_server_tls_enabled", port=port)

        with open(ssl_keyfile, "rb") as f:
            private_key = f.read()

        with open(ssl_certfile, "rb") as f:
            certificate_chain = f.read()

        root_certificates = None
        if ssl_ca_certs:
            with open(ssl_ca_certs, "rb") as f:
                root_certificates = f.read()

        server_credentials = grpc.ssl_server_credentials(
            [(private_key, certificate_chain)],
            root_certificates=root_certificates,
            require_client_auth=bool(root_certificates),
        )
        server.add_secure_port(f"[::]:{port}", server_credentials)
    else:
        logger.info("grpc_server_insecure", port=port)
        server.add_insecure_port(f"[::]:{port}")

    logger.info(
        "grpc_server_configured",
        port=port,
        max_workers=max_workers,
        max_concurrent_requests=max_concurrent_requests,
        batch_size=batch_size,
        max_message_size_mb=MAX_MESSAGE_LENGTH // (1024 * 1024),
    )

    return server


async def start_grpc_server(server: grpc.aio.Server) -> None:
    """
    Start the gRPC server.

    Args:
        server: Configured gRPC server instance
    """
    await server.start()
    logger.info("grpc_server_started")


async def stop_grpc_server(server: grpc.aio.Server, grace_period: float = 5.0) -> None:
    """
    Stop the gRPC server gracefully.

    Args:
        server: Running gRPC server instance
        grace_period: Time to wait for active RPCs to complete (seconds)
    """
    logger.info("grpc_server_stopping", grace_period=grace_period)
    await server.stop(grace_period)
    logger.info("grpc_server_stopped")
