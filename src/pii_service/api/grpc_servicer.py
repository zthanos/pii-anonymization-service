"""gRPC servicer implementation for structured data anonymization."""

import orjson
import asyncio
import structlog
from typing import AsyncIterator

from ..proto import (
    AnonymizeRequest,
    AnonymizeResponse,
    DeanonymizeRequest,
    DeanonymizeResponse,
    StructuredAnonymizerServicer,
)
from ..core.structured_tokenizer import StructuredTokenizer
from ..utils.metrics import (
    records_processed_total,
    tokenization_latency_seconds,
)

logger = structlog.get_logger(__name__)


class StructuredAnonymizerServicerImpl(StructuredAnonymizerServicer):
    """Implementation of the StructuredAnonymizer gRPC service."""

    def __init__(self, structured_tokenizer: StructuredTokenizer, max_concurrent: int = 100, batch_size: int = 50):
        """
        Initialize the gRPC servicer.

        Args:
            structured_tokenizer: Tokenizer for structured data operations
            max_concurrent: Maximum concurrent requests to process (default: 100)
            batch_size: Number of records to batch together (default: 50)
        """
        self.structured_tokenizer = structured_tokenizer
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size

    async def _process_anonymize_request(
        self, request: AnonymizeRequest
    ) -> AnonymizeResponse:
        """
        Process a single anonymization request.
        
        Args:
            request: Anonymization request
            
        Returns:
            AnonymizeResponse
        """
        try:
            # Parse JSON record
            try:
                record = orjson.loads(request.record_json)
            except orjson.JSONDecodeError as e:
                logger.error(
                    "grpc_anonymize_json_parse_error",
                    record_id=request.record_id,
                    system_id=request.system_id,
                    error=str(e),
                )
                return AnonymizeResponse(
                    record_id=request.record_id,
                    anonymized_json="",
                    token_ids=[],
                    error=f"Invalid JSON: {str(e)}",
                )

            # Anonymize the record
            import time
            start_time = time.time()

            anonymized = await self.structured_tokenizer.anonymize_record(
                record, request.system_id
            )

            duration = time.time() - start_time
            tokenization_latency_seconds.labels(
                system_id=request.system_id
            ).observe(duration)

            records_processed_total.labels(
                system_id=request.system_id,
                operation="anonymize",
            ).inc()

            # Return successful response
            return AnonymizeResponse(
                record_id=request.record_id,
                anonymized_json=orjson.dumps(anonymized.record).decode(),
                token_ids=anonymized.token_ids,
                error="",
            )

        except Exception as e:
            # Return error response
            logger.error(
                "grpc_anonymize_error",
                record_id=request.record_id,
                system_id=request.system_id,
                error=str(e),
                exc_info=True,
            )

            return AnonymizeResponse(
                record_id=request.record_id,
                anonymized_json="",
                token_ids=[],
                error=str(e),
            )

    async def Anonymize(
        self,
        request_iterator: AsyncIterator[AnonymizeRequest],
        context,
    ) -> AsyncIterator[AnonymizeResponse]:
        """
        Bidirectional streaming RPC for anonymizing structured records.
        
        Processes requests in batches with concurrent batch processing and
        true parallel response streaming. Responses are streamed immediately
        as each batch completes, maximizing throughput.

        Args:
            request_iterator: Stream of anonymization requests
            context: gRPC context

        Yields:
            AnonymizeResponse for each processed record
        """
        # Use unbounded queue for maximum throughput
        response_queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(self.max_concurrent // self.batch_size)
        active_tasks = set()
        
        async def process_batch_with_semaphore(batch_records, batch_requests):
            """Process a batch and stream responses immediately."""
            async with semaphore:
                async for response in self._process_anonymize_batch(batch_records, batch_requests):
                    await response_queue.put(response)
        
        async def consume_requests():
            """Consume requests from iterator and create batch tasks."""
            try:
                batch = []
                batch_requests = []
                
                async for request in request_iterator:
                    # Parse JSON record
                    try:
                        record = orjson.loads(request.record_json)
                    except orjson.JSONDecodeError as e:
                        # Queue error response immediately
                        await response_queue.put(AnonymizeResponse(
                            record_id=request.record_id,
                            anonymized_json="",
                            token_ids=[],
                            error=f"Invalid JSON: {str(e)}",
                        ))
                        continue
                    
                    # Add to batch
                    batch.append(record)
                    batch_requests.append(request)
                    
                    # Process batch when full (transfer ownership, no copy)
                    if len(batch) >= self.batch_size:
                        task = asyncio.create_task(
                            process_batch_with_semaphore(batch, batch_requests)
                        )
                        active_tasks.add(task)
                        task.add_done_callback(active_tasks.discard)
                        batch = []
                        batch_requests = []
                
                # Process remaining records
                if batch:
                    task = asyncio.create_task(
                        process_batch_with_semaphore(batch, batch_requests)
                    )
                    active_tasks.add(task)
                    task.add_done_callback(active_tasks.discard)
                
            finally:
                # Wait for all batch tasks to complete
                if active_tasks:
                    await asyncio.gather(*active_tasks, return_exceptions=True)
                # Signal completion with sentinel
                await response_queue.put(None)
        
        # Start consuming requests in background
        consumer_task = asyncio.create_task(consume_requests())
        
        # Stream responses as they arrive (true parallel streaming)
        while True:
            response = await response_queue.get()
            if response is None:
                break
            yield response
        
        # Wait for consumer to finish
        await consumer_task
    
    async def _process_anonymize_batch(
        self,
        records: list,
        requests: list,
    ) -> AsyncIterator[AnonymizeResponse]:
        """
        Process a batch of anonymization requests.
        
        Args:
            records: List of parsed JSON records
            requests: List of corresponding AnonymizeRequest objects
            
        Yields:
            AnonymizeResponse for each record in the batch
        """
        import time
        start_time = time.time()
        
        # Get system_id from first request (all should have same system_id)
        system_id = requests[0].system_id
        
        try:
            # Batch anonymize all records
            results = await self.structured_tokenizer.anonymize_batch(records, system_id)
            
            duration = time.time() - start_time
            
            # Yield responses for each record
            for request, result in zip(requests, results):
                if result.error:
                    yield AnonymizeResponse(
                        record_id=request.record_id,
                        anonymized_json="",
                        token_ids=[],
                        error=result.error,
                    )
                else:
                    tokenization_latency_seconds.labels(
                        system_id=system_id
                    ).observe(duration / len(records))
                    
                    records_processed_total.labels(
                        system_id=system_id,
                        operation="anonymize",
                    ).inc()
                    
                    yield AnonymizeResponse(
                        record_id=request.record_id,
                        anonymized_json=orjson.dumps(result.record).decode(),
                        token_ids=result.token_ids,
                        error="",
                    )
        
        except Exception as e:
            # Yield error for all records in batch
            logger.error(
                "batch_anonymize_error",
                system_id=system_id,
                batch_size=len(records),
                error=str(e),
                exc_info=True,
            )
            
            for request in requests:
                yield AnonymizeResponse(
                    record_id=request.record_id,
                    anonymized_json="",
                    token_ids=[],
                    error=str(e),
                )

    async def _process_deanonymize_request(
        self, request: DeanonymizeRequest
    ) -> DeanonymizeResponse:
        """
        Process a single de-anonymization request.
        
        Args:
            request: De-anonymization request
            
        Returns:
            DeanonymizeResponse
        """
        try:
            # Parse JSON record
            try:
                record = orjson.loads(request.record_json)
            except orjson.JSONDecodeError as e:
                logger.error(
                    "grpc_deanonymize_json_parse_error",
                    record_id=request.record_id,
                    system_id=request.system_id,
                    error=str(e),
                )
                return DeanonymizeResponse(
                    record_id=request.record_id,
                    deanonymized_json="",
                    error=f"Invalid JSON: {str(e)}",
                )

            # De-anonymize the record
            import time
            start_time = time.time()

            deanonymized = await self.structured_tokenizer.deanonymize_record(
                record, request.system_id
            )

            duration = time.time() - start_time
            tokenization_latency_seconds.labels(
                system_id=request.system_id
            ).observe(duration)

            records_processed_total.labels(
                system_id=request.system_id,
                operation="deanonymize",
            ).inc()

            # Return successful response
            return DeanonymizeResponse(
                record_id=request.record_id,
                deanonymized_json=orjson.dumps(deanonymized.record).decode(),
                error="",
            )

        except Exception as e:
            # Return error response
            logger.error(
                "grpc_deanonymize_error",
                record_id=request.record_id,
                system_id=request.system_id,
                error=str(e),
                exc_info=True,
            )

            return DeanonymizeResponse(
                record_id=request.record_id,
                deanonymized_json="",
                error=str(e),
            )

    async def Deanonymize(
        self,
        request_iterator: AsyncIterator[DeanonymizeRequest],
        context,
    ) -> AsyncIterator[DeanonymizeResponse]:
        """
        Bidirectional streaming RPC for de-anonymizing structured records.
        
        Processes requests concurrently with a semaphore to limit concurrency.

        Args:
            request_iterator: Stream of de-anonymization requests
            context: gRPC context

        Yields:
            DeanonymizeResponse for each processed record
        """
        # Use a queue to maintain order while processing concurrently
        response_queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        active_tasks = set()
        
        async def process_with_semaphore(request: DeanonymizeRequest):
            """Process request with concurrency limit."""
            async with semaphore:
                response = await self._process_deanonymize_request(request)
                await response_queue.put(response)
        
        async def consume_requests():
            """Consume requests from iterator and create tasks."""
            try:
                async for request in request_iterator:
                    task = asyncio.create_task(process_with_semaphore(request))
                    active_tasks.add(task)
                    task.add_done_callback(active_tasks.discard)
            finally:
                # Signal that all requests have been submitted
                await response_queue.put(None)
        
        # Start consuming requests in background
        consumer_task = asyncio.create_task(consume_requests())
        
        # Yield responses as they complete
        while True:
            response = await response_queue.get()
            if response is None:
                # All requests processed
                break
            yield response
        
        # Wait for consumer to finish
        await consumer_task
        
        # Wait for any remaining tasks
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
