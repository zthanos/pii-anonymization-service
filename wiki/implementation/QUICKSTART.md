# Quick Start Guide

Get the service running quickly with the current structured and unstructured architecture.

## Prerequisites

- Docker and Docker Compose
- UV

Optional for local unstructured semantic detection outside Docker:

```bash
uv sync --extra unstructured-local
```

## Step 1: Generate Encryption Keys

```bash
uv run python scripts/generate_key.py
```

You need keys for all systems in the example policy:

- `CUSTOMER_DB_KEY`
- `ANALYTICS_DB_KEY`
- `HR_SYSTEM_KEY`

## Step 2: Configure `.env`

Copy [.env.example](/C:/Users/thano/projects/anomymization/.env.example) to `.env` and set at least:

```env
CUSTOMER_DB_KEY=...
ANALYTICS_DB_KEY=...
HR_SYSTEM_KEY=...
API_KEY=test_api_key_12345
REDIS_PASSWORD=redis_dev_password
```

## Step 3: Start the Service

Single instance:

```bash
docker compose up -d --build
docker compose logs -f pii-service
```

Multi instance:

```bash
docker compose -f docker-compose.multi.yml up -d --build
docker compose -f docker-compose.multi.yml logs -f
```

## Step 4: Verify Health

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "policy_version": "..."
}
```

## Step 5: Test Structured Anonymization

```bash
curl -X POST http://localhost:8000/structured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer test_api_key_12345" \
  -d '[
    {
      "email": "john.doe@example.com",
      "name": "John Doe",
      "ssn": "123-45-6789"
    }
  ]'
```

## Step 6: Test Unstructured Anonymization

```bash
curl -X POST http://localhost:8000/unstructured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer test_api_key_12345" \
  -d '{
    "text": "Ο Γιάννης Παπαδόπουλος έχει email user@example.com και τηλέφωνο 6912345678",
    "return_entity_map": false
  }'
```

Notes:

- Unstructured uses a local detector pipeline, not an external LLM API.
- The first unstructured request can be slower because the semantic model may load or download.
- Unstructured is currently REST-only.

## Step 7: Run Benchmarks

Recommended clean benchmark entrypoints on Windows PowerShell:

```powershell
.\scripts\Run-StructuredSingleBenchmark.ps1
.\scripts\Run-StructuredMultiBenchmark.ps1
.\scripts\Run-UnstructuredSingleBenchmark.ps1
.\scripts\Run-UnstructuredMultiBenchmark.ps1
```

These scripts reset Redis state before the run, so the results are more consistent.

## Troubleshooting

### Service does not start

Check resolved Compose config:

```bash
docker compose config
```

Common cause:

- missing `HR_SYSTEM_KEY`

### Unstructured returns detector/model errors

Inside Docker, the image already installs the `unstructured-local` dependencies. For local host execution, make sure you ran:

```bash
uv sync --extra unstructured-local
```

### Health returns `503`

This usually means Redis is still loading its dataset. Wait a bit and retry `/health`.

## Next Reading

- [README](/C:/Users/thano/projects/anomymization/README.md)
- [Benchmarking Guide](/C:/Users/thano/projects/anomymization/wiki/benchmarks/BENCHMARKING.md)
