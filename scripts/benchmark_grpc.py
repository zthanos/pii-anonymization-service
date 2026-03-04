#!/usr/bin/env python3
"""
gRPC Benchmark Script for PII Anonymization Service

This script benchmarks gRPC streaming performance with large datasets.
Supports loading data from files and measuring throughput/latency.
"""

import asyncio
import json
import time
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, AsyncIterator
from dataclasses import dataclass, asdict
import grpc

# Add proto directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pii_service.proto import pii_service_pb2
from pii_service.proto import pii_service_pb2_grpc


@dataclass
class BenchmarkResult:
    """Benchmark execution results."""
    operation: str
    total_records: int
    execution_time_seconds: float
    throughput_records_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_p999_ms: float
    errors: int
    success_rate: float


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
        # Configure channel options for high throughput
        options = [
            ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.http2.max_pings_without_data', 0),
            ('grpc.keepalive_permit_without_calls', 1),
        ]
        
        self.channel = grpc.aio.insecure_channel(self.grpc_host, options=options)
        self.stub = pii_service_pb2_grpc.StructuredAnonymizerStub(self.channel)
        
        # Wait for channel to be ready
        await self.channel.channel_ready()
        print(f"✓ Connected to gRPC server at {self.grpc_host}")
    
    def load_records_from_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Load records from JSON or NDJSON file.
        
        Args:
            file_path: Path to data file
            
        Returns:
            List of records
        """
        print(f"Loading records from {file_path}...")
        records = []
        
        with open(file_path, 'r') as f:
            if file_path.suffix == '.ndjson':
                # NDJSON format
                for i, line in enumerate(f):
                    if line.strip():
                        records.append(json.loads(line))
                    if (i + 1) % 100000 == 0:
                        print(f"  Loaded {i + 1:,} records...", end='\r')
            else:
                # JSON array format
                records = json.load(f)
        
        print(f"  Loaded {len(records):,} records... Done!")
        return records
    
    async def request_generator(
        self, 
        records: List[Dict[str, Any]]
    ) -> AsyncIterator[pii_service_pb2.AnonymizeRequest]:
        """
        Generate requests to send to server.
        
        Args:
            records: List of records to anonymize
            
        Yields:
            AnonymizeRequest messages
        """
        for i, record in enumerate(records):
            request = pii_service_pb2.AnonymizeRequest(
                system_id=self.system_id,
                record_id=str(i),
                record_json=json.dumps(record)
            )
            yield request
    
    async def deanonymize_request_generator(
        self, 
        records: List[Dict[str, Any]]
    ) -> AsyncIterator[pii_service_pb2.DeanonymizeRequest]:
        """
        Generate de-anonymization requests.
        
        Args:
            records: List of anonymized records
            
        Yields:
            DeanonymizeRequest messages
        """
        for i, record in enumerate(records):
            request = pii_service_pb2.DeanonymizeRequest(
                system_id=self.system_id,
                record_id=str(i),
                record_json=json.dumps(record)
            )
            yield request
    
    async def benchmark_anonymize(
        self, 
        records: List[Dict[str, Any]],
        save_output: Path = None
    ) -> BenchmarkResult:
        """
        Benchmark anonymization with gRPC streaming.
        
        Args:
            records: List of records to anonymize
            save_output: Optional path to save anonymized records
            
        Returns:
            BenchmarkResult with metrics
        """
        print(f"\nStarting anonymization benchmark...")
        print(f"  Records: {len(records):,}")
        print(f"  System ID: {self.system_id}")
        
        latencies: List[float] = []
        errors = 0
        anonymized_records = []
        
        # Track start times for each record
        record_start_times = {}
        
        print("\nSending requests...")
        start_time = time.perf_counter()
        
        try:
            # Start bidirectional streaming
            response_stream = self.stub.Anonymize(
                self.request_generator(records)
            )
            
            # Mark all records as sent (for latency calculation)
            send_time = time.perf_counter()
            for i in range(len(records)):
                record_start_times[str(i)] = send_time
            
            # Process responses
            response_count = 0
            async for response in response_stream:
                response_count += 1
                record_id = response.record_id
                end_time = time.perf_counter()
                
                if response.error:
                    errors += 1
                else:
                    # Calculate latency for this record
                    if record_id in record_start_times:
                        latency = (end_time - record_start_times[record_id]) * 1000  # ms
                        latencies.append(latency)
                    
                    # Save anonymized record if requested
                    if save_output:
                        anonymized_records.append(json.loads(response.anonymized_json))
                
                # Progress indicator
                if response_count % 10000 == 0:
                    elapsed = end_time - start_time
                    current_throughput = response_count / elapsed
                    print(f"  Processed {response_count:,} / {len(records):,} records "
                          f"({current_throughput:,.0f} records/sec)...", end='\r')
        
        except Exception as e:
            print(f"\n✗ Error during streaming: {e}")
            errors += 1
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        print(f"\n  Processed {len(records):,} / {len(records):,} records... Done!")
        
        # Save anonymized records if requested
        if save_output and anonymized_records:
            print(f"\nSaving anonymized records to {save_output}...")
            with open(save_output, 'w') as f:
                for record in anonymized_records:
                    f.write(json.dumps(record) + '\n')
            print(f"  Saved {len(anonymized_records):,} records")
        
        # Calculate metrics
        throughput = len(records) / execution_time
        success_rate = ((len(records) - errors) / len(records)) * 100
        
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
            operation="anonymize",
            total_records=len(records),
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            errors=errors,
            success_rate=success_rate
        )
        
        return result
    
    async def benchmark_deanonymize(
        self, 
        records: List[Dict[str, Any]]
    ) -> BenchmarkResult:
        """
        Benchmark de-anonymization with gRPC streaming.
        
        Args:
            records: List of anonymized records to de-anonymize
            
        Returns:
            BenchmarkResult with metrics
        """
        print(f"\nStarting de-anonymization benchmark...")
        print(f"  Records: {len(records):,}")
        print(f"  System ID: {self.system_id}")
        
        latencies: List[float] = []
        errors = 0
        
        # Track start times for each record
        record_start_times = {}
        
        print("\nSending requests...")
        start_time = time.perf_counter()
        
        try:
            # Start bidirectional streaming
            response_stream = self.stub.Deanonymize(
                self.deanonymize_request_generator(records)
            )
            
            # Mark all records as sent
            send_time = time.perf_counter()
            for i in range(len(records)):
                record_start_times[str(i)] = send_time
            
            # Process responses
            response_count = 0
            async for response in response_stream:
                response_count += 1
                record_id = response.record_id
                end_time = time.perf_counter()
                
                if response.error:
                    errors += 1
                else:
                    # Calculate latency
                    if record_id in record_start_times:
                        latency = (end_time - record_start_times[record_id]) * 1000  # ms
                        latencies.append(latency)
                
                # Progress indicator
                if response_count % 10000 == 0:
                    elapsed = end_time - start_time
                    current_throughput = response_count / elapsed
                    print(f"  Processed {response_count:,} / {len(records):,} records "
                          f"({current_throughput:,.0f} records/sec)...", end='\r')
        
        except Exception as e:
            print(f"\n✗ Error during streaming: {e}")
            errors += 1
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        print(f"\n  Processed {len(records):,} / {len(records):,} records... Done!")
        
        # Calculate metrics
        throughput = len(records) / execution_time
        success_rate = ((len(records) - errors) / len(records)) * 100
        
        # Calculate latency percentiles
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        result = BenchmarkResult(
            operation="deanonymize",
            total_records=len(records),
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            errors=errors,
            success_rate=success_rate
        )
        
        return result
    
    async def close(self):
        """Close gRPC channel."""
        if self.channel:
            await self.channel.close()


def print_result(result: BenchmarkResult):
    """Print benchmark result in formatted table."""
    print("\n" + "=" * 70)
    print(f"BENCHMARK RESULTS - {result.operation.upper()}")
    print("=" * 70)
    print(f"Total Records:        {result.total_records:,}")
    print(f"Execution Time:       {result.execution_time_seconds:.2f} seconds")
    print(f"Throughput:           {result.throughput_records_per_sec:,.0f} records/sec")
    print(f"Success Rate:         {result.success_rate:.2f}%")
    print(f"Errors:               {result.errors:,}")
    print()
    print("Latency Percentiles:")
    print(f"  p50:                {result.latency_p50_ms:.2f} ms")
    print(f"  p95:                {result.latency_p95_ms:.2f} ms")
    print(f"  p99:                {result.latency_p99_ms:.2f} ms")
    print(f"  p999:               {result.latency_p999_ms:.2f} ms")
    print()
    
    # Check targets
    print("Target Validation:")
    if result.throughput_records_per_sec >= 50000:
        print(f"  ✓ Throughput target met (≥50k records/sec)")
    else:
        print(f"  ✗ Throughput target NOT met (<50k records/sec)")
    
    if result.operation == "anonymize":
        if result.latency_p95_ms <= 5.0:
            print(f"  ✓ Latency target met (≤5ms p95)")
        else:
            print(f"  ✗ Latency target NOT met (>5ms p95)")
    else:  # deanonymize
        if result.latency_p95_ms <= 3.0:
            print(f"  ✓ De-anonymization latency target met (≤3ms p95)")
        else:
            print(f"  ✗ De-anonymization latency target NOT met (>3ms p95)")
    
    print("=" * 70)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="gRPC benchmark for PII anonymization service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark anonymization with 1M records
  python benchmark_grpc.py -i test_data_1m.ndjson -o anonymize
  
  # Benchmark both anonymization and de-anonymization
  python benchmark_grpc.py -i test_data_1m.ndjson -o both --save-anonymized anonymized_1m.ndjson
  
  # Use custom gRPC host and system ID
  python benchmark_grpc.py -i data.ndjson -o anonymize --host localhost:50051 --system-id analytics_db
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input data file (JSON or NDJSON)'
    )
    
    parser.add_argument(
        '-o', '--operation',
        type=str,
        choices=['anonymize', 'deanonymize', 'both'],
        default='anonymize',
        help='Operation to benchmark (default: anonymize)'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='localhost:50051',
        help='gRPC server address (default: localhost:50051)'
    )
    
    parser.add_argument(
        '--system-id',
        type=str,
        default='customer_db',
        help='System identifier (default: customer_db)'
    )
    
    parser.add_argument(
        '--save-anonymized',
        type=str,
        help='Save anonymized records to file (NDJSON)'
    )
    
    parser.add_argument(
        '--results-json',
        type=str,
        help='Save results to JSON file'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Initialize benchmark
    benchmark = GRPCBenchmark(
        grpc_host=args.host,
        system_id=args.system_id
    )
    
    try:
        # Connect to server
        print("Connecting to gRPC server...")
        await benchmark.connect()
        
        # Load data
        records = benchmark.load_records_from_file(input_path)
        
        results = {}
        
        # Run anonymization benchmark
        if args.operation in ['anonymize', 'both']:
            save_path = Path(args.save_anonymized) if args.save_anonymized else None
            result = await benchmark.benchmark_anonymize(records, save_path)
            print_result(result)
            results['anonymize'] = asdict(result)
            
            # If running both, use anonymized records for de-anonymization
            if args.operation == 'both':
                if save_path and save_path.exists():
                    anonymized_records = benchmark.load_records_from_file(save_path)
                else:
                    print("\n⚠ Warning: Cannot run de-anonymization without saved anonymized records")
                    print("  Use --save-anonymized to save anonymized records")
                    anonymized_records = None
                
                if anonymized_records:
                    result = await benchmark.benchmark_deanonymize(anonymized_records)
                    print_result(result)
                    results['deanonymize'] = asdict(result)
        
        elif args.operation == 'deanonymize':
            # Assume input file contains anonymized records
            result = await benchmark.benchmark_deanonymize(records)
            print_result(result)
            results['deanonymize'] = asdict(result)
        
        # Save results to JSON if requested
        if args.results_json:
            results_path = Path(args.results_json)
            with open(results_path, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n✓ Results saved to {results_path}")
    
    finally:
        await benchmark.close()


if __name__ == "__main__":
    asyncio.run(main())
