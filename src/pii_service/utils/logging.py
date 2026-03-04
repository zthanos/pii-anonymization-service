"""Structured logging configuration using structlog."""

import logging
import sys
import structlog
from typing import Any


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured logging with JSON output.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


def sanitize_for_logging(value: Any, is_token: bool = False) -> str:
    """
    Sanitize values for logging to prevent PII leakage.
    
    Args:
        value: Value to sanitize
        is_token: If True, show token prefix for debugging
        
    Returns:
        Sanitized string safe for logging
    """
    if value is None:
        return "None"

    value_str = str(value)

    if is_token:
        # Show first 8 characters of token for debugging
        if len(value_str) > 8:
            return f"{value_str[:8]}..."
        return value_str

    # For PII values, never log the actual value
    return "[REDACTED]"
