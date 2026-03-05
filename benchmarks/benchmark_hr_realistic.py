#!/usr/bin/env python3
"""
Realistic HR scenario benchmark for PII Anonymization Service.

Tests anonymization and de-anonymization of 360,000 employee records
with 12 properties each, measuring actual time needed for both operations.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import List, Dict, Any
import statistics

import grpc
import orjson

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pii_service.proto import pii_service_v2_pb2, pii_service_v2_pb2_grpc


class HRBenchmark:
    """Benchmark for HR system realistic scenario."""
    
    def __init__(
        self,
        grpc_host: str = "localhost",
        grpc_port: int = 50051,
        system_id: str = "hr_system"
    ):
        self.grpc_host = grpc_host
        self.grpc_port = grpc_port
        self.system_id = system_id
        self.channel = None
        self.stub = None
    
    async def connect(self):
        """Connect to gRPC server."""
        self.channel = grpc.aio.insecure_channel(
            f"{self.grpc_host}:{self.grpc_port}",
            options=[
                ('grpc.max_send_message_length', 100 * 1024 * 1024),
                ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ]
        )
        self.stub = pii_service_v2_pb2_grpc.StructuredAnonymizerV2Stub(self.channel)
        print(f"✅ Connected to gRPC server at {self.grpc_host}:{self.grpc_port}")
    
    async def close(self):
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
    
    def load_test_data(self, file_path: str) -> List[Dict[str, Any]]:
        """Load test data from NDJSON file."""
        print(f"\n📂 Loading test data from {file_path}...")
        records = []
        
        with open(file_path, 'r') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        print(f"✅ Loaded {len(records):,} records")
        return records
    
    async def anonymize_batch(
        self,
        records: List[Dict[str, Any]],
        batch_size: int = 5000
    ) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
        """
        Anonymize records in batches.
        
        Returns:
            (anonymized_records, total_time_seconds, stats)
        """
        print(f"\n🔒 Starting anonymization...")
        print(f"  Total records: {len(records):,}")
        print(f"  Batch size: {batch_size:,}")
        print(f"  System ID: {self.system_id}")
        
        anonymized_records = []
        batch_times = []
        total_start = time.time()
        
        # Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_start = time.time()
            
            # Create batch request
            record_items = []
            for idx, record in enumerate(batch):
                record_items.append(
                    pii_service_v2_pb2.RecordItem(
                        record_id=str(i + idx),
                        record_data=orjson.dumps(record)
                    )
                )
            
            request = pii_service_v2_pb2.BatchAnonymizeRequest(
                system_id=self.system_id,
                records=record_items
            )
            
            # Send request and get response
            response = await self.stub.AnonymizeBatch(request)
            
            # Parse responses
            for result in response.results:
                if result.error:
                    print(f"❌ Error in record {result.record_id}: {result.error}")
                else:
                    anonymized_records.append(orjson.loads(result.anonymized_data))
            
            batch_time = time.time() - batch_start
            batch_times.append(batch_time)
            
            # Progress update
            processed = min(i + batch_size, len(records))
            throughput = len(batch) / batch_time
            print(f"  Progress: {processed:,}/{len(records):,} ({processed/len(records)*100:.1f}%) - "
                  f"Batch time: {batch_time:.2f}s - Throughput: {throughput:,.0f} rec/sec")
        
        total_time = time.time() - total_start
        
        # Calculate statistics
        stats = {
            "total_records": len(records),
            "successful_records": len(anonymized_records),
            "failed_records": len(records) - len(anonymized_records),
            "total_time_seconds": total_time,
            "total_time_formatted": self._format_time(total_time),
            "average_throughput": len(records) / total_time,
            "batch_times": {
                "min": min(batch_times),
                "max": max(batch_times),
                "mean": statistics.mean(batch_times),
                "median": statistics.median(batch_times),
            },
            "batch_throughputs": {
                "min": batch_size / max(batch_times),
                "max": batch_size / min(batch_times),
                "mean": batch_size / statistics.mean(batch_times),
            }
        }
        
        print(f"\n✅ Anonymization complete!")
        print(f"  Total time: {stats['total_time_formatted']}")
        print(f"  Average throughput: {stats['average_throughput']:,.0f} records/sec")
        print(f"  Successful: {stats['successful_records']:,}")
        print(f"  Failed: {stats['failed_records']:,}")
        
        return anonymized_records, total_time, stats
    
    async def deanonymize_batch(
        self,
        records: List[Dict[str, Any]],
        batch_size: int = 5000
    ) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
        """
        De-anonymize records in batches.
        
        Returns:
            (deanonymized_records, total_time_seconds, stats)
        """
        print(f"\n🔓 Starting de-anonymization...")
        print(f"  Total records: {len(records):,}")
        print(f"  Batch size: {batch_size:,}")
        print(f"  System ID: {self.system_id}")
        
        deanonymized_records = []
        batch_times = []
        total_start = time.time()
        
        # Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_start = time.time()
            
            # Create batch request
            record_items = []
            for idx, record in enumerate(batch):
                record_items.append(
                    pii_service_v2_pb2.RecordItem(
                        record_id=str(i + idx),
                        record_data=orjson.dumps(record)
                    )
                )
            
            request = pii_service_v2_pb2.BatchDeanonymizeRequest(
                system_id=self.system_id,
                records=record_items
            )
            
            # Send request and get response
            response = await self.stub.DeanonymizeBatch(request)
            
            # Parse responses
            for result in response.results:
                if result.error:
                    print(f"❌ Error in record {result.record_id}: {result.error}")
                else:
                    deanonymized_records.append(orjson.loads(result.deanonymized_data))
            
            batch_time = time.time() - batch_start
            batch_times.append(batch_time)
            
            # Progress update
            processed = min(i + batch_size, len(records))
            throughput = len(batch) / batch_time
            print(f"  Progress: {processed:,}/{len(records):,} ({processed/len(records)*100:.1f}%) - "
                  f"Batch time: {batch_time:.2f}s - Throughput: {throughput:,.0f} rec/sec")
        
        total_time = time.time() - total_start
        
        # Calculate statistics
        stats = {
            "total_records": len(records),
            "successful_records": len(deanonymized_records),
            "failed_records": len(records) - len(deanonymized_records),
            "total_time_seconds": total_time,
            "total_time_formatted": self._format_time(total_time),
            "average_throughput": len(records) / total_time,
            "batch_times": {
                "min": min(batch_times),
                "max": max(batch_times),
                "mean": statistics.mean(batch_times),
                "median": statistics.median(batch_times),
            },
            "batch_throughputs": {
                "min": batch_size / max(batch_times),
                "max": batch_size / min(batch_times),
                "mean": batch_size / statistics.mean(batch_times),
            }
        }
        
        print(f"\n✅ De-anonymization complete!")
        print(f"  Total time: {stats['total_time_formatted']}")
        print(f"  Average throughput: {stats['average_throughput']:,.0f} records/sec")
        print(f"  Successful: {stats['successful_records']:,}")
        print(f"  Failed: {stats['failed_records']:,}")
        
        return deanonymized_records, total_time, stats
    
    def verify_reversibility(
        self,
        original: List[Dict[str, Any]],
        deanonymized: List[Dict[str, Any]],
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """Verify that de-anonymization correctly restores original data."""
        print(f"\n🔍 Verifying data reversibility...")
        print(f"  Checking {sample_size} random samples...")
        
        if len(original) != len(deanonymized):
            print(f"❌ Record count mismatch: {len(original)} vs {len(deanonymized)}")
            return {"success": False, "error": "Record count mismatch"}
        
        # Check random samples
        import random
        samples = random.sample(range(len(original)), min(sample_size, len(original)))
        
        mismatches = []
        for idx in samples:
            orig = original[idx]
            deanon = deanonymized[idx]
            
            # Remove _pii_anonymized field if present
            deanon_clean = {k: v for k, v in deanon.items() if k != "_pii_anonymized"}
            
            if orig != deanon_clean:
                mismatches.append({
                    "index": idx,
                    "original": orig,
                    "deanonymized": deanon_clean
                })
        
        if mismatches:
            print(f"❌ Found {len(mismatches)} mismatches in {sample_size} samples")
            print(f"  First mismatch at index {mismatches[0]['index']}:")
            print(f"    Original: {mismatches[0]['original']}")
            print(f"    De-anonymized: {mismatches[0]['deanonymized']}")
            return {"success": False, "mismatches": len(mismatches), "sample_size": sample_size}
        
        print(f"✅ All {sample_size} samples match perfectly!")
        print(f"  Data reversibility: 100%")
        return {"success": True, "verified_samples": sample_size}
    
    def _format_time(self, seconds: float) -> str:
        """Format time in human-readable format."""
        if seconds < 60:
            return f"{seconds:.2f} seconds"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes} minutes {secs:.2f} seconds"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours} hours {minutes} minutes {secs:.2f} seconds"
    
    def save_results(
        self,
        results: Dict[str, Any],
        output_file: str = "data/benchmark_results/hr_realistic_benchmark.json"
    ):
        """Save benchmark results to file."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Results saved to {output_file}")


async def main():
    """Run HR realistic scenario benchmark."""
    print("=" * 80)
    print("HR REALISTIC SCENARIO BENCHMARK")
    print("=" * 80)
    print("\nScenario:")
    print("  - 360,000 employee records")
    print("  - 12 properties per record (employee_id, ssn, email, phone, names, etc.)")
    print("  - PII fields: employee_id, ssn, email, phone, first_name, last_name,")
    print("                date_of_birth, salary, bank_account, position, department,")
    print("                emergency_contact")
    print("  - Batch size: 5,000 records")
    print("  - System: hr_system")
    
    # Initialize benchmark
    benchmark = HRBenchmark()
    
    try:
        # Connect to service
        await benchmark.connect()
        
        # Load test data
        test_data_file = "data/test_data/hr_test_data_360k.ndjson"
        if not Path(test_data_file).exists():
            print(f"\n❌ Test data file not found: {test_data_file}")
            print("   Please run: python scripts/generate_hr_test_data.py")
            return
        
        original_records = benchmark.load_test_data(test_data_file)
        
        # Run anonymization benchmark
        anonymized_records, anon_time, anon_stats = await benchmark.anonymize_batch(
            original_records,
            batch_size=5000
        )
        
        # Run de-anonymization benchmark
        deanonymized_records, deanon_time, deanon_stats = await benchmark.deanonymize_batch(
            anonymized_records,
            batch_size=5000
        )
        
        # Verify reversibility
        verification = benchmark.verify_reversibility(
            original_records,
            deanonymized_records,
            sample_size=100
        )
        
        # Compile results
        results = {
            "scenario": {
                "name": "HR Realistic Scenario",
                "total_records": len(original_records),
                "properties_per_record": 12,
                "pii_fields": 12,
                "system_id": "hr_system",
                "batch_size": 5000
            },
            "anonymization": anon_stats,
            "deanonymization": deanon_stats,
            "verification": verification,
            "summary": {
                "total_time_seconds": anon_time + deanon_time,
                "total_time_formatted": benchmark._format_time(anon_time + deanon_time),
                "anonymization_time": benchmark._format_time(anon_time),
                "deanonymization_time": benchmark._format_time(deanon_time),
                "data_integrity": "100%" if verification["success"] else "FAILED"
            }
        }
        
        # Print summary
        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)
        print(f"\n📊 Total Records: {len(original_records):,}")
        print(f"📊 Properties per Record: 12")
        print(f"📊 PII Fields: 12")
        print(f"\n⏱️  Anonymization Time: {results['summary']['anonymization_time']}")
        print(f"⚡ Anonymization Throughput: {anon_stats['average_throughput']:,.0f} records/sec")
        print(f"\n⏱️  De-anonymization Time: {results['summary']['deanonymization_time']}")
        print(f"⚡ De-anonymization Throughput: {deanon_stats['average_throughput']:,.0f} records/sec")
        print(f"\n⏱️  Total Time: {results['summary']['total_time_formatted']}")
        print(f"✅ Data Integrity: {results['summary']['data_integrity']}")
        
        # Save results
        benchmark.save_results(results)
        
        print("\n" + "=" * 80)
        print("✅ BENCHMARK COMPLETE")
        print("=" * 80)
        
    finally:
        await benchmark.close()


if __name__ == "__main__":
    asyncio.run(main())
