"""Redis-based token storage with connection pooling and retry logic."""

from typing import List, Optional, Dict
from dataclasses import dataclass
import structlog
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from tenacity import retry, stop_after_attempt, wait_exponential


logger = structlog.get_logger()


@dataclass
class TokenMapping:
    """Mapping of token to encrypted value for batch operations.
    
    Attributes:
        system_id: System identifier for namespacing
        token: Token string
        encrypted_value: AES-256-GCM encrypted PII value
        ttl_seconds: Time-to-live in seconds (0 = no expiry)
    """
    system_id: str
    token: str
    encrypted_value: bytes
    ttl_seconds: int = 0


class TokenStore:
    """Redis token store with connection pooling and retry logic.
    
    Provides async Redis operations for storing and retrieving encrypted tokens
    with automatic retry on transient failures and connection pooling for performance.
    """

    def __init__(
        self,
        redis_url: str,
        pool_size: int = 50,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
    ):
        """Initialize Redis connection pool.
        
        Args:
            redis_url: Redis connection URL (redis://host:port/db)
            pool_size: Maximum connections in pool (default 50)
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.pool = ConnectionPool.from_url(
            redis_url,
            max_connections=pool_size,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            decode_responses=False,  # We work with bytes
            retry=Retry(ExponentialBackoff(), 3),
        )
        self.redis = Redis(connection_pool=self.pool)
        self.logger = logger.bind(component="token_store")

    async def close(self) -> None:
        """Close Redis connection pool."""
        await self.redis.close()
        await self.pool.disconnect()

    def build_key(self, system_id: str, token: str) -> str:
        """Build namespaced Redis key.
        
        Format: {system_id}:token:{token}
        Example: customer_db:token:abc123-def456-789
        
        Args:
            system_id: System identifier
            token: Token string
            
        Returns:
            Namespaced Redis key
        """
        return f"{system_id}:token:{token}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def store_token(
        self,
        system_id: str,
        token: str,
        encrypted_value: bytes,
        ttl_seconds: int,
    ) -> None:
        """Store a single token-to-encrypted-value mapping with retry logic.
        
        Automatically retries up to 3 times with exponential backoff on transient failures.
        
        Args:
            system_id: System identifier for namespacing
            token: Token string
            encrypted_value: AES-256-GCM encrypted PII value
            ttl_seconds: Time-to-live in seconds (0 = no expiry)
            
        Raises:
            Exception: If all retry attempts fail
        """
        key = self.build_key(system_id, token)

        try:
            if ttl_seconds > 0:
                await self.redis.setex(key, ttl_seconds, encrypted_value)
            else:
                await self.redis.set(key, encrypted_value)
        except Exception as e:
            self.logger.error(
                "store_token_failed",
                system_id=system_id,
                token=token[:8],
                error=str(e),
            )
            raise

    async def store_batch(self, mappings: List[TokenMapping]) -> None:
        """Store multiple tokens using optimized Redis operations.
        
        Uses Lua script for atomic MSET with TTL, significantly reducing
        the number of Redis commands from 80,000+ to just a few.
        
        Args:
            mappings: List of TokenMapping objects
            
        Raises:
            Exception: If operation fails
        """
        if not mappings:
            return

        try:
            # Group mappings by TTL for efficient processing
            ttl_groups: Dict[int, List[TokenMapping]] = {}
            for mapping in mappings:
                ttl = mapping.ttl_seconds
                if ttl not in ttl_groups:
                    ttl_groups[ttl] = []
                ttl_groups[ttl].append(mapping)

            # Process each TTL group
            for ttl, group in ttl_groups.items():
                if ttl > 0:
                    # Use Lua script for atomic MSET with EXPIRE
                    # This reduces 2N operations (SET + EXPIRE) to 1 operation
                    lua_script = """
                    local ttl = ARGV[1]
                    for i = 2, #ARGV, 2 do
                        redis.call('SET', ARGV[i], ARGV[i+1], 'EX', ttl)
                    end
                    return #ARGV / 2 - 1
                    """
                    
                    # Build arguments: [ttl, key1, val1, key2, val2, ...]
                    args = [str(ttl)]
                    for mapping in group:
                        key = self.build_key(mapping.system_id, mapping.token)
                        args.append(key)
                        args.append(mapping.encrypted_value)
                    
                    # Execute Lua script
                    await self.redis.eval(lua_script, 0, *args)
                else:
                    # No TTL - use MSET
                    mset_dict = {}
                    for mapping in group:
                        key = self.build_key(mapping.system_id, mapping.token)
                        mset_dict[key] = mapping.encrypted_value
                    
                    if mset_dict:
                        await self.redis.mset(mset_dict)

        except Exception as e:
            self.logger.error(
                "store_batch_failed",
                count=len(mappings),
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def retrieve_token(
        self,
        system_id: str,
        token: str,
    ) -> Optional[bytes]:
        """Retrieve encrypted value for a token with retry logic.
        
        Automatically retries up to 3 times with exponential backoff on transient failures.
        
        Args:
            system_id: System identifier
            token: Token string
            
        Returns:
            Encrypted value bytes or None if not found/expired
            
        Raises:
            Exception: If all retry attempts fail
        """
        key = self.build_key(system_id, token)

        try:
            value = await self.redis.get(key)
            return value
        except Exception as e:
            self.logger.error(
                "retrieve_token_failed",
                system_id=system_id,
                token=token[:8],
                error=str(e),
            )
            raise

    async def retrieve_batch(
        self,
        system_id: str,
        tokens: List[str],
    ) -> Dict[str, Optional[bytes]]:
        """Retrieve multiple tokens efficiently using Redis pipeline.
        
        Pipeline reduces round-trips from N to 1, significantly improving performance
        for batch operations.
        
        Args:
            system_id: System identifier
            tokens: List of token strings
            
        Returns:
            Dict mapping token to encrypted value (None if not found)
            
        Raises:
            Exception: If pipeline execution fails
        """
        if not tokens:
            return {}

        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for token in tokens:
                    key = self.build_key(system_id, token)
                    pipe.get(key)

                values = await pipe.execute()

            result = dict(zip(tokens, values))

            return result
        except Exception as e:
            self.logger.error(
                "retrieve_batch_failed",
                count=len(tokens),
                system_id=system_id,
                error=str(e),
            )
            raise

    async def health_check(self) -> bool:
        """Check Redis connectivity using PING command.
        
        Returns:
            True if Redis responds to PING within timeout, False otherwise
        """
        try:
            response = await self.redis.ping()
            return response is True
        except Exception as e:
            self.logger.error("health_check_failed", error=str(e))
            return False
