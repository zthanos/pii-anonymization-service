"""Tests for TokenStore class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from redis.asyncio import Redis
from src.pii_service.core.token_store import TokenStore, TokenMapping


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock(spec=Redis)
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.close = AsyncMock()
    redis.pipeline = MagicMock()
    return redis


@pytest.fixture
def mock_pool():
    """Create a mock connection pool."""
    pool = MagicMock()
    pool.disconnect = AsyncMock()
    return pool


@pytest.fixture
def token_store(mock_redis, mock_pool):
    """Create a TokenStore instance with mocked Redis."""
    with patch("src.pii_service.core.token_store.ConnectionPool") as mock_pool_class:
        mock_pool_class.from_url.return_value = mock_pool
        with patch("src.pii_service.core.token_store.Redis") as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            store = TokenStore(redis_url="redis://localhost:6379/0")
            return store


class TestTokenStore:
    """Test suite for TokenStore class."""
    
    def test_build_key(self, token_store):
        """Test build_key method creates correct namespaced keys."""
        key = token_store.build_key("customer_db", "abc123-def456")
        assert key == "customer_db:token:abc123-def456"
        
        key = token_store.build_key("analytics", "xyz789")
        assert key == "analytics:token:xyz789"
    
    async def test_store_token_with_ttl(self, token_store, mock_redis):
        """Test storing a token with TTL."""
        encrypted_value = b"encrypted_data"
        
        await token_store.store_token(
            system_id="customer_db",
            token="abc123",
            encrypted_value=encrypted_value,
            ttl_seconds=3600,
        )
        
        mock_redis.setex.assert_called_once_with(
            "customer_db:token:abc123",
            3600,
            encrypted_value,
        )
    
    async def test_store_token_without_ttl(self, token_store, mock_redis):
        """Test storing a token without TTL (no expiry)."""
        encrypted_value = b"encrypted_data"
        
        await token_store.store_token(
            system_id="customer_db",
            token="abc123",
            encrypted_value=encrypted_value,
            ttl_seconds=0,
        )
        
        mock_redis.set.assert_called_once_with(
            "customer_db:token:abc123",
            encrypted_value,
        )
    
    async def test_store_token_retry_on_failure(self, token_store, mock_redis):
        """Test that store_token retries on transient failures."""
        # First two calls fail, third succeeds
        mock_redis.set.side_effect = [
            Exception("Connection error"),
            Exception("Connection error"),
            True,
        ]
        
        encrypted_value = b"encrypted_data"
        
        await token_store.store_token(
            system_id="customer_db",
            token="abc123",
            encrypted_value=encrypted_value,
            ttl_seconds=0,
        )
        
        # Should have been called 3 times (2 failures + 1 success)
        assert mock_redis.set.call_count == 3
    
    async def test_store_token_fails_after_retries(self, token_store, mock_redis):
        """Test that store_token raises exception after all retries fail."""
        mock_redis.set.side_effect = Exception("Persistent connection error")
        
        encrypted_value = b"encrypted_data"
        
        with pytest.raises(Exception, match="Persistent connection error"):
            await token_store.store_token(
                system_id="customer_db",
                token="abc123",
                encrypted_value=encrypted_value,
                ttl_seconds=0,
            )
        
        # Should have been called 3 times (all failures)
        assert mock_redis.set.call_count == 3
    
    async def test_retrieve_token_found(self, token_store, mock_redis):
        """Test retrieving an existing token."""
        encrypted_value = b"encrypted_data"
        mock_redis.get.return_value = encrypted_value
        
        result = await token_store.retrieve_token(
            system_id="customer_db",
            token="abc123",
        )
        
        assert result == encrypted_value
        mock_redis.get.assert_called_once_with("customer_db:token:abc123")
    
    async def test_retrieve_token_not_found(self, token_store, mock_redis):
        """Test retrieving a non-existent token."""
        mock_redis.get.return_value = None
        
        result = await token_store.retrieve_token(
            system_id="customer_db",
            token="nonexistent",
        )
        
        assert result is None
        mock_redis.get.assert_called_once_with("customer_db:token:nonexistent")
    
    async def test_retrieve_token_retry_on_failure(self, token_store, mock_redis):
        """Test that retrieve_token retries on transient failures."""
        encrypted_value = b"encrypted_data"
        
        # First two calls fail, third succeeds
        mock_redis.get.side_effect = [
            Exception("Connection error"),
            Exception("Connection error"),
            encrypted_value,
        ]
        
        result = await token_store.retrieve_token(
            system_id="customer_db",
            token="abc123",
        )
        
        assert result == encrypted_value
        assert mock_redis.get.call_count == 3
    
    async def test_store_batch_with_mixed_ttl(self, token_store, mock_redis):
        """Test storing multiple tokens with mixed TTL settings."""
        mappings = [
            TokenMapping(
                system_id="customer_db",
                token="token1",
                encrypted_value=b"value1",
                ttl_seconds=3600,
            ),
            TokenMapping(
                system_id="customer_db",
                token="token2",
                encrypted_value=b"value2",
                ttl_seconds=0,
            ),
            TokenMapping(
                system_id="customer_db",
                token="token3",
                encrypted_value=b"value3",
                ttl_seconds=7200,
            ),
        ]
        
        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = mock_pipe
        
        await token_store.store_batch(mappings)
        
        # Verify pipeline was used
        mock_redis.pipeline.assert_called_once_with(transaction=False)
        
        # Verify correct operations were added to pipeline
        assert mock_pipe.setex.call_count == 2  # token1 and token3 have TTL
        assert mock_pipe.set.call_count == 1  # token2 has no TTL
        
        # Verify execute was called
        mock_pipe.execute.assert_called_once()
    
    async def test_store_batch_empty_list(self, token_store, mock_redis):
        """Test storing an empty batch does nothing."""
        await token_store.store_batch([])
        
        # Pipeline should not be called for empty list
        mock_redis.pipeline.assert_not_called()
    
    async def test_retrieve_batch(self, token_store, mock_redis):
        """Test retrieving multiple tokens."""
        tokens = ["token1", "token2", "token3"]
        values = [b"value1", None, b"value3"]
        
        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=values)
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = mock_pipe
        
        result = await token_store.retrieve_batch(
            system_id="customer_db",
            tokens=tokens,
        )
        
        # Verify results
        assert result == {
            "token1": b"value1",
            "token2": None,
            "token3": b"value3",
        }
        
        # Verify pipeline was used
        mock_redis.pipeline.assert_called_once_with(transaction=False)
        assert mock_pipe.get.call_count == 3
        mock_pipe.execute.assert_called_once()
    
    async def test_retrieve_batch_empty_list(self, token_store, mock_redis):
        """Test retrieving an empty batch returns empty dict."""
        result = await token_store.retrieve_batch(
            system_id="customer_db",
            tokens=[],
        )
        
        assert result == {}
        mock_redis.pipeline.assert_not_called()
    
    async def test_health_check_success(self, token_store, mock_redis):
        """Test health check when Redis is healthy."""
        mock_redis.ping.return_value = True
        
        result = await token_store.health_check()
        
        assert result is True
        mock_redis.ping.assert_called_once()
    
    async def test_health_check_failure(self, token_store, mock_redis):
        """Test health check when Redis is unhealthy."""
        mock_redis.ping.side_effect = Exception("Connection refused")
        
        result = await token_store.health_check()
        
        assert result is False
        mock_redis.ping.assert_called_once()
    
    async def test_close(self, token_store, mock_redis, mock_pool):
        """Test closing the connection pool."""
        await token_store.close()
        
        mock_redis.close.assert_called_once()
        mock_pool.disconnect.assert_called_once()
    
    async def test_store_batch_failure(self, token_store, mock_redis):
        """Test that store_batch raises exception on pipeline failure."""
        mappings = [
            TokenMapping(
                system_id="customer_db",
                token="token1",
                encrypted_value=b"value1",
                ttl_seconds=0,
            ),
        ]
        
        # Mock pipeline that fails
        mock_pipe = AsyncMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("Pipeline error"))
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = mock_pipe
        
        with pytest.raises(Exception, match="Pipeline error"):
            await token_store.store_batch(mappings)
    
    async def test_retrieve_batch_failure(self, token_store, mock_redis):
        """Test that retrieve_batch raises exception on pipeline failure."""
        tokens = ["token1", "token2"]
        
        # Mock pipeline that fails
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("Pipeline error"))
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = mock_pipe
        
        with pytest.raises(Exception, match="Pipeline error"):
            await token_store.retrieve_batch(
                system_id="customer_db",
                tokens=tokens,
            )


class TestTokenMapping:
    """Test suite for TokenMapping model."""
    
    def test_token_mapping_creation(self):
        """Test creating a TokenMapping instance."""
        mapping = TokenMapping(
            system_id="customer_db",
            token="abc123",
            encrypted_value=b"encrypted_data",
            ttl_seconds=3600,
        )
        
        assert mapping.system_id == "customer_db"
        assert mapping.token == "abc123"
        assert mapping.encrypted_value == b"encrypted_data"
        assert mapping.ttl_seconds == 3600
    
    def test_token_mapping_default_ttl(self):
        """Test TokenMapping with default TTL (0)."""
        mapping = TokenMapping(
            system_id="customer_db",
            token="abc123",
            encrypted_value=b"encrypted_data",
        )
        
        assert mapping.ttl_seconds == 0
