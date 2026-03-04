"""Tests for UnstructuredTokenizer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.pii_service.core.unstructured_tokenizer import (
    UnstructuredTokenizer,
    RateLimiter,
    RateLimitExceededError,
    AnonymizedText,
)
from src.pii_service.core.policy_loader import PolicyLoader
from src.pii_service.core.token_store import TokenStore
from src.pii_service.core.crypto_engine import CryptoEngine
from src.pii_service.core.llm_client import LLMClient
from src.pii_service.models.entity import EntitySpan
from src.pii_service.models.policy import (
    Policy,
    SystemConfig,
    UnstructuredConfig,
    StructuredConfig,
    PIIField,
)


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    import os
    return os.urandom(32)


@pytest.fixture
def policy_loader(encryption_key):
    """Create a mock PolicyLoader."""
    loader = MagicMock(spec=PolicyLoader)
    
    # Mock system config
    config = SystemConfig(
        system_id="test_system",
        encryption_key_ref="env:TEST_KEY",
        unstructured=UnstructuredConfig(
            llm_model="test-model",
            entity_types=["PERSON", "EMAIL", "PHONE"],
            rate_limit_per_minute=100,
            max_text_length=50000,
        ),
        structured=StructuredConfig(
            pii_fields=[],
            token_ttl_seconds=3600,
        ),
    )
    
    loader.get_system_config.return_value = config
    loader.get_encryption_key.return_value = encryption_key
    
    return loader


@pytest.fixture
def token_store():
    """Create a mock TokenStore."""
    store = AsyncMock(spec=TokenStore)
    store.store_batch = AsyncMock()
    store.retrieve_batch = AsyncMock(return_value={})
    return store


@pytest.fixture
def crypto_engine():
    """Create a real CryptoEngine for testing."""
    return CryptoEngine()


@pytest.fixture
def llm_client():
    """Create a mock LLMClient."""
    client = AsyncMock(spec=LLMClient)
    client.extract_entities = AsyncMock(return_value=[])
    return client


@pytest.fixture
def tokenizer(policy_loader, token_store, crypto_engine, llm_client):
    """Create an UnstructuredTokenizer instance."""
    return UnstructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
        llm_client=llm_client,
    )


class TestRateLimiter:
    """Tests for RateLimiter class."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests_within_limit(self):
        """Test that rate limiter allows requests within limit."""
        limiter = RateLimiter(requests_per_minute=10)
        
        # Should allow first 10 requests
        for i in range(10):
            result = await limiter.check_rate_limit("client1")
            assert result is True
        
        # 11th request should be blocked
        result = await limiter.check_rate_limit("client1")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rate_limiter_per_client_isolation(self):
        """Test that rate limiter tracks clients separately."""
        limiter = RateLimiter(requests_per_minute=5)
        
        # Client1 makes 5 requests
        for i in range(5):
            result = await limiter.check_rate_limit("client1")
            assert result is True
        
        # Client1 is now blocked
        result = await limiter.check_rate_limit("client1")
        assert result is False
        
        # Client2 should still be allowed
        result = await limiter.check_rate_limit("client2")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_sliding_window(self):
        """Test that rate limiter uses sliding window."""
        limiter = RateLimiter(requests_per_minute=5)
        
        # Make 5 requests
        for i in range(5):
            result = await limiter.check_rate_limit("client1")
            assert result is True
        
        # Blocked now
        result = await limiter.check_rate_limit("client1")
        assert result is False
        
        # Simulate time passing by manually setting old timestamps
        old_time = datetime.now() - timedelta(minutes=1, seconds=1)
        limiter.client_requests["client1"] = [old_time] * 5
        
        # Should be allowed again (old requests are outside window)
        result = await limiter.check_rate_limit("client1")
        assert result is True


class TestUnstructuredTokenizer:
    """Tests for UnstructuredTokenizer class."""
    
    @pytest.mark.asyncio
    async def test_anonymize_text_basic(self, tokenizer, llm_client):
        """Test basic text anonymization."""
        # Mock LLM response
        entities = [
            EntitySpan(type="PERSON", value="John Doe", start=8, end=16),
            EntitySpan(type="EMAIL", value="john@example.com", start=20, end=37),
        ]
        llm_client.extract_entities.return_value = entities
        
        text = "Contact John Doe at john@example.com"
        result = await tokenizer.anonymize_text(
            text=text,
            system_id="test_system",
            client_id="client1",
        )
        
        # Check that text was anonymized
        assert isinstance(result, AnonymizedText)
        assert result.anonymized_text != text
        assert "John Doe" not in result.anonymized_text
        assert "john@example.com" not in result.anonymized_text
        
        # Check that tokens were stored
        tokenizer.token_store.store_batch.assert_called_once()
        stored_mappings = tokenizer.token_store.store_batch.call_args[0][0]
        assert len(stored_mappings) == 2
    
    @pytest.mark.asyncio
    async def test_anonymize_text_with_entity_map(self, tokenizer, llm_client):
        """Test text anonymization with entity map."""
        entities = [
            EntitySpan(type="PERSON", value="Alice", start=0, end=5),
        ]
        llm_client.extract_entities.return_value = entities
        
        text = "Alice works here"
        result = await tokenizer.anonymize_text(
            text=text,
            system_id="test_system",
            client_id="client1",
            return_entity_map=True,
        )
        
        # Check that entity map is included
        assert result.entity_map is not None
        assert len(result.entity_map) == 1
        
        # Check entity map structure
        token = list(result.entity_map.keys())[0]
        entity = result.entity_map[token]
        assert entity.type == "PERSON"
        assert entity.value == "Alice"
    
    @pytest.mark.asyncio
    async def test_anonymize_text_filters_entity_types(self, tokenizer, llm_client):
        """Test that only configured entity types are tokenized."""
        # LLM returns entities including types not in config
        entities = [
            EntitySpan(type="PERSON", value="John", start=0, end=4),
            EntitySpan(type="SSN", value="123-45-6789", start=10, end=21),  # Not in config
        ]
        llm_client.extract_entities.return_value = entities
        
        text = "John SSN: 123-45-6789"
        result = await tokenizer.anonymize_text(
            text=text,
            system_id="test_system",
            client_id="client1",
        )
        
        # Only PERSON should be tokenized (SSN not in entity_types)
        stored_mappings = tokenizer.token_store.store_batch.call_args[0][0]
        assert len(stored_mappings) == 1
        assert stored_mappings[0].encrypted_value  # PERSON entity encrypted
    
    @pytest.mark.asyncio
    async def test_anonymize_text_validates_length(self, tokenizer):
        """Test that text length is validated."""
        # Text exceeds max_text_length (50000)
        text = "x" * 50001
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            await tokenizer.anonymize_text(
                text=text,
                system_id="test_system",
                client_id="client1",
            )
    
    @pytest.mark.asyncio
    async def test_anonymize_text_enforces_rate_limit(self, tokenizer, llm_client):
        """Test that rate limiting is enforced."""
        entities = []
        llm_client.extract_entities.return_value = entities
        
        text = "Test text"
        
        # Make requests up to the limit (100)
        for i in range(100):
            result = await tokenizer.anonymize_text(
                text=text,
                system_id="test_system",
                client_id="client1",
            )
            assert isinstance(result, AnonymizedText)
        
        # 101st request should be blocked
        with pytest.raises(RateLimitExceededError, match="Rate limit exceeded"):
            await tokenizer.anonymize_text(
                text=text,
                system_id="test_system",
                client_id="client1",
            )
    
    @pytest.mark.asyncio
    async def test_replace_entities_longest_first(self, tokenizer):
        """Test that entities are replaced longest-first."""
        entities = [
            EntitySpan(type="EMAIL", value="john@example.com", start=16, end=33, token="tok_email"),
            EntitySpan(type="PERSON", value="John", start=8, end=12, token="tok_person"),
            EntitySpan(type="PERSON", value="John Doe", start=8, end=16, token="tok_full_name"),
        ]
        
        text = "Contact John Doe at john@example.com"
        anonymized, entity_map = tokenizer.replace_entities(text, entities)
        
        # Longest entity "John Doe" should be replaced, not "John"
        assert "tok_full_name" in anonymized
        assert "tok_person" not in anonymized  # Overlapping shorter entity skipped
        assert "tok_email" in anonymized
        
        # Entity map should only contain non-overlapping entities
        assert len(entity_map) == 2
        assert "tok_full_name" in entity_map
        assert "tok_email" in entity_map
    
    @pytest.mark.asyncio
    async def test_replace_entities_handles_overlaps(self, tokenizer):
        """Test that overlapping entities are handled correctly."""
        entities = [
            EntitySpan(type="PERSON", value="John", start=0, end=4, token="tok1"),
            EntitySpan(type="PERSON", value="John Doe", start=0, end=8, token="tok2"),
            EntitySpan(type="PERSON", value="Doe", start=5, end=8, token="tok3"),
        ]
        
        text = "John Doe works here"
        anonymized, entity_map = tokenizer.replace_entities(text, entities)
        
        # Only longest entity should be replaced
        assert "tok2" in anonymized
        assert "tok1" not in anonymized
        assert "tok3" not in anonymized
        
        # Only one entity in map
        assert len(entity_map) == 1
        assert "tok2" in entity_map
    
    @pytest.mark.asyncio
    async def test_replace_entities_maintains_positions(self, tokenizer):
        """Test that replacements maintain correct positions."""
        entities = [
            EntitySpan(type="PERSON", value="Alice", start=0, end=5, token="tok_alice"),
            EntitySpan(type="PERSON", value="Bob", start=10, end=13, token="tok_bob"),
        ]
        
        text = "Alice and Bob work together"
        anonymized, entity_map = tokenizer.replace_entities(text, entities)
        
        # Check structure is maintained
        assert anonymized == "tok_alice and tok_bob work together"
        assert len(entity_map) == 2
    
    def test_extract_tokens_uuid(self, tokenizer):
        """Test extraction of UUID tokens."""
        text = "Contact abc12345-1234-1234-1234-123456789abc at work"
        tokens = tokenizer.extract_tokens(text)
        
        assert len(tokens) == 1
        assert tokens[0] == "abc12345-1234-1234-1234-123456789abc"
    
    def test_extract_tokens_hmac(self, tokenizer):
        """Test extraction of HMAC tokens."""
        hmac_token = "a" * 64  # 64 hex characters
        text = f"Token: {hmac_token}"
        tokens = tokenizer.extract_tokens(text)
        
        assert len(tokens) == 1
        assert tokens[0] == hmac_token
    
    def test_extract_tokens_prefixed(self, tokenizer):
        """Test extraction of prefixed tokens."""
        text = "Email: EMAIL_abc12345-1234-1234-1234-123456789abc and ADDR_" + "b" * 64
        tokens = tokenizer.extract_tokens(text)
        
        assert len(tokens) == 2
        assert tokens[0].startswith("EMAIL_")
        assert tokens[1].startswith("ADDR_")
    
    def test_extract_tokens_multiple(self, tokenizer):
        """Test extraction of multiple tokens."""
        uuid_token = "abc12345-1234-1234-1234-123456789abc"
        hmac_token = "a" * 64
        prefixed_token = f"EMAIL_{uuid_token}"
        
        text = f"Tokens: {uuid_token} and {hmac_token} and {prefixed_token}"
        tokens = tokenizer.extract_tokens(text)
        
        assert len(tokens) == 3
    
    def test_extract_tokens_no_tokens(self, tokenizer):
        """Test extraction when no tokens present."""
        text = "This is plain text with no tokens"
        tokens = tokenizer.extract_tokens(text)
        
        assert len(tokens) == 0
    
    @pytest.mark.asyncio
    async def test_deanonymize_text_basic(self, tokenizer, token_store, crypto_engine, encryption_key):
        """Test basic text de-anonymization."""
        # Setup: create tokens and encrypted values
        token1 = "abc12345-1234-1234-1234-123456789abc"
        token2 = "def12345-1234-1234-1234-123456789def"
        
        encrypted1 = crypto_engine.encrypt("John Doe", encryption_key)
        encrypted2 = crypto_engine.encrypt("john@example.com", encryption_key)
        
        # Mock token retrieval
        token_store.retrieve_batch.return_value = {
            token1: encrypted1,
            token2: encrypted2,
        }
        
        text = f"Contact {token1} at {token2}"
        result = await tokenizer.deanonymize_text(text, "test_system")
        
        # Check that tokens were replaced with original values
        assert "John Doe" in result
        assert "john@example.com" in result
        assert token1 not in result
        assert token2 not in result
    
    @pytest.mark.asyncio
    async def test_deanonymize_text_leaves_unknown_tokens(self, tokenizer, token_store):
        """Test that unknown tokens are left unchanged."""
        token1 = "abc12345-1234-1234-1234-123456789abc"
        token2 = "def12345-1234-1234-1234-123456789def"
        
        # Only token1 exists in store
        token_store.retrieve_batch.return_value = {
            token1: None,  # Not found
            token2: None,  # Not found
        }
        
        text = f"Contact {token1} at {token2}"
        result = await tokenizer.deanonymize_text(text, "test_system")
        
        # Tokens should remain unchanged
        assert token1 in result
        assert token2 in result
    
    @pytest.mark.asyncio
    async def test_deanonymize_text_handles_decryption_errors(
        self, tokenizer, token_store, crypto_engine, encryption_key
    ):
        """Test that decryption errors leave tokens unchanged."""
        token1 = "abc12345-1234-1234-1234-123456789abc"
        
        # Return corrupted encrypted value
        token_store.retrieve_batch.return_value = {
            token1: b"corrupted_data",
        }
        
        text = f"Contact {token1}"
        result = await tokenizer.deanonymize_text(text, "test_system")
        
        # Token should remain unchanged due to decryption error
        assert token1 in result
    
    @pytest.mark.asyncio
    async def test_deanonymize_text_no_tokens(self, tokenizer):
        """Test de-anonymization when no tokens present."""
        text = "This is plain text with no tokens"
        result = await tokenizer.deanonymize_text(text, "test_system")
        
        # Text should be unchanged
        assert result == text
    
    @pytest.mark.asyncio
    async def test_deanonymize_text_prefixed_tokens(
        self, tokenizer, token_store, crypto_engine, encryption_key
    ):
        """Test de-anonymization of prefixed tokens."""
        token = "EMAIL_abc12345-1234-1234-1234-123456789abc"
        encrypted = crypto_engine.encrypt("user@example.com", encryption_key)
        
        token_store.retrieve_batch.return_value = {
            token: encrypted,
        }
        
        text = f"Contact: {token}"
        result = await tokenizer.deanonymize_text(text, "test_system")
        
        assert "user@example.com" in result
        assert token not in result
    
    @pytest.mark.asyncio
    async def test_anonymize_text_no_entities(self, tokenizer, llm_client):
        """Test anonymization when LLM finds no entities."""
        llm_client.extract_entities.return_value = []
        
        text = "This text has no PII"
        result = await tokenizer.anonymize_text(
            text=text,
            system_id="test_system",
            client_id="client1",
        )
        
        # Text should be unchanged
        assert result.anonymized_text == text
        
        # No tokens should be stored
        tokenizer.token_store.store_batch.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_anonymize_text_encryption_integration(
        self, tokenizer, llm_client, token_store, crypto_engine, encryption_key
    ):
        """Test that entities are properly encrypted and can be decrypted."""
        entities = [
            EntitySpan(type="EMAIL", value="test@example.com", start=0, end=16),
        ]
        llm_client.extract_entities.return_value = entities
        
        text = "test@example.com"
        result = await tokenizer.anonymize_text(
            text=text,
            system_id="test_system",
            client_id="client1",
        )
        
        # Get the stored encrypted value
        stored_mappings = token_store.store_batch.call_args[0][0]
        encrypted_value = stored_mappings[0].encrypted_value
        
        # Verify we can decrypt it
        decrypted = crypto_engine.decrypt(encrypted_value, encryption_key)
        assert decrypted == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_rate_limiter_creates_per_system(self, tokenizer):
        """Test that rate limiters are created per system."""
        limiter1 = tokenizer._get_rate_limiter("test_system")
        limiter2 = tokenizer._get_rate_limiter("test_system")
        
        # Should return same instance
        assert limiter1 is limiter2
        
        # Should be a RateLimiter instance
        assert isinstance(limiter1, RateLimiter)
    
    @pytest.mark.asyncio
    async def test_anonymize_text_without_unstructured_config(self, tokenizer, policy_loader):
        """Test error when system has no unstructured config."""
        # Mock config without unstructured section
        config = SystemConfig(
            system_id="test_system",
            encryption_key_ref="env:TEST_KEY",
            structured=StructuredConfig(pii_fields=[], token_ttl_seconds=0),
        )
        policy_loader.get_system_config.return_value = config
        
        with pytest.raises(ValueError, match="does not have unstructured configuration"):
            await tokenizer.anonymize_text(
                text="Test",
                system_id="test_system",
                client_id="client1",
            )
