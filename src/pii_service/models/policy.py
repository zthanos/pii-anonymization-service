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
        llm_model: Anthropic model identifier for entity extraction
        entity_types: List of PII entity types to extract
        rate_limit_per_minute: Maximum LLM API calls per minute per client
        max_text_length: Maximum text length in characters
    """

    llm_model: str = "claude-3-haiku-20240307"
    entity_types: List[str]
    rate_limit_per_minute: int = Field(default=100, gt=0)
    max_text_length: int = Field(default=50000, gt=0)


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
