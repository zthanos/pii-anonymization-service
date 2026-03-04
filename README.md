# PII Anonymization Service

A high-performance Python 3.12 microservice for tokenization and de-tokenization of personally identifiable information (PII) in both structured and unstructured data.

## Features

- **Structured Data Tokenization**: Process JSON records at 50k+ records/second via gRPC streaming with <5ms p95 latency
- **Unstructured Data Tokenization**: LLM-assisted PII extraction from free-form text using Anthropic Claude API
- **Reversible Tokenization**: AES-256-GCM encrypted storage enabling secure de-tokenization
- **Policy-Driven Configuration**: YAML-based multi-tenant configuration with hot-reload support
- **Dual Protocol Support**: REST API and gRPC streaming for maximum flexibility
- **Production-Ready**: Health checks, Prometheus metrics, structured logging, circuit breakers, and retry logic

## Performance Targets

- **Throughput**: 50,000+ records/second via gRPC streaming
- **Latency**: <5ms p95 for anonymization, <3ms p95 for de-anonymization
- **Scalability**: Stateless design with Redis backend for horizontal scaling

## Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv) - Fast Python package manager
- Docker and Docker Compose (for containerized deployment)
- Redis 7.2+ (provided via docker-compose)
- Anthropic API key (for unstructured data tokenization)

## Installation

### 1. Install UV

UV is a fast Python package and project manager. Install it using:

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone the Repository

```bash
git clone <repository-url>
cd pii-anonymization-service
```

### 3. Install Dependencies

```bash
uv sync
```

This will create a virtual environment and install all dependencies from `uv.lock`.

## Configuration

### Environment Variables

Create a `.env` file in the project root (see `.env.example` for reference):

```bash
# Redis configuration
REDIS_URL=redis://localhost:6379/0
REDIS_POOL_SIZE=50

# Policy configuration
POLICY_PATH=policies/example_policy.yaml

# Encryption keys (generate with scripts/generate_key.py)
CUSTOMER_DB_KEY=<base64-encoded-32-byte-key>
ANALYTICS_DB_KEY=<base64-encoded-32-byte-key>

# LLM API configuration
ANTHROPIC_API_KEY=<your-anthropic-api-key>

# Logging
LOG_LEVEL=INFO

# API authentication
API_KEY=<your-api-key>

# Server ports
HTTP_PORT=8000
GRPC_PORT=50051

# TLS configuration (optional)
SSL_KEYFILE=
SSL_CERTFILE=
SSL_CA_CERTS=
```

### Generate Encryption Keys

Generate secure 32-byte encryption keys for each system:

```bash
uv run python scripts/generate_key.py
```

Copy the output and add it to your `.env` file.

### Policy Configuration

Edit `policies/example_policy.yaml` to configure PII fields and tokenization rules for your systems:

```yaml
systems:
  - system_id: "customer_db"
    encryption_key_ref: "env:CUSTOMER_DB_KEY"
    
    structured:
      pii_fields:
        - name: "email"
          deterministic: true
          token_format: "uuid"
          nullable: false
        
        - name: "ssn"
          deterministic: true
          token_format: "deterministic"
          nullable: false
      
      token_ttl_seconds: 86400  # 24 hours
    
    unstructured:
      llm_model: "claude-3-haiku-20240307"
      entity_types: ["PERSON", "EMAIL", "PHONE", "SSN", "ADDRESS"]
      rate_limit_per_minute: 100
      max_text_length: 50000
```

## Running the Service

### Option 1: Docker Compose (Recommended)

The easiest way to run the service with all dependencies:

```bash
# Start the service and Redis
docker-compose up -d

# View logs
docker-compose logs -f pii-service

# Stop the service
docker-compose down
```

The service will be available at:
- REST API: http://localhost:8000
- gRPC: localhost:50051
- Health check: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

### Option 2: Local Development

Run Redis separately and start the service locally:

```bash
# Start Redis (in a separate terminal)
docker run -d -p 6379:6379 redis:7.2-alpine

# Run the service
uv run python -m pii_service.main
```

## API Usage

### Health Check

```bash
curl http://localhost:8000/health
```

### Structured Data Anonymization (REST)

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

Response (NDJSON):
```json
{"record":{"email":"550e8400-e29b-41d4-a716-446655440000","name":"John Doe","ssn":"a1b2c3d4...","_pii_anonymized":true},"token_ids":["550e8400-e29b-41d4-a716-446655440000","a1b2c3d4..."],"error":null}
```

### Structured Data De-anonymization (REST)

```bash
curl -X POST http://localhost:8000/structured/deanonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '[
    {
      "email": "550e8400-e29b-41d4-a716-446655440000",
      "name": "John Doe",
      "ssn": "a1b2c3d4..."
    }
  ]'
```

### Unstructured Data Anonymization

```bash
curl -X POST http://localhost:8000/unstructured/anonymize \
  -H "Content-Type: application/json" \
  -H "X-System-ID: customer_db" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "text": "Contact John Doe at john@example.com or call 555-1234",
    "return_entity_map": true
  }'
```

### Policy Hot-Reload

```bash
curl -X POST http://localhost:8000/admin/policy/reload \
  -H "Authorization: Bearer your-api-key"
```

### Prometheus Metrics

```bash
curl http://localhost:8000/metrics
```

## gRPC Usage

For high-throughput scenarios, use the gRPC streaming API:

```python
import grpc
from pii_service.proto import (
    StructuredAnonymizerStub,
    AnonymizeRequest,
)

# Create channel
channel = grpc.insecure_channel('localhost:50051')
stub = StructuredAnonymizerStub(channel)

# Stream requests
def request_generator():
    for i in range(1000):
        yield AnonymizeRequest(
            system_id="customer_db",
            record_id=f"record_{i}",
            record_json='{"email":"user@example.com"}',
        )

# Process responses
for response in stub.Anonymize(request_generator()):
    if response.error:
        print(f"Error: {response.error}")
    else:
        print(f"Anonymized: {response.anonymized_json}")
```

## Development

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/pii_service --cov-report=html

# Run specific test file
uv run pytest tests/test_structured_tokenizer.py
```

### Code Formatting

```bash
# Format code with black
uv run black src tests

# Lint with ruff
uv run ruff check src tests

# Type check with mypy
uv run mypy src
```

## Benchmarking

Run performance benchmarks to validate throughput and latency targets:

```bash
# Run structured data benchmarks
uv run python benchmarks/benchmark_structured.py

# Generate benchmark report
uv run python scripts/generate_benchmark_report.py
```

Benchmark results will be saved to:
- `benchmark_results.json` - Raw benchmark data
- `benchmark_report.html` - HTML report with visualizations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
└─────────────┬───────────────────────┬───────────────────────┘
              │                       │
              │ REST API              │ gRPC Streaming
              │                       │
┌─────────────▼───────────────────────▼───────────────────────┐
│              PII Anonymization Service                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   FastAPI    │  │    gRPC      │  │    Admin     │     │
│  │   Server     │  │   Server     │  │  Endpoints   │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                           │                                 │
│         ┌─────────────────▼─────────────────┐              │
│         │   Structured/Unstructured         │              │
│         │      Tokenizers                   │              │
│         └─────────────────┬─────────────────┘              │
│                           │                                 │
│         ┌─────────────────▼─────────────────┐              │
│         │   Crypto Engine + Token Store     │              │
│         └─────────────────┬─────────────────┘              │
└───────────────────────────┼─────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │   Redis (Token Store) │
                └───────────────────────┘
```

## Security

- All PII values are encrypted with AES-256-GCM before storage
- Encryption keys are loaded from environment variables or mounted secrets
- Service runs as non-root user (UID 1000) in Docker container
- TLS 1.2+ support for all HTTP and gRPC communications
- API key authentication for all non-health endpoints
- No plaintext PII is ever logged

## Troubleshooting

### Service won't start

1. Check Redis connectivity:
   ```bash
   docker-compose logs redis
   ```

2. Verify encryption keys are set:
   ```bash
   echo $CUSTOMER_DB_KEY
   ```

3. Check policy file syntax:
   ```bash
   uv run python -c "import yaml; yaml.safe_load(open('policies/example_policy.yaml'))"
   ```

### Performance issues

1. Check Redis latency:
   ```bash
   redis-cli --latency
   ```

2. Monitor metrics:
   ```bash
   curl http://localhost:8000/metrics | grep latency
   ```

3. Increase connection pool size:
   ```bash
   export REDIS_POOL_SIZE=100
   ```

## Documentation

For detailed documentation about the optimization journey, implementation details, and performance analysis, see the [Documentation Wiki](./wiki/).

### Quick Links
- [Optimization Journey](./wiki/optimization/OPTIMIZATION_JOURNEY_COMPLETE.md) - Complete performance optimization story (3.5k → 59k rec/sec)
- [Phase 1: Batch Messages](./wiki/optimization/PHASE_1_COMPLETE.md) - 5.2x improvement through batching
- [Phase 3: Multi-Instance](./wiki/optimization/PHASE_3_MULTI_INSTANCE_COMPLETE.md) - 3.2x improvement through horizontal scaling
- [gRPC Optimization Guide](./wiki/implementation/GRPC_OPTIMIZATION_GUIDE.md) - gRPC tuning best practices
- [CQRS Analysis](./wiki/analysis/CQRS_ANALYSIS.md) - Architectural pattern evaluation

## Data Directory

Test data, benchmark results, and profiling data are organized in the [data/](./data/) directory. See [data/README.md](./data/README.md) for details.

- `data/benchmark_results/` - Performance benchmark results
- `data/test_data/` - Test datasets (NDJSON)
- `data/test_results/` - Test execution results
- `data/profiling/` - Performance profiling data

**Note:** The data directory is git-ignored and files are generated during testing/benchmarking.

## License

[Your License Here]

## Support

For issues and questions, please open an issue on GitHub.
