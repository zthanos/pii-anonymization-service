# HR Realistic Scenario Benchmark

## Overview

This benchmark validates the PII Anonymization Service with a realistic HR system scenario, processing 360,000 employee records with 12 properties each.

## Scenario Details

### Dataset Characteristics

- **Total Records:** 360,000 employees
- **Properties per Record:** 12
- **PII Fields:** 12 (all properties contain sensitive data)
- **System ID:** `hr_system`
- **Batch Size:** 5,000 records per batch

### Record Structure

Each employee record contains:

1. **Employee Identification**
   - `employee_id` - Unique employee identifier (prefixed token)
   - `ssn` - Social Security Number (deterministic token)
   - `email` - Corporate email address (UUID token)
   - `phone` - Phone number (UUID token, nullable)

2. **Personal Information**
   - `first_name` - First name (prefixed token)
   - `last_name` - Last name (prefixed token)
   - `date_of_birth` - Date of birth (deterministic token)

3. **Payroll Information** (can expose identity)
   - `salary` - Annual salary (UUID token)
   - `bank_account` - Bank account number (deterministic token)

4. **Position Information** (can expose identity for unique roles)
   - `position` - Job title (prefixed token)
   - `department` - Department name (prefixed token)

5. **Benefits Information**
   - `emergency_contact` - Emergency contact details (UUID token, nullable)

### Why This Scenario is Realistic

1. **Large Scale:** 360,000 records represents a large enterprise
2. **Deep Records:** 12 properties per record is typical for HR systems
3. **Mixed Token Types:** Uses deterministic, non-deterministic, and prefixed tokens
4. **Nullable Fields:** Some fields can be null (phone, emergency_contact)
5. **Identity Exposure Risk:** Salary, position, and department can expose identity when combined
6. **Long TTL:** 1-year token TTL is realistic for HR compliance requirements

## Running the Benchmark

### Prerequisites

1. Service must be running:
   ```bash
   # Single instance
   docker-compose up -d
   
   # Or multi-instance (recommended for best performance)
   docker-compose -f docker-compose.multi.yml up -d
   ```

2. Environment variable `HR_SYSTEM_KEY` must be set (script will generate if missing)

### Quick Start

Run the automated script:

```bash
bash scripts/run_hr_benchmark.sh
```

This script will:
1. Check if service is running
2. Generate encryption key if needed
3. Generate 360,000 test records if not already present
4. Restart service to load HR policy
5. Run the benchmark
6. Save results to `data/benchmark_results/hr_realistic_benchmark.json`

### Manual Steps

If you prefer to run manually:

```bash
# 1. Generate encryption key
export HR_SYSTEM_KEY=$(python scripts/generate_key.py)
echo "HR_SYSTEM_KEY=$HR_SYSTEM_KEY" >> .env

# 2. Generate test data
python scripts/generate_hr_test_data.py 360000

# 3. Restart service
docker-compose restart pii-service

# 4. Run benchmark
python benchmarks/benchmark_hr_realistic.py
```

## Expected Results

### Single Instance Performance

Based on current performance metrics (18,673 rec/sec):

- **Anonymization Time:** ~19.3 seconds
- **De-anonymization Time:** ~12.9 seconds (faster, <3ms p95)
- **Total Time:** ~32.2 seconds
- **Throughput:** ~11,180 records/sec (combined)

### Multi-Instance Performance (4 instances)

Based on current performance metrics (59,151 rec/sec):

- **Anonymization Time:** ~6.1 seconds
- **De-anonymization Time:** ~4.1 seconds
- **Total Time:** ~10.2 seconds
- **Throughput:** ~35,294 records/sec (combined)

### Actual Results

Run the benchmark to get actual results for your environment. Results will include:

- Total time for anonymization
- Total time for de-anonymization
- Throughput (records/sec) for both operations
- Batch-level statistics (min, max, mean, median times)
- Data integrity verification (100% reversibility check)

## Benchmark Output

The benchmark provides detailed progress output:

```
==========================================
HR REALISTIC SCENARIO BENCHMARK
==========================================

Scenario:
  - 360,000 employee records
  - 12 properties per record
  - PII fields: employee_id, ssn, email, phone, first_name, last_name,
                date_of_birth, salary, bank_account, position, department,
                emergency_contact
  - Batch size: 5,000 records
  - System: hr_system

✅ Connected to gRPC server at localhost:50051

📂 Loading test data from data/test_data/hr_test_data_360k.ndjson...
✅ Loaded 360,000 records

🔒 Starting anonymization...
  Total records: 360,000
  Batch size: 5,000
  System ID: hr_system
  Progress: 5,000/360,000 (1.4%) - Batch time: 0.27s - Throughput: 18,519 rec/sec
  Progress: 10,000/360,000 (2.8%) - Batch time: 0.26s - Throughput: 19,231 rec/sec
  ...
  Progress: 360,000/360,000 (100.0%) - Batch time: 0.27s - Throughput: 18,519 rec/sec

✅ Anonymization complete!
  Total time: 19.28 seconds
  Average throughput: 18,672 records/sec
  Successful: 360,000
  Failed: 0

🔓 Starting de-anonymization...
  Total records: 360,000
  Batch size: 5,000
  System ID: hr_system
  Progress: 5,000/360,000 (1.4%) - Batch time: 0.18s - Throughput: 27,778 rec/sec
  ...

✅ De-anonymization complete!
  Total time: 12.86 seconds
  Average throughput: 27,993 records/sec
  Successful: 360,000
  Failed: 0

🔍 Verifying data reversibility...
  Checking 100 random samples...
✅ All 100 samples match perfectly!
  Data reversibility: 100%

==========================================
BENCHMARK SUMMARY
==========================================

📊 Total Records: 360,000
📊 Properties per Record: 12
📊 PII Fields: 12

⏱️  Anonymization Time: 19.28 seconds
⚡ Anonymization Throughput: 18,672 records/sec

⏱️  De-anonymization Time: 12.86 seconds
⚡ De-anonymization Throughput: 27,993 records/sec

⏱️  Total Time: 32.14 seconds
✅ Data Integrity: 100%

💾 Results saved to data/benchmark_results/hr_realistic_benchmark.json

==========================================
✅ BENCHMARK COMPLETE
==========================================
```

## Results File

Results are saved in JSON format with detailed statistics:

```json
{
  "scenario": {
    "name": "HR Realistic Scenario",
    "total_records": 360000,
    "properties_per_record": 12,
    "pii_fields": 12,
    "system_id": "hr_system",
    "batch_size": 5000
  },
  "anonymization": {
    "total_records": 360000,
    "successful_records": 360000,
    "failed_records": 0,
    "total_time_seconds": 19.28,
    "total_time_formatted": "19.28 seconds",
    "average_throughput": 18672.0,
    "batch_times": {
      "min": 0.25,
      "max": 0.29,
      "mean": 0.27,
      "median": 0.27
    },
    "batch_throughputs": {
      "min": 17241.0,
      "max": 20000.0,
      "mean": 18519.0
    }
  },
  "deanonymization": {
    "total_records": 360000,
    "successful_records": 360000,
    "failed_records": 0,
    "total_time_seconds": 12.86,
    "total_time_formatted": "12.86 seconds",
    "average_throughput": 27993.0,
    "batch_times": {
      "min": 0.17,
      "max": 0.19,
      "mean": 0.18,
      "median": 0.18
    },
    "batch_throughputs": {
      "min": 26316.0,
      "max": 29412.0,
      "mean": 27778.0
    }
  },
  "verification": {
    "success": true,
    "verified_samples": 100
  },
  "summary": {
    "total_time_seconds": 32.14,
    "total_time_formatted": "32.14 seconds",
    "anonymization_time": "19.28 seconds",
    "deanonymization_time": "12.86 seconds",
    "data_integrity": "100%"
  }
}
```

## Performance Analysis

### Anonymization vs De-anonymization

De-anonymization is typically faster because:
- No encryption needed (only decryption)
- No token generation
- Simpler Redis operations (read-only)
- Lower CPU usage

### Batch Processing Efficiency

The benchmark processes records in batches of 5,000:
- Minimizes gRPC overhead (1 message per 5,000 records)
- Enables Redis pipelining for bulk operations
- Maintains consistent throughput across batches

### Scalability

For even better performance:
- Use multi-instance deployment (4 instances = 3.2x improvement)
- Increase concurrency (16 concurrent requests optimal)
- Consider Redis optimization (Phase 4) for 1.3-1.5x improvement

## Use Cases

This benchmark validates the service for:

1. **Batch HR Data Processing**
   - Nightly anonymization of employee records
   - Compliance reporting with anonymized data
   - Data warehouse ETL pipelines

2. **HR Analytics**
   - Anonymize data for analytics teams
   - De-anonymize for authorized access
   - Maintain data lineage and reversibility

3. **Compliance & Auditing**
   - GDPR right to erasure (token expiration)
   - SOC 2 data protection requirements
   - HIPAA-like controls for sensitive HR data

4. **Data Sharing**
   - Share anonymized data with third parties
   - Selective de-anonymization for authorized users
   - Cross-border data transfer compliance

## Troubleshooting

### Service Not Running

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs pii-service

# Restart service
docker-compose restart pii-service
```

### Test Data Generation Fails

```bash
# Check disk space
df -h

# Manually generate smaller dataset for testing
python scripts/generate_hr_test_data.py 10000
```

### Benchmark Fails

```bash
# Check gRPC connectivity
grpcurl -plaintext localhost:50051 list

# Verify policy loaded
curl http://localhost:8000/health

# Check Redis connectivity
docker-compose exec redis redis-cli ping
```

### Performance Lower Than Expected

1. Check system resources (CPU, memory, disk I/O)
2. Verify Redis is not overloaded
3. Consider using multi-instance deployment
4. Check network latency (Docker bridge overhead)

## Next Steps

After running this benchmark:

1. **Review Results:** Analyze the JSON output for your environment
2. **Compare Performance:** Compare against targets (50k rec/sec multi-instance)
3. **Optimize if Needed:** Consider Phase 4 (Redis optimization) if needed
4. **Production Planning:** Use results to estimate production capacity
5. **Capacity Planning:** Calculate required instances for your workload

## Related Documentation

- [Optimization Journey](../optimization/OPTIMIZATION_JOURNEY_COMPLETE.md)
- [Quality Report](../deployment/QUALITY_REPORT.md)
- [Benchmarking Guide](BENCHMARKING.md)
- [Performance Targets](../../README.md#performance-targets)
