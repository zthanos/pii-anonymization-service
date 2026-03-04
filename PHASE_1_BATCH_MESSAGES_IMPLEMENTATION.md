# Phase 1: Batch Messages Implementation ✅

## Overview

Implemented V2 batch API to eliminate per-record gRPC serialization overhead.

**Expected Improvement:** 3-5x → **10k-18k records/sec**

## What Was Implemented

### 1. New Proto Contract (V2)

**File:** `src/pii_service/proto/pii_service_v2.proto`

**Key Changes:**
- `BatchAnonymizeRequest` with `repeated RecordItem` (200+ records per message)
- `bytes record_data` instead of `string record_json` (no string conversion)
- `BatchAnonymizeResponse` with batch-level statistics
- Both unary and streaming batch APIs

**Benefits:**
- 1x protobuf decode per batch (not 200x)
- Direct bytes passthrough (no string conversion)
- Batch-level statistics for monitoring

### 2. V2 Servicer Implementation

**File:** `src/pii_service/api/grpc_servicer_v2.py`

**Key Features:**
- `AnonymizeBatch()` - Unary batch RPC (simplest)
- `DeanonymizeBatch()` - Batch de-anonymization
- `AnonymizeBatchStream()` - Streaming batches (for very large datasets)
- Direct `orjson.loads()` on bytes (no string conversion)
- Batch-level error handling and statistics

**Optimizations:**
- Single protobuf decode per batch
- Direct bytes → orjson.loads (no intermediate string)
- Batch processing in tokenizer
- Comprehensive error handling per record

### 3. V2 Server

**File:** `src/pii_service/api/grpc_server_v2.py`

**Features:**
- Serves both V1 (streaming) and V2 (batch) APIs
- Backward compatible with existing clients
- Optimized gRPC settings (message sizes, flow control)

### 4. Benchmark Script

**File:** `benchmarks/benchmark_v2.py`

**Tests:**
- Different batch sizes (100, 200, 500, 1000)
- Unary batch API
- Streaming batch API
- Comparison with V1 performance

### 5. Startup Script

**File:** `scripts/start_service_v2.py`

Simple script to start service with V2 API support.

## How to Use

### 1. Compile Proto

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    src/pii_service/proto/pii_service_v2.proto
```

### 2. Start Service with V2 API

```bash
# Option A: Using docker-compose (rebuild image first)
docker-compose build pii-service
docker-compose up -d

# Option B: Using startup script
python scripts/start_service_v2.py
```

### 3. Run Benchmark

```bash
python benchmarks/benchmark_v2.py
```

## Expected Results

### Current Performance (V1)
- **Throughput:** 3,585 records/sec
- **Bottleneck:** Per-record protobuf decode (40% overhead)

### Expected Performance (V2)

| Batch Size | Expected Throughput | Improvement |
|------------|---------------------|-------------|
| 100 | 8,000-10,000 rec/sec | 2.2-2.8x |
| 200 | 10,000-14,000 rec/sec | 2.8-3.9x |
| 500 | 12,000-18,000 rec/sec | 3.3-5.0x |
| 1000 | 14,000-20,000 rec/sec | 3.9-5.6x |

**Best Case:** 18,000 records/sec (5x improvement) ✅

## API Comparison

### V1 API (Streaming per-record)

```python
# Client sends 1 record per message
async def request_generator():
    for record in records:
        yield AnonymizeRequest(
            system_id="customer_db",
            record_id=str(i),
            record_json=json.dumps(record),  # String conversion
        )

# 10,000 records = 10,000 protobuf decodes
```

### V2 API (Batch messages)

```python
# Client sends 200 records per message
batch_items = []
for record in records[:200]:
    batch_items.append(RecordItem(
        record_id=str(i),
        record_data=orjson.dumps(record),  # Direct bytes
    ))

request = BatchAnonymizeRequest(
    system_id="customer_db",
    records=batch_items,
)

response = await stub.AnonymizeBatch(request)

# 10,000 records = 50 protobuf decodes (200 per batch)
```

## Client Migration Guide

### Before (V1)

```python
import grpc
from pii_service.proto import pii_service_pb2 as pb2
from pii_service.proto import pii_service_pb2_grpc as pb2_grpc

channel = grpc.aio.insecure_channel('localhost:50051')
stub = pb2_grpc.StructuredAnonymizerStub(channel)

async def anonymize_records(records):
    async def request_generator():
        for i, record in enumerate(records):
            yield pb2.AnonymizeRequest(
                system_id="customer_db",
                record_id=str(i),
                record_json=json.dumps(record),
            )
    
    async for response in stub.Anonymize(request_generator()):
        # Process response
        pass
```

### After (V2)

```python
import grpc
import orjson
from pii_service.proto import pii_service_v2_pb2 as pb2
from pii_service.proto import pii_service_v2_pb2_grpc as pb2_grpc

channel = grpc.aio.insecure_channel('localhost:50051')
stub = pb2_grpc.StructuredAnonymizerV2Stub(channel)

async def anonymize_records(records, batch_size=200):
    # Create batches
    for i in range(0, len(records), batch_size):
        batch_records = records[i:i + batch_size]
        
        # Create batch request
        record_items = []
        for j, record in enumerate(batch_records):
            record_items.append(pb2.RecordItem(
                record_id=str(i + j),
                record_data=orjson.dumps(record),  # Direct bytes
            ))
        
        request = pb2.BatchAnonymizeRequest(
            system_id="customer_db",
            records=record_items,
        )
        
        # Send batch
        response = await stub.AnonymizeBatch(request)
        
        # Process results
        for result in response.results:
            if not result.error:
                anonymized = orjson.loads(result.anonymized_data)
                # Process anonymized record
```

## Next Steps

After validating Phase 1 performance:

1. **Phase 2: Worker Pool** (1-2 days) → 1.3-1.5x additional improvement
2. **Phase 3: Multi-Process** (2-3 days) → 4-8x additional improvement
3. **Phase 4: Redis + Platform** (1-2 days) → 1.3-1.8x additional improvement

**Combined:** 20-60x total improvement → **70k-215k records/sec** 🚀

## Files Created

- ✅ `src/pii_service/proto/pii_service_v2.proto` - V2 proto contract
- ✅ `src/pii_service/api/grpc_servicer_v2.py` - V2 servicer implementation
- ✅ `src/pii_service/api/grpc_server_v2.py` - V2 server with both APIs
- ✅ `benchmarks/benchmark_v2.py` - V2 benchmark script
- ✅ `scripts/start_service_v2.py` - V2 startup script
- ✅ `scripts/compile_proto_v2.sh` - Proto compilation script
- ✅ `PHASE_1_BATCH_MESSAGES_IMPLEMENTATION.md` - This document

## Testing

```bash
# 1. Compile proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    src/pii_service/proto/pii_service_v2.proto

# 2. Start service (in one terminal)
python scripts/start_service_v2.py

# 3. Run benchmark (in another terminal)
python benchmarks/benchmark_v2.py
```

## Status

✅ **Phase 1 Implementation Complete**

Ready for testing and benchmarking!

---

**Date:** March 4, 2026  
**Expected Improvement:** 3-5x  
**Expected Throughput:** 10k-18k records/sec
