"""Tests for policy configuration Pydantic models."""

import pytest
from pydantic import ValidationError

from pii_service.models import PIIField, Policy, StructuredConfig, SystemConfig, UnstructuredConfig


class TestPIIField:
    def test_pii_field_basic(self):
        field = PIIField(name="email")
        assert field.name == "email"
        assert field.deterministic is False
        assert field.token_format == "uuid"
        assert field.token_prefix is None
        assert field.nullable is False

    def test_pii_field_with_prefix(self):
        field = PIIField(name="ssn", deterministic=True, token_format="prefixed", token_prefix="SSN_")
        assert field.token_prefix == "SSN_"

    def test_pii_field_prefixed_without_prefix_fails(self):
        with pytest.raises(ValidationError):
            PIIField(name="email", token_format="prefixed")


class TestStructuredConfig:
    def test_structured_config_basic(self):
        config = StructuredConfig(pii_fields=[PIIField(name="email"), PIIField(name="name")])
        assert len(config.pii_fields) == 2
        assert config.token_ttl_seconds == 0

    def test_structured_config_negative_ttl_fails(self):
        with pytest.raises(ValidationError):
            StructuredConfig(pii_fields=[PIIField(name="email")], token_ttl_seconds=-1)


class TestUnstructuredConfig:
    def test_unstructured_config_basic(self):
        config = UnstructuredConfig(
            detector="hybrid",
            entities=[
                UnstructuredConfig.EntityRule(type="EMAIL", detection=["deterministic"]),
                UnstructuredConfig.EntityRule(type="PERSON", detection=["semantic"], action="redact"),
            ],
        )
        assert config.detector == "hybrid"
        assert config.max_text_length == 50000
        assert config.semantic_detector is not None

    def test_unstructured_config_zero_max_length_fails(self):
        with pytest.raises(ValidationError):
            UnstructuredConfig(
                detector="deterministic",
                entities=[UnstructuredConfig.EntityRule(type="EMAIL", detection=["deterministic"])],
                max_text_length=0,
            )

    def test_unstructured_config_semantic_detector_backfilled(self):
        config = UnstructuredConfig(
            detector="hybrid",
            entities=[UnstructuredConfig.EntityRule(type="PERSON", detection=["semantic"])],
        )
        assert config.semantic_detector is not None
        assert config.semantic_detector.enabled_for == ["PERSON"]

    def test_unstructured_config_deterministic_detector_rejects_semantic_rules(self):
        with pytest.raises(ValidationError):
            UnstructuredConfig(
                detector="deterministic",
                entities=[UnstructuredConfig.EntityRule(type="PERSON", detection=["semantic"])],
            )

    def test_unstructured_config_semantic_detector_rejects_deterministic_rules(self):
        with pytest.raises(ValidationError):
            UnstructuredConfig(
                detector="semantic",
                entities=[UnstructuredConfig.EntityRule(type="EMAIL", detection=["deterministic"])],
            )


class TestSystemConfig:
    def test_system_config_both_structured_and_unstructured(self):
        config = SystemConfig(
            system_id="full_system",
            encryption_key_ref="env:KEY",
            structured=StructuredConfig(pii_fields=[PIIField(name="email")]),
            unstructured=UnstructuredConfig(
                detector="hybrid",
                entities=[UnstructuredConfig.EntityRule(type="PERSON", detection=["semantic"])],
            ),
        )
        assert config.structured is not None
        assert config.unstructured is not None


class TestPolicy:
    def test_policy_with_default_system(self):
        policy = Policy(
            systems=[
                SystemConfig(system_id="system1", encryption_key_ref="env:KEY1"),
                SystemConfig(system_id="system2", encryption_key_ref="env:KEY2"),
            ],
            default_system="system1",
        )
        assert policy.default_system == "system1"

    def test_policy_duplicate_system_ids_fails(self):
        with pytest.raises(ValidationError):
            Policy(
                systems=[
                    SystemConfig(system_id="duplicate", encryption_key_ref="env:KEY1"),
                    SystemConfig(system_id="duplicate", encryption_key_ref="env:KEY2"),
                ]
            )
