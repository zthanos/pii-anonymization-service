"""Large-scale V2 batch API benchmark."""

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


async def benchmark_v2(num_records=100000, batch_size=5000):
    """Benchmark V2 batch API."""
    print("\n" + "="*60)
    print("V2 BATCH API BENCHMARK - LARGE SCALE")
    print("="*60)
    print(f"Total Records: {num_records:,}")
    print(f"Batch Size: {batch_size}")
    print(f"Number of Batches: {num_records // batch_size}")
    print("="*60 + "\n")
    
    # Connect
    channel = grpc.aio.insecure_channel(
        'localhost:50051',
        options=[
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
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
    
    # Benchmark
    print("Running benchmark...")
    start_time = time.perf_counter()
    
    total_success = 0
    total_errors = 0
    
    for i, batch_request in enumerate(batches):
        try:
            response = await stub.AnonymizeBatch(batch_request)
            total_success += response.stats.success_count
            total_errors += response.stats.error_count
            
            elapsed = time.perf_counter() - start_time
            processed = (i + 1) * batch_size
            throughput = processed / elapsed
            print(f"  Batch {i+1}/{len(batches)}: {processed:,} records ({throughput:,.0f} rec/sec)")
        except Exception as e:
            print(f"  Error in batch {i}: {e}")
            total_errors += batch_size
    
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    throughput = num_records / execution_time
    
    # Results
    print(f"\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Total Records: {num_records:,}")
    print(f"Successful: {total_success:,}")
    print(f"Errors: {total_errors}")
    print(f"Execution Time: {execution_time:.2f}s")
    print(f"Throughput: {throughput:,.0f} records/sec")
    print("="*60 + "\n")
    
    # Comparison
    baseline = 3585
    improvement = throughput / baseline
    print("Improvement vs V1:")
    print(f"  V1 (streaming): {baseline:,} records/sec")
    print(f"  V2 (batch): {throughput:,.0f} records/sec")
    print(f"  Improvement: {improvement:.1f}x")
    print("="*60 + "\n")
    
    await channel.close()
    return throughput


async def main():
    """Run benchmarks."""
    print("\n" + "="*60)
    print("PII ANONYMIZATION SERVICE - V2 BATCH API")
    print("LARGE SCALE TESTING")
    print("="*60)
    
    # Test with 100k records
    await benchmark_v2(num_records=100000, batch_size=5000)


if __name__ == "__main__":
    asyncio.run(main())
