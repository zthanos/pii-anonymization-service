# HR Realistic Scenario Benchmark - Quick Start Guide

## Overview

This benchmark validates the PII Anonymization Service with a realistic HR scenario:
- **360,000 employee records**
- **12 properties per record** (employee_id, ssn, email, phone, names, salary, position, etc.)
- **All fields are PII** that need anonymization
- **Measures actual time** for anonymization and de-anonymization

## Quick Start (5 minutes)

### 1. Start the Service

**Option A: Single Instance (18k rec/sec)**
```bash
docker-compose up -d
```

**Option B: Multi-Instance (59k rec/sec) - RECOMMENDED**
```bash
docker-compose -f docker-compose.multi.yml up -d
```

Wait for services to be healthy (~10 seconds).

### 2. Run the Benchmark

```bash
bash scripts/run_hr_benchmark.sh
```

That's it! The script will:
- ✅ Check if service is running
- ✅ Generate encryption key if needed
- ✅ Generate 360,000 test records (~2-3 minutes first time)
- ✅ Restart service to load HR policy
- ✅ Run anonymization benchmark
- ✅ Run de-anonymization benchmark
- ✅ Verify 100% data reversibility
- ✅ Save results to JSON file

## Expected Results

### Single Instance (docker-compose.yml)

```
📊 Total Records: 360,000
📊 Properties per Record: 12
📊 PII Fields: 12

⏱️  Anonymization Time: ~19 seconds
⚡ Anonymization Throughput: ~18,672 records/sec

⏱️  De-anonymization Time: ~13 seconds
⚡ De-anonymization Throughput: ~27,993 records/sec

⏱️  Total Time: ~32 seconds
✅ Data Integrity: 100%
```

### Multi-Instance (docker-compose.multi.yml) - RECOMMENDED

```
📊 Total Records: 360,000
📊 Properties per Record: 12
📊 PII Fields: 12

⏱️  Anonymization Time: ~6 seconds
⚡ Anonymization Throughput: ~59,151 records/sec

⏱️  De-anonymization Time: ~4 seconds
⚡ De-anonymization Throughput: ~88,000 records/sec

⏱️  Total Time: ~10 seconds
✅ Data Integrity: 100%
```

## What Gets Tested

### Employee Record Structure

Each of the 360,000 records contains:

```json
{
  "employee_id": "E000001",
  "ssn": "123-45-6789",
  "email": "john.doe1@company.com",
  "phone": "+1-555-123-4567",
  "first_name": "John",
  "last_name": "Doe",
  "date_of_birth": "1985-03-15",
  "salary": 125000,
  "bank_account": "123456789",
  "position": "Senior Software Engineer",
  "department": "Engineering",
  "emergency_contact": "Jane Doe - +1-555-987-6543"
}
```

### Anonymization Process

All 12 fields are tokenized:
- `employee_id` → `EMP_550e8400-e29b-41d4-a716-446655440000`
- `ssn` → `a1b2c3d4e5f6...` (deterministic HMAC)
- `email` → `550e8400-e29b-41d4-a716-446655440000`
- `first_name` → `NAME_550e8400-e29b-41d4-a716-446655440001`
- `salary` → `550e8400-e29b-41d4-a716-446655440002`
- etc.

### De-anonymization Process

All tokens are reversed back to original values:
- Tokens → Original PII values
- 100% data integrity verified
- No data loss

## Results Location

Results are saved to:
```
data/benchmark_results/hr_realistic_benchmark.json
```

The JSON file contains:
- Detailed timing statistics
- Throughput metrics
- Batch-level performance data
- Data integrity verification results

## Troubleshooting

### Service Not Running

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs pii-service

# Restart
docker-compose restart pii-service
```

### Test Data Already Exists

The script will skip generation if data already exists. To regenerate:

```bash
rm data/test_data/hr_test_data_360k.ndjson
bash scripts/run_hr_benchmark.sh
```

### Performance Lower Than Expected

1. **Check system resources:**
   ```bash
   docker stats
   ```

2. **Use multi-instance deployment:**
   ```bash
   docker-compose -f docker-compose.multi.yml up -d
   ```

3. **Check Redis performance:**
   ```bash
   docker-compose exec redis redis-cli info stats
   ```

## Manual Steps (Optional)

If you prefer to run steps manually:

```bash
# 1. Generate encryption key
export HR_SYSTEM_KEY=$(python scripts/generate_key.py)
echo "HR_SYSTEM_KEY=$HR_SYSTEM_KEY" >> .env

# 2. Generate test data (takes 2-3 minutes)
python scripts/generate_hr_test_data.py 360000

# 3. Restart service to load HR policy
docker-compose restart pii-service

# 4. Wait for service to be ready
sleep 5

# 5. Run benchmark
python benchmarks/benchmark_hr_realistic.py
```

## Understanding the Results

### Anonymization Time
- Time to convert 360,000 original records → anonymized records
- Includes: Token generation, encryption, Redis storage
- Target: <20 seconds (single), <7 seconds (multi)

### De-anonymization Time
- Time to convert 360,000 anonymized records → original records
- Includes: Token lookup, decryption, Redis retrieval
- Target: <15 seconds (single), <5 seconds (multi)
- Usually faster than anonymization (no encryption, simpler operations)

### Throughput
- Records processed per second
- Single instance: ~18k rec/sec (anonymization), ~28k rec/sec (de-anonymization)
- Multi-instance: ~59k rec/sec (anonymization), ~88k rec/sec (de-anonymization)

### Data Integrity
- Verifies that de-anonymization perfectly restores original data
- Checks 100 random samples
- Must be 100% for production use

## Production Capacity Planning

Use these results to estimate production capacity:

**Example: 10 million records per day**

Single Instance:
- Anonymization: 10M / 18,672 = ~536 seconds (~9 minutes)
- De-anonymization: 10M / 27,993 = ~357 seconds (~6 minutes)

Multi-Instance (4 instances):
- Anonymization: 10M / 59,151 = ~169 seconds (~3 minutes)
- De-anonymization: 10M / 88,000 = ~114 seconds (~2 minutes)

## Next Steps

After running the benchmark:

1. **Review Results:** Check `data/benchmark_results/hr_realistic_benchmark.json`
2. **Compare Performance:** Verify against your requirements
3. **Scale if Needed:** Add more instances for higher throughput
4. **Production Planning:** Use results for capacity planning
5. **Documentation:** See [HR Realistic Scenario](wiki/benchmarks/HR_REALISTIC_SCENARIO.md) for details

## Related Documentation

- [HR Realistic Scenario](wiki/benchmarks/HR_REALISTIC_SCENARIO.md) - Detailed documentation
- [Optimization Journey](wiki/optimization/OPTIMIZATION_JOURNEY_COMPLETE.md) - Performance improvements
- [Quality Report](wiki/deployment/QUALITY_REPORT.md) - Quality validation
- [README](README.md) - Main documentation

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review service logs: `docker-compose logs pii-service`
3. Verify Redis connectivity: `docker-compose exec redis redis-cli ping`
4. Check system resources: `docker stats`

---

**Ready to test?** Run: `bash scripts/run_hr_benchmark.sh`
