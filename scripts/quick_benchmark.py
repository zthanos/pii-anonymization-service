"""Quick benchmark to test final optimized performance."""

import asyncio
import time
import json
import sys
import os
import grpc

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pii_service.proto import pii_service_pb2
from pii_service.proto import pii_service_pb2_grpc


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


async def run_grpc_benchmark(num_records: int = 10000):
    """Run gRPC streaming benchmark."""
    print(f"Starting gRPC streaming benchmark: {num_records:,} records")
    
    # Connect to gRPC server
    channel = grpc.aio.insecure_channel('localhost:50051')
    stub = pii_service_pb2_grpc.StructuredAnonymizerStub(channel)
    
    # Generate test records
    print("Generating test records...")
    records = [await generate_test_record() for _ in range(num_records)]
    
    # Request generator
    async def request_generator():
        """Generate requests to send to server."""
        for i, record in enumerate(records):
            request = pii_service_pb2.AnonymizeRequest(
                system_id="customer_db",
                record_id=str(i),
                record_json=json.dumps(record)
            )
            yield request
    
    # Run benchmark
    print("Running gRPC streaming anonymization...")
    start_time = time.perf_counter()
    
    response_count = 0
    error_count = 0
    
    try:
        # Start bidirectional streaming
        response_stream = stub.Anonymize(request_generator())
        
        # Process responses
        async for response in response_stream:
            response_count += 1
            if response.error:
                error_count += 1
    
    except Exception as e:
        print(f"Error during gRPC streaming: {e}")
        error_count += 1
    
    end_time = time.perf_counter()
    
    # Calculate metrics
    execution_time = end_time - start_time
    throughput = num_records / execution_time
    
    # Print results
    print(f"\n{'='*60}")
    print(f"FINAL BENCHMARK RESULTS")
    print(f"{'='*60}")
    print(f"  Total Records: {num_records:,}")
    print(f"  Responses Received: {response_count:,}")
    print(f"  Execution Time: {execution_time:.2f}s")
    print(f"  Throughput: {throughput:,.0f} records/sec")
    print(f"  Errors: {error_count}")
    print(f"{'='*60}")
    
    # Close channel
    await channel.close()
    
    return throughput


async def main():
    """Run quick benchmark."""
    # Test with 10k records
    throughput = await run_grpc_benchmark(10000)
    
    # Calculate improvement from baseline
    baseline = 229  # records/sec
    improvement = throughput / baseline
    
    print(f"\nImprovement from baseline:")
    print(f"  Baseline: {baseline} records/sec")
    print(f"  Current: {throughput:,.0f} records/sec")
    print(f"  Improvement: {improvement:.1f}x")
    
    # Calculate capacity
    capacity_per_hour = throughput * 3600
    print(f"\nCapacity:")
    print(f"  {capacity_per_hour:,.0f} records/hour")
    print(f"  {capacity_per_hour / 1_000_000:.1f} million records/hour")


if __name__ == "__main__":
    asyncio.run(main())
