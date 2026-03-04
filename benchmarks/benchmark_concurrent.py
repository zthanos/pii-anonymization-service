"""Concurrent benchmark to test multi-instance scaling."""

import asyncio
import time
import orjson
import grpc
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pii_service.proto import pii_service_v2_pb2 as pb2
from pii_service.proto import pii_service_v2_pb2_grpc as pb2_grpc


async def generate_test_record():
    """Generate a test record with PII fields."""
    timestamp = time.time_ns()
    return {
        "email": f"user{timestamp}@example.com",
        "name": f"User {timestamp}",
        "ssn": f"{timestamp % 1000000000:09d}",
        "address": {
            "street": f"{timestamp % 10000} Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94102"
        },
        "phone": f"+1-555-{timestamp % 10000:04d}",
        "user_id": f"user_{timestamp}",
    }


async def send_batch(stub, batch_request, batch_id):
    """Send a single batch and return results."""
    try:
        response = await stub.AnonymizeBatch(batch_request)
        return {
            'batch_id': batch_id,
            'success': response.stats.success_count,
            'errors': response.stats.error_count,
            'time_ms': response.stats.processing_time_ms,
        }
    except Exception as e:
        return {
            'batch_id': batch_id,
            'success': 0,
            'errors': len(batch_request.records),
            'time_ms': 0,
            'error': str(e),
        }


async def benchmark_concurrent(
    num_records=100000,
    batch_size=5000,
    num_concurrent=10,
):
    """
    Benchmark with concurrent requests to test multi-instance scaling.
    
    Args:
        num_records: Total number of records to process
        batch_size: Records per batch
        num_concurrent: Number of concurrent requests
    """
    print("\n" + "="*60)
    print("CONCURRENT BENCHMARK - MULTI-INSTANCE")
    print("="*60)
    print(f"Total Records: {num_records:,}")
    print(f"Batch Size: {batch_size}")
    print(f"Number of Batches: {num_records // batch_size}")
    print(f"Concurrent Requests: {num_concurrent}")
    print("="*60 + "\n")
    
    # Connect
    channel = grpc.aio.insecure_channel(
        'localhost:50051',
        options=[
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.http2.max_pings_without_data', 0),
        ]
    )
    stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)
    
    # Generate records
    print("Generating test records...")
    records = [await generate_test_record() for _ in range(num_records)]
    print(f"Generated {num_records:,} records\n")
    
    # Create batches
    print("Creating batches...")
    batches = []
    for i in range(0, num_records, batch_size):
        batch_records = records[i:i + batch_size]
        record_items = [
            pb2.RecordItem(
                record_id=str(i + j),
                record_data=orjson.dumps(record),
            )
            for j, record in enumerate(batch_records)
        ]
        batches.append(pb2.BatchAnonymizeRequest(
            system_id="customer_db",
            records=record_items,
        ))
    print(f"Created {len(batches)} batches\n")
    
    # Benchmark with concurrent requests
    print(f"Running benchmark with {num_concurrent} concurrent requests...")
    start_time = time.perf_counter()
    
    # Create tasks for concurrent execution
    tasks = []
    for batch_id, batch_request in enumerate(batches):
        task = asyncio.create_task(send_batch(stub, batch_request, batch_id))
        tasks.append(task)
        
        # Limit concurrency
        if len(tasks) >= num_concurrent:
            # Wait for at least one to complete
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Process completed tasks
            for task in done:
                result = await task
                tasks.remove(task)
                
                # Progress update
                completed_batches = batch_id - len(tasks) + 1
                if completed_batches % 5 == 0:
                    elapsed = time.perf_counter() - start_time
                    processed = completed_batches * batch_size
                    throughput = processed / elapsed
                    print(f"  Processed {processed:,} records ({throughput:,.0f} rec/sec)")
    
    # Wait for remaining tasks
    if tasks:
        results = await asyncio.gather(*tasks)
    
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    throughput = num_records / execution_time
    
    # Results
    print(f"\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Total Records: {num_records:,}")
    print(f"Execution Time: {execution_time:.2f}s")
    print(f"Throughput: {throughput:,.0f} records/sec")
    print(f"Concurrent Requests: {num_concurrent}")
    print("="*60 + "\n")
    
    # Comparison
    baseline = 3585
    single_instance = 18673
    improvement_vs_v1 = throughput / baseline
    improvement_vs_single = throughput / single_instance
    
    print("Performance Comparison:")
    print(f"  V1 (streaming): {baseline:,} records/sec")
    print(f"  V2 (single instance): {single_instance:,} records/sec")
    print(f"  V2 (multi-instance): {throughput:,.0f} records/sec")
    print(f"  Improvement vs V1: {improvement_vs_v1:.1f}x")
    print(f"  Improvement vs single: {improvement_vs_single:.1f}x")
    print("="*60 + "\n")
    
    await channel.close()
    return throughput


async def main():
    """Run benchmarks with different concurrency levels."""
    print("\n" + "="*60)
    print("PII ANONYMIZATION SERVICE - MULTI-INSTANCE BENCHMARK")
    print("="*60)
    
    # Test different concurrency levels
    concurrency_levels = [1, 4, 8, 16, 20]
    results = {}
    
    for concurrency in concurrency_levels:
        throughput = await benchmark_concurrent(
            num_records=100000,
            batch_size=5000,
            num_concurrent=concurrency,
        )
        results[concurrency] = throughput
        await asyncio.sleep(2)
    
    # Summary
    print("\n" + "="*60)
    print("CONCURRENCY COMPARISON")
    print("="*60)
    for concurrency, throughput in results.items():
        print(f"Concurrency {concurrency:2d}: {throughput:,.0f} records/sec")
    
    best_concurrency = max(results, key=results.get)
    best_throughput = results[best_concurrency]
    print(f"\nBest: Concurrency {best_concurrency} -> {best_throughput:,.0f} records/sec")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
