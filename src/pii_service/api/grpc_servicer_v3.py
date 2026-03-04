"""gRPC V3 servicer implementation with worker pool pattern."""

import orjson
import asyncio
import structlog
import time
import uuid
from typing import AsyncIterator

from ..proto import pii_service_v2_pb2 as pb2
from ..proto import pii_service_v2_pb2_grpc as pb2_grpc
from ..core.structured_tokenizer import StructuredTokenizer
from ..core.worker_pool import WorkerPool, WorkItem
from ..utils.metrics import (
    records_processed_total,
    tokenization_latency_seconds,
)

logger = structlog.get_logger(__name__)


class StructuredAnonymizerV3ServicerImpl(pb2_grpc.StructuredAnonymizerV2Servicer):
    """
    V3 Implementation with worker pool pattern.
    
    Key improvements over V2:
    - Fixed worker pool (no task creation per batch)
    - Bounded queues for backpressure
    - Reduced context switching
    - Stable scheduling
    
    Expected improvement: 1.3-1.5x over V2
    """

    def __init__(
        self,
        structured_tokenizer: StructuredTokenizer,
        num_workers: int = 50,
        queue_size: int = 100,
    ):
        """
        Initialize the V3 gRPC servicer with worker pool.

        Args:
            structured_tokenizer: Tokenizer for structured data operations
            num_workers: Number of worker tasks in the pool
            queue_size: Maximum size of work queue
        """
        self.structured_tokenizer = structured_tokenizer
        self.worker_pool = WorkerPool(
            num_workers=num_workers,
            tokenizer=structured_tokenizer,
            queue_size=queue_size,
        )
        self.pending_requests = {}  # batch_id -> asyncio.Future

    async def start(self):
        """Start the worker pool."""
        await self.worker_pool.start()
        
        # Start result collector task
        self.result_collector_task = asyncio.create_task(self._collect_results())

    async def stop(self):
        """Stop the worker pool."""
        await self.worker_pool.stop()
        
        # Cancel result collector
        if hasattr(self, 'result_collector_task'):
            self.result_collector_task.cancel()
            try:
                await self.result_collector_task
            except asyncio.CancelledError:
                pass

    async def _collect_results(self):
        """Background task that collects results and resolves futures."""
        while True:
            try:
                # Get result from worker pool
                work_result = await self.worker_pool.get_result()
                
                # Find the corresponding future
                future = self.pending_requests.pop(work_result.batch_id, None)
                
                if future and not future.done():
                    # Resolve the future with the result
                    future.set_result(work_result)
                else:
                    logger.warning(
                        "orphaned_result",
                        batch_id=work_result.batch_id,
                    )
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "result_collector_error",
                    error=str(e),
                    exc_info=True,
                )

    async def AnonymizeBatch(
        self,
        request: pb2.BatchAnonymizeRequest,
        context,
    ) -> pb2.BatchAnonymizeResponse:
        """
        Batch anonymization using worker pool.
        
        Args:
            request: Batch request with multiple records
            context: gRPC context
            
        Returns:
            Batch response with results for all records
        """
        start_time = time.time()
        system_id = request.system_id
        batch_id = str(uuid.uuid4())
        
        # Parse all records from bytes
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
        
        # Process all valid records using worker pool
        results = []
        success_count = 0
        error_count = len(parse_errors)
        
        if records:
            try:
                # Create work item
                work_item = WorkItem(
                    batch_id=batch_id,
                    records=records,
                    record_ids=record_ids,
                    system_id=system_id,
                    operation="anonymize",
                )
                
                # Create future for this request
                future = asyncio.Future()
                self.pending_requests[batch_id] = future
                
                # Submit to worker pool (blocks if queue is full - backpressure)
                await self.worker_pool.submit_work(work_item)
                
                # Wait for result
                work_result = await future
                
                # Check for worker error
                if work_result.error:
                    raise Exception(work_result.error)
                
                # Build results from worker output
                anonymized_results = work_result.results
                
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
                
                # Clean up pending request
                self.pending_requests.pop(batch_id, None)
        
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
        Batch de-anonymization using worker pool.
        
        Args:
            request: Batch request with multiple records
            context: gRPC context
            
        Returns:
            Batch response with results for all records
        """
        start_time = time.time()
        system_id = request.system_id
        batch_id = str(uuid.uuid4())
        
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
        
        # Process all valid records using worker pool
        results = []
        success_count = 0
        error_count = len(parse_errors)
        
        if records:
            try:
                # Create work item
                work_item = WorkItem(
                    batch_id=batch_id,
                    records=records,
                    record_ids=record_ids,
                    system_id=system_id,
                    operation="deanonymize",
                )
                
                # Create future for this request
                future = asyncio.Future()
                self.pending_requests[batch_id] = future
                
                # Submit to worker pool
                await self.worker_pool.submit_work(work_item)
                
                # Wait for result
                work_result = await future
                
                # Check for worker error
                if work_result.error:
                    raise Exception(work_result.error)
                
                # Build results
                deanonymized_results = work_result.results
                
                for record_id, result in zip(record_ids, deanonymized_results):
                    if result.error:
                        error_count += 1
                        results.append(pb2.DeanonymizeResult(
                            record_id=record_id,
                            deanonymized_data=b"",
                            error=result.error,
                        ))
                    else:
                        success_count += 1
                        results.append(pb2.DeanonymizeResult(
                            record_id=record_id,
                            deanonymized_data=orjson.dumps(result.record),
                            error="",
                        ))
                        
                        records_processed_total.labels(
                            system_id=system_id,
                            operation="deanonymize",
                        ).inc()
                
            except Exception as e:
                logger.error(
                    "batch_deanonymize_error",
                    system_id=system_id,
                    batch_size=len(records),
                    error=str(e),
                    exc_info=True,
                )
                # Return errors for all records
                for record_id in record_ids:
                    error_count += 1
                    results.append(pb2.DeanonymizeResult(
                        record_id=record_id,
                        deanonymized_data=b"",
                        error=str(e),
                    ))
                
                # Clean up pending request
                self.pending_requests.pop(batch_id, None)
        
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
        Streaming batch anonymization using worker pool.
        
        Args:
            request_iterator: Stream of batch requests
            context: gRPC context
            
        Yields:
            Batch responses
        """
        async for request in request_iterator:
            # Process each batch using worker pool and yield response
            response = await self.AnonymizeBatch(request, context)
            yield response
