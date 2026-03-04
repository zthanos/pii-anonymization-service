"""gRPC server with V2 batch API support."""

import asyncio
import grpc
from concurrent import futures

from .grpc_servicer import StructuredAnonymizerServicerImpl
from .grpc_servicer_v2 import StructuredAnonymizerV2ServicerImpl
from ..proto import pii_service_pb2_grpc
from ..proto import pii_service_v2_pb2_grpc
from ..core.structured_tokenizer import StructuredTokenizer


async def serve_v2(
    structured_tokenizer: StructuredTokenizer,
    port: int = 50051,
    max_workers: int = 50,
    max_concurrent: int = 1000,
    batch_size: int = 200,
):
    """
    Start gRPC server with both V1 (streaming) and V2 (batch) APIs.
    
    Args:
        structured_tokenizer: Tokenizer instance
        port: Port to listen on
        max_workers: Number of worker threads
        max_concurrent: Max concurrent requests (V1 only)
        batch_size: Batch size for V1 streaming
    """
    # Create server with optimized settings
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_send_message_length', 100 * 1024 * 1024),     # 100MB
            ('grpc.http2.max_pings_without_data', 0),
            ('grpc.http2.min_time_between_pings_ms', 10000),
            ('grpc.http2.min_ping_interval_without_data_ms', 5000),
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.http2.max_frame_size', 16384),
            ('grpc.http2.initial_window_size', 1024 * 1024),
        ],
    )
    
    # Add V1 servicer (streaming API - backward compatible)
    v1_servicer = StructuredAnonymizerServicerImpl(
        structured_tokenizer=structured_tokenizer,
        max_concurrent=max_concurrent,
        batch_size=batch_size,
    )
    pii_service_pb2_grpc.add_StructuredAnonymizerServicer_to_server(
        v1_servicer, server
    )
    
    # Add V2 servicer (batch API - optimized)
    v2_servicer = StructuredAnonymizerV2ServicerImpl(
        structured_tokenizer=structured_tokenizer,
    )
    pii_service_v2_pb2_grpc.add_StructuredAnonymizerV2Servicer_to_server(
        v2_servicer, server
    )
    
    # Bind to port
    server.add_insecure_port(f'[::]:{port}')
    
    # Start server
    await server.start()
    print(f"✓ gRPC server started on port {port}")
    print(f"  - V1 API: pii.StructuredAnonymizer (streaming)")
    print(f"  - V2 API: pii.v2.StructuredAnonymizerV2 (batch)")
    
    # Wait for termination
    await server.wait_for_termination()
