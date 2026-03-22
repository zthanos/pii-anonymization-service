"""Tests for UnstructuredTokenizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pii_service.core.crypto_engine import CryptoEngine
from src.pii_service.core.detectors import DeterministicDetector
from src.pii_service.core.policy_loader import PolicyLoader
from src.pii_service.core.token_store import TokenStore
from src.pii_service.core.unstructured_tokenizer import AnonymizedText, UnstructuredTokenizer
from src.pii_service.models.entity import DetectionFinding, EntitySpan
from src.pii_service.models.policy import StructuredConfig, SystemConfig, UnstructuredConfig


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    import os

    return os.urandom(32)


@pytest.fixture
def policy_loader(encryption_key):
    """Create a mock PolicyLoader."""
    loader = MagicMock(spec=PolicyLoader)
    config = SystemConfig(
        system_id="test_system",
        encryption_key_ref="env:TEST_KEY",
        unstructured=UnstructuredConfig(
            detector="hybrid",
            max_text_length=50000,
            semantic_detector=UnstructuredConfig.SemanticDetectorConfig(
                model="pprokopidis/elNER18-bert-base-greek-uncased-v1-bs8-e150-lr5e-06",
                enabled_for=["PERSON"],
            ),
            entities=[
                UnstructuredConfig.EntityRule(
                    type="PERSON",
                    detection=["semantic"],
                    action="tokenize",
                    min_confidence=0.9,
                ),
                UnstructuredConfig.EntityRule(
                    type="EMAIL",
                    detection=["deterministic"],
                    action="tokenize",
                ),
            ],
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
def tokenizer(policy_loader, token_store, crypto_engine):
    """Create an UnstructuredTokenizer instance."""
    tokenizer = UnstructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
    )
    tokenizer.detector = AsyncMock()
    tokenizer.detector.detect.return_value = []
    return tokenizer


class TestUnstructuredTokenizer:
    """Tests for UnstructuredTokenizer class."""

    @pytest.mark.asyncio
    async def test_anonymize_text_basic(self, tokenizer):
        """Test basic text anonymization."""
        tokenizer.detector.detect.return_value = [
            DetectionFinding(
                type="PERSON",
                value="John Doe",
                start=8,
                end=16,
                detector="semantic",
                confidence=0.99,
                action="tokenize",
            ),
            DetectionFinding(
                type="EMAIL",
                value="john@example.com",
                start=20,
                end=36,
                detector="deterministic",
                confidence=1.0,
                action="tokenize",
            ),
        ]

        text = "Contact John Doe at john@example.com"
        result = await tokenizer.anonymize_text(text=text, system_id="test_system", client_id="client1")

        assert isinstance(result, AnonymizedText)
        assert result.anonymized_text != text
        assert "John Doe" not in result.anonymized_text
        assert "john@example.com" not in result.anonymized_text
        tokenizer.token_store.store_batch.assert_called_once()
        assert len(tokenizer.token_store.store_batch.call_args[0][0]) == 2

    @pytest.mark.asyncio
    async def test_anonymize_text_with_entity_map(self, tokenizer):
        """Test text anonymization with entity map."""
        tokenizer.detector.detect.return_value = [
            DetectionFinding(
                type="PERSON",
                value="Alice",
                start=0,
                end=5,
                detector="semantic",
                confidence=0.99,
                action="tokenize",
            )
        ]

        result = await tokenizer.anonymize_text(
            text="Alice works here",
            system_id="test_system",
            client_id="client1",
            return_entity_map=True,
        )

        assert result.entity_map is not None
        assert len(result.entity_map) == 1
        entity = next(iter(result.entity_map.values()))
        assert entity.type == "PERSON"
        assert entity.value == "Alice"

    @pytest.mark.asyncio
    async def test_anonymize_text_filters_unconfigured_entity_types(self, tokenizer):
        """Test that only configured entity types are transformed."""
        tokenizer.detector.detect.return_value = [
            DetectionFinding(
                type="PERSON",
                value="John",
                start=0,
                end=4,
                detector="semantic",
                confidence=0.99,
                action="tokenize",
            ),
            DetectionFinding(
                type="SSN",
                value="123-45-6789",
                start=10,
                end=21,
                detector="semantic",
                confidence=0.99,
                action="tokenize",
            ),
        ]

        await tokenizer.anonymize_text("John SSN: 123-45-6789", "test_system", "client1")

        stored_mappings = tokenizer.token_store.store_batch.call_args[0][0]
        assert len(stored_mappings) == 1

    @pytest.mark.asyncio
    async def test_anonymize_text_validates_length(self, tokenizer):
        """Test that text length is validated."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            await tokenizer.anonymize_text(text="x" * 50001, system_id="test_system", client_id="client1")

    @pytest.mark.asyncio
    async def test_replace_entities_longest_first(self, tokenizer):
        """Test that entities are replaced longest-first."""
        entities = [
            EntitySpan(type="EMAIL", value="john@example.com", start=16, end=32, token="tok_email"),
            EntitySpan(type="PERSON", value="John", start=8, end=12, token="tok_person"),
            EntitySpan(type="PERSON", value="John Doe", start=8, end=16, token="tok_full_name"),
        ]

        anonymized, entity_map = tokenizer.replace_entities("Contact John Doe at john@example.com", entities)

        assert "tok_full_name" in anonymized
        assert "tok_person" not in anonymized
        assert "tok_email" in anonymized
        assert len(entity_map) == 2

    def test_extract_tokens_multiple(self, tokenizer):
        """Test extraction of multiple token formats."""
        uuid_token = "abc12345-1234-1234-1234-123456789abc"
        hmac_token = "a" * 64
        prefixed_token = f"EMAIL_{uuid_token}"
        tokens = tokenizer.extract_tokens(f"Tokens: {uuid_token} and {hmac_token} and {prefixed_token}")
        assert len(tokens) == 3

    @pytest.mark.asyncio
    async def test_deanonymize_text_basic(self, tokenizer, token_store, crypto_engine, encryption_key):
        """Test basic text de-anonymization."""
        token1 = "abc12345-1234-1234-1234-123456789abc"
        token2 = "def12345-1234-1234-1234-123456789def"
        token_store.retrieve_batch.return_value = {
            token1: crypto_engine.encrypt("John Doe", encryption_key),
            token2: crypto_engine.encrypt("john@example.com", encryption_key),
        }

        result = await tokenizer.deanonymize_text(f"Contact {token1} at {token2}", "test_system")

        assert "John Doe" in result
        assert "john@example.com" in result

    @pytest.mark.asyncio
    async def test_deanonymize_text_leaves_unknown_tokens(self, tokenizer, token_store):
        """Test that unknown tokens are left unchanged."""
        token = "abc12345-1234-1234-1234-123456789abc"
        token_store.retrieve_batch.return_value = {token: None}
        result = await tokenizer.deanonymize_text(f"Contact {token}", "test_system")
        assert token in result

    @pytest.mark.asyncio
    async def test_anonymize_text_no_findings(self, tokenizer):
        """Test anonymization when detector finds no entities."""
        result = await tokenizer.anonymize_text(text="This text has no PII", system_id="test_system", client_id="client1")
        assert result.anonymized_text == "This text has no PII"
        tokenizer.token_store.store_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_anonymize_text_redacts_semantic_findings(self, tokenizer):
        """Test redact actions are applied without storing tokens."""
        tokenizer.detector.detect.return_value = [
            DetectionFinding(
                type="PERSON",
                value="Alice",
                start=0,
                end=5,
                detector="semantic",
                confidence=0.99,
                action="redact",
            )
        ]
        config = tokenizer.policy_loader.get_system_config.return_value
        config.unstructured.entities = [
            UnstructuredConfig.EntityRule(
                type="PERSON",
                detection=["semantic"],
                action="redact",
            )
        ]

        result = await tokenizer.anonymize_text("Alice works here", "test_system", "client1")

        assert result.anonymized_text == "[REDACTED:PERSON] works here"
        tokenizer.token_store.store_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_anonymize_text_encryption_integration(self, tokenizer, token_store, crypto_engine, encryption_key):
        """Test that stored values remain decryptable."""
        tokenizer.detector.detect.return_value = [
            DetectionFinding(
                type="EMAIL",
                value="test@example.com",
                start=0,
                end=16,
                detector="deterministic",
                confidence=1.0,
                action="tokenize",
            )
        ]

        await tokenizer.anonymize_text(text="test@example.com", system_id="test_system", client_id="client1")

        encrypted_value = token_store.store_batch.call_args[0][0][0].encrypted_value
        decrypted, value_type = crypto_engine.decrypt(encrypted_value, encryption_key)
        assert decrypted == "test@example.com"
        assert value_type == "str"

    @pytest.mark.asyncio
    async def test_anonymize_text_without_unstructured_config(self, tokenizer, policy_loader):
        """Test error when system has no unstructured config."""
        policy_loader.get_system_config.return_value = SystemConfig(
            system_id="test_system",
            encryption_key_ref="env:TEST_KEY",
            structured=StructuredConfig(pii_fields=[], token_ttl_seconds=0),
        )

        with pytest.raises(ValueError, match="does not have unstructured configuration"):
            await tokenizer.anonymize_text(text="Test", system_id="test_system", client_id="client1")


class TestDeterministicDetector:
    """Tests for strict-pattern deterministic detection."""

    @pytest.mark.asyncio
    async def test_detects_email_and_phone(self):
        """Test deterministic detector emits findings for strict patterns."""
        detector = DeterministicDetector()
        config = UnstructuredConfig(
            detector="deterministic",
            entities=[
                UnstructuredConfig.EntityRule(type="EMAIL", detection=["deterministic"]),
                UnstructuredConfig.EntityRule(type="PHONE_GR", detection=["deterministic"]),
            ],
        )

        findings = await detector.detect(
            "Επικοινωνία: user@example.com, τηλέφωνο 6912345678",
            config,
        )

        assert {finding.type for finding in findings} == {"EMAIL", "PHONE_GR"}
