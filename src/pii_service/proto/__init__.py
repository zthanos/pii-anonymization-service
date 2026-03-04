"""gRPC protocol buffer definitions for PII service."""

from .pii_service_pb2 import (
    AnonymizeRequest,
    AnonymizeResponse,
    DeanonymizeRequest,
    DeanonymizeResponse,
)
from .pii_service_pb2_grpc import (
    StructuredAnonymizerServicer,
    StructuredAnonymizerStub,
    add_StructuredAnonymizerServicer_to_server,
)

__all__ = [
    "AnonymizeRequest",
    "AnonymizeResponse",
    "DeanonymizeRequest",
    "DeanonymizeResponse",
    "StructuredAnonymizerServicer",
    "StructuredAnonymizerStub",
    "add_StructuredAnonymizerServicer_to_server",
]
