# PII Anonymization Service

A high-performance Python 3.12 microservice for reversible PII tokenization and de-tokenization across structured records and unstructured text.

## Current Status

- Structured processing is optimized for high-throughput REST and gRPC workloads.
- Unstructured processing now uses a local detector pipeline instead of external LLM APIs.
- The default unstructured path is `hybrid`: deterministic recognizers for strict identifiers plus optional local Greek NER for semantic entities.
- Unstructured support is currently exposed over REST only. gRPC is structured-only.

## Features

- Structured tokenization for JSON records with policy-driven field rules
- Unstructured anonymization with local detector backends
- Reversible tokenization backed by AES-256-GCM and Redis
- Multi-tenant YAML policy model with hot reload
- REST plus gRPC support for structured data
- Docker single-instance and multi-instance deployment
- Health checks, Prometheus metrics, and structured logging

## Architecture

### Structured path

```text
record -> structured tokenizer -> crypto engine + token store
```

### Unstructured path

```text
text -> detector pipeline -> findings -> overlap resolution -> tokenize/redact
```

Default detector stages:

1. Prefilter
2. Deterministic recognizers for identifiers such as email, phone, AFM, AMKA
3. Optional semantic detector using a local Hugging Face model for entities such as `PERSON`, `ORG`, `LOCATION`

## Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv)
- Docker and Docker Compose
- Redis 7.2+ if you are not using Compose

For local unstructured semantic detection outside Docker, install the local model dependencies too:

```bash
uv sync --extra unstructured-local
```

## Installation

```bash
git clone <repository-url>
cd anomymization
uv sync
```

## Configuration

Copy [.env.example](/C:/Users/thano/projects/anomymization/.env.example) to `.env` and set at least:

```env
CUSTOMER_DB_KEY=...
ANALYTICS_DB_KEY=...
HR_SYSTEM_KEY=...
API_KEY=your-api-key
REDIS_PASSWORD=redis_dev_password
```

Generate encryption keys with:

```bash
uv run python scripts/generate_key.py
```

### Policy Model

See [example_policy.yaml](/C:/Users/thano/projects/anomymization/policies/example_policy.yaml) for the current schema.

Structured policy example:

```yaml
structured:
  pii_fields:
    - name: "email"
      deterministic: true
      token_format: "uuid"
```

Unstructured policy example:

```yaml
unstructured:
  detector: "hybrid"

  semantic_detector:
    provider: "huggingface"
    model: "amichailidis/bert-base-greek-uncased-v1-finetuned-ner"
    threshold: 0.85
    enabled_for:
      - "PERSON"
      - "ORG"
      - "LOCATION"

  entities:
    - type: "EMAIL"
      detection: ["deterministic"]
      action: "tokenize"
    - type: "PERSON"
      detection: ["semantic"]
      action: "redact"
      min_confidence: 0.90
```

## Running the Service

### Single instance

```bash
docker compose up -d --build
docker compose logs -f pii-service
```

Endpoints:

- REST: `http://localhost:8000`
- Structured gRPC: `localhost:50051`
- Health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`

### Multi instance

```bash
docker compose -f docker-compose.multi.yml up -d --build
docker compose -f docker-compose.multi.yml logs -f
```

In multi-instance mode:

- Nginx exposes REST on `http://localhost:8000`
- Envoy exposes structured gRPC on `localhost:50051`
- Redis is shared across all service instances

### Local development

```bash
uv run python -m pii_service.main
```

If you need unstructured semantic detection locally, prefer:

```bash
uv sync --extra unstructured-local
uv run python -m pii_service.main
```

## API Usage

All non-health endpoints require:

```text
Authorization: Bearer <api-key>
X-System-ID: <system-id>
```

### Structured anonymization

```bash
curl -X POST http://localhost:8000/structured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '[
    {
      "email": "user@example.com",
      "name": "John Doe",
      "ssn": "123-45-6789"
    }
  ]'
```

### Unstructured anonymization

```bash
curl -X POST http://localhost:8000/unstructured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "text": "Ο Γιάννης Παπαδόπουλος έχει email user@example.com και τηλέφωνο 6912345678",
    "return_entity_map": true
  }'
```

### Unstructured de-anonymization

```bash
curl -X POST http://localhost:8000/unstructured/deanonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "text": "Contact token 550e8400-e29b-41d4-a716-446655440000"
  }'
```

## gRPC Usage

Structured gRPC APIs currently available:

1. `StructuredAnonymizerV2`
2. `StructuredAnonymizer` legacy streaming API

Unstructured gRPC is not implemented at this stage.

## Benchmarking

### Recommended benchmark entrypoints

For clean runs with a fresh Redis state, use the PowerShell wrappers in [scripts](/C:/Users/thano/projects/anomymization/scripts):

```powershell
.\scripts\Run-StructuredSingleBenchmark.ps1
.\scripts\Run-StructuredMultiBenchmark.ps1
.\scripts\Run-UnstructuredSingleBenchmark.ps1
.\scripts\Run-UnstructuredMultiBenchmark.ps1
```

These scripts:

- stop existing single and multi stacks
- remove Redis volumes for a clean benchmark state
- start the correct Docker stack
- wait for `/health`
- warm up the unstructured detector path before measuring
- save timestamped JSON results under `data/benchmark_results`

### Unstructured quality check

To validate detection quality on known text samples, use:

```powershell
.\scripts\Run-UnstructuredQualityCheck.ps1 `
  -Text "Ο Γιάννης Παπαδόπουλος έχει email user@example.com και τηλέφωνο 6912345678" `
  -ExpectedValue "Γιάννης Παπαδόπουλος" `
  -ExpectedValue "user@example.com" `
  -ExpectedValue "6912345678"
```

You can also use files:

```powershell
.\scripts\Run-UnstructuredQualityCheck.ps1 `
  -TextPath .\data\sample_text.txt `
  -ExpectedValuesPath .\data\expected_values.json `
  -OutputPath .\data\benchmark_results\unstructured-quality-report.json
```

The quality check reports:

- matched expected values
- missed expected values
- unexpected tokenized values
- overall success rate

This is useful for catching regressions in the unstructured detector pipeline separately from latency/throughput SLAs.

### Direct benchmark commands

```bash
uv run python benchmarks/benchmark_structured.py \
  --base-url http://localhost:8000 \
  --grpc-host localhost:50051 \
  --system-id customer_db \
  --api-key your-api-key

uv run python benchmarks/benchmark_unstructured.py \
  --base-url http://localhost:8000 \
  --system-id customer_db \
  --api-key your-api-key \
  --requests 200 \
  --concurrency 20
```

### Current interpretation

- Structured benchmark numbers are the main throughput/SLA validation path.
- Unstructured benchmark numbers should be evaluated separately from structured, because the semantic detector stage has different latency characteristics.
- The first unstructured request after startup may include model load and download cost if the model is not cached.

## Development

### Tests

```bash
uv run pytest
```

### Formatting and linting

```bash
uv run black src tests
uv run ruff check src tests
uv run mypy src
```

## Documentation

Useful guides:

- [Quick Start](/C:/Users/thano/projects/anomymization/wiki/implementation/QUICKSTART.md)
- [Benchmarking Guide](/C:/Users/thano/projects/anomymization/wiki/benchmarks/BENCHMARKING.md)
- [Implementation Summary](/C:/Users/thano/projects/anomymization/wiki/implementation/IMPLEMENTATION_SUMMARY.md)
- [Documentation Wiki](/C:/Users/thano/projects/anomymization/wiki/README.md)

## Data and Results

Generated benchmark artifacts are stored under [data](/C:/Users/thano/projects/anomymization/data), especially:

- [data/benchmark_results](/C:/Users/thano/projects/anomymization/data/benchmark_results)
- [data/profiling](/C:/Users/thano/projects/anomymization/data/profiling)

## License

This project is licensed under the MIT License. See [LICENSE](/C:/Users/thano/projects/anomymization/LICENSE).
