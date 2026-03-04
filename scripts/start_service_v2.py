"""Start the PII service with V2 batch API support."""

import asyncio
import signal
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pii_service.config import settings
from pii_service.core.policy_loader import PolicyLoader
from pii_service.core.token_store import TokenStore
from pii_service.core.crypto_engine import CryptoEngine
from pii_service.core.structured_tokenizer import StructuredTokenizer
from pii_service.api.grpc_server_v2 import serve_v2
from pii_service.utils.logging import setup_logging
import structlog

logger = structlog.get_logger(__name__)


async def main():
    """Start the service with V2 API."""
    # Setup logging
    setup_logging(log_level=settings.LOG_LEVEL)
    
    logger.info("service_starting_v2", grpc_port=settings.GRPC_PORT)
    
    # Initialize components
    logger.info("loading_policy", path="policies/example_policy.yaml")
    policy_loader = PolicyLoader()
    await policy_loader.load_policy("policies/example_policy.yaml")
    logger.info("policy_loaded", version=policy_loader.policy.version)
    
    logger.info("initializing_token_store")
    token_store = TokenStore(
        redis_url=settings.REDIS_URL,
        pool_size=settings.REDIS_POOL_SIZE,
    )
    
    crypto_engine = CryptoEngine()
    
    structured_tokenizer = StructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
    )
    
    logger.info("components_initialized")
    
    # Start gRPC server with V2 API
    await serve_v2(
        structured_tokenizer=structured_tokenizer,
        port=settings.GRPC_PORT,
        max_workers=settings.GRPC_MAX_WORKERS,
        max_concurrent=settings.GRPC_MAX_CONCURRENT_REQUESTS,
        batch_size=settings.GRPC_BATCH_SIZE,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✓ Service stopped")
