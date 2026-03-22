"""Data models for entity extraction and detection findings."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class EntitySpan(BaseModel):
    """Represents a PII entity extracted from text.
    
    Attributes:
        type: Entity type (e.g., PERSON, EMAIL, PHONE, SSN, ADDRESS)
        value: The extracted text value
        start: Character offset where the entity starts (0-indexed)
        end: Character offset where the entity ends (exclusive)
        token: Token that replaces this entity (set during tokenization)
    """

    type: str = Field(..., description="Entity type")
    value: str = Field(..., description="Extracted text value")
    start: int = Field(..., ge=0, description="Start character offset")
    end: int = Field(..., ge=0, description="End character offset")
    token: Optional[str] = Field(default=None, description="Token replacing this entity")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"EntitySpan(type={self.type}, value={self.value!r}, start={self.start}, end={self.end})"


class DetectionFinding(BaseModel):
    """Canonical finding emitted by any unstructured detector."""

    type: str = Field(..., description="Canonical entity type")
    value: str = Field(..., description="Extracted text value")
    start: int = Field(..., ge=0, description="Start character offset")
    end: int = Field(..., ge=0, description="End character offset")
    detector: str = Field(..., description="Detector identifier")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional detector confidence score",
    )
    action: Literal["tokenize", "redact"] = Field(
        default="tokenize",
        description="Transformation action to apply",
    )
    token: Optional[str] = Field(default=None, description="Token replacing this finding")

    def to_entity_span(self) -> EntitySpan:
        """Convert a finding to the legacy entity representation."""
        return EntitySpan(
            type=self.type,
            value=self.value,
            start=self.start,
            end=self.end,
            token=self.token,
        )
