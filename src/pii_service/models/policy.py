"""Pydantic models for policy configuration."""

import time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PIIField(BaseModel):
    """Configuration for a PII field in structured data.
    
    Attributes:
        name: Field name or dot-notation path (e.g., "email" or "address.street")
        deterministic: Whether to use deterministic tokenization (HMAC-SHA256)
        token_format: Format of the generated token
        token_prefix: Prefix for tokens when token_format is "prefixed"
        nullable: Whether the field can be null
    """

    name: str
    deterministic: bool = False
    token_format: Literal["uuid", "deterministic", "prefixed"] = "uuid"
    token_prefix: Optional[str] = None
    nullable: bool = False

    @model_validator(mode="after")
    def validate_prefix_requirement(self) -> "PIIField":
        """Validate that token_prefix is provided when token_format is 'prefixed'."""
        if self.token_format == "prefixed" and not self.token_prefix:
            raise ValueError("token_prefix required when token_format is 'prefixed'")
        return self


class StructuredConfig(BaseModel):
    """Configuration for structured data tokenization.
    
    Attributes:
        pii_fields: List of PII field configurations
        token_ttl_seconds: Time-to-live for tokens in seconds (0 = no expiry)
    """

    pii_fields: List[PIIField]
    token_ttl_seconds: int = Field(default=0, ge=0)


class UnstructuredConfig(BaseModel):
    """Configuration for unstructured data tokenization.
    
    Attributes:
        detector: Detector strategy for unstructured processing
        max_text_length: Maximum text length in characters
    """

    class PrefilterConfig(BaseModel):
        enabled: bool = True
        min_length: int = Field(default=8, ge=0)

    class SemanticDetectorConfig(BaseModel):
        provider: Literal["huggingface"] = "huggingface"
        model: Optional[str] = None
        threshold: float = Field(default=0.85, ge=0.0, le=1.0)
        enabled_for: List[str] = Field(default_factory=list)

    class OverlapResolutionConfig(BaseModel):
        strategy: Literal["longest_match"] = "longest_match"

    class EntityRule(BaseModel):
        type: str
        detection: List[Literal["deterministic", "semantic"]] = Field(
            default_factory=list
        )
        action: Literal["tokenize", "redact"] = "tokenize"
        min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    detector: Literal["deterministic", "hybrid", "semantic"] = "hybrid"
    max_text_length: int = Field(default=50000, gt=0)
    prefilter: PrefilterConfig = Field(default_factory=PrefilterConfig)
    semantic_detector: Optional[SemanticDetectorConfig] = None
    entities: List[EntityRule]
    overlap_resolution: OverlapResolutionConfig = Field(
        default_factory=OverlapResolutionConfig
    )

    @model_validator(mode="after")
    def validate_entity_configuration(self) -> "UnstructuredConfig":
        """Validate detector/entity consistency and backfill semantic config."""
        if self.detector in {"semantic", "hybrid"} and self.semantic_detector is None:
            semantic_entities = [
                entity.type
                for entity in self.entities
                if "semantic" in entity.detection
            ]
            if semantic_entities:
                self.semantic_detector = self.SemanticDetectorConfig(
                    enabled_for=semantic_entities
                )

        if self.detector == "deterministic" and any(
            "semantic" in entity.detection for entity in self.entities
        ):
            raise ValueError("deterministic detector cannot be used with semantic entity rules")

        if self.detector == "semantic" and any(
            "deterministic" in entity.detection for entity in self.entities
        ):
            raise ValueError("semantic detector cannot be used with deterministic entity rules")

        return self


class SystemConfig(BaseModel):
    """Configuration for a specific system.
    
    Attributes:
        system_id: Unique identifier for the system
        encryption_key_ref: Reference to encryption key (env:VAR_NAME or file:/path)
        structured: Configuration for structured data tokenization
        unstructured: Configuration for unstructured data tokenization
    """

    system_id: str
    encryption_key_ref: str
    structured: Optional[StructuredConfig] = None
    unstructured: Optional[UnstructuredConfig] = None

    @field_validator("encryption_key_ref")
    @classmethod
    def validate_key_ref(cls, v: str) -> str:
        """Validate that encryption_key_ref has correct format."""
        if not (v.startswith("env:") or v.startswith("file:")):
            raise ValueError("encryption_key_ref must start with 'env:' or 'file:'")
        return v


class Policy(BaseModel):
    """Root policy configuration.
    
    Attributes:
        systems: List of system configurations
        default_system: Default system_id to use when not specified
        version: Policy version (defaults to current timestamp)
    """

    systems: List[SystemConfig]
    default_system: Optional[str] = None
    version: str = Field(default_factory=lambda: str(int(time.time())))

    @field_validator("systems")
    @classmethod
    def validate_unique_system_ids(cls, v: List[SystemConfig]) -> List[SystemConfig]:
        """Validate that all system_ids are unique."""
        system_ids = [s.system_id for s in v]
        if len(system_ids) != len(set(system_ids)):
            raise ValueError("Duplicate system_id values found")
        return v

    @model_validator(mode="after")
    def validate_default_system_exists(self) -> "Policy":
        """Validate that default_system exists in systems list if specified."""
        if self.default_system:
            system_ids = {s.system_id for s in self.systems}
            if self.default_system not in system_ids:
                raise ValueError(
                    f"default_system '{self.default_system}' not found in systems list"
                )
        return self
