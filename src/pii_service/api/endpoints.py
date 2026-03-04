"""FastAPI endpoint handlers."""

import json
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
import structlog

from ..models.api import (
    UnstructuredRequest,
    UnstructuredResponse,
    DeanonymizeRequest,
    DeanonymizeResponse,
    HealthResponse,
    PolicyReloadResponse,
)
from ..core.structured_tokenizer import StructuredTokenizer
from ..core.unstructured_tokenizer import UnstructuredTokenizer
from ..core.policy_loader import PolicyLoader
from ..core.token_store import TokenStore
from ..utils.metrics import get_metrics, track_record_processed


logger = structlog.get_logger(__name__)


# Router for all endpoints
router = APIRouter()


# Dependency injection placeholders
# These will be set by the main application
_policy_loader: PolicyLoader = None
_structured_tokenizer: StructuredTokenizer = None
_unstructured_tokenizer: UnstructuredTokenizer = None
_token_store: TokenStore = None


def set_dependencies(
    policy_loader: PolicyLoader,
    structured_tokenizer: StructuredTokenizer,
    unstructured_tokenizer: UnstructuredTokenizer,
    token_store: TokenStore,
):
    """Set global dependencies for endpoints."""
    global _policy_loader, _structured_tokenizer, _unstructured_tokenizer, _token_store
    _policy_loader = policy_loader
    _structured_tokenizer = structured_tokenizer
    _unstructured_tokenizer = unstructured_tokenizer
    _token_store = token_store


def get_policy_loader() -> PolicyLoader:
    """Dependency to get PolicyLoader instance."""
    if _policy_loader is None:
        raise HTTPException(status_code=500, detail="PolicyLoader not initialized")
    return _policy_loader


def get_structured_tokenizer() -> StructuredTokenizer:
    """Dependency to get StructuredTokenizer instance."""
    if _structured_tokenizer is None:
        raise HTTPException(status_code=500, detail="StructuredTokenizer not initialized")
    return _structured_tokenizer


def get_unstructured_tokenizer() -> UnstructuredTokenizer:
    """Dependency to get UnstructuredTokenizer instance."""
    if _unstructured_tokenizer is None:
        raise HTTPException(status_code=500, detail="UnstructuredTokenizer not initialized")
    return _unstructured_tokenizer


def get_token_store() -> TokenStore:
    """Dependency to get TokenStore instance."""
    if _token_store is None:
        raise HTTPException(status_code=500, detail="TokenStore not initialized")
    return _token_store


async def stream_records_as_ndjson(records: List[Dict[str, Any]], system_id: str):
    """
    Stream records as NDJSON (newline-delimited JSON).
    
    Args:
        records: List of records to anonymize
        system_id: System identifier
        
    Yields:
        NDJSON lines
    """
    tokenizer = get_structured_tokenizer()

    for record in records:
        try:
            # Anonymize record
            anonymized = await tokenizer.anonymize_record(record, system_id)

            # Track metric
            track_record_processed(system_id, "anonymize")

            # Convert to dict and yield as JSON line
            result = {
                "record": anonymized.record,
                "token_ids": anonymized.token_ids,
                "error": anonymized.error,
                "_pii_anonymized": anonymized._pii_anonymized,
            }
            yield json.dumps(result) + "\n"

        except Exception as e:
            logger.error("record_anonymization_failed", error=str(e), exc_info=True)
            # Return error for this record
            error_result = {
                "record": record,
                "token_ids": [],
                "error": str(e),
                "_pii_anonymized": False,
            }
            yield json.dumps(error_result) + "\n"


async def stream_deanonymize_as_ndjson(records: List[Dict[str, Any]], system_id: str):
    """
    Stream de-anonymized records as NDJSON.
    
    Args:
        records: List of tokenized records to de-anonymize
        system_id: System identifier
        
    Yields:
        NDJSON lines
    """
    tokenizer = get_structured_tokenizer()

    for record in records:
        try:
            # De-anonymize record
            deanonymized = await tokenizer.deanonymize_record(record, system_id)

            # Track metric
            track_record_processed(system_id, "deanonymize")

            # Convert to dict and yield as JSON line
            result = {
                "record": deanonymized.record,
                "errors": deanonymized.errors,
            }
            yield json.dumps(result) + "\n"

        except Exception as e:
            logger.error("record_deanonymization_failed", error=str(e), exc_info=True)
            # Return error for this record
            error_result = {
                "record": record,
                "errors": {"_global": str(e)},
            }
            yield json.dumps(error_result) + "\n"


@router.post("/structured/anonymize")
async def anonymize_structured(
    records: List[Dict[str, Any]],
    x_system_id: str = Header(..., alias="X-System-ID"),
):
    """
    Anonymize structured data records.
    
    Args:
        records: List of JSON records to anonymize
        x_system_id: System identifier from header
        
    Returns:
        StreamingResponse with NDJSON
    """
    logger.info("anonymize_structured_request", system_id=x_system_id, record_count=len(records))

    return StreamingResponse(
        stream_records_as_ndjson(records, x_system_id),
        media_type="application/x-ndjson",
    )


@router.post("/structured/deanonymize")
async def deanonymize_structured(
    records: List[Dict[str, Any]],
    x_system_id: str = Header(..., alias="X-System-ID"),
):
    """
    De-anonymize structured data records.
    
    Args:
        records: List of tokenized JSON records to de-anonymize
        x_system_id: System identifier from header
        
    Returns:
        StreamingResponse with NDJSON
    """
    logger.info("deanonymize_structured_request", system_id=x_system_id, record_count=len(records))

    return StreamingResponse(
        stream_deanonymize_as_ndjson(records, x_system_id),
        media_type="application/x-ndjson",
    )


@router.post("/unstructured/anonymize", response_model=UnstructuredResponse)
async def anonymize_unstructured(
    request_data: UnstructuredRequest,
    request: Request,
    x_system_id: str = Header(..., alias="X-System-ID"),
):
    """
    Anonymize unstructured text.
    
    Args:
        request_data: Request with text and return_entity_map flag
        request: FastAPI request (for client_id)
        x_system_id: System identifier from header
        
    Returns:
        UnstructuredResponse with anonymized text and optional entity map
    """
    logger.info("anonymize_unstructured_request", system_id=x_system_id, text_length=len(request_data.text))

    # Get client_id from request state (set by auth middleware)
    client_id = getattr(request.state, "client_id", "unknown")

    tokenizer = get_unstructured_tokenizer()

    try:
        # Anonymize text
        result = await tokenizer.anonymize_text(
            request_data.text,
            x_system_id,
            client_id,
            request_data.return_entity_map,
        )

        return UnstructuredResponse(
            anonymized_text=result.anonymized_text,
            entity_map=result.entity_map if request_data.return_entity_map else None,
        )

    except Exception as e:
        logger.error("unstructured_anonymization_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unstructured/deanonymize", response_model=DeanonymizeResponse)
async def deanonymize_unstructured(
    request_data: DeanonymizeRequest,
    x_system_id: str = Header(..., alias="X-System-ID"),
):
    """
    De-anonymize unstructured text.
    
    Args:
        request_data: Request with tokenized text
        x_system_id: System identifier from header
        
    Returns:
        DeanonymizeResponse with original text
    """
    logger.info("deanonymize_unstructured_request", system_id=x_system_id, text_length=len(request_data.text))

    tokenizer = get_unstructured_tokenizer()

    try:
        # De-anonymize text
        deanonymized_text = await tokenizer.deanonymize_text(
            request_data.text,
            x_system_id,
        )

        return DeanonymizeResponse(text=deanonymized_text)

    except Exception as e:
        logger.error("unstructured_deanonymization_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        HealthResponse with status and policy version
    """
    token_store = get_token_store()
    policy_loader = get_policy_loader()

    try:
        # Check Redis connectivity with 2 second timeout
        is_healthy = await asyncio.wait_for(
            token_store.health_check(),
            timeout=2.0
        )

        if is_healthy:
            return HealthResponse(
                status="healthy",
                policy_version=policy_loader.get_policy_version(),
            )
        else:
            return Response(
                content=json.dumps({
                    "status": "unhealthy",
                    "policy_version": policy_loader.get_policy_version(),
                }),
                status_code=503,
                media_type="application/json",
            )

    except asyncio.TimeoutError:
        logger.error("health_check_timeout")
        return Response(
            content=json.dumps({
                "status": "unhealthy",
                "policy_version": policy_loader.get_policy_version(),
            }),
            status_code=503,
            media_type="application/json",
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e), exc_info=True)
        return Response(
            content=json.dumps({
                "status": "unhealthy",
                "policy_version": policy_loader.get_policy_version(),
            }),
            status_code=503,
            media_type="application/json",
        )


@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns:
        Prometheus metrics in text format
    """
    metrics_data, content_type = get_metrics()
    return Response(content=metrics_data, media_type=content_type)


@router.post("/admin/policy/reload", response_model=PolicyReloadResponse)
async def reload_policy():
    """
    Reload policy from disk.
    
    Returns:
        PolicyReloadResponse with success status and new version
    """
    policy_loader = get_policy_loader()

    try:
        await policy_loader.reload_policy()

        logger.info("policy_reloaded", version=policy_loader.get_policy_version())

        return PolicyReloadResponse(
            success=True,
            policy_version=policy_loader.get_policy_version(),
        )

    except Exception as e:
        logger.error("policy_reload_failed", error=str(e), exc_info=True)

        return PolicyReloadResponse(
            success=False,
            policy_version=policy_loader.get_policy_version(),
            error=str(e),
        )
