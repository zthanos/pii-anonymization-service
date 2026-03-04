"""Prometheus metrics for observability."""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from typing import Literal


# Records processed counter
records_processed_total = Counter(
    "records_processed_total",
    "Total number of records processed",
    ["system_id", "operation"]
)

# Tokenization latency histogram
tokenization_latency_seconds = Histogram(
    "tokenization_latency_seconds",
    "Latency of tokenization operations in seconds",
    ["system_id"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

# Redis operation latency histogram
redis_operation_latency_seconds = Histogram(
    "redis_operation_latency_seconds",
    "Latency of Redis operations in seconds",
    ["operation"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
)

# LLM API calls counter
llm_api_calls_total = Counter(
    "llm_api_calls_total",
    "Total number of LLM API calls",
    ["model", "status"]
)

# LLM API errors counter
llm_api_errors_total = Counter(
    "llm_api_errors_total",
    "Total number of LLM API errors",
    ["error_type"]
)


def get_metrics() -> tuple[bytes, str]:
    """
    Generate Prometheus metrics in text format.
    
    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST


def track_record_processed(system_id: str, operation: Literal["anonymize", "deanonymize"]) -> None:
    """
    Track a processed record.
    
    Args:
        system_id: System identifier
        operation: Operation type (anonymize or deanonymize)
    """
    records_processed_total.labels(system_id=system_id, operation=operation).inc()


def track_redis_operation(operation: str, duration_seconds: float) -> None:
    """
    Track a Redis operation.
    
    Args:
        operation: Operation type (store, retrieve, ping, etc.)
        duration_seconds: Operation duration in seconds
    """
    redis_operation_latency_seconds.labels(operation=operation).observe(duration_seconds)


def track_llm_call(model: str, status: Literal["success", "error"]) -> None:
    """
    Track an LLM API call.
    
    Args:
        model: Model name
        status: Call status (success or error)
    """
    llm_api_calls_total.labels(model=model, status=status).inc()


def track_llm_error(error_type: str) -> None:
    """
    Track an LLM API error.
    
    Args:
        error_type: Type of error (timeout, rate_limit, invalid_response, etc.)
    """
    llm_api_errors_total.labels(error_type=error_type).inc()
