#!/usr/bin/env python3
"""Test different batch sizes to find optimal performance."""

import subprocess
import time
import json
import sys
from pathlib import Path

# Batch sizes to test
BATCH_SIZES = [50, 100, 200, 500]

# Test data file
TEST_FILE = "data/test_data/test_data_10k.ndjson"

# Results
results = []

print("=" * 60)
print("Batch Size Optimization Test")
print("=" * 60)
print(f"Test file: {TEST_FILE}")
print(f"Batch sizes: {BATCH_SIZES}")
print("=" * 60)
print()

for batch_size in BATCH_SIZES:
    print(f"Testing batch_size={batch_size}...")
    print("-" * 60)
    
    # Update .env file with new batch size
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r") as f:
            lines = f.readlines()
        
        # Update or add GRPC_BATCH_SIZE
        found = False
        for i, line in enumerate(lines):
            if line.startswith("GRPC_BATCH_SIZE="):
                lines[i] = f"GRPC_BATCH_SIZE={batch_size}\n"
                found = True
                break
        
        if not found:
            lines.append(f"GRPC_BATCH_SIZE={batch_size}\n")
        
        with open(env_file, "w") as f:
            f.writelines(lines)
    
    # Restart service
    print(f"  Restarting service with batch_size={batch_size}...")
    subprocess.run(["docker-compose", "down"], 
                   stdout=subprocess.DEVNULL, 
                   stderr=subprocess.DEVNULL)
    subprocess.run(["docker-compose", "up", "-d", "--build"], 
                   stdout=subprocess.DEVNULL, 
                   stderr=subprocess.DEVNULL)
    
    # Wait for service to be ready
    print("  Waiting for service to be ready...")
    time.sleep(15)
    
    # Run benchmark
    print("  Running benchmark...")
    result_file = f"results_batch_{batch_size}.json"
    
    try:
        result = subprocess.run(
            [
                "uv", "run", "python", "scripts/benchmark_grpc.py",
                "-i", TEST_FILE,
                "-o", "anonymize",
                "--results-json", result_file
            ],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Parse results
        if Path(result_file).exists():
            with open(result_file, "r") as f:
                data = json.load(f)
                
                results.append({
                    "batch_size": batch_size,
                    "throughput": data.get("throughput_records_per_sec", 0),
                    "latency_p95": data.get("latency_p95_ms", 0),
                    "execution_time": data.get("execution_time_seconds", 0),
                    "success_rate": data.get("success_rate_percent", 0)
                })
                
                print(f"  ✓ Throughput: {data.get('throughput_records_per_sec', 0):.2f} records/sec")
                print(f"  ✓ Latency p95: {data.get('latency_p95_ms', 0):.2f} ms")
        else:
            print(f"  ✗ Benchmark failed - no results file")
            results.append({
                "batch_size": batch_size,
                "throughput": 0,
                "latency_p95": 0,
                "execution_time": 0,
                "success_rate": 0,
                "error": "No results file"
            })
    
    except subprocess.TimeoutExpired:
        print(f"  ✗ Benchmark timed out")
        results.append({
            "batch_size": batch_size,
            "throughput": 0,
            "latency_p95": 0,
            "execution_time": 0,
            "success_rate": 0,
            "error": "Timeout"
        })
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append({
            "batch_size": batch_size,
            "throughput": 0,
            "latency_p95": 0,
            "execution_time": 0,
            "success_rate": 0,
            "error": str(e)
        })
    
    print()

# Print summary
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print()
print(f"{'Batch Size':<12} {'Throughput':<20} {'Latency p95':<15} {'Improvement'}")
print("-" * 60)

baseline_throughput = results[0]["throughput"] if results else 0

for r in results:
    improvement = ""
    if baseline_throughput > 0 and r["throughput"] > 0:
        improvement = f"{r['throughput'] / baseline_throughput:.2f}x"
    
    print(f"{r['batch_size']:<12} {r['throughput']:<20.2f} {r['latency_p95']:<15.2f} {improvement}")

print()

# Find best configuration
best = max(results, key=lambda x: x["throughput"])
print(f"Best configuration: batch_size={best['batch_size']}")
print(f"Best throughput: {best['throughput']:.2f} records/sec")
print()

# Save detailed results
with open("data/benchmark_results/batch_size_optimization_results.json", "w") as f:
    json.dump({
        "test_file": TEST_FILE,
        "results": results,
        "best_config": best
    }, f, indent=2)

print("Detailed results saved to: data/benchmark_results/batch_size_optimization_results.json")
print("=" * 60)
