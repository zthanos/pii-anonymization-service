"""Worker pool for batch processing with fixed workers and bounded queues."""

import asyncio
import structlog
from typing import List, Tuple, Any, Optional
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class WorkItem:
    """Work item for the worker pool."""
    batch_id: str
    records: List[dict]
    record_ids: List[str]
    system_id: str
    operation: str  # "anonymize" or "deanonymize"


@dataclass
class WorkResult:
    """Result from processing a work item."""
    batch_id: str
    results: List[Any]
    error: Optional[str] = None


class WorkerPool:
    """
    Fixed worker pool for batch processing.
    
    Benefits over task-per-batch:
    - No task creation overhead per batch
    - Stable scheduling (long-lived workers)
    - Backpressure with bounded queue
    - Reduced context switching
    """

    def __init__(
        self,
        num_workers: int,
        tokenizer,
        queue_size: int = 100,
    ):
        """
        Initialize the worker pool.
        
        Args:
            num_workers: Number of long-lived worker tasks
            tokenizer: StructuredTokenizer instance
            queue_size: Maximum size of work queue (for backpressure)
        """
        self.num_workers = num_workers
        self.tokenizer = tokenizer
        self.work_queue = asyncio.Queue(maxsize=queue_size)
        self.result_queue = asyncio.Queue()
        self.workers = []
        self.running = False
        
        logger.info(
            "worker_pool_initialized",
            num_workers=num_workers,
            queue_size=queue_size,
        )

    async def start(self):
        """Start all worker tasks."""
        if self.running:
            return
        
        self.running = True
        
        # Start long-lived workers
        for worker_id in range(self.num_workers):
            worker = asyncio.create_task(self._worker(worker_id))
            self.workers.append(worker)
        
        logger.info("worker_pool_started", num_workers=len(self.workers))

    async def stop(self):
        """Stop all worker tasks gracefully."""
        if not self.running:
            return
        
        self.running = False
        
        # Send stop signals to all workers
        for _ in range(self.num_workers):
            await self.work_queue.put(None)
        
        # Wait for all workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        logger.info("worker_pool_stopped")

    async def _worker(self, worker_id: int):
        """
        Long-lived worker that processes batches from the queue.
        
        Args:
            worker_id: Unique identifier for this worker
        """
        logger.debug("worker_started", worker_id=worker_id)
        
        while self.running:
            try:
                # Get work item from queue (blocks if empty)
                work_item = await self.work_queue.get()
                
                # Check for stop signal
                if work_item is None:
                    break
                
                # Process the batch
                try:
                    if work_item.operation == "anonymize":
                        results = await self.tokenizer.anonymize_batch(
                            work_item.records,
                            work_item.system_id,
                        )
                    elif work_item.operation == "deanonymize":
                        # Process each record for deanonymization
                        results = []
                        for record in work_item.records:
                            result = await self.tokenizer.deanonymize_record(
                                record,
                                work_item.system_id,
                            )
                            results.append(result)
                    else:
                        raise ValueError(f"Unknown operation: {work_item.operation}")
                    
                    # Put result in result queue
                    await self.result_queue.put(WorkResult(
                        batch_id=work_item.batch_id,
                        results=results,
                        error=None,
                    ))
                
                except Exception as e:
                    logger.error(
                        "worker_processing_error",
                        worker_id=worker_id,
                        batch_id=work_item.batch_id,
                        error=str(e),
                        exc_info=True,
                    )
                    
                    # Put error result
                    await self.result_queue.put(WorkResult(
                        batch_id=work_item.batch_id,
                        results=[],
                        error=str(e),
                    ))
                
                finally:
                    # Mark task as done
                    self.work_queue.task_done()
            
            except asyncio.CancelledError:
                logger.info("worker_cancelled", worker_id=worker_id)
                break
            except Exception as e:
                logger.error(
                    "worker_error",
                    worker_id=worker_id,
                    error=str(e),
                    exc_info=True,
                )
        
        logger.debug("worker_stopped", worker_id=worker_id)

    async def submit_work(self, work_item: WorkItem) -> str:
        """
        Submit work to the pool.
        
        This method blocks if the queue is full (backpressure).
        
        Args:
            work_item: Work item to process
            
        Returns:
            Batch ID for tracking the result
        """
        await self.work_queue.put(work_item)
        return work_item.batch_id

    async def get_result(self) -> WorkResult:
        """
        Get a result from the pool.
        
        This method blocks until a result is available.
        
        Returns:
            Work result
        """
        return await self.result_queue.get()

    def pending_work_count(self) -> int:
        """Get the number of pending work items in the queue."""
        return self.work_queue.qsize()

    def pending_results_count(self) -> int:
        """Get the number of pending results in the queue."""
        return self.result_queue.qsize()
