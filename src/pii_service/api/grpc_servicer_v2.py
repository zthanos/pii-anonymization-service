"""gRPC V2 servicer implementation with batch message support."""

import orjson
import asyncio
import structlog
import time
from typing import AsyncIterator

from ..proto import pii_service_v2_pb2 as pb2
from ..proto import pii_service_v2_pb2_grpc as pb2_grpc
from ..core.structured_tokenizer import StructuredTokenizer
from ..utils.metrics import (
    records_processed_total,
    tokenization_latency_seconds,
)

logger = structlog.get_logger(__name__)


class StructuredAnonymizerV2ServicerImpl(pb2_grpc.StructuredAnonymizerV2Servicer):
    """
    V2 Implementation with batch message support.
    
    Key improvements:
    - Client-side batching (1 message = 200+ records)
    - Bytes passthrough (no string conversion)
    - Direct orjson.loads on bytes
    - Eliminates per-record protobuf overhead
    """

    def __init__(self, structured_tokenizer: StructuredTokenizer):
        """
        Initialize the V2 gRPC servicer.

        Args:
            structured_tokenizer: Tokenizer for structured data operations
        """
        self.structured_tokenizer = structured_tokenizer

    async def AnonymizeBatch(
        self,
        request: pb2.BatchAnonymizeRequest,
        context,
    ) -> pb2.BatchAnonymizeResponse:
        """
        Batch anonymization - processes multiple records in a single request.
        
        This eliminates per-record protobuf decode overhead:
        - 1 protobuf decode for entire batch (not N decodes)
        - Direct bytes → orjson.loads (no string conversion)
        - Batch processing in tokenizer
        
        Args:
            request: Batch request with multiple records
            context: gRPC context
            
        Returns:
            Batch response with results for all records
        """
        start_time = time.time()
        system_id = request.system_id
        
        # Parse all records from bytes (single operation per batch)
        records = []
        record_ids = []
        parse_errors = []
        
        for i, item in enumerate(request.records):
            try:
                # Direct orjson.loads on bytes (no string conversion)
                record = orjson.loads(item.record_data)
                records.append(record)
                record_ids.append(item.record_id)
            except orjson.JSONDecodeError as e:
                logger.error(
                    "batch_anonymize_json_parse_error",
                    record_id=item.record_id,
                    system_id=system_id,
                    error=str(e),
                )
                parse_errors.append((i, item.record_id, str(e)))
        
        # Process all valid records in a single batch
        results = []
        success_count = 0
        error_count = len(parse_errors)
        
        if records:
            try:
                # Batch anonymize all records at once
                anonymized_results = await self.structured_tokenizer.anonymize_batch(
                    records, system_id
                )
                
                # Build results
                for record_id, result in zip(record_ids, anonymized_results):
                    if result.error:
                        error_count += 1
                        results.append(pb2.RecordResult(
                            record_id=record_id,
                            anonymized_data=b"",
                            token_ids=[],
                            error=result.error,
                        ))
                    else:
                        success_count += 1
                        # Direct orjson.dumps to bytes (no string conversion)
                        results.append(pb2.RecordResult(
                            record_id=record_id,
                            anonymized_data=orjson.dumps(result.record),
                            token_ids=result.token_ids,
                            error="",
                        ))
                        
                        # Track metrics
                        records_processed_total.labels(
                            system_id=system_id,
                            operation="anonymize",
                        ).inc()
                
            except Exception as e:
                logger.error(
                    "batch_anonymize_error",
                    system_id=system_id,
                    batch_size=len(records),
                    error=str(e),
                    exc_info=True,
                )
                # Return errors for all records
                for record_id in record_ids:
                    error_count += 1
                    results.append(pb2.RecordResult(
                        record_id=record_id,
                        anonymized_data=b"",
                        token_ids=[],
                        error=str(e),
                    ))
        
        # Add parse errors to results
        for _, record_id, error_msg in parse_errors:
            results.append(pb2.RecordResult(
                record_id=record_id,
                anonymized_data=b"",
                token_ids=[],
                error=f"JSON parse error: {error_msg}",
            ))
        
        # Calculate batch statistics
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Track batch latency
        if success_count > 0:
            tokenization_latency_seconds.labels(
                system_id=system_id
            ).observe(processing_time_ms / 1000.0)
        
        return pb2.BatchAnonymizeResponse(
            results=results,
            stats=pb2.BatchStats(
                success_count=success_count,
                error_count=error_count,
                processing_time_ms=processing_time_ms,
            ),
        )

    async def DeanonymizeBatch(
        self,
        request: pb2.BatchDeanonymizeRequest,
        context,
    ) -> pb2.BatchDeanonymizeResponse:
        """
        Batch de-anonymization - processes multiple records in a single request.
        
        Args:
            request: Batch request with multiple records
            context: gRPC context
            
        Returns:
            Batch response with results for all records
        """
        start_time = time.time()
        system_id = request.system_id
        
        # Parse all records from bytes
        records = []
        record_ids = []
        parse_errors = []
        
        for i, item in enumerate(request.records):
            try:
                record = orjson.loads(item.record_data)
                records.append(record)
                record_ids.append(item.record_id)
            except orjson.JSONDecodeError as e:
                logger.error(
                    "batch_deanonymize_json_parse_error",
                    record_id=item.record_id,
                    system_id=system_id,
                    error=str(e),
                )
                parse_errors.append((i, item.record_id, str(e)))
        
        # Process all valid records
        results = []
        success_count = 0
        error_count = len(parse_errors)
        
        if records:
            try:
                # De-anonymize all records
                for record_id, record in zip(record_ids, records):
                    try:
                        deanonymized = await self.structured_tokenizer.deanonymize_record(
                            record, system_id
                        )
                        
                        # Check if there are any errors (DeanonymizedRecord has 'errors' dict, not 'error' string)
                        if deanonymized.errors:
                            error_count += 1
                            # Combine all field errors into a single error message
                            error_msg = "; ".join([f"{k}: {v}" for k, v in deanonymized.errors.items()])
                            results.append(pb2.DeanonymizeResult(
                                record_id=record_id,
                                deanonymized_data=b"",
                                error=error_msg,
                            ))
                        else:
                            success_count += 1
                            results.append(pb2.DeanonymizeResult(
                                record_id=record_id,
                                deanonymized_data=orjson.dumps(deanonymized.record),
                                error="",
                            ))
                            
                            records_processed_total.labels(
                                system_id=system_id,
                                operation="deanonymize",
                            ).inc()
                    
                    except Exception as e:
                        error_count += 1
                        results.append(pb2.DeanonymizeResult(
                            record_id=record_id,
                            deanonymized_data=b"",
                            error=str(e),
                        ))
                
            except Exception as e:
                logger.error(
                    "batch_deanonymize_error",
                    system_id=system_id,
                    batch_size=len(records),
                    error=str(e),
                    exc_info=True,
                )
        
        # Add parse errors
        for _, record_id, error_msg in parse_errors:
            results.append(pb2.DeanonymizeResult(
                record_id=record_id,
                deanonymized_data=b"",
                error=f"JSON parse error: {error_msg}",
            ))
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        if success_count > 0:
            tokenization_latency_seconds.labels(
                system_id=system_id
            ).observe(processing_time_ms / 1000.0)
        
        return pb2.BatchDeanonymizeResponse(
            results=results,
            stats=pb2.BatchStats(
                success_count=success_count,
                error_count=error_count,
                processing_time_ms=processing_time_ms,
            ),
        )

    async def AnonymizeBatchStream(
        self,
        request_iterator: AsyncIterator[pb2.BatchAnonymizeRequest],
        context,
    ) -> AsyncIterator[pb2.BatchAnonymizeResponse]:
        """
        Streaming batch anonymization - for very large datasets.
        
        Processes batches as they arrive and streams responses back.
        Each batch is still processed as a unit (no per-record overhead).
        
        Args:
            request_iterator: Stream of batch requests
            context: gRPC context
            
        Yields:
            Batch responses
        """
        async for request in request_iterator:
            # Process each batch and yield response immediately
            response = await self.AnonymizeBatch(request, context)
            yield response
