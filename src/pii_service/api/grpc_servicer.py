"""gRPC servicer implementation for structured data anonymization."""

import json
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

    def __init__(self, structured_tokenizer: StructuredTokenizer, max_concurrent: int = 100):
        """
        Initialize the gRPC servicer.

        Args:
            structured_tokenizer: Tokenizer for structured data operations
            max_concurrent: Maximum concurrent requests to process (default: 100)
        """
        self.structured_tokenizer = structured_tokenizer
        self.max_concurrent = max_concurrent

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
                record = json.loads(request.record_json)
            except json.JSONDecodeError as e:
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

            logger.debug(
                "grpc_anonymize_success",
                record_id=request.record_id,
                system_id=request.system_id,
                token_count=len(anonymized.token_ids),
                duration_ms=duration * 1000,
            )

            # Return successful response
            return AnonymizeResponse(
                record_id=request.record_id,
                anonymized_json=json.dumps(anonymized.record),
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
        
        Processes requests concurrently with a semaphore to limit concurrency.
        This significantly improves throughput compared to sequential processing.

        Args:
            request_iterator: Stream of anonymization requests
            context: gRPC context

        Yields:
            AnonymizeResponse for each processed record
        """
        # Use a queue to maintain order while processing concurrently
        response_queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        active_tasks = set()
        
        async def process_with_semaphore(request: AnonymizeRequest):
            """Process request with concurrency limit."""
            async with semaphore:
                response = await self._process_anonymize_request(request)
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
                record = json.loads(request.record_json)
            except json.JSONDecodeError as e:
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

            logger.debug(
                "grpc_deanonymize_success",
                record_id=request.record_id,
                system_id=request.system_id,
                duration_ms=duration * 1000,
            )

            # Return successful response
            return DeanonymizeResponse(
                record_id=request.record_id,
                deanonymized_json=json.dumps(deanonymized.record),
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
