# Quick Start Guide

Get the PII Anonymization Service running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Anthropic API key (optional, for unstructured data tokenization)

## Step 1: Generate Encryption Keys

```bash
# Generate encryption keys
uv run python scripts/generate_key.py
```

Copy the output keys for the next step.

## Step 2: Configure Environment

Create a `.env` file in the project root:

```bash
# Copy the example
cp .env.example .env

# Edit .env and add your keys
nano .env  # or use your favorite editor
```

Required variables:
- `CUSTOMER_DB_KEY` - Paste the generated key
- `ANALYTICS_DB_KEY` - Paste the generated key
- `ANTHROPIC_API_KEY` - Your Anthropic API key (optional)
- `API_KEY` - Set a secure API key for authentication

## Step 3: Start the Service

```bash
# Start with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f pii-service
```

The service will be available at:
- REST API: http://localhost:8000
- gRPC: localhost:50051

## Step 4: Test the Service

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "redis_connected": true,
  "policy_version": "1234567890"
}
```

### Anonymize Structured Data

```bash
curl -X POST http://localhost:8000/structured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '[
    {
      "email": "john.doe@example.com",
      "name": "John Doe",
      "ssn": "123-45-6789"
    }
  ]'
```

Expected response (NDJSON):
```json
{"record":{"email":"550e8400-e29b-41d4-a716-446655440000","name":"John Doe","ssn":"a1b2c3d4e5f6...","_pii_anonymized":true},"token_ids":["550e8400-...","a1b2c3d4..."],"error":null}
```

### De-anonymize Data

```bash
curl -X POST http://localhost:8000/structured/deanonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '[
    {
      "email": "550e8400-e29b-41d4-a716-446655440000",
      "ssn": "a1b2c3d4e5f6..."
    }
  ]'
```

## Step 5: Monitor the Service

### View Metrics

```bash
curl http://localhost:8000/metrics
```

### View Logs

```bash
docker-compose logs -f pii-service
```

## Troubleshooting

### Service won't start

1. Check Redis is running:
   ```bash
   docker-compose ps redis
   ```

2. Check environment variables:
   ```bash
   docker-compose config
   ```

3. View detailed logs:
   ```bash
   docker-compose logs pii-service
   ```

### Authentication errors

Make sure you're using the correct API key:
```bash
# Check your .env file
grep API_KEY .env

# Use it in requests
curl -H "Authorization: Bearer your-api-key-here" ...
```

### Redis connection errors

1. Check Redis is healthy:
   ```bash
   docker-compose exec redis redis-cli ping
   ```

2. Verify Redis password matches in docker-compose.yml and .env

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Configure your own policy in `policies/example_policy.yaml`
- Set up TLS for production use
- Run benchmarks to validate performance

## Stopping the Service

```bash
# Stop the service
docker-compose down

# Stop and remove volumes (clears Redis data)
docker-compose down -v
```
