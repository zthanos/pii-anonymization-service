#!/usr/bin/env python3
"""
Simplified Concurrent HR Benchmark - No console output, writes to file only
"""

import asyncio
import grpc
import orjson
import time
import sys
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pii_service.proto import pii_service_v2_pb2 as pb2
from src.pii_service.proto import pii_service_v2_pb2_grpc as pb2_grpc


@dataclass
class Config:
    grpc_host: str = "localhost"
    grpc_port: int = 50051
    system_id: str = "hr_system"
    test_data_path: str = "data/test_data/hr_test_data_360k.ndjson"
    batch_size: int = 2000
    num_workers: int = 16
    results_path: str = "data/benchmark_results/hr_concurrent_benchmark.json"
    max_message_length: int = 100 * 1024 * 1024


class Benchmark:
    def __init__(self, config: Config):
        self.config = config
        self.records = []
        self.log_file = open("benchmark_concurrent_log.txt", "w", encoding="utf-8")
    
    def log(self, msg: str):
        """Write to log file"""
        self.log_file.write(msg + "\n")
        self.log_file.flush()
    
    def load_data(self):
        self.log("Loading test data...")
        with open(self.config.test_data_path, 'r') as f:
            for line in f:
                if line.strip():
                    self.records.append(orjson.loads(line))
        self.log(f"Loaded {len(self.records)} records")
    
    async def anonymize_batch(self, stub, batch, batch_id):
        start = time.time()
        items = [pb2.RecordItem(record_id=f"b{batch_id}_r{i}", record_data=orjson.dumps(r)) 
                 for i, r in enumerate(batch)]
        request = pb2.BatchAnonymizeRequest(system_id=self.config.system_id, records=items)
        response = await stub.AnonymizeBatch(request)
        
        # Collect anonymized records for de-anonymization
        anonymized_records = []
        for result in response.results:
            if not result.error:
                anonymized_records.append(orjson.loads(result.anonymized_data))
        
        return response.stats.success_count, response.stats.error_count, time.time() - start, anonymized_records
    
    async def deanonymize_batch(self, stub, batch, batch_id):
        start = time.time()
        items = [pb2.RecordItem(record_id=f"b{batch_id}_r{i}", record_data=orjson.dumps(r)) 
                 for i, r in enumerate(batch)]
        request = pb2.BatchDeanonymizeRequest(system_id=self.config.system_id, records=items)
        response = await stub.DeanonymizeBatch(request)
        return response.stats.success_count, response.stats.error_count, time.time() - start
    
    async def worker_anonymize(self, worker_id, batches):
        options = [
            ('grpc.max_send_message_length', self.config.max_message_length),
            ('grpc.max_receive_message_length', self.config.max_message_length),
        ]
        async with grpc.aio.insecure_channel(
            f"{self.config.grpc_host}:{self.config.grpc_port}", options=options
        ) as channel:
            stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)
            total_success = 0
            total_failed = 0
            all_anonymized = []
            start = time.time()
            for batch_id, batch in enumerate(batches):
                success, failed, _, anonymized = await self.anonymize_batch(stub, batch, batch_id)
                total_success += success
                total_failed += failed
                all_anonymized.extend(anonymized)
            elapsed = time.time() - start
            return worker_id, total_success, total_failed, elapsed, all_anonymized
    
    async def worker_deanonymize(self, worker_id, batches):
        options = [
            ('grpc.max_send_message_length', self.config.max_message_length),
            ('grpc.max_receive_message_length', self.config.max_message_length),
        ]
        async with grpc.aio.insecure_channel(
            f"{self.config.grpc_host}:{self.config.grpc_port}", options=options
        ) as channel:
            stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)
            total_success = 0
            total_failed = 0
            start = time.time()
            for batch_id, batch in enumerate(batches):
                success, failed, _ = await self.deanonymize_batch(stub, batch, batch_id)
                total_success += success
                total_failed += failed
            elapsed = time.time() - start
            return worker_id, total_success, total_failed, elapsed
    
    def split_work(self):
        batches = []
        for i in range(0, len(self.records), self.config.batch_size):
            batches.append(self.records[i:i + self.config.batch_size])
        
        worker_batches = [[] for _ in range(self.config.num_workers)]
        for i, batch in enumerate(batches):
            worker_batches[i % self.config.num_workers].append(batch)
        return worker_batches
    
    async def run(self):
        self.log("=== HR CONCURRENT BENCHMARK ===")
        self.load_data()
        
        worker_batches = self.split_work()
        self.log(f"Workers: {self.config.num_workers}, Batch size: {self.config.batch_size}")
        
        # Anonymization
        self.log("Starting anonymization...")
        start = time.time()
        tasks = [self.worker_anonymize(i, batches) for i, batches in enumerate(worker_batches)]
        anon_results = await asyncio.gather(*tasks)
        anon_time = time.time() - start
        
        anon_success = sum(r[1] for r in anon_results)
        anon_failed = sum(r[2] for r in anon_results)
        anon_throughput = anon_success / anon_time if anon_time > 0 else 0
        
        self.log(f"Anonymization: {anon_time:.2f}s, {anon_throughput:,.0f} rec/sec")
        self.log(f"  Success: {anon_success}, Failed: {anon_failed}")
        
        # Collect all anonymized records from workers
        all_anonymized = []
        for result in anon_results:
            all_anonymized.extend(result[4])  # result[4] is the anonymized records list
        self.log(f"Collected {len(all_anonymized)} anonymized records for de-anonymization")
        
        # Create new batches from anonymized records
        deanon_batches = []
        for i in range(0, len(all_anonymized), self.config.batch_size):
            deanon_batches.append(all_anonymized[i:i + self.config.batch_size])
        
        deanon_worker_batches = [[] for _ in range(self.config.num_workers)]
        for i, batch in enumerate(deanon_batches):
            deanon_worker_batches[i % self.config.num_workers].append(batch)
        
        # De-anonymization
        self.log("Starting de-anonymization...")
        start = time.time()
        tasks = [self.worker_deanonymize(i, batches) for i, batches in enumerate(deanon_worker_batches)]
        deanon_results = await asyncio.gather(*tasks)
        deanon_time = time.time() - start
        
        deanon_success = sum(r[1] for r in deanon_results)
        deanon_failed = sum(r[2] for r in deanon_results)
        deanon_throughput = deanon_success / deanon_time if deanon_time > 0 else 0
        
        self.log(f"De-anonymization: {deanon_time:.2f}s, {deanon_throughput:,.0f} rec/sec")
        self.log(f"  Success: {deanon_success}, Failed: {deanon_failed}")
        
        # Save results
        results = {
            "scenario": {
                "name": "HR Concurrent",
                "total_records": len(self.records),
                "pii_fields": 12,
                "batch_size": self.config.batch_size,
                "num_workers": self.config.num_workers,
            },
            "anonymization": {
                "total_time_seconds": anon_time,
                "throughput": anon_throughput,
                "successful_records": anon_success,
                "failed_records": anon_failed,
            },
            "deanonymization": {
                "total_time_seconds": deanon_time,
                "throughput": deanon_throughput,
                "successful_records": deanon_success,
                "failed_records": deanon_failed,
            },
            "summary": {
                "total_time_seconds": anon_time + deanon_time,
                "anonymization_throughput_rec_per_sec": anon_throughput,
                "deanonymization_throughput_rec_per_sec": deanon_throughput,
            }
        }
        
        Path(self.config.results_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.results_path, 'wb') as f:
            f.write(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        
        self.log(f"Results saved to {self.config.results_path}")
        self.log("=== BENCHMARK COMPLETE ===")
        self.log_file.close()


async def main():
    config = Config()
    benchmark = Benchmark(config)
    try:
        await benchmark.run()
    except Exception as e:
        benchmark.log(f"ERROR: {e}")
        import traceback
        benchmark.log(traceback.format_exc())
        benchmark.log_file.close()


if __name__ == "__main__":
    asyncio.run(main())
