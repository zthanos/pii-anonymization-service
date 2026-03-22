# Benchmarking Guide

This guide reflects the current benchmark flow for the service.

## What We Benchmark Today

### Structured

- REST structured anonymization and de-anonymization
- Structured gRPC V1/V2 throughput path
- Single-instance and multi-instance Docker stacks

### Unstructured

- REST unstructured anonymization and de-anonymization
- Single-instance and multi-instance Docker stacks
- Local detector pipeline behavior, including semantic detector latency

Unstructured gRPC is not implemented yet.

## Clean Benchmark Principle

Benchmark numbers are much noisier if Redis contains old state or if the service is still cold-starting.

Recommended practice:

1. stop existing stacks
2. remove Redis volume
3. start only the stack you want to test
4. wait for `/health`
5. warm up the unstructured path before measuring

The PowerShell wrappers in [scripts](/C:/Users/thano/projects/anomymization/scripts) do this for you.

## Recommended Commands

### Structured single

```powershell
.\scripts\Run-StructuredSingleBenchmark.ps1
```

### Structured multi

```powershell
.\scripts\Run-StructuredMultiBenchmark.ps1
```

### Unstructured single

```powershell
.\scripts\Run-UnstructuredSingleBenchmark.ps1
```

### Unstructured multi

```powershell
.\scripts\Run-UnstructuredMultiBenchmark.ps1
```

### Unstructured quality validation

```powershell
.\scripts\Run-UnstructuredQualityCheck.ps1 `
  -Text "Ο Γιάννης Παπαδόπουλος έχει email user@example.com και τηλέφωνο 6912345678" `
  -ExpectedValue "Γιάννης Παπαδόπουλος" `
  -ExpectedValue "user@example.com" `
  -ExpectedValue "6912345678"
```

## What The Scripts Do

Each script:

- brings down single and multi Compose stacks
- removes Redis volumes with `docker compose down -v`
- starts the target stack with rebuild by default
- waits until `http://localhost:8000/health` returns `200`
- for unstructured, sends a warm-up request before the benchmark
- writes timestamped JSON results to `data/benchmark_results`

The quality script checks correctness rather than throughput:

- sends a plain text sample to `/unstructured/anonymize`
- compares the response against expected values
- calculates matched, missed, unexpected detections, and overall success rate
- optionally saves a JSON report

## Direct Benchmark Commands

### Structured

```bash
uv run python benchmarks/benchmark_structured.py \
  --base-url http://localhost:8000 \
  --grpc-host localhost:50051 \
  --system-id customer_db \
  --api-key test_api_key_12345 \
  --output data/benchmark_results/structured-manual.json
```

### Unstructured

```bash
uv run python benchmarks/benchmark_unstructured.py \
  --base-url http://localhost:8000 \
  --system-id customer_db \
  --api-key test_api_key_12345 \
  --requests 200 \
  --concurrency 20 \
  --throughput-sla 200 \
  --p95-sla-ms 150 \
  --output data/benchmark_results/unstructured-manual.json
```

### Unstructured quality check

```powershell
.\scripts\Run-UnstructuredQualityCheck.ps1 `
  -TextPath .\data\sample_text.txt `
  -ExpectedValuesPath .\data\expected_values.json `
  -OutputPath .\data\benchmark_results\unstructured-quality-report.json
```

Example expected values file:

```json
[
  "user@example.com",
  "6912345678",
  { "value": "Γιάννης Παπαδόπουλος", "type": "PERSON" }
]
```

## Important Notes For Unstructured Benchmarks

- The unstructured detector path is local and policy-driven.
- Default policy uses deterministic recognizers plus a Hugging Face Greek NER model.
- The first request after startup can include model download/loading time.
- Long texts may hit a very different latency regime than short identifier-heavy texts.
- Structured and unstructured SLAs should be tracked separately.

## Result Files

Results are stored under [data/benchmark_results](/C:/Users/thano/projects/anomymization/data/benchmark_results).

Typical outputs:

- `structured-single-<timestamp>.json`
- `structured-multi-<timestamp>.json`
- `unstructured-single-<timestamp>.json`
- `unstructured-multi-<timestamp>.json`

## Current Interpretation Guidance

### Structured

These numbers are the main validation path for high-throughput service claims.

### Unstructured

Use these numbers to track:

- local detector throughput
- semantic detector cold start cost
- latency by text class and text length
- single vs multi-instance scaling behavior

Do not compare structured and unstructured throughput directly as if they were the same workload shape.

For correctness/regression tracking, use the quality check script in parallel with the performance benchmarks.

## Troubleshooting

### `503 Service Unavailable` on `/health`

Redis is often still loading its dataset. Wait and retry, or use the PowerShell wrappers which already wait for health.

### `401` during benchmark

The benchmark API key does not match the running stack. Check:

```bash
docker compose config
```

### Semantic detector dependency/model errors

If you are running outside Docker, install:

```bash
uv sync --extra unstructured-local
```

### Benchmark is noisy between runs

Use the PowerShell wrappers so each run starts from a clean Redis state.
