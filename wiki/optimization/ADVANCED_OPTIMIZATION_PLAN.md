# Advanced Optimization Plan - Path to 50k+ records/sec

## Executive Summary

Excellent suggestions! These optimizations target the actual bottlenecks and can realistically achieve 50k+ records/sec.

**Current Performance:** 3,585 records/sec  
**Target:** 50,000+ records/sec  
**Gap:** 14x improvement needed

**Proposed Optimizations (Priority Order):**
1. **Batch gRPC Messages** → 3-5x improvement (eliminate per-record serialization)
2. **Worker Pool Pattern** → 1.3-1.5x improvement (reduce concurrency overhead)
3. **Multi-process** → 4-8x improvement (break GIL, scale linearly)
4. **Redis Optimization** → 1.2-1.5x improvement (EVALSHA, data model)
5. **Platform Wins** → 1.1-1.2x improvement (uvloop, tuning)

**Combined Expected:** 20-60x improvement → **70k-215k records/sec** ✅

## Current Bottleneck Analysis

From profiling:
- **gRPC Serialization:** 40% (protobuf encode/decode per record)
- **Concurrency Overhead:** 20% (task creation, semaphores, queues)
- **Redis Operations:** 15% (already optimized with Lua)
- **Encryption:** 10% (AES-GCM)
- **Other:** 15% (JSON parsing, field extraction)

## Optimization 1: Batch gRPC Messages (HIGHEST IMPACT)

### Problem
Currently: Stream 1 record per message
- 10,000 records = 10,000 protobuf decode operations
- 10,000 Python object creations
- 10,000 queue operations
- Massive serialization overhead

### Solution: Client-Side Batching

**New Proto Contract:**
```protobuf
message BatchAnonymizeRequest {
  string system_id = 1;
  repeated RecordItem records = 2;  // 200 records per batch
}

message RecordItem {
  string record_id = 1;
  bytes record_data = 2;  // Raw JSON bytes (not string)
}

message BatchAnonymizeResponse {
  repeated RecordResult results = 1;
}

message RecordResult {
  string record_id = 1;
  bytes anonymized_data = 2;  // Raw JSON bytes
  repeated string token_ids = 3;
  string error = 4;
}
```

**Benefits:**
- 1x protobuf decode per 200 records (not 200x)
- 1x gRPC message overhead (not 200x)
- Bytes passthrough (no string conversion)
- Direct orjson.loads on bytes

**Expected Impact:** 3-5x improvement → **10k-18k records/sec**

### Implementation Strategy

**Option A: Keep Streaming + Batch Messages**
```python
# Client sends batches via stream
async def request_generator():
    batch = []
    for record in records:
        batch.append(RecordItem(record_id=..., record_data=orjson.dumps(record)))
        if len(batch) >= 200:
            yield BatchAnonymizeRequest(system_id=..., records=batch)
            batch = []
```

**Option B: Unary Batch RPC (Simpler)**
```protobuf
rpc AnonymizeBatch(BatchAnonymizeRequest) returns (BatchAnonymizeResponse);
```
- Simpler implementation
- Still supports large batches
- Can add streaming later if needed

**Recommendation:** Start with Option B (unary), add streaming if needed.

## Optimization 2: Worker Pool Pattern

### Problem
Current: `asyncio.create_task()` per batch
- Task creation overhead
- Semaphore contention
- Queue overhead
- Context switching

### Solution: Fixed Worker Pool

```python
class WorkerPool:
    def __init__(self, num_workers: int, tokenizer):
        self.batch_queue = asyncio.Queue(maxsize=100)  # Bounded
        self.result_queue = asyncio.Queue()
        self.workers = []
        self.tokenizer = tokenizer
        
        # Start long-lived workers
        for _ in range(num_workers):
            worker = asyncio.create_task(self._worker())
            self.workers.append(worker)
    
    async def _worker(self):
        """Long-lived worker that processes batches."""
        while True:
            batch_records, batch_ids = await self.batch_queue.get()
            try:
                results = await self.tokenizer.anonymize_batch(batch_records, system_id)
                await self.result_queue.put((batch_ids, results))
            except Exception as e:
                await self.result_queue.put((batch_ids, [error] * len(batch_ids)))
    
    async def submit_batch(self, records, ids):
        """Submit batch for processing (with backpressure)."""
        await self.batch_queue.put((records, ids))
    
    async def get_results(self):
        """Get processed results."""
        return await self.result_queue.get()
```

**Benefits:**
- No task creation per batch
- Stable scheduling
- Backpressure with bounded queue
- Reduced context switching

**Expected Impact:** 1.3-1.5x improvement → **13k-27k records/sec**

## Optimization 3: Multi-Process (BREAK THE GIL)

### Problem
Python GIL limits single-process throughput
- CPU-bound: protobuf, crypto, orchestration
- Single process maxes out at ~4k records/sec

### Solution: Multi-Process gRPC Server

**Option A: SO_REUSEPORT (Linux)**
```python
# Start 4-8 processes on same port
import multiprocessing

def start_server(port):
    server = grpc.aio.server(
        options=[
            ('grpc.so_reuseport', 1),  # Enable SO_REUSEPORT
            ('grpc.max_workers', 10),
        ]
    )
    # ... add servicer, bind, start
    
if __name__ == '__main__':
    num_processes = multiprocessing.cpu_count()
    processes = []
    for _ in range(num_processes):
        p = multiprocessing.Process(target=start_server, args=(50051,))
        p.start()
        processes.append(p)
```

**Option B: Envoy/nginx Load Balancer**
```yaml
# docker-compose.yml
services:
  pii-service-1:
    build: .
    ports: ["50052:50051"]
  pii-service-2:
    build: .
    ports: ["50053:50051"]
  pii-service-3:
    build: .
    ports: ["50054:50051"]
  pii-service-4:
    build: .
    ports: ["50055:50051"]
  
  envoy:
    image: envoyproxy/envoy:v1.28
    ports: ["50051:50051"]
    # Load balance across 4 instances
```

**Expected Impact:** 4-8x improvement → **52k-216k records/sec** ✅

## Optimization 4: Redis Fine-Tuning

### 4.1 Use EVALSHA (Not EVAL)

**Current:** Sends Lua script every time
```python
await self.redis.eval(lua_script, 0, *args)  # Sends full script
```

**Optimized:** Pre-load script, use SHA
```python
class TokenStore:
    def __init__(self):
        self.script_sha = None
    
    async def _ensure_script_loaded(self):
        if not self.script_sha:
            self.script_sha = await self.redis.script_load(lua_script)
    
    async def store_batch(self, mappings):
        await self._ensure_script_loaded()
        await self.redis.evalsha(self.script_sha, 0, *args)  # Just SHA
```

### 4.2 Optimize Data Model (1 Key Per Record)

**Current:** 4 keys per record (email, name, ssn, address)
- 10k records = 40k Redis operations
- More network chatter

**Optimized:** 1 key per record with packed structure
```python
# Store all fields in one key
key = f"{system_id}:record:{record_id}"
value = orjson.dumps({
    "email_token": token1,
    "name_token": token2,
    "ssn_token": token3,
    "address_token": token4,
    "encrypted_values": {
        token1: encrypted_email,
        token2: encrypted_name,
        # ...
    }
})
await redis.setex(key, ttl, value)
```

**Benefits:**
- 1 Redis operation per record (not 4)
- Less network overhead
- Atomic updates

**Expected Impact:** 1.2-1.5x improvement

### 4.3 Unix Socket (Co-located Redis)

If Redis is on same host:
```python
# .env
REDIS_URL=unix:///var/run/redis/redis.sock
```

**Benefits:**
- Lower latency (no TCP overhead)
- Less CPU (no TCP stack)
- ~10-20% improvement for co-located Redis

## Optimization 5: Platform Wins

### 5.1 uvloop (Linux Only)

```python
# main.py
import uvloop
uvloop.install()  # Before asyncio.run()

# Expected: +5-15% improvement
```

### 5.2 gRPC Tuning

```python
server = grpc.aio.server(
    options=[
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.http2.max_pings_without_data', 0),
        ('grpc.http2.min_time_between_pings_ms', 10000),
        ('grpc.http2.min_ping_interval_without_data_ms', 5000),
        ('grpc.keepalive_time_ms', 10000),
        ('grpc.keepalive_timeout_ms', 5000),
        ('grpc.http2.max_frame_size', 16384),
        ('grpc.http2.initial_window_size', 1024 * 1024),
    ]
)
```

## Implementation Roadmap

### Phase 1: Batch Messages (Highest ROI)
**Effort:** 2-3 days  
**Expected:** 3-5x improvement → 10k-18k records/sec

1. Design new proto contract (batch messages)
2. Implement server-side batch handler
3. Update client/benchmark to use batches
4. Test and validate

### Phase 2: Worker Pool
**Effort:** 1-2 days  
**Expected:** 1.3-1.5x improvement → 13k-27k records/sec

1. Implement WorkerPool class
2. Replace task-per-batch with worker pool
3. Tune worker count and queue sizes
4. Benchmark

### Phase 3: Multi-Process
**Effort:** 2-3 days  
**Expected:** 4-8x improvement → 52k-216k records/sec

1. Implement SO_REUSEPORT or Envoy setup
2. Test with 4-8 processes
3. Validate Redis connection pooling
4. Load test

### Phase 4: Redis + Platform
**Effort:** 1-2 days  
**Expected:** 1.3-1.8x cumulative improvement

1. Implement EVALSHA
2. Optimize data model (1 key per record)
3. Add uvloop
4. Tune gRPC settings

## Expected Performance Timeline

| Phase | Optimization | Throughput | Cumulative |
|-------|-------------|------------|------------|
| Current | Baseline | 3,585 rec/sec | 1.0x |
| Phase 1 | Batch Messages | 14,340 rec/sec | 4.0x |
| Phase 2 | Worker Pool | 20,076 rec/sec | 5.6x |
| Phase 3 | Multi-Process (4x) | 80,304 rec/sec | 22.4x |
| Phase 4 | Redis + Platform | 104,395 rec/sec | 29.1x |

**Final Target:** 100k+ records/sec ✅ (2x over target!)

## Recommendation

**Start with Phase 1 (Batch Messages)** - highest ROI, relatively simple.

This alone should get you to 10k-18k records/sec, which is 2-5x improvement.

Then evaluate if you need Phase 2-4 based on your actual requirements.

Would you like me to:
1. **Design the new proto contract** (batch messages + bytes passthrough)?
2. **Implement Phase 1** (batch message support)?
3. **Create a detailed implementation plan** for all phases?

Let me know and I'll proceed!
