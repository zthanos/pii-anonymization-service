# Profiling Analysis & Optimization Recommendations

## Executive Summary

Profiled 10,000 records processed in batches of 200 (50 batches total).

**Total Time**: 1.890 seconds
**Throughput**: ~5,291 records/sec (in pure Python, without gRPC overhead)

## Bottleneck Analysis

### 1. Redis Operations - 62% of total time (1.177s)

**Functions**:
- `token_store.py:store_batch` - 1.177s (62%)
- `client.py:_execute_pipeline` - 1.098s (58%)
- `connection.py:pack_command` - 0.366s (19%)
- `client.py:parse_response` - 0.626s (33%)

**What's happening**:
- 50 Redis pipelines (one per batch)
- Each pipeline stores ~800 tokens (200 records × 4 fields)
- Command packing and response parsing overhead

**Optimization Opportunities**:

#### A. Use Redis MSET instead of individual SET commands
**Current**: 40,000 individual SET commands in pipelines
**Proposed**: Use MSET for multiple keys at once

```python
# Instead of:
for token_mapping in mappings:
    pipe.set(key, value, ex=ttl)

# Use:
# Group by TTL, then use MSET
mset_dict = {key: value for key, value in mappings}
pipe.mset(mset_dict)
# Then set expiry in bulk
for key in mset_dict.keys():
    pipe.expire(key, ttl)
```

**Expected Impact**: 20-30% reduction in Redis time → +400-600 records/sec

#### B. Increase batch size further
**Current**: batch_size=200
**Proposed**: Try batch_size=500 or 1000 for pure throughput

With fewer batches:
- Fewer pipeline round-trips
- Better amortization of overhead

**Expected Impact**: 10-15% improvement → +200-300 records/sec

#### C. Use Redis connection pooling more efficiently
**Current**: Pool size=200
**Analysis**: May be over-provisioned for local testing

**Action**: Monitor actual connection usage

### 2. Encryption - 6% of total time (0.122s)

**Functions**:
- `crypto_engine.py:encrypt` - 0.122s (6%)
- Actual AESGCM encryption - 0.034s (2%)
- Overhead (base64, etc.) - 0.088s (4%)

**What's happening**:
- 40,000 encryption operations (one per field)
- AES-GCM encryption is fast (0.034s)
- Base64 encoding overhead (0.088s)

**Optimization Opportunities**:

#### A. Batch encryption
**Proposed**: Encrypt multiple values in one call

```python
# Instead of encrypting one at a time:
for value in values:
    encrypted = cipher.encrypt(nonce, value, None)

# Batch encrypt (if library supports):
encrypted_values = cipher.encrypt_batch(nonces, values)
```

**Expected Impact**: 20-30% reduction in encryption time → +100-150 records/sec

#### B. Use faster encoding
**Current**: base64.b64encode
**Proposed**: Use base64.urlsafe_b64encode (slightly faster)

**Expected Impact**: Minimal (5-10 records/sec)

### 3. Pydantic Validation - 3% of total time (0.057s)

**Functions**:
- `TokenMapping.__init__` - 0.057s (3%)
- Creating 50,000 TokenMapping objects

**What's happening**:
- Pydantic validates every TokenMapping creation
- 50,000 validations for 40,000 tokens

**Optimization Opportunities**:

#### A. Use model_construct for internal objects
**Proposed**: Skip validation for internally-created objects

```python
# Instead of:
token_mapping = TokenMapping(
    system_id=system_id,
    token=token,
    encrypted_value=encrypted_value,
    ttl_seconds=ttl
)

# Use:
token_mapping = TokenMapping.model_construct(
    system_id=system_id,
    token=token,
    encrypted_value=encrypted_value,
    ttl_seconds=ttl
)
```

**Expected Impact**: 50-70% reduction in validation time → +50-100 records/sec

#### B. Use dataclasses instead of Pydantic for internal models
**Proposed**: TokenMapping doesn't need validation - it's internal

```python
from dataclasses import dataclass

@dataclass
class TokenMapping:
    system_id: str
    token: str
    encrypted_value: str
    ttl_seconds: int
```

**Expected Impact**: 80-90% reduction in validation time → +80-120 records/sec

## Optimization Priority

### Quick Wins (1-2 hours, 15-25% improvement)

1. **Use model_construct for TokenMapping** (30 min)
   - Expected: +50-100 records/sec
   - Risk: Low
   - Effort: Very Low

2. **Optimize Redis MSET usage** (1 hour)
   - Expected: +400-600 records/sec
   - Risk: Medium (need to test TTL handling)
   - Effort: Medium

3. **Replace TokenMapping with dataclass** (30 min)
   - Expected: +80-120 records/sec
   - Risk: Low
   - Effort: Low

**Total Expected**: +530-820 records/sec → **4,347-4,637 records/sec**

### Medium Effort (2-4 hours, 10-15% improvement)

4. **Batch encryption** (2 hours)
   - Expected: +100-150 records/sec
   - Risk: Medium (depends on library support)
   - Effort: Medium

5. **Optimize batch size for throughput** (1 hour)
   - Expected: +200-300 records/sec
   - Risk: Low
   - Effort: Low

**Total Expected**: +300-450 records/sec → **4,647-5,087 records/sec**

### Combined Total

**Current**: 3,817 records/sec (with gRPC)
**Expected after optimizations**: **5,200-5,900 records/sec** (36-55% improvement)

## Implementation Plan

### Phase 1: Quick Wins (Day 1)

1. Replace TokenMapping with dataclass
2. Use model_construct where needed
3. Optimize Redis MSET usage
4. Test and benchmark

**Target**: 4,500+ records/sec

### Phase 2: Medium Effort (Day 2)

1. Implement batch encryption
2. Optimize batch size
3. Test and benchmark

**Target**: 5,500+ records/sec

### Phase 3: Reassess (Day 3)

- If >5,500 records/sec: Great progress!
- If <5,500 records/sec: Consider architecture changes

## Detailed Optimization Code

### 1. Replace TokenMapping with dataclass

```python
# In token_store.py
from dataclasses import dataclass

@dataclass
class TokenMapping:
    """Mapping between token and encrypted value."""
    system_id: str
    token: str
    encrypted_value: str
    ttl_seconds: int
```

### 2. Optimize Redis MSET

```python
# In token_store.py:store_batch()
async def store_batch(self, mappings: List[TokenMapping]) -> None:
    """Store multiple token mappings using MSET for efficiency."""
    if not mappings:
        return
    
    # Group by TTL
    ttl_groups = {}
    for mapping in mappings:
        ttl = mapping.ttl_seconds
        if ttl not in ttl_groups:
            ttl_groups[ttl] = []
        ttl_groups[ttl].append(mapping)
    
    # Process each TTL group
    async with self.redis.pipeline(transaction=False) as pipe:
        for ttl, group in ttl_groups.items():
            # Build MSET dict
            mset_dict = {}
            for mapping in group:
                key = self._build_key(mapping.system_id, mapping.token)
                mset_dict[key] = mapping.encrypted_value
            
            # Use MSET for bulk set
            if mset_dict:
                pipe.mset(mset_dict)
                
                # Set expiry for all keys
                for key in mset_dict.keys():
                    pipe.expire(key, ttl)
        
        await pipe.execute()
```

### 3. Batch Encryption (if supported)

```python
# In crypto_engine.py
def encrypt_batch(self, values: List[str], key: bytes) -> List[str]:
    """Encrypt multiple values efficiently."""
    cipher = AESGCM(key)
    encrypted_values = []
    
    for value in values:
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, value.encode('utf-8'), None)
        encrypted = base64.b64encode(nonce + ciphertext).decode('utf-8')
        encrypted_values.append(encrypted)
    
    return encrypted_values
```

## Next Steps

1. Implement Quick Wins (Phase 1)
2. Benchmark after each change
3. Document improvements
4. Proceed to Phase 2 if needed

## Conclusion

The profiling revealed that **Redis operations are the primary bottleneck** (62% of time). By optimizing Redis usage with MSET and reducing Pydantic overhead, we can achieve **5,500+ records/sec** (44% improvement).

This would bring us to **24x improvement from baseline** (229 → 5,500 records/sec), getting us much closer to the 50k target.
