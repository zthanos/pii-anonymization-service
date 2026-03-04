"""Benchmark script for V2 batch API."""

import asyncio
import time
import orjson
import grpc
import sys
import os
from typing import List, Dict, Any

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pii_service.proto import pii_service_v2_pb2 as pb2
from pii_service.proto import pii_service_v2_pb2_grpc as pb2_grpc


async def generate_test_record() -> Dict[str, Any]:
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


async def benchmark_v2_batch(
    num_records: int = 10000,
    batch_size: int = 200,
    system_id: str = "customer_db",
):
    """
    Benchmark V2 batch API.
    
    Args:
        num_records: Total number of records to process
        batch_size: Number of records per batch message
        system_id: System identifier
    """
    print(f"\n{'='*60}")
    print(f"V2 BATCH API BENCHMARK")
    print(f"{'='*60}")
    print(f"Total Records: {num_records:,}")
    print(f"Batch Size: {batch_size}")
    print(f"Number of Batches: {num_records // batch_size}")
    print(f"{'='*60}\n")
    
    # Connect to gRPC server
    channel = grpc.aio.insecure_channel('localhost:50051')
    stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)
    
    # Generate test records
    print("Generating test records...")
    records = [await generate_test_record() for _ in range(num_records)]
    print(f"✓ Generated {num_records:,} records\n")
    
    # Create batches
    print("Creating batches...")
    batches = []
    for i in range(0, num_records, batch_size):
        batch_records = records[i:i + batch_size]
        
        # Create RecordItem messages with bytes payload
        record_items = []
        for j, record in enumerate(batch_records):
            record_items.append(pb2.RecordItem(
                record_id=str(i + j),
                record_data=orjson.dumps(record),  # Direct bytes
            ))
        
        # Create batch request
        batch_request = pb2.BatchAnonymizeRequest(
            system_id=system_id,
            records=record_items,
        )
        batches.append(batch_request)
    
    print(f"✓ Created {len(batches)} batches\n")
    
    # Benchmark: Send all batches
    print("Running benchmark...")
    start_time = time.perf_counter()
    
    total_success = 0
    total_errors = 0
    
    # Send batches sequentially (unary RPC)
    for i, batch_request in enumerate(batches):
        try:
            response = await stub.AnonymizeBatch(batch_request)
            total_success += response.stats.success_count
            total_errors += response.stats.error_count
            
            if (i + 1) % 10 == 0:
                elapsed = time.perf_counter() - start_time
                processed = (i + 1) * batch_size
                throughput = processed / elapsed
                print(f"  Processed {processed:,} records ({throughput:,.0f} rec/sec)")
        
        except Exception as e:
            print(f"  Error in batch {i}: {e}")
            total_errors += batch_size
    
    end_time = time.perf_counter()
    
    # Calculate metrics
    execution_time = end_time - start_time
    throughput = num_records / execution_time
    
    # Print results
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Total Records: {num_records:,}")
    print(f"Successful: {total_success:,}")
    print(f"Errors: {total_errors}")
    print(f"Execution Time: {execution_time:.2f}s")
    print(f"Throughput: {throughput:,.0f} records/sec")
    print(f"{'='*60}\n")
    
    # Calculate improvement
    baseline = 3585  # Current V1 performance
    improvement = throughput / baseline
    print(f"Improvement vs V1:")
    print(f"  V1 (streaming): {baseline:,} records/sec")
    print(f"  V2 (batch): {throughput:,.0f} records/sec")
    print(f"  Improvement: {improvement:.1f}x")
    print(f"{'='*60}\n")
    
    # Close channel
    await channel.close()
    
    return throughput


async def benchmark_v2_streaming(
    num_records: int = 10000,
    batch_size: int = 200,
    system_id: str = "customer_db",
):
    """
    Benchmark V2 streaming batch API.
    
    Args:
        num_records: Total number of records to process
        batch_size: Number of records per batch message
        system_id: System identifier
    """
    print(f"\n{'='*60}")
    print(f"V2 STREAMING BATCH API BENCHMARK")
    print(f"{'='*60}")
    print(f"Total Records: {num_records:,}")
    print(f"Batch Size: {batch_size}")
    print(f"{'='*60}\n")
    
    # Connect to gRPC server
    channel = grpc.aio.insecure_channel('localhost:50051')
    stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)
    
    # Generate test records
    print("Generating test records...")
    records = [await generate_test_record() for _ in range(num_records)]
    print(f"✓ Generated {num_records:,} records\n")
    
    # Batch request generator
    async def request_generator():
        """Generate batch requests."""
        for i in range(0, num_records, batch_size):
            batch_records = records[i:i + batch_size]
            
            record_items = []
            for j, record in enumerate(batch_records):
                record_items.append(pb2.RecordItem(
                    record_id=str(i + j),
                    record_data=orjson.dumps(record),
                ))
            
            yield pb2.BatchAnonymizeRequest(
                system_id=system_id,
                records=record_items,
            )
    
    # Benchmark: Stream batches
    print("Running streaming benchmark...")
    start_time = time.perf_counter()
    
    total_success = 0
    total_errors = 0
    batch_count = 0
    
    try:
        response_stream = stub.AnonymizeBatchStream(request_generator())
        
        async for response in response_stream:
            total_success += response.stats.success_count
            total_errors += response.stats.error_count
            batch_count += 1
            
            if batch_count % 10 == 0:
                elapsed = time.perf_counter() - start_time
                processed = batch_count * batch_size
                throughput = processed / elapsed
                print(f"  Processed {processed:,} records ({throughput:,.0f} rec/sec)")
    
    except Exception as e:
        print(f"  Error during streaming: {e}")
    
    end_time = time.perf_counter()
    
    # Calculate metrics
    execution_time = end_time - start_time
    throughput = num_records / execution_time
    
    # Print results
    print(f"\n{'='*60}")
    print(f"STREAMING RESULTS")
    print(f"{'='*60}")
    print(f"Total Records: {num_records:,}")
    print(f"Successful: {total_success:,}")
    print(f"Errors: {total_errors}")
    print(f"Execution Time: {execution_time:.2f}s")
    print(f"Throughput: {throughput:,.0f} records/sec")
    print(f"{'='*60}\n")
    
    # Close channel
    await channel.close()
    
    return throughput


async def main():
    """Run V2 benchmarks."""
    print("\n" + "="*60)
    print("PII ANONYMIZATION SERVICE - V2 BATCH API BENCHMARKS")
    print("="*60)
    
    # Test different batch sizes
    batch_sizes = [100, 200, 500, 1000]
    
    print("\n" + "="*60)
    print("TESTING DIFFERENT BATCH SIZES (Unary)")
    print("="*60)
    
    results = {}
    for batch_size in batch_sizes:
        throughput = await benchmark_v2_batch(
            num_records=10000,
            batch_size=batch_size,
        )
        results[batch_size] = throughput
        await asyncio.sleep(2)  # Cool down
    
    # Print comparison
    print("\n" + "="*60)
    print("BATCH SIZE COMPARISON")
    print("="*60)
    for batch_size, throughput in results.items():
        print(f"Batch Size {batch_size:4d}: {throughput:,.0f} records/sec")
    print("="*60)
    
    # Find best batch size
    best_batch_size = max(results, key=results.get)
    best_throughput = results[best_batch_size]
    print(f"\nBest: Batch Size {best_batch_size} → {best_throughput:,.0f} records/sec")
    
    # Test streaming with best batch size
    print("\n" + "="*60)
    print(f"TESTING STREAMING API (Batch Size {best_batch_size})")
    print("="*60)
    
    streaming_throughput = await benchmark_v2_streaming(
        num_records=10000,
        batch_size=best_batch_size,
    )
    
    # Final comparison
    print("\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    print(f"V1 Streaming (per-record): 3,585 records/sec")
    print(f"V2 Unary (batch): {best_throughput:,.0f} records/sec")
    print(f"V2 Streaming (batch): {streaming_throughput:,.0f} records/sec")
    print("="*60)
    
    improvement = best_throughput / 3585
    print(f"\nImprovement: {improvement:.1f}x faster! 🚀")


if __name__ == "__main__":
    asyncio.run(main())

