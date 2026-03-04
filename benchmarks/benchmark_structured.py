"""Benchmark script for structured data anonymization performance testing."""

import asyncio
import time
import psutil
import statistics
from typing import List, Dict, Any
import json
from dataclasses import dataclass, asdict
import httpx
import sys
import grpc
import sys
import os

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pii_service.proto import pii_service_pb2
from pii_service.proto import pii_service_pb2_grpc


@dataclass
class BenchmarkResult:
    """Benchmark execution results."""
    total_records: int
    execution_time_seconds: float
    throughput_records_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_p999_ms: float
    memory_usage_mb: float
    cpu_utilization_percent: float
    errors: int


class StructuredBenchmark:
    """Benchmark for structured data anonymization."""
    
    def __init__(self, base_url: str, system_id: str, api_key: str = "test_key"):
        """
        Initialize benchmark.
        
        Args:
            base_url: Base URL of the service (e.g., http://localhost:8000)
            system_id: System identifier for policy lookup
            api_key: API key for authentication
        """
        self.base_url = base_url
        self.system_id = system_id
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def generate_test_record(self) -> Dict[str, Any]:
        """
        Generate a test record with PII fields.
        
        Returns:
            Dictionary with PII data matching the policy configuration
        """
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
    
    async def anonymize_record(self, record: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Anonymize a single record and return latency in milliseconds.
        
        Args:
            record: Record to anonymize
            
        Returns:
            Tuple of (latency in milliseconds, anonymized record), or (-1, None) if error occurred
        """
        start = time.perf_counter()
        
        try:
            response = await self.client.post(
                f"{self.base_url}/structured/anonymize",
                json=[record],
                headers={
                    "X-System-ID": self.system_id,
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            response.raise_for_status()
            
            end = time.perf_counter()
            
            # Parse response to get anonymized record
            response_text = response.text.strip()
            if response_text:
                anonymized_record = json.loads(response_text.split('\n')[0])
                return (end - start) * 1000, anonymized_record  # Convert to milliseconds
            else:
                return -1, None
        except Exception as e:
            print(f"Error anonymizing record: {e}")
            return -1, None  # Indicate error
    
    async def deanonymize_record(self, record: Dict[str, Any]) -> float:
        """
        De-anonymize a single record and return latency in milliseconds.
        
        Args:
            record: Anonymized record to de-anonymize
            
        Returns:
            Latency in milliseconds, or -1 if error occurred
        """
        start = time.perf_counter()
        
        try:
            response = await self.client.post(
                f"{self.base_url}/structured/deanonymize",
                json=[record],
                headers={
                    "X-System-ID": self.system_id,
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            response.raise_for_status()
            
            end = time.perf_counter()
            return (end - start) * 1000  # Convert to milliseconds
        except Exception as e:
            print(f"Error de-anonymizing record: {e}")
            return -1  # Indicate error
    
    async def run_benchmark(
        self, 
        num_records: int, 
        concurrency: int = 100
    ) -> BenchmarkResult:
        """
        Run benchmark with specified parameters.
        
        Args:
            num_records: Total number of records to process
            concurrency: Number of concurrent requests
            
        Returns:
            BenchmarkResult with metrics
        """
        print(f"Starting benchmark: {num_records:,} records, concurrency={concurrency}")
        
        # Track system metrics
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate test records
        print("Generating test records...")
        records = [await self.generate_test_record() for _ in range(num_records)]
        
        # Run benchmark
        print("Running anonymization...")
        start_time = time.perf_counter()
        
        # Get initial CPU measurement
        process.cpu_percent()  # First call returns 0, so we discard it
        await asyncio.sleep(0.1)  # Small delay for CPU measurement
        cpu_start = process.cpu_percent()
        
        latencies: List[float] = []
        errors = 0
        
        # Process records with concurrency limit
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_record(record: Dict[str, Any]):
            nonlocal errors
            async with semaphore:
                latency, _ = await self.anonymize_record(record)
                if latency < 0:
                    errors += 1
                else:
                    latencies.append(latency)
        
        tasks = [process_record(record) for record in records]
        await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        cpu_end = process.cpu_percent()
        
        # Calculate metrics
        execution_time = end_time - start_time
        throughput = num_records / execution_time
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = final_memory - initial_memory
        cpu_utilization = (cpu_start + cpu_end) / 2
        
        # Calculate latency percentiles
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            """Calculate percentile from sorted data."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        result = BenchmarkResult(
            total_records=num_records,
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            memory_usage_mb=memory_usage,
            cpu_utilization_percent=cpu_utilization,
            errors=errors
        )
        
        return result
    
    async def run_deanonymization_benchmark(
        self, 
        num_records: int, 
        concurrency: int = 100
    ) -> BenchmarkResult:
        """
        Run de-anonymization benchmark with specified parameters.
        
        First anonymizes records to get tokenized data, then measures
        de-anonymization performance.
        
        Args:
            num_records: Total number of records to process
            concurrency: Number of concurrent requests
            
        Returns:
            BenchmarkResult with de-anonymization metrics
        """
        print(f"Starting de-anonymization benchmark: {num_records:,} records, concurrency={concurrency}")
        
        # Track system metrics
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate and anonymize test records first
        print("Generating and anonymizing test records...")
        records = [await self.generate_test_record() for _ in range(num_records)]
        
        # Anonymize all records to get tokenized data
        anonymized_records = []
        for record in records:
            _, anonymized = await self.anonymize_record(record)
            if anonymized:
                anonymized_records.append(anonymized)
        
        if len(anonymized_records) < num_records:
            print(f"Warning: Only {len(anonymized_records)} records successfully anonymized")
        
        # Run de-anonymization benchmark
        print("Running de-anonymization...")
        start_time = time.perf_counter()
        
        # Get initial CPU measurement
        process.cpu_percent()  # First call returns 0, so we discard it
        await asyncio.sleep(0.1)  # Small delay for CPU measurement
        cpu_start = process.cpu_percent()
        
        latencies: List[float] = []
        errors = 0
        
        # Process records with concurrency limit
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_record(record: Dict[str, Any]):
            nonlocal errors
            async with semaphore:
                latency = await self.deanonymize_record(record)
                if latency < 0:
                    errors += 1
                else:
                    latencies.append(latency)
        
        tasks = [process_record(record) for record in anonymized_records]
        await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        cpu_end = process.cpu_percent()
        
        # Calculate metrics
        execution_time = end_time - start_time
        throughput = len(anonymized_records) / execution_time
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = final_memory - initial_memory
        cpu_utilization = (cpu_start + cpu_end) / 2
        
        # Calculate latency percentiles
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            """Calculate percentile from sorted data."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        result = BenchmarkResult(
            total_records=len(anonymized_records),
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            memory_usage_mb=memory_usage,
            cpu_utilization_percent=cpu_utilization,
            errors=errors
        )
        
        return result
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


class GRPCBenchmark:
    """Benchmark for gRPC streaming anonymization."""
    
    def __init__(self, grpc_host: str, system_id: str):
        """
        Initialize gRPC benchmark.
        
        Args:
            grpc_host: gRPC server address (e.g., localhost:50051)
            system_id: System identifier for policy lookup
        """
        self.grpc_host = grpc_host
        self.system_id = system_id
        self.channel = None
        self.stub = None
    
    async def connect(self):
        """Establish gRPC connection."""
        self.channel = grpc.aio.insecure_channel(self.grpc_host)
        self.stub = pii_service_pb2_grpc.StructuredAnonymizerStub(self.channel)
    
    async def generate_test_record(self) -> Dict[str, Any]:
        """
        Generate a test record with PII fields.
        
        Returns:
            Dictionary with PII data matching the policy configuration
        """
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
    
    async def run_grpc_streaming_benchmark(
        self, 
        num_records: int
    ) -> BenchmarkResult:
        """
        Run gRPC streaming benchmark.
        
        Uses bidirectional streaming to send and receive records concurrently.
        
        Args:
            num_records: Total number of records to process
            
        Returns:
            BenchmarkResult with metrics
        """
        print(f"Starting gRPC streaming benchmark: {num_records:,} records")
        
        # Track system metrics
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate test records
        print("Generating test records...")
        records = [await self.generate_test_record() for _ in range(num_records)]
        
        # Get initial CPU measurement
        process.cpu_percent()  # First call returns 0, so we discard it
        await asyncio.sleep(0.1)  # Small delay for CPU measurement
        cpu_start = process.cpu_percent()
        
        latencies: List[float] = []
        errors = 0
        
        # Request generator
        async def request_generator():
            """Generate requests to send to server."""
            for i, record in enumerate(records):
                request = pii_service_pb2.AnonymizeRequest(
                    system_id=self.system_id,
                    record_id=str(i),
                    record_json=json.dumps(record)
                )
                yield request
        
        # Run benchmark
        print("Running gRPC streaming anonymization...")
        start_time = time.perf_counter()
        
        try:
            # Start bidirectional streaming
            response_stream = self.stub.Anonymize(request_generator())
            
            # Track latencies per record
            record_start_times = {}
            for i in range(num_records):
                record_start_times[str(i)] = time.perf_counter()
            
            # Process responses
            async for response in response_stream:
                record_id = response.record_id
                end_time = time.perf_counter()
                
                if response.error:
                    errors += 1
                else:
                    # Calculate latency for this record
                    if record_id in record_start_times:
                        latency = (end_time - record_start_times[record_id]) * 1000  # ms
                        latencies.append(latency)
        
        except Exception as e:
            print(f"Error during gRPC streaming: {e}")
            errors += 1
        
        end_time = time.perf_counter()
        cpu_end = process.cpu_percent()
        
        # Calculate metrics
        execution_time = end_time - start_time
        throughput = num_records / execution_time
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = final_memory - initial_memory
        cpu_utilization = (cpu_start + cpu_end) / 2
        
        # Calculate latency percentiles
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            """Calculate percentile from sorted data."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        result = BenchmarkResult(
            total_records=num_records,
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            memory_usage_mb=memory_usage,
            cpu_utilization_percent=cpu_utilization,
            errors=errors
        )
        
        return result
    
    async def close(self):
        """Close gRPC channel."""
        if self.channel:
            await self.channel.close()


async def main():
    """Run benchmark suite."""
    # Check if service is running
    print("Checking if service is running...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print("Error: Service health check failed")
                print(f"Status code: {response.status_code}")
                sys.exit(1)
            print("Service is running ✓\n")
    except Exception as e:
        print(f"Error: Cannot connect to service at http://localhost:8000")
        print(f"Details: {e}")
        print("\nPlease start the service with: docker-compose up -d")
        sys.exit(1)
    
    # Initialize benchmarks
    rest_benchmark = StructuredBenchmark(
        base_url="http://localhost:8000",
        system_id="customer_db",
        api_key="test_key"
    )
    
    grpc_benchmark = GRPCBenchmark(
        grpc_host="localhost:50051",
        system_id="customer_db"
    )
    
    try:
        await grpc_benchmark.connect()
        
        # Run multiple benchmark scenarios
        scenarios = [
            (1000, 10),      # 1k records, 10 concurrent
            (10000, 50),     # 10k records, 50 concurrent
            (50000, 100),    # 50k records, 100 concurrent
            (100000, 200),   # 100k records, 200 concurrent
        ]
        
        anonymization_results = []
        deanonymization_results = []
        grpc_results = []
        
        # Run REST anonymization benchmarks
        print(f"\n{'='*60}")
        print("REST ANONYMIZATION BENCHMARKS")
        print(f"{'='*60}")
        
        for num_records, concurrency in scenarios:
            print(f"\n{'='*60}")
            print(f"Scenario: {num_records:,} records, {concurrency} concurrent")
            print(f"{'='*60}")
            
            result = await rest_benchmark.run_benchmark(num_records, concurrency)
            anonymization_results.append(result)
            
            # Print results
            print(f"\nResults:")
            print(f"  Total Records: {result.total_records:,}")
            print(f"  Execution Time: {result.execution_time_seconds:.2f}s")
            print(f"  Throughput: {result.throughput_records_per_sec:,.0f} records/sec")
            print(f"  Latency p50: {result.latency_p50_ms:.2f}ms")
            print(f"  Latency p95: {result.latency_p95_ms:.2f}ms")
            print(f"  Latency p99: {result.latency_p99_ms:.2f}ms")
            print(f"  Latency p999: {result.latency_p999_ms:.2f}ms")
            print(f"  Memory Usage: {result.memory_usage_mb:.2f}MB")
            print(f"  CPU Utilization: {result.cpu_utilization_percent:.1f}%")
            print(f"  Errors: {result.errors}")
            
            # Check if targets met
            print(f"\nTarget Validation:")
            if result.throughput_records_per_sec >= 50000:
                print(f"  ✓ Throughput target met (≥50k records/sec)")
            else:
                print(f"  ✗ Throughput target NOT met (<50k records/sec)")
            
            if result.latency_p95_ms <= 5.0:
                print(f"  ✓ Latency target met (≤5ms p95)")
            else:
                print(f"  ✗ Latency target NOT met (>5ms p95)")
        
        # Run gRPC streaming benchmarks
        print(f"\n{'='*60}")
        print("gRPC STREAMING ANONYMIZATION BENCHMARKS")
        print(f"{'='*60}")
        
        # Use same record counts but without concurrency parameter (streaming handles it)
        grpc_scenarios = [1000, 10000, 50000, 100000]
        
        for num_records in grpc_scenarios:
            print(f"\n{'='*60}")
            print(f"Scenario: {num_records:,} records (bidirectional streaming)")
            print(f"{'='*60}")
            
            result = await grpc_benchmark.run_grpc_streaming_benchmark(num_records)
            grpc_results.append(result)
            
            # Print results
            print(f"\nResults:")
            print(f"  Total Records: {result.total_records:,}")
            print(f"  Execution Time: {result.execution_time_seconds:.2f}s")
            print(f"  Throughput: {result.throughput_records_per_sec:,.0f} records/sec")
            print(f"  Latency p50: {result.latency_p50_ms:.2f}ms")
            print(f"  Latency p95: {result.latency_p95_ms:.2f}ms")
            print(f"  Latency p99: {result.latency_p99_ms:.2f}ms")
            print(f"  Latency p999: {result.latency_p999_ms:.2f}ms")
            print(f"  Memory Usage: {result.memory_usage_mb:.2f}MB")
            print(f"  CPU Utilization: {result.cpu_utilization_percent:.1f}%")
            print(f"  Errors: {result.errors}")
            
            # Check if targets met
            print(f"\nTarget Validation:")
            if result.throughput_records_per_sec >= 50000:
                print(f"  ✓ gRPC throughput target met (≥50k records/sec)")
            else:
                print(f"  ✗ gRPC throughput target NOT met (<50k records/sec)")
            
            if result.latency_p95_ms <= 5.0:
                print(f"  ✓ Latency target met (≤5ms p95)")
            else:
                print(f"  ✗ Latency target NOT met (>5ms p95)")
        
        # Run de-anonymization benchmarks
        print(f"\n{'='*60}")
        print("REST DE-ANONYMIZATION BENCHMARKS")
        print(f"{'='*60}")
        
        for num_records, concurrency in scenarios:
            print(f"\n{'='*60}")
            print(f"Scenario: {num_records:,} records, {concurrency} concurrent")
            print(f"{'='*60}")
            
            result = await rest_benchmark.run_deanonymization_benchmark(num_records, concurrency)
            deanonymization_results.append(result)
            
            # Print results
            print(f"\nResults:")
            print(f"  Total Records: {result.total_records:,}")
            print(f"  Execution Time: {result.execution_time_seconds:.2f}s")
            print(f"  Throughput: {result.throughput_records_per_sec:,.0f} records/sec")
            print(f"  Latency p50: {result.latency_p50_ms:.2f}ms")
            print(f"  Latency p95: {result.latency_p95_ms:.2f}ms")
            print(f"  Latency p99: {result.latency_p99_ms:.2f}ms")
            print(f"  Latency p999: {result.latency_p999_ms:.2f}ms")
            print(f"  Memory Usage: {result.memory_usage_mb:.2f}MB")
            print(f"  CPU Utilization: {result.cpu_utilization_percent:.1f}%")
            print(f"  Errors: {result.errors}")
            
            # Check if targets met
            print(f"\nTarget Validation:")
            if result.latency_p95_ms <= 3.0:
                print(f"  ✓ De-anonymization latency target met (≤3ms p95)")
            else:
                print(f"  ✗ De-anonymization latency target NOT met (>3ms p95)")
        
        # Print comparison summary
        print(f"\n{'='*60}")
        print("REST vs gRPC PERFORMANCE COMPARISON")
        print(f"{'='*60}")
        
        for i, num_records in enumerate(grpc_scenarios):
            if i < len(anonymization_results) and i < len(grpc_results):
                rest_result = anonymization_results[i]
                grpc_result = grpc_results[i]
                
                print(f"\n{num_records:,} records:")
                print(f"  REST Throughput:  {rest_result.throughput_records_per_sec:,.0f} records/sec")
                print(f"  gRPC Throughput:  {grpc_result.throughput_records_per_sec:,.0f} records/sec")
                
                if grpc_result.throughput_records_per_sec > rest_result.throughput_records_per_sec:
                    improvement = ((grpc_result.throughput_records_per_sec / rest_result.throughput_records_per_sec) - 1) * 100
                    print(f"  → gRPC is {improvement:.1f}% faster")
                else:
                    improvement = ((rest_result.throughput_records_per_sec / grpc_result.throughput_records_per_sec) - 1) * 100
                    print(f"  → REST is {improvement:.1f}% faster")
                
                print(f"\n  REST p95 Latency: {rest_result.latency_p95_ms:.2f}ms")
                print(f"  gRPC p95 Latency: {grpc_result.latency_p95_ms:.2f}ms")
        
        # Save results to JSON
        with open("benchmark_results.json", "w") as f:
            json.dump({
                "rest_anonymization": [asdict(r) for r in anonymization_results],
                "grpc_anonymization": [asdict(r) for r in grpc_results],
                "rest_deanonymization": [asdict(r) for r in deanonymization_results]
            }, f, indent=2)
        
        print(f"\n{'='*60}")
        print("Benchmark results saved to benchmark_results.json")
        print(f"{'='*60}")
        
    finally:
        await rest_benchmark.close()
        await grpc_benchmark.close()


if __name__ == "__main__":
    asyncio.run(main())
