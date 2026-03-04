"""Tests for policy configuration Pydantic models."""

import pytest
from pydantic import ValidationError

from pii_service.models import (
    PIIField,
    Policy,
    StructuredConfig,
    SystemConfig,
    UnstructuredConfig,
)


class TestPIIField:
    """Tests for PIIField model."""
    
    def test_pii_field_basic(self):
        """Test basic PIIField creation."""
        field = PIIField(name="email")
        assert field.name == "email"
        assert field.deterministic is False
        assert field.token_format == "uuid"
        assert field.token_prefix is None
        assert field.nullable is False
    
    def test_pii_field_with_prefix(self):
        """Test PIIField with prefixed token format."""
        field = PIIField(
            name="ssn",
            deterministic=True,
            token_format="prefixed",
            token_prefix="SSN_"
        )
        assert field.token_prefix == "SSN_"
    
    def test_pii_field_prefixed_without_prefix_fails(self):
        """Test that prefixed format requires token_prefix."""
        with pytest.raises(ValidationError) as exc_info:
            PIIField(name="email", token_format="prefixed")
        assert "token_prefix required" in str(exc_info.value)
    
    def test_pii_field_dot_notation(self):
        """Test PIIField with dot-notation path."""
        field = PIIField(name="address.street")
        assert field.name == "address.street"


class TestStructuredConfig:
    """Tests for StructuredConfig model."""
    
    def test_structured_config_basic(self):
        """Test basic StructuredConfig creation."""
        config = StructuredConfig(
            pii_fields=[
                PIIField(name="email"),
                PIIField(name="name")
            ]
        )
        assert len(config.pii_fields) == 2
        assert config.token_ttl_seconds == 0
    
    def test_structured_config_with_ttl(self):
        """Test StructuredConfig with TTL."""
        config = StructuredConfig(
            pii_fields=[PIIField(name="email")],
            token_ttl_seconds=86400
        )
        assert config.token_ttl_seconds == 86400
    
    def test_structured_config_negative_ttl_fails(self):
        """Test that negative TTL is rejected."""
        with pytest.raises(ValidationError):
            StructuredConfig(
                pii_fields=[PIIField(name="email")],
                token_ttl_seconds=-1
            )


class TestUnstructuredConfig:
    """Tests for UnstructuredConfig model."""
    
    def test_unstructured_config_basic(self):
        """Test basic UnstructuredConfig creation."""
        config = UnstructuredConfig(
            entity_types=["PERSON", "EMAIL", "PHONE"]
        )
        assert config.llm_model == "claude-3-haiku-20240307"
        assert len(config.entity_types) == 3
        assert config.rate_limit_per_minute == 100
        assert config.max_text_length == 50000
    
    def test_unstructured_config_custom_model(self):
        """Test UnstructuredConfig with custom model."""
        config = UnstructuredConfig(
            llm_model="claude-3-opus-20240229",
            entity_types=["EMAIL"],
            rate_limit_per_minute=50,
            max_text_length=100000
        )
        assert config.llm_model == "claude-3-opus-20240229"
        assert config.rate_limit_per_minute == 50
        assert config.max_text_length == 100000
    
    def test_unstructured_config_zero_rate_limit_fails(self):
        """Test that zero rate limit is rejected."""
        with pytest.raises(ValidationError):
            UnstructuredConfig(
                entity_types=["EMAIL"],
                rate_limit_per_minute=0
            )
    
    def test_unstructured_config_zero_max_length_fails(self):
        """Test that zero max length is rejected."""
        with pytest.raises(ValidationError):
            UnstructuredConfig(
                entity_types=["EMAIL"],
                max_text_length=0
            )


class TestSystemConfig:
    """Tests for SystemConfig model."""
    
    def test_system_config_env_key_ref(self):
        """Test SystemConfig with env: key reference."""
        config = SystemConfig(
            system_id="customer_db",
            encryption_key_ref="env:CUSTOMER_DB_KEY",
            structured=StructuredConfig(
                pii_fields=[PIIField(name="email")]
            )
        )
        assert config.system_id == "customer_db"
        assert config.encryption_key_ref == "env:CUSTOMER_DB_KEY"
        assert config.structured is not None
    
    def test_system_config_file_key_ref(self):
        """Test SystemConfig with file: key reference."""
        config = SystemConfig(
            system_id="analytics_db",
            encryption_key_ref="file:/run/secrets/key"
        )
        assert config.encryption_key_ref == "file:/run/secrets/key"
    
    def test_system_config_invalid_key_ref_fails(self):
        """Test that invalid key reference format is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SystemConfig(
                system_id="test",
                encryption_key_ref="invalid_format"
            )
        assert "must start with 'env:' or 'file:'" in str(exc_info.value)
    
    def test_system_config_both_structured_and_unstructured(self):
        """Test SystemConfig with both structured and unstructured configs."""
        config = SystemConfig(
            system_id="full_system",
            encryption_key_ref="env:KEY",
            structured=StructuredConfig(
                pii_fields=[PIIField(name="email")]
            ),
            unstructured=UnstructuredConfig(
                entity_types=["PERSON", "EMAIL"]
            )
        )
        assert config.structured is not None
        assert config.unstructured is not None


class TestPolicy:
    """Tests for Policy model."""
    
    def test_policy_basic(self):
        """Test basic Policy creation."""
        policy = Policy(
            systems=[
                SystemConfig(
                    system_id="system1",
                    encryption_key_ref="env:KEY1",
                    structured=StructuredConfig(
                        pii_fields=[PIIField(name="email")]
                    )
                )
            ]
        )
        assert len(policy.systems) == 1
        assert policy.version is not None
    
    def test_policy_with_default_system(self):
        """Test Policy with default_system."""
        policy = Policy(
            systems=[
                SystemConfig(
                    system_id="system1",
                    encryption_key_ref="env:KEY1"
                ),
                SystemConfig(
                    system_id="system2",
                    encryption_key_ref="env:KEY2"
                )
            ],
            default_system="system1"
        )
        assert policy.default_system == "system1"
    
    def test_policy_duplicate_system_ids_fails(self):
        """Test that duplicate system_ids are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Policy(
                systems=[
                    SystemConfig(
                        system_id="duplicate",
                        encryption_key_ref="env:KEY1"
                    ),
                    SystemConfig(
                        system_id="duplicate",
                        encryption_key_ref="env:KEY2"
                    )
                ]
            )
        assert "Duplicate system_id" in str(exc_info.value)
    
    def test_policy_invalid_default_system_fails(self):
        """Test that invalid default_system is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Policy(
                systems=[
                    SystemConfig(
                        system_id="system1",
                        encryption_key_ref="env:KEY1"
                    )
                ],
                default_system="nonexistent"
            )
        assert "not found in systems list" in str(exc_info.value)
    
    def test_policy_custom_version(self):
        """Test Policy with custom version."""
        policy = Policy(
            systems=[
                SystemConfig(
                    system_id="system1",
                    encryption_key_ref="env:KEY1"
                )
            ],
            version="1.0.0"
        )
        assert policy.version == "1.0.0"
    
    def test_policy_multiple_systems(self):
        """Test Policy with multiple systems."""
        policy = Policy(
            systems=[
                SystemConfig(
                    system_id="customer_db",
                    encryption_key_ref="env:CUSTOMER_KEY",
                    structured=StructuredConfig(
                        pii_fields=[
                            PIIField(name="email", deterministic=True),
                            PIIField(
                                name="ssn",
                                deterministic=True,
                                token_format="prefixed",
                                token_prefix="SSN_"
                            )
                        ],
                        token_ttl_seconds=86400
                    )
                ),
                SystemConfig(
                    system_id="analytics_db",
                    encryption_key_ref="file:/run/secrets/analytics_key",
                    unstructured=UnstructuredConfig(
                        entity_types=["PERSON", "EMAIL", "PHONE"],
                        rate_limit_per_minute=50
                    )
                )
            ],
            default_system="customer_db"
        )
        assert len(policy.systems) == 2
        assert policy.systems[0].structured is not None
        assert policy.systems[1].unstructured is not None
