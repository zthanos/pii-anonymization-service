# PII Anonymization Service - Benchmarking Guide

This guide explains how to generate test data and run performance benchmarks for the PII Anonymization Service.

## Table of Contents

- [Quick Start](#quick-start)
- [Generating Test Data](#generating-test-data)
- [Running gRPC Benchmarks](#running-grpc-benchmarks)
- [Performance Targets](#performance-targets)
- [Interpreting Results](#interpreting-results)
- [Troubleshooting](#troubleshooting)

## Quick Start

```bash
# 1. Start the service
docker-compose up -d

# 2. Generate 1 million test records
uv run python scripts/generate_test_data.py -n 1000000 -o test_data_1m.ndjson

# 3. Run gRPC anonymization benchmark
uv run python scripts/benchmark_grpc.py -i test_data_1m.ndjson -o anonymize --save-anonymized anonymized_1m.ndjson

# 4. Run gRPC de-anonymization benchmark
uv run python scripts/benchmark_grpc.py -i anonymized_1m.ndjson -o deanonymize

# 5. Or run both in sequence
uv run python scripts/benchmark_grpc.py -i test_data_1m.ndjson -o both --save-anonymized anonymized_1m.ndjson
```

## Generating Test Data

The `generate_test_data.py` script creates realistic PII records for benchmarking.

### Basic Usage

```bash
# Generate 1 million records (NDJSON format, memory efficient)
uv run python scripts/generate_test_data.py -n 1000000 -o test_data_1m.ndjson

# Generate 10k records (JSON array format)
uv run python scripts/generate_test_data.py -n 10000 -o test_data_10k.json -f json

# Use custom seed for reproducibility
uv run python scripts/generate_test_data.py -n 100000 -o test_data.ndjson -s 12345
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `-n, --num-records` | Number of records to generate (required) | - |
| `-o, --output` | Output file path (required) | - |
| `-f, --format` | Output format: `json` or `ndjson` | `ndjson` |
| `-s, --seed` | Random seed for reproducibility | `42` |
| `--batch-size` | Generate in batches (loads in memory) | None (streaming) |

### Output Formats

**NDJSON (Recommended for large datasets)**:
- Newline-delimited JSON
- Memory efficient (streaming)
- One record per line
- Ideal for 100k+ records

**JSON**:
- Standard JSON array
- Loads entire dataset in memory
- Better for small datasets (<100k records)

### Generated Record Structure

Each record contains realistic PII matching the service policy:

```json
{
  "email": "john.smith@example.com",
  "name": "John Smith",
  "ssn": "123-45-6789",
  "address": {
    "street": "123 Main St",
    "city": "San Francisco",
    "state": "CA",
    "zip": "94102"
  },
  "phone": "+1-555-1234",
  "user_id": "user_0000000001",
  "account_type": "premium",
  "status": "active",
  "created_at": "2024-03-15"
}
```

### Performance

Generation speed: ~100,000 records/second

| Records | File Size | Generation Time |
|---------|-----------|-----------------|
| 10,000 | ~5 MB | ~0.1 seconds |
| 100,000 | ~50 MB | ~1 second |
| 1,000,000 | ~500 MB | ~10 seconds |

## Running gRPC Benchmarks

The `benchmark_grpc.py` script measures gRPC streaming performance.

### Basic Usage

```bash
# Anonymization benchmark
uv run python scripts/benchmark_grpc.py \
  -i test_data_1m.ndjson \
  -o anonymize \
  --save-anonymized anonymized_1m.ndjson

# De-anonymization benchmark
uv run python scripts/benchmark_grpc.py \
  -i anonymized_1m.ndjson \
  -o deanonymize

# Both operations in sequence
uv run python scripts/benchmark_grpc.py \
  -i test_data_1m.ndjson \
  -o both \
  --save-anonymized anonymized_1m.ndjson \
  --results-json benchmark_results.json
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `-i, --input` | Input data file (JSON or NDJSON) (required) | - |
| `-o, --operation` | Operation: `anonymize`, `deanonymize`, or `both` | `anonymize` |
| `--host` | gRPC server address | `localhost:50051` |
| `--system-id` | System identifier for policy lookup | `customer_db` |
| `--save-anonymized` | Save anonymized records to file (NDJSON) | None |
| `--results-json` | Save results to JSON file | None |

### Example Workflows

**1. Full Benchmark Suite (1M records)**

```bash
# Generate data
uv run python scripts/generate_test_data.py -n 1000000 -o data_1m.ndjson

# Run both operations
uv run python scripts/benchmark_grpc.py \
  -i data_1m.ndjson \
  -o both \
  --save-anonymized anonymized_1m.ndjson \
  --results-json results_1m.json
```

**2. Incremental Testing**

```bash
# Test with increasing dataset sizes
for n in 10000 100000 500000 1000000; do
  echo "Testing with $n records..."
  uv run python scripts/generate_test_data.py -n $n -o data_${n}.ndjson
  uv run python scripts/benchmark_grpc.py \
    -i data_${n}.ndjson \
    -o anonymize \
    --results-json results_${n}.json
done
```

**3. Different System IDs**

```bash
# Test with different policy configurations
uv run python scripts/benchmark_grpc.py \
  -i test_data.ndjson \
  -o anonymize \
  --system-id analytics_db
```

## Performance Targets

The service is designed to meet these performance targets:

### Throughput
- **Target**: ≥50,000 records/second via gRPC streaming
- **Measurement**: Total records / execution time

### Latency (Anonymization)
- **Target**: ≤5ms p95 latency
- **Measurement**: 95th percentile of per-record latency

### Latency (De-anonymization)
- **Target**: ≤3ms p95 latency
- **Measurement**: 95th percentile of per-record latency

### Success Rate
- **Target**: ≥99.9% success rate
- **Measurement**: (Total records - errors) / total records

## Interpreting Results

### Sample Output

```
======================================================================
BENCHMARK RESULTS - ANONYMIZE
======================================================================
Total Records:        1,000,000
Execution Time:       18.45 seconds
Throughput:           54,200 records/sec
Success Rate:         100.00%
Errors:               0

Latency Percentiles:
  p50:                2.15 ms
  p95:                4.32 ms
  p99:                6.78 ms
  p999:               12.45 ms

Target Validation:
  ✓ Throughput target met (≥50k records/sec)
  ✓ Latency target met (≤5ms p95)
======================================================================
```

### Key Metrics Explained

**Throughput (records/sec)**:
- Measures overall processing speed
- Higher is better
- Affected by: network latency, Redis performance, CPU

**Latency Percentiles**:
- p50 (median): Half of requests complete faster
- p95: 95% of requests complete faster (target metric)
- p99: 99% of requests complete faster
- p999: 99.9% of requests complete faster

**Success Rate**:
- Percentage of records processed without errors
- Should be >99.9% for production use
- Errors may indicate: Redis connectivity issues, policy misconfigurations

### Performance Analysis

**Good Performance**:
```
Throughput: 50,000+ records/sec
p95 Latency: <5ms (anonymize), <3ms (deanonymize)
Success Rate: >99.9%
```

**Needs Optimization**:
```
Throughput: <50,000 records/sec
p95 Latency: >5ms (anonymize), >3ms (deanonymize)
Success Rate: <99.9%
```

### Optimization Tips

**If throughput is low**:
1. Check Redis connection pool size (default: 50)
2. Verify network latency between service and Redis
3. Monitor CPU utilization
4. Consider horizontal scaling

**If latency is high**:
1. Check Redis performance (use `redis-cli --latency`)
2. Verify encryption key resolution is cached
3. Monitor memory usage
4. Check for network congestion

**If success rate is low**:
1. Check Redis connectivity and health
2. Verify policy configuration is valid
3. Check service logs for errors
4. Monitor Redis memory usage

## Troubleshooting

### Service Not Running

```bash
# Check service status
docker-compose ps

# Start service
docker-compose up -d

# Check logs
docker-compose logs -f pii-service
```

### Connection Refused

```bash
# Verify gRPC port is exposed
docker-compose ps pii-service

# Check if port 50051 is listening
netstat -an | grep 50051

# Test connectivity
grpcurl -plaintext localhost:50051 list
```

### Out of Memory

For very large datasets (>1M records), ensure sufficient memory:

```bash
# Check available memory
free -h

# Monitor memory during benchmark
watch -n 1 'docker stats pii-service --no-stream'
```

### Redis Connection Issues

```bash
# Check Redis health
docker exec pii-redis redis-cli -a redis_dev_password PING

# Check Redis memory
docker exec pii-redis redis-cli -a redis_dev_password INFO memory

# Check Redis connections
docker exec pii-redis redis-cli -a redis_dev_password CLIENT LIST
```

### Slow Performance

```bash
# Check Redis latency
docker exec pii-redis redis-cli -a redis_dev_password --latency

# Monitor service CPU/memory
docker stats pii-service

# Check service logs for errors
docker-compose logs pii-service | grep -i error
```

## Advanced Usage

### Custom Benchmark Scenarios

Create custom test data with specific patterns:

```python
# custom_data_generator.py
import json

def generate_custom_record(i):
    return {
        "email": f"test{i}@example.com",
        "name": f"Test User {i}",
        "ssn": f"{i:09d}",
        # ... custom fields
    }

with open('custom_data.ndjson', 'w') as f:
    for i in range(1000000):
        f.write(json.dumps(generate_custom_record(i)) + '\n')
```

### Parallel Benchmarks

Run multiple benchmarks in parallel:

```bash
# Terminal 1
uv run python scripts/benchmark_grpc.py -i data1.ndjson -o anonymize

# Terminal 2
uv run python scripts/benchmark_grpc.py -i data2.ndjson -o anonymize

# Monitor combined throughput
docker stats pii-service
```

### Continuous Benchmarking

Set up automated benchmarking:

```bash
#!/bin/bash
# continuous_benchmark.sh

while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  uv run python scripts/benchmark_grpc.py \
    -i test_data_1m.ndjson \
    -o anonymize \
    --results-json "results_${timestamp}.json"
  
  sleep 300  # Run every 5 minutes
done
```

## See Also

- [README.md](README.md) - Service overview and setup
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [openapi.yaml](openapi.yaml) - API specification
- [DEPLOYMENT_TEST_RESULTS.md](DEPLOYMENT_TEST_RESULTS.md) - Deployment validation
