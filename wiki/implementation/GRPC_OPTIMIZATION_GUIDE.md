# gRPC Throughput Optimization Guide

## Summary of Improvements

We've implemented several optimizations to improve gRPC streaming throughput:

### 1. Concurrent Request Processing ✅

**Before**: Sequential processing (`async for request in request_iterator`)
- Each request waited for the previous one to complete
- Throughput: ~229 records/sec

**After**: Concurrent processing with semaphore
- Process up to 1000 requests concurrently
- Use asyncio.Queue for response ordering
- Throughput: ~1,147 records/sec (5x improvement)

**Changes Made**:
- `src/pii_service/api/grpc_servicer.py`: Added concurrent processing with semaphore
- `src/pii_service/api/grpc_server.py`: Increased max_workers from 10 to 50
- `src/pii_service/config.py`: Added `GRPC_MAX_CONCURRENT_REQUESTS` setting

### 2. Increased Worker Threads ✅

**Before**: 10 worker threads
**After**: 50 worker threads

This allows more concurrent I/O operations (Redis, encryption).

### 3. Optimized gRPC Channel Options ✅

Added performance-oriented channel options:
```python
("grpc.max_concurrent_streams", 1000),
("grpc.http2.min_time_between_pings_ms", 10000),
("grpc.http2.max_ping_strikes", 2),
```

## Current Performance

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Throughput | 229 records/sec | 1,147 records/sec | 5x |
| Target | 50,000 records/sec | 50,000 records/sec | - |
| Gap | 49,771 records/sec | 48,853 records/sec | - |

## Further Optimization Strategies

### 1. Batch Processing in Tokenizer

**Current**: Each record processed individually
**Optimization**: Process records in batches

```python
# In structured_tokenizer.py
async def anonymize_batch(
    self,
    records: List[dict],
    system_id: str,
) -> List[AnonymizedRecord]:
    """Process multiple records in a single batch."""
    # Extract all PII fields from all records
    # Generate all tokens at once
    # Single Redis pipeline for all tokens
    # Return all results
```

**Expected Impact**: 2-3x improvement

### 2. Redis Pipeline Optimization

**Current**: One pipeline per record (4-5 tokens per record)
**Optimization**: One pipeline for multiple records

```python
# Batch 100 records together
# Single Redis pipeline with 400-500 operations
# Reduces network round-trips by 100x
```

**Expected Impact**: 5-10x improvement

### 3. Connection Pooling Tuning

**Current**: Redis pool size = 50
**Optimization**: Increase based on concurrency

```python
# Formula: pool_size = max_concurrent_requests / 10
REDIS_POOL_SIZE = 200  # For 1000 concurrent requests
```

**Expected Impact**: 1.5-2x improvement

### 4. Reduce JSON Serialization Overhead

**Current**: json.dumps() for each record
**Optimization**: Use faster JSON library

```python
import orjson  # 2-3x faster than json

# In grpc_servicer.py
anonymized_json=orjson.dumps(anonymized.record).decode()
```

**Expected Impact**: 1.2-1.5x improvement

### 5. Optimize Encryption

**Current**: AES-256-GCM per field
**Optimization**: Batch encryption or use faster cipher

```python
# Option 1: Batch encrypt multiple values
encrypted_values = crypto_engine.encrypt_batch(values, key)

# Option 2: Use ChaCha20-Poly1305 (faster on non-AES hardware)
```

**Expected Impact**: 1.5-2x improvement

### 6. Remove Logging Overhead

**Current**: Debug logging for each record
**Optimization**: Conditional logging or sampling

```python
# Only log every 1000th record
if record_count % 1000 == 0:
    logger.debug(...)
```

**Expected Impact**: 1.1-1.2x improvement

### 7. Profile and Identify Bottlenecks

Use profiling to find the actual bottleneck:

```bash
# Install profiling tools
uv add py-spy

# Profile the service
py-spy record -o profile.svg -- python -m pii_service.main

# Or use cProfile
python -m cProfile -o profile.stats -m pii_service.main
```

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours)
1. ✅ Concurrent processing (DONE - 5x improvement)
2. ✅ Increase worker threads (DONE)
3. ✅ Optimize gRPC options (DONE)
4. Increase Redis pool size
5. Remove debug logging

**Expected Total**: 8-10x improvement → ~2,000-2,500 records/sec

### Phase 2: Medium Effort (4-6 hours)
1. Batch processing in tokenizer
2. Redis pipeline optimization
3. Faster JSON serialization (orjson)

**Expected Total**: 20-30x improvement → ~6,000-9,000 records/sec

### Phase 3: Advanced (1-2 days)
1. Batch encryption
2. Custom memory allocators
3. C++ extensions for hot paths
4. Horizontal scaling with load balancing

**Expected Total**: 50-100x improvement → ~15,000-25,000 records/sec

### Phase 4: Architecture Changes (1 week)
1. Separate encryption service
2. Redis cluster with sharding
3. gRPC load balancing
4. Async batch processing queue

**Expected Total**: 200-300x improvement → 50,000+ records/sec ✅

## Configuration Tuning

### Current Settings

```python
# config.py
REDIS_POOL_SIZE = 50
GRPC_MAX_WORKERS = 50
GRPC_MAX_CONCURRENT_REQUESTS = 1000
```

### Recommended Settings for High Throughput

```python
# For 50k records/sec target
REDIS_POOL_SIZE = 200
GRPC_MAX_WORKERS = 100
GRPC_MAX_CONCURRENT_REQUESTS = 2000

# Redis configuration
REDIS_URL = "redis://redis:6379/0?socket_keepalive=1&socket_timeout=5"

# gRPC channel options
("grpc.max_concurrent_streams", 2000),
("grpc.http2.max_frame_size", 16384),
("grpc.http2.bdp_probe", 1),
```

### Environment Variables

```bash
# .env
REDIS_POOL_SIZE=200
GRPC_MAX_WORKERS=100
GRPC_MAX_CONCURRENT_REQUESTS=2000

# For production
REDIS_URL=redis://redis-cluster:6379/0
LOG_LEVEL=WARNING  # Reduce logging overhead
```

## Benchmarking Best Practices

### 1. Warm-up Period

```bash
# Run a small benchmark first to warm up connections
uv run python scripts/benchmark_grpc.py -i test_data_1k.ndjson -o anonymize

# Then run the real benchmark
uv run python scripts/benchmark_grpc.py -i test_data_100k.ndjson -o anonymize
```

### 2. Monitor System Resources

```bash
# Terminal 1: Run benchmark
uv run python scripts/benchmark_grpc.py -i test_data_100k.ndjson -o anonymize

# Terminal 2: Monitor Docker stats
docker stats pii-service pii-redis

# Terminal 3: Monitor Redis
docker exec pii-redis redis-cli -a redis_dev_password --latency
```

### 3. Incremental Testing

```bash
# Test with increasing dataset sizes
for n in 1000 5000 10000 50000 100000; do
  echo "Testing with $n records..."
  uv run python scripts/benchmark_grpc.py \
    -i test_data_${n}.ndjson \
    -o anonymize \
    --results-json results_${n}.json
done
```

## Troubleshooting

### Low Throughput

**Symptoms**: <1,000 records/sec

**Possible Causes**:
1. Redis connection issues
2. Network latency
3. CPU bottleneck
4. Memory pressure

**Solutions**:
```bash
# Check Redis latency
docker exec pii-redis redis-cli -a redis_dev_password --latency

# Check CPU usage
docker stats pii-service

# Check memory
docker exec pii-service free -h

# Check network
docker exec pii-service ping redis
```

### High Latency

**Symptoms**: p95 > 100ms

**Possible Causes**:
1. Redis slow queries
2. Encryption overhead
3. JSON serialization
4. Logging overhead

**Solutions**:
```bash
# Profile Redis
docker exec pii-redis redis-cli -a redis_dev_password SLOWLOG GET 10

# Reduce logging
export LOG_LEVEL=WARNING

# Use faster JSON library
uv add orjson
```

### Memory Issues

**Symptoms**: OOM errors, high memory usage

**Possible Causes**:
1. Too many concurrent requests
2. Large record sizes
3. Memory leaks

**Solutions**:
```bash
# Reduce concurrency
export GRPC_MAX_CONCURRENT_REQUESTS=500

# Increase Docker memory limit
docker-compose down
# Edit docker-compose.yml: add memory: 4g
docker-compose up -d

# Monitor memory
docker stats pii-service
```

## Next Steps

1. **Implement Phase 1 optimizations** (Redis pool size, remove debug logging)
2. **Profile the service** to identify actual bottlenecks
3. **Implement Phase 2 optimizations** (batch processing, orjson)
4. **Re-benchmark** and measure improvements
5. **Iterate** until reaching 50k records/sec target

## Conclusion

We've achieved a **5x improvement** in throughput (229 → 1,147 records/sec) through concurrent processing. To reach the 50k records/sec target, we need to implement batch processing, optimize Redis operations, and potentially make architectural changes.

The most impactful next steps are:
1. Batch processing in tokenizer (2-3x)
2. Redis pipeline optimization (5-10x)
3. Increase Redis pool size (1.5-2x)

Combined, these should get us to ~15,000-30,000 records/sec, much closer to the target.
