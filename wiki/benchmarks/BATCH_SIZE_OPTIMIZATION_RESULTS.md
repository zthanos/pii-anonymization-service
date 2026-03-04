# Batch Size Optimization Results

## Test Configuration

- **Test Date**: March 4, 2026
- **Test File**: test_data_10k.ndjson (10,000 records)
- **Operation**: Anonymize
- **System**: customer_db

## Results Summary

| Batch Size | Throughput (records/sec) | Latency p95 (ms) | Execution Time (s) | Improvement vs Baseline |
|------------|--------------------------|------------------|--------------------|-----------------------|
| 50 (baseline) | 3,285 | 2,969 | 3.04 | 1.00x |
| 100 | 3,357 | 2,886 | 2.98 | 1.02x |
| 200 | **3,817** | **2,539** | **2.62** | **1.16x** |
| 500 | 3,672 | 2,647 | 2.72 | 1.12x |

## Key Findings

### 1. Optimal Batch Size: 200

**batch_size=200** provides the best performance:
- **Throughput**: 3,817 records/sec (16% improvement over baseline)
- **Latency p95**: 2,539 ms (14% improvement over baseline)
- **Execution Time**: 2.62 seconds (14% faster)

### 2. Performance Curve

The performance follows a curve:
- **50 → 100**: Small improvement (2%)
- **100 → 200**: Significant improvement (14%)
- **200 → 500**: Performance degrades slightly (-4%)

This suggests that batch_size=200 hits the sweet spot between:
- **Batch efficiency**: Fewer Redis round-trips
- **Concurrency**: More batches can be processed concurrently
- **Memory pressure**: Smaller batches use less memory

### 3. Why batch_size=500 is Slower

Larger batches (500) are slower because:
1. **Reduced concurrency**: With max_concurrent=1000 and batch_size=500, only 2 batches can run concurrently
2. **Longer processing time per batch**: Each batch takes longer to process
3. **Memory pressure**: Larger batches may cause more GC pauses

## Recommendation

**Set GRPC_BATCH_SIZE=200** for optimal performance.

This configuration provides:
- 16% improvement over batch_size=50
- Best balance between throughput and latency
- Efficient use of system resources

## Updated Performance Summary

With batch_size=200, we've achieved:

| Metric | Value |
|--------|-------|
| **Current Throughput** | 3,817 records/sec |
| **Total Improvement** | 16.7x from baseline (229 → 3,817) |
| **Target** | 50,000 records/sec |
| **Gap** | 13.1x more needed |

## Next Steps

Now that we've optimized batch size, the next steps are:

### 1. Profile the Service (Option 1B)

Use py-spy to identify bottlenecks:
```bash
uv add py-spy
docker exec -it pii-service py-spy record -o profile.svg -- python -m pii_service.main
```

### 2. Potential Further Optimizations

Based on profiling results, consider:
- **Optimize encryption**: Batch encryption or faster cipher
- **Optimize Redis operations**: Use MSET for multiple keys
- **Cache policy configuration**: Avoid repeated lookups
- **Reduce memory allocations**: Reuse objects where possible

### 3. Architecture Changes (if needed)

For reaching 50k+ records/sec:
- Redis cluster with sharding
- Multiple service instances with load balancing
- Separate encryption service
- Async batch processing queue

## Configuration Update

Update `.env` file:
```bash
GRPC_BATCH_SIZE=200
```

This setting will be used automatically when the service starts.
