"""API request and response models."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class AnonymizedRecord(BaseModel):
    """Response model for anonymized record."""
    record: Dict[str, Any]
    token_ids: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    _pii_anonymized: bool = False


class DeanonymizedRecord(BaseModel):
    """Response model for de-anonymized record."""
    record: Dict[str, Any]
    error: Optional[str] = None


class UnstructuredRequest(BaseModel):
    """Request model for unstructured text anonymization."""
    text: str
    return_entity_map: bool = False


class UnstructuredResponse(BaseModel):
    """Response model for unstructured text anonymization."""
    anonymized_text: str
    entity_map: Optional[Dict[str, Any]] = None


class DeanonymizeRequest(BaseModel):
    """Request model for text de-anonymization."""
    text: str


class DeanonymizeResponse(BaseModel):
    """Response model for text de-anonymization."""
    text: str


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    policy_version: Optional[str] = None


class PolicyReloadResponse(BaseModel):
    """Response model for policy reload."""
    success: bool
    policy_version: Optional[str] = None
    error: Optional[str] = None
