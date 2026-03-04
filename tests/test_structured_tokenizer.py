"""Tests for StructuredTokenizer."""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from src.pii_service.core.structured_tokenizer import (
    StructuredTokenizer,
    AnonymizedRecord,
    DeanonymizedRecord,
)
from src.pii_service.core.policy_loader import PolicyLoader
from src.pii_service.core.token_store import TokenStore, TokenMapping
from src.pii_service.core.crypto_engine import CryptoEngine


@pytest.fixture
def crypto_engine():
    """Create CryptoEngine instance."""
    return CryptoEngine()


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    return os.urandom(32)


@pytest.fixture
async def policy_loader(tmp_path, encryption_key):
    """Create PolicyLoader with test policy."""
    policy_file = tmp_path / "test_policy.yaml"
    
    # Write encryption key to file
    key_file = tmp_path / "test_key.bin"
    key_file.write_bytes(encryption_key)
    
    # Convert path to use forward slashes for YAML compatibility
    key_file_str = str(key_file).replace('\\', '/')
    
    policy_content = f"""
systems:
  - system_id: "test_system"
    encryption_key_ref: "file:{key_file_str}"
    structured:
      pii_fields:
        - name: "email"
          deterministic: true
          token_format: "deterministic"
          nullable: false
        - name: "name"
          deterministic: false
          token_format: "uuid"
          nullable: false
        - name: "address.street"
          deterministic: false
          token_format: "prefixed"
          token_prefix: "ADDR_"
          nullable: true
        - name: "ssn"
          deterministic: true
          token_format: "deterministic"
          nullable: false
      token_ttl_seconds: 3600
"""
    
    policy_file.write_text(policy_content)
    
    loader = PolicyLoader()
    await loader.load_policy(str(policy_file))
    return loader


@pytest.fixture
def mock_token_store():
    """Create mock TokenStore."""
    store = AsyncMock(spec=TokenStore)
    store.store_batch = AsyncMock()
    store.retrieve_batch = AsyncMock(return_value={})
    return store


@pytest.fixture
def tokenizer(policy_loader, mock_token_store, crypto_engine):
    """Create StructuredTokenizer instance."""
    return StructuredTokenizer(
        policy_loader=policy_loader,
        token_store=mock_token_store,
        crypto_engine=crypto_engine,
    )


class TestFieldExtraction:
    """Tests for field extraction and setting."""
    
    def test_extract_simple_field(self, tokenizer):
        """Test extracting a simple top-level field."""
        record = {"email": "user@example.com", "name": "John"}
        
        value = tokenizer.extract_field_value(record, "email")
        assert value == "user@example.com"
    
    def test_extract_nested_field(self, tokenizer):
        """Test extracting a nested field with dot-notation."""
        record = {
            "address": {
                "street": "123 Main St",
                "city": "Springfield"
            }
        }
        
        value = tokenizer.extract_field_value(record, "address.street")
        assert value == "123 Main St"
    
    def test_extract_deeply_nested_field(self, tokenizer):
        """Test extracting a deeply nested field."""
        record = {
            "user": {
                "profile": {
                    "contact": {
                        "email": "deep@example.com"
                    }
                }
            }
        }
        
        value = tokenizer.extract_field_value(record, "user.profile.contact.email")
        assert value == "deep@example.com"
    
    def test_extract_missing_field(self, tokenizer):
        """Test extracting a field that doesn't exist."""
        record = {"name": "John"}
        
        value = tokenizer.extract_field_value(record, "email")
        assert value is None
    
    def test_extract_missing_nested_field(self, tokenizer):
        """Test extracting a nested field where parent doesn't exist."""
        record = {"name": "John"}
        
        value = tokenizer.extract_field_value(record, "address.street")
        assert value is None
    
    def test_extract_non_dict_intermediate(self, tokenizer):
        """Test extracting when intermediate value is not a dict."""
        record = {"address": "123 Main St"}  # address is string, not dict
        
        with pytest.raises(ValueError, match="is not a dict"):
            tokenizer.extract_field_value(record, "address.street")
    
    def test_set_simple_field(self, tokenizer):
        """Test setting a simple top-level field."""
        record = {}
        
        tokenizer.set_field_value(record, "email", "user@example.com")
        assert record["email"] == "user@example.com"
    
    def test_set_nested_field_creates_intermediate(self, tokenizer):
        """Test setting nested field creates intermediate dicts."""
        record = {}
        
        tokenizer.set_field_value(record, "address.street", "123 Main St")
        assert record == {"address": {"street": "123 Main St"}}
    
    def test_set_deeply_nested_field(self, tokenizer):
        """Test setting deeply nested field."""
        record = {}
        
        tokenizer.set_field_value(record, "user.profile.email", "deep@example.com")
        assert record == {
            "user": {
                "profile": {
                    "email": "deep@example.com"
                }
            }
        }
    
    def test_set_field_with_existing_parent(self, tokenizer):
        """Test setting field when parent dict already exists."""
        record = {"address": {"city": "Springfield"}}
        
        tokenizer.set_field_value(record, "address.street", "123 Main St")
        assert record == {
            "address": {
                "city": "Springfield",
                "street": "123 Main St"
            }
        }
    
    def test_set_field_non_dict_intermediate(self, tokenizer):
        """Test setting field when intermediate value is not a dict."""
        record = {"address": "123 Main St"}  # address is string, not dict
        
        with pytest.raises(ValueError, match="is not a dict"):
            tokenizer.set_field_value(record, "address.street", "Main St")


class TestTokenGeneration:
    """Tests for token generation."""
    
    def test_generate_uuid_token(self, tokenizer, encryption_key):
        """Test generating UUID token."""
        token = tokenizer.generate_token(
            "user@example.com",
            deterministic=False,
            key=encryption_key,
            token_format="uuid",
        )
        
        # UUID format: 8-4-4-4-12 hex digits
        assert len(token) == 36
        assert token.count('-') == 4
    
    def test_generate_deterministic_token(self, tokenizer, encryption_key):
        """Test generating deterministic HMAC token."""
        token = tokenizer.generate_token(
            "user@example.com",
            deterministic=True,
            key=encryption_key,
            token_format="deterministic",
        )
        
        # HMAC-SHA256 produces 64 hex characters
        assert len(token) == 64
        assert all(c in '0123456789abcdef' for c in token)
    
    def test_deterministic_token_consistency(self, tokenizer, encryption_key):
        """Test that deterministic tokens are consistent."""
        token1 = tokenizer.generate_token(
            "user@example.com",
            deterministic=True,
            key=encryption_key,
            token_format="deterministic",
        )
        
        token2 = tokenizer.generate_token(
            "user@example.com",
            deterministic=True,
            key=encryption_key,
            token_format="deterministic",
        )
        
        assert token1 == token2
    
    def test_uuid_token_non_deterministic(self, tokenizer, encryption_key):
        """Test that UUID tokens are different each time."""
        token1 = tokenizer.generate_token(
            "user@example.com",
            deterministic=False,
            key=encryption_key,
            token_format="uuid",
        )
        
        token2 = tokenizer.generate_token(
            "user@example.com",
            deterministic=False,
            key=encryption_key,
            token_format="uuid",
        )
        
        assert token1 != token2
    
    def test_generate_prefixed_uuid_token(self, tokenizer, encryption_key):
        """Test generating prefixed UUID token."""
        token = tokenizer.generate_token(
            "user@example.com",
            deterministic=False,
            key=encryption_key,
            token_format="prefixed",
            token_prefix="EMAIL_",
        )
        
        assert token.startswith("EMAIL_")
        # Remove prefix and check UUID format
        uuid_part = token[6:]
        assert len(uuid_part) == 36
    
    def test_generate_prefixed_deterministic_token(self, tokenizer, encryption_key):
        """Test generating prefixed deterministic token."""
        token = tokenizer.generate_token(
            "user@example.com",
            deterministic=True,
            key=encryption_key,
            token_format="prefixed",
            token_prefix="EMAIL_",
        )
        
        assert token.startswith("EMAIL_")
        # Remove prefix and check HMAC format
        hmac_part = token[6:]
        assert len(hmac_part) == 64


@pytest.mark.asyncio
class TestRecordAnonymization:
    """Tests for single record anonymization."""
    
    async def test_anonymize_simple_record(self, tokenizer, mock_token_store):
        """Test anonymizing a simple record."""
        record = {
            "email": "user@example.com",
            "name": "John Doe",
            "ssn": "123-45-6789"
        }
        
        result = await tokenizer.anonymize_record(record, "test_system")
        
        assert result._pii_anonymized is True
        assert result.error is None
        assert len(result.token_ids) == 3
        
        # Check that PII fields are replaced with tokens
        assert result.record["email"] != "user@example.com"
        assert result.record["name"] != "John Doe"
        assert result.record["ssn"] != "123-45-6789"
        
        # Check that _pii_anonymized flag is added
        assert result.record["_pii_anonymized"] is True
        
        # Check that store_batch was called
        mock_token_store.store_batch.assert_called_once()
        call_args = mock_token_store.store_batch.call_args[0][0]
        assert len(call_args) == 3
        assert all(isinstance(m, TokenMapping) for m in call_args)
    
    async def test_anonymize_nested_record(self, tokenizer, mock_token_store):
        """Test anonymizing a record with nested fields."""
        record = {
            "email": "user@example.com",
            "name": "John Doe",
            "address": {
                "street": "123 Main St",
                "city": "Springfield"
            },
            "ssn": "123-45-6789"
        }
        
        result = await tokenizer.anonymize_record(record, "test_system")
        
        assert result._pii_anonymized is True
        assert result.error is None
        
        # Check that nested field is tokenized
        assert result.record["address"]["street"] != "123 Main St"
        assert result.record["address"]["street"].startswith("ADDR_")
        
        # Check that non-PII nested field is unchanged
        assert result.record["address"]["city"] == "Springfield"
    
    async def test_anonymize_with_nullable_null_field(self, tokenizer, mock_token_store):
        """Test anonymizing record with null nullable field."""
        record = {
            "email": "user@example.com",
            "name": "John Doe",
            "address": {
                "street": None,  # Nullable field
                "city": "Springfield"
            },
            "ssn": "123-45-6789"
        }
        
        result = await tokenizer.anonymize_record(record, "test_system")
        
        assert result._pii_anonymized is True
        assert result.error is None
        
        # Null nullable field should be skipped
        assert result.record["address"]["street"] is None
    
    async def test_anonymize_with_non_nullable_null_field(self, tokenizer, mock_token_store):
        """Test anonymizing record with null non-nullable field fails."""
        record = {
            "email": None,  # Non-nullable field
            "name": "John Doe",
            "ssn": "123-45-6789"
        }
        
        result = await tokenizer.anonymize_record(record, "test_system")
        
        # Check that the record has the error flag
        assert result.record.get("_pii_anonymized") is False
        assert result.error is not None
        assert "is null but not nullable" in result.error
    
    async def test_anonymize_deterministic_token_consistency(self, tokenizer, mock_token_store):
        """Test that deterministic fields produce consistent tokens."""
        record1 = {"email": "user@example.com", "name": "John", "ssn": "123-45-6789"}
        record2 = {"email": "user@example.com", "name": "Jane", "ssn": "123-45-6789"}
        
        result1 = await tokenizer.anonymize_record(record1, "test_system")
        result2 = await tokenizer.anonymize_record(record2, "test_system")
        
        # Email and SSN are deterministic, should have same tokens
        assert result1.record["email"] == result2.record["email"]
        assert result1.record["ssn"] == result2.record["ssn"]
        
        # Name is non-deterministic, should have different tokens
        assert result1.record["name"] != result2.record["name"]
    
    async def test_anonymize_preserves_non_pii_fields(self, tokenizer, mock_token_store):
        """Test that non-PII fields are preserved."""
        record = {
            "email": "user@example.com",
            "name": "John Doe",
            "ssn": "123-45-6789",
            "age": 30,
            "country": "USA"
        }
        
        result = await tokenizer.anonymize_record(record, "test_system")
        
        # Non-PII fields should be unchanged
        assert result.record["age"] == 30
        assert result.record["country"] == "USA"
    
    async def test_anonymize_invalid_system_id(self, tokenizer, mock_token_store):
        """Test anonymizing with invalid system_id."""
        record = {"email": "user@example.com"}
        
        result = await tokenizer.anonymize_record(record, "invalid_system")
        
        # Check that the record has the error flag
        assert result.record.get("_pii_anonymized") is False
        assert result.error is not None
        assert "not found" in result.error


@pytest.mark.asyncio
class TestStreamAnonymization:
    """Tests for streaming anonymization."""
    
    async def test_anonymize_stream(self, tokenizer, mock_token_store):
        """Test streaming anonymization of multiple records."""
        async def record_generator():
            yield {"email": "user1@example.com", "name": "John", "ssn": "111-11-1111"}
            yield {"email": "user2@example.com", "name": "Jane", "ssn": "222-22-2222"}
            yield {"email": "user3@example.com", "name": "Bob", "ssn": "333-33-3333"}
        
        results = []
        async for result in tokenizer.anonymize_stream(record_generator(), "test_system"):
            results.append(result)
        
        assert len(results) == 3
        assert all(r._pii_anonymized for r in results)
        assert all(r.error is None for r in results)
    
    async def test_anonymize_stream_continues_on_error(self, tokenizer, mock_token_store):
        """Test that stream continues processing after one record fails."""
        async def record_generator():
            yield {"email": "user1@example.com", "name": "John", "ssn": "111-11-1111"}
            yield {"email": None, "name": "Jane", "ssn": "222-22-2222"}  # Will fail
            yield {"email": "user3@example.com", "name": "Bob", "ssn": "333-33-3333"}
        
        results = []
        async for result in tokenizer.anonymize_stream(record_generator(), "test_system"):
            results.append(result)
        
        assert len(results) == 3
        assert results[0]._pii_anonymized is True
        assert results[1].record.get("_pii_anonymized") is False  # Failed record
        assert results[2]._pii_anonymized is True


@pytest.mark.asyncio
class TestRecordDeanonymization:
    """Tests for record de-anonymization."""
    
    async def test_deanonymize_simple_record(self, tokenizer, mock_token_store, crypto_engine, encryption_key):
        """Test de-anonymizing a simple record."""
        # First anonymize a record
        original_record = {
            "email": "user@example.com",
            "name": "John Doe",
            "ssn": "123-45-6789"
        }
        
        anonymized = await tokenizer.anonymize_record(original_record, "test_system")
        
        # Mock retrieve_batch to return encrypted values
        encrypted_values = {}
        for token_id in anonymized.token_ids:
            # Find which field this token belongs to
            for field in ["email", "name", "ssn"]:
                if anonymized.record[field] == token_id:
                    encrypted_values[token_id] = crypto_engine.encrypt(
                        original_record[field],
                        encryption_key
                    )
        
        mock_token_store.retrieve_batch.return_value = encrypted_values
        
        # De-anonymize
        result = await tokenizer.deanonymize_record(anonymized.record, "test_system")
        
        assert len(result.errors) == 0
        assert result.record["email"] == "user@example.com"
        assert result.record["name"] == "John Doe"
        assert result.record["ssn"] == "123-45-6789"
        assert "_pii_anonymized" not in result.record
    
    async def test_deanonymize_with_missing_token(self, tokenizer, mock_token_store):
        """Test de-anonymizing when token is not found in Redis."""
        tokenized_record = {
            "email": "tok_abc123",
            "name": "tok_xyz789",
            "ssn": "tok_def456"
        }
        
        # Mock retrieve_batch to return None for some tokens
        mock_token_store.retrieve_batch.return_value = {
            "tok_abc123": None,  # Missing/expired
            "tok_xyz789": b"encrypted_data",
            "tok_def456": b"encrypted_data"
        }
        
        result = await tokenizer.deanonymize_record(tokenized_record, "test_system")
        
        assert "email" in result.errors
        assert "not found or expired" in result.errors["email"]
    
    async def test_deanonymize_nested_record(self, tokenizer, mock_token_store, crypto_engine, policy_loader):
        """Test de-anonymizing a record with nested fields."""
        # Get the encryption key from the policy loader (same key the tokenizer uses)
        encryption_key = policy_loader.get_encryption_key("test_system")
        
        original_record = {
            "email": "user@example.com",
            "name": "John Doe",
            "address": {
                "street": "123 Main St",
                "city": "Springfield"
            },
            "ssn": "123-45-6789"
        }
        
        anonymized = await tokenizer.anonymize_record(original_record, "test_system")
        
        # Extract the encrypted values that were stored during anonymization
        # The mock was called with TokenMapping objects containing the encrypted values
        assert mock_token_store.store_batch.called, "store_batch should have been called"
        call_args = mock_token_store.store_batch.call_args
        mappings = call_args[0][0]  # First positional argument is the list of TokenMapping objects
        
        # Build encrypted_values dict from the actual mappings that were stored
        encrypted_values = {mapping.token: mapping.encrypted_value for mapping in mappings}
        
        # Verify all tokens have encrypted values
        assert len(encrypted_values) == len(anonymized.token_ids), \
            f"Missing encrypted values: {set(anonymized.token_ids) - set(encrypted_values.keys())}"
        
        # Configure the existing mock to return encrypted values
        # The tokenizer already has a reference to this mock from the fixture
        mock_token_store.retrieve_batch.return_value = encrypted_values
        
        result = await tokenizer.deanonymize_record(anonymized.record, "test_system")
        
        assert len(result.errors) == 0, f"Errors: {result.errors}"
        assert result.record["email"] == "user@example.com"
        assert result.record["name"] == "John Doe"
        assert result.record["ssn"] == "123-45-6789"
        assert result.record["address"]["street"] == "123 Main St"
        assert result.record["address"]["city"] == "Springfield"
    
    async def test_deanonymize_with_null_field(self, tokenizer, mock_token_store):
        """Test de-anonymizing record with null field."""
        tokenized_record = {
            "email": "tok_abc123",
            "name": "tok_xyz789",
            "address": {
                "street": None,  # Null field
                "city": "Springfield"
            },
            "ssn": "tok_def456"
        }
        
        mock_token_store.retrieve_batch.return_value = {}
        
        result = await tokenizer.deanonymize_record(tokenized_record, "test_system")
        
        # Null field should be skipped, no error
        assert "address.street" not in result.errors
        assert result.record["address"]["street"] is None
