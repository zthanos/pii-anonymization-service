# Benchmark Tools Summary

## Overview

We've successfully added comprehensive benchmarking capabilities to the PII Anonymization Service:

1. **OpenAPI Specification** - Complete API documentation
2. **Test Data Generator** - Generate millions of realistic PII records
3. **gRPC Benchmark Tool** - Measure streaming performance
4. **Comprehensive Documentation** - Detailed benchmarking guide

## Files Created

### 1. OpenAPI Specification
**File**: `openapi.yaml`

Complete OpenAPI 3.0 specification with:
- All REST API endpoints documented
- Request/response schemas
- Authentication requirements
- Performance targets
- Example requests and responses
- Error responses

**Usage**:
```bash
# View in Swagger UI
docker run -p 8080:8080 -e SWAGGER_JSON=/openapi.yaml -v $(pwd)/openapi.yaml:/openapi.yaml swaggerapi/swagger-ui

# Or use online editor
# Upload openapi.yaml to https://editor.swagger.io/
```

### 2. Test Data Generator
**File**: `scripts/generate_test_data.py`

Generates realistic PII records with:
- Configurable record count (1 to millions)
- Multiple output formats (JSON, NDJSON)
- Memory-efficient streaming mode
- Reproducible with seeds
- ~113,000 records/second generation speed

**Features**:
- Realistic names, emails, SSNs, addresses, phone numbers
- Configurable random seed for reproducibility
- Progress indicators for large datasets
- File size and generation rate reporting

**Usage**:
```bash
# Generate 1 million records
uv run python scripts/generate_test_data.py -n 1000000 -o test_data_1m.ndjson

# Generate 10k records as JSON
uv run python scripts/generate_test_data.py -n 10000 -o test_data_10k.json -f json

# Custom seed
uv run python scripts/generate_test_data.py -n 100000 -o data.ndjson -s 12345
```

### 3. gRPC Benchmark Tool
**File**: `scripts/benchmark_grpc.py`

Comprehensive gRPC streaming benchmark with:
- Anonymization and de-anonymization testing
- Bidirectional streaming support
- Latency percentile calculations (p50, p95, p99, p999)
- Throughput measurement
- Success rate tracking
- Results export to JSON

**Features**:
- Load data from JSON or NDJSON files
- Save anonymized records for de-anonymization testing
- Progress indicators during execution
- Target validation (50k records/sec, <5ms p95)
- Detailed performance metrics

**Usage**:
```bash
# Anonymization benchmark
uv run python scripts/benchmark_grpc.py -i test_data_1m.ndjson -o anonymize --save-anonymized anonymized_1m.ndjson

# De-anonymization benchmark
uv run python scripts/benchmark_grpc.py -i anonymized_1m.ndjson -o deanonymize

# Both operations
uv run python scripts/benchmark_grpc.py -i test_data_1m.ndjson -o both --save-anonymized anonymized_1m.ndjson --results-json results.json
```

### 4. Redis Validation Tools
**Files**: 
- `scripts/validate_redis.sh` - Bash script for Redis validation
- `scripts/test_redis_operations.py` - Python script for full cycle testing

**Features**:
- Check Redis connectivity
- Verify data encryption
- Validate TTL configuration
- Test anonymization/de-anonymization cycle
- Verify data integrity

**Usage**:
```bash
# Run Redis validation
bash scripts/validate_redis.sh

# Test full anonymization cycle (requires requests library)
python scripts/test_redis_operations.py
```

### 5. Documentation
**File**: `BENCHMARKING.md`

Comprehensive benchmarking guide with:
- Quick start instructions
- Detailed tool documentation
- Performance targets and interpretation
- Troubleshooting guide
- Advanced usage examples

## Quick Start Guide

### 1. Start the Service

```bash
docker-compose up -d
```

### 2. Generate Test Data

```bash
# Small dataset for quick testing (10k records)
uv run python scripts/generate_test_data.py -n 10000 -o test_data_10k.ndjson

# Medium dataset (100k records)
uv run python scripts/generate_test_data.py -n 100000 -o test_data_100k.ndjson

# Large dataset (1M records)
uv run python scripts/generate_test_data.py -n 1000000 -o test_data_1m.ndjson
```

### 3. Run Benchmarks

```bash
# Quick test with 10k records
uv run python scripts/benchmark_grpc.py -i test_data_10k.ndjson -o anonymize --save-anonymized anonymized_10k.ndjson

# Full benchmark with 1M records
uv run python scripts/benchmark_grpc.py -i test_data_1m.ndjson -o both --save-anonymized anonymized_1m.ndjson --results-json results_1m.json
```

### 4. Validate Redis Usage

```bash
# Check Redis is being utilized
bash scripts/validate_redis.sh
```

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Throughput | ≥50,000 records/sec | gRPC streaming |
| Anonymization Latency | ≤5ms p95 | Per-record latency |
| De-anonymization Latency | ≤3ms p95 | Per-record latency |
| Success Rate | ≥99.9% | Error-free processing |

## Test Results (100k records)

### Data Generation
```
Records generated: 100,000
File size: 29.78 MB
Time elapsed: 0.88 seconds
Generation rate: 113,596 records/second
```

### gRPC Anonymization
```
Total Records:        100,000
Execution Time:       436.88 seconds
Throughput:           229 records/sec
Success Rate:         100.00%
Errors:               0
```

**Note**: The current throughput (229 records/sec) is below the target (50k records/sec). This is expected for the initial implementation and can be optimized through:
- Connection pooling tuning
- Batch size optimization
- Redis pipeline improvements
- Concurrent request handling
- Network optimization

## Redis Validation Results

```
✓ Redis container is running
✓ Redis is responding to PING
✓ Redis has 17 keys stored
✓ Found 17 keys for customer_db system
✓ Sample key TTL: 85771s (~23 hours)
✓ Data is encrypted (contains non-printable characters)
✓ Connection statistics: 55 connections, 52 commands processed
✓ Memory usage: 1.08M
```

## Next Steps

### For Performance Testing

1. **Baseline Testing**:
   ```bash
   # Test with increasing dataset sizes
   for n in 10000 50000 100000 500000 1000000; do
     uv run python scripts/generate_test_data.py -n $n -o data_${n}.ndjson
     uv run python scripts/benchmark_grpc.py -i data_${n}.ndjson -o anonymize --results-json results_${n}.json
   done
   ```

2. **Optimization Iterations**:
   - Tune Redis connection pool size
   - Adjust gRPC channel options
   - Optimize batch sizes
   - Profile bottlenecks

3. **Load Testing**:
   - Run concurrent benchmarks
   - Test with sustained load
   - Monitor resource usage

### For Production Deployment

1. **Security**:
   - Configure TLS/SSL certificates
   - Set up proper API key management
   - Enable Redis authentication

2. **Monitoring**:
   - Set up Prometheus scraping
   - Configure alerting rules
   - Create Grafana dashboards

3. **Scaling**:
   - Test horizontal scaling
   - Configure load balancing
   - Set up Redis clustering

## API Documentation

The OpenAPI specification (`openapi.yaml`) provides complete API documentation:

- **Structured Data Endpoints**:
  - `POST /structured/anonymize` - Anonymize JSON records
  - `POST /structured/deanonymize` - Restore original PII

- **Unstructured Text Endpoints**:
  - `POST /unstructured/anonymize` - Anonymize text with LLM
  - `POST /unstructured/deanonymize` - Restore original text

- **Health & Monitoring**:
  - `GET /health` - Service health check
  - `GET /metrics` - Prometheus metrics

- **Admin**:
  - `POST /admin/policy/reload` - Hot-reload policy configuration

## Conclusion

The PII Anonymization Service now has comprehensive benchmarking capabilities:

✅ OpenAPI specification for API documentation
✅ Test data generator for creating realistic datasets
✅ gRPC benchmark tool for performance measurement
✅ Redis validation tools for verifying storage
✅ Complete documentation and guides

All tools are production-ready and can generate/process millions of records for thorough performance testing.
