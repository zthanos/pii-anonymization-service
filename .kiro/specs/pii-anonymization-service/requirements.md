# Requirements Document

## Introduction

The PII Anonymization Service is a Python 3.12 containerized service that provides near real-time tokenization and de-tokenization for structured data via REST and gRPC streaming endpoints, and LLM-assisted PII extraction and anonymization for unstructured data. The service uses YAML policy-driven configuration for PII field identification, encryption keys, and tokenization rules, with Redis as the persistence layer for token-to-encrypted-value mappings using AES-256-GCM encryption. The project uses UV as the Python package and project manager for dependency management, virtual environment handling, and build tooling.

## Glossary

- **PII_Service**: The Python FastAPI + gRPC application that performs tokenization and de-tokenization operations
- **Token_Store**: The Redis database that stores encrypted PII values indexed by tokens
- **Policy_Loader**: The component that loads, validates, and hot-reloads YAML policy files
- **Structured_Tokenizer**: The component that tokenizes structured data records based on policy-defined PII fields
- **Unstructured_Tokenizer**: The component that uses LLM API to identify and tokenize PII in free-form text
- **Crypto_Engine**: The component that performs AES-256-GCM encryption and decryption operations
- **Token**: A reversible opaque surrogate (UUID or deterministic hash) that replaces a PII value
- **System_ID**: An identifier in the policy file that namespaces rules for a specific upstream system
- **Policy_File**: A YAML configuration file defining PII fields, encryption keys, and tokenization rules per system
- **Deterministic_Token**: A token generated via HMAC-SHA256 where the same PII value always produces the same token
- **Non_Deterministic_Token**: A UUID v4 token where the same PII value may produce different tokens
- **LLM_Client**: The component that interfaces with the Anthropic API for PII entity extraction
- **Entity_Span**: A substring in unstructured text identified as PII with start offset, end offset, type, and value
- **UV**: A fast Python package and project manager used for dependency management, virtual environments, and project tooling
- **Benchmark_Report**: A performance report containing execution time, throughput, latency percentiles, and resource utilization metrics

## Requirements

### Requirement 1: Policy File Loading and Validation

**User Story:** As a system administrator, I want the service to validate policy files at startup, so that configuration errors are caught before processing any data.

#### Acceptance Criteria

1. WHEN the PII_Service starts, THE Policy_Loader SHALL load the YAML policy file from the configured path
2. WHEN the policy file contains invalid YAML syntax, THEN THE Policy_Loader SHALL halt startup and log a descriptive error message
3. WHEN the policy file contains a system_id without required fields, THEN THE Policy_Loader SHALL halt startup and log which fields are missing
4. WHEN the policy file contains an invalid encryption_key_ref format, THEN THE Policy_Loader SHALL halt startup and log the invalid reference
5. THE Policy_Loader SHALL resolve encryption key references from environment variables when the format is env:VAR_NAME
6. THE Policy_Loader SHALL resolve encryption key references from mounted files when the format is file:/path
7. WHEN a referenced environment variable does not exist, THEN THE Policy_Loader SHALL halt startup and log the missing variable name
8. WHEN a referenced file path does not exist, THEN THE Policy_Loader SHALL halt startup and log the missing file path

### Requirement 2: Policy Hot-Reload

**User Story:** As a system administrator, I want to reload policy files without restarting the service, so that I can update configuration with zero downtime.

#### Acceptance Criteria

1. WHEN the PII_Service receives a SIGHUP signal, THE Policy_Loader SHALL reload the policy file from disk
2. WHEN a POST request is sent to /admin/policy/reload, THE Policy_Loader SHALL reload the policy file from disk
3. WHEN the reloaded policy file is valid, THE Policy_Loader SHALL replace the active policy within 2 seconds
4. WHEN the reloaded policy file is invalid, THEN THE Policy_Loader SHALL retain the current policy and return an error response
5. WHILE policy reload is in progress, THE PII_Service SHALL continue processing requests using the current policy
6. WHEN policy reload completes, THE PII_Service SHALL use the new policy for all subsequent requests

### Requirement 3: Structured Data Tokenization via REST Streaming

**User Story:** As a client application, I want to anonymize millions of structured records via REST streaming, so that I can process large datasets efficiently.

#### Acceptance Criteria

1. WHEN a POST request is sent to /structured/anonymize with a system_id header, THE Structured_Tokenizer SHALL process each record in the request body
2. FOR ALL PII fields defined in the policy for the given system_id, THE Structured_Tokenizer SHALL replace the field value with a token
3. WHEN a PII field uses dot-notation (e.g., address.street), THE Structured_Tokenizer SHALL navigate nested JSON objects to extract the value
4. WHEN a PII field is configured as deterministic, THE Structured_Tokenizer SHALL generate an HMAC-SHA256 token using the system encryption key
5. WHEN a PII field is configured as non-deterministic, THE Structured_Tokenizer SHALL generate a UUID v4 token
6. WHEN a PII field is configured with token_format prefixed, THE Structured_Tokenizer SHALL prepend the configured prefix to the token
7. THE Structured_Tokenizer SHALL stream each anonymized record immediately upon completion without waiting for the entire batch
8. WHEN a record is successfully anonymized, THE Structured_Tokenizer SHALL add a _pii_anonymized field set to true
9. WHEN a record fails tokenization, THEN THE Structured_Tokenizer SHALL return the record unmodified with an error field describing the failure
10. THE Structured_Tokenizer SHALL process records using async I/O to avoid blocking the event loop

### Requirement 4: Structured Data Tokenization via gRPC Streaming

**User Story:** As a high-throughput client application, I want to anonymize structured records via bidirectional gRPC streaming, so that I can achieve maximum performance.

#### Acceptance Criteria

1. WHEN a client opens a bidirectional stream to pii.StructuredAnonymizer/Anonymize, THE Structured_Tokenizer SHALL accept AnonymizeRequest messages
2. FOR ALL AnonymizeRequest messages received, THE Structured_Tokenizer SHALL parse the record_json field as JSON
3. FOR ALL PII fields defined in the policy for the given system_id, THE Structured_Tokenizer SHALL replace the field value with a token
4. THE Structured_Tokenizer SHALL return an AnonymizeResponse message immediately upon completing each record
5. WHEN a record is successfully anonymized, THE Structured_Tokenizer SHALL include the anonymized_json and token_ids in the response
6. WHEN a record fails tokenization, THEN THE Structured_Tokenizer SHALL include a non-empty error field in the response
7. THE Structured_Tokenizer SHALL support concurrent sending and receiving of messages on the bidirectional stream
8. THE Structured_Tokenizer SHALL process at least 50,000 records per second on a 4 vCPU / 8 GB RAM container

### Requirement 5: Token Storage in Redis

**User Story:** As the PII Service, I want to store encrypted PII values in Redis indexed by tokens, so that I can retrieve original values during de-tokenization.

#### Acceptance Criteria

1. WHEN a token is generated, THE Token_Store SHALL encrypt the original PII value using AES-256-GCM
2. THE Crypto_Engine SHALL generate a unique 96-bit nonce using os.urandom for each encryption operation
3. THE Crypto_Engine SHALL prepend the nonce to the ciphertext before storing in Redis
4. THE Token_Store SHALL store the encrypted value in Redis with a key format of {system_id}:token:{token_value}
5. WHEN the policy specifies a token_ttl_seconds greater than 0, THE Token_Store SHALL set the Redis key TTL to that value
6. WHEN the policy specifies a token_ttl_seconds of 0, THE Token_Store SHALL set no expiry on the Redis key
7. THE Token_Store SHALL use Redis pipelining for bulk writes to minimize round-trips
8. THE Token_Store SHALL use a connection pool with a configurable pool size (default 50 connections)
9. THE Token_Store SHALL verify the GCM authentication tag when reading encrypted values from Redis
10. WHEN the GCM authentication tag verification fails, THEN THE Token_Store SHALL return an error indicating data corruption

### Requirement 6: Unstructured Data Tokenization

**User Story:** As a client application, I want to anonymize PII in free-form text using LLM assistance, so that I can protect sensitive information in documents and logs.

#### Acceptance Criteria

1. WHEN a POST request is sent to /unstructured/anonymize with a system_id header, THE Unstructured_Tokenizer SHALL send the text to the LLM_Client
2. THE LLM_Client SHALL use the model specified in the policy unstructured.llm_model field
3. THE LLM_Client SHALL instruct the LLM to extract entities matching the types listed in policy unstructured.entity_types
4. THE LLM_Client SHALL parse the LLM response as JSON to extract entity spans with start offset, end offset, type, and value
5. WHEN the LLM response is not valid JSON, THEN THE LLM_Client SHALL return an error response
6. FOR ALL entity spans where the type is in the policy entity_types list, THE Unstructured_Tokenizer SHALL tokenize the entity value
7. FOR ALL entity spans where the type is not in the policy entity_types list, THE Unstructured_Tokenizer SHALL ignore the entity
8. THE Unstructured_Tokenizer SHALL replace entity spans in the original text with tokens in a single pass using longest-span-first ordering
9. WHEN return_entity_map is true in the request, THE Unstructured_Tokenizer SHALL include a map of tokens to entity metadata in the response
10. THE Unstructured_Tokenizer SHALL enforce a configurable per-minute rate limit per client to prevent runaway LLM API costs
11. THE Unstructured_Tokenizer SHALL enforce a maximum input text length (default 50,000 characters)

### Requirement 7: Structured Data De-tokenization

**User Story:** As a client application, I want to restore original PII values from tokenized records, so that I can display or process the actual data when authorized.

#### Acceptance Criteria

1. WHEN a POST request is sent to /structured/deanonymize with a system_id header, THE Structured_Tokenizer SHALL process each record in the request body
2. FOR ALL fields in the record that contain token values, THE Structured_Tokenizer SHALL retrieve the encrypted value from the Token_Store
3. THE Crypto_Engine SHALL decrypt the encrypted value using AES-256-GCM with the system encryption key
4. THE Structured_Tokenizer SHALL replace the token value with the decrypted original value
5. THE Structured_Tokenizer SHALL stream each de-tokenized record immediately upon completion
6. WHEN a token does not exist in Redis, THEN THE Structured_Tokenizer SHALL return an error for that specific field without failing the entire record
7. WHEN a token has expired, THEN THE Structured_Tokenizer SHALL return an error for that specific field indicating expiration
8. THE Structured_Tokenizer SHALL achieve p95 latency under 3 milliseconds for single record de-tokenization

### Requirement 8: Unstructured Data De-tokenization

**User Story:** As a client application, I want to restore original PII values in tokenized text, so that I can display the actual content when authorized.

#### Acceptance Criteria

1. WHEN a POST request is sent to /unstructured/deanonymize with a system_id header, THE Unstructured_Tokenizer SHALL scan the input text for all token patterns
2. FOR ALL tokens found in the text, THE Unstructured_Tokenizer SHALL retrieve the encrypted value from the Token_Store
3. THE Crypto_Engine SHALL decrypt the encrypted value using AES-256-GCM with the system encryption key
4. THE Unstructured_Tokenizer SHALL replace each token in the text with its decrypted original value
5. WHEN a token does not exist in Redis, THEN THE Unstructured_Tokenizer SHALL leave the token unchanged in the text
6. WHEN a token has expired, THEN THE Unstructured_Tokenizer SHALL leave the token unchanged in the text

### Requirement 9: Health and Readiness Checks

**User Story:** As a container orchestrator, I want to check service health and readiness, so that I can route traffic only to healthy instances.

#### Acceptance Criteria

1. THE PII_Service SHALL expose a GET /health endpoint
2. WHEN the /health endpoint is called, THE PII_Service SHALL check Redis connectivity
3. WHEN Redis is reachable and responds to PING, THE PII_Service SHALL return HTTP 200 with status healthy
4. WHEN Redis is unreachable or does not respond within 2 seconds, THEN THE PII_Service SHALL return HTTP 503 with status unhealthy
5. THE PII_Service SHALL include the current policy version in the health response
6. THE PII_Service SHALL respond to health checks within 2 seconds

### Requirement 10: Observability and Metrics

**User Story:** As a platform operator, I want to monitor service performance and errors, so that I can detect and resolve issues proactively.

#### Acceptance Criteria

1. THE PII_Service SHALL expose a GET /metrics endpoint in Prometheus format
2. THE PII_Service SHALL track a records_processed_total counter labeled by system_id and operation type
3. THE PII_Service SHALL track a tokenization_latency_seconds histogram labeled by system_id
4. THE PII_Service SHALL track a redis_operation_latency_seconds histogram labeled by operation type
5. THE PII_Service SHALL track an llm_api_calls_total counter labeled by model and status
6. THE PII_Service SHALL track an llm_api_errors_total counter labeled by error type
7. THE PII_Service SHALL emit structured JSON logs to stdout
8. THE PII_Service SHALL support configurable log level via LOG_LEVEL environment variable
9. THE PII_Service SHALL NOT log any plaintext PII values at any log level
10. THE PII_Service SHALL log token values for debugging purposes

### Requirement 11: Security and Authentication

**User Story:** As a security administrator, I want to ensure all PII is encrypted and access is authenticated, so that sensitive data is protected.

#### Acceptance Criteria

1. THE Crypto_Engine SHALL encrypt all PII values using AES-256-GCM before storing in Redis
2. THE Token_Store SHALL NOT write any plaintext PII value to Redis
3. THE Crypto_Engine SHALL load encryption keys from environment variables or mounted secrets at runtime
4. THE Crypto_Engine SHALL NOT read encryption keys from any config file or source code
5. THE PII_Service SHALL support API key authentication via Authorization: Bearer header for all non-health endpoints
6. THE PII_Service SHALL return HTTP 401 when a request lacks a valid API key
7. THE PII_Service SHALL support TLS 1.2 or higher for all HTTP and gRPC communications
8. THE PII_Service SHALL run as a non-root user (UID 1000) in the Docker container
9. THE PII_Service SHALL NOT mount the Docker socket

### Requirement 12: Error Handling and Resilience

**User Story:** As a client application, I want the service to handle errors gracefully, so that transient failures do not cause data loss.

#### Acceptance Criteria

1. WHEN Redis connection fails during a tokenization operation, THE Token_Store SHALL retry up to 3 times with exponential backoff
2. WHEN Redis connection fails after all retries, THEN THE PII_Service SHALL return an error response to the client
3. WHEN the LLM API returns an error, THE LLM_Client SHALL return a descriptive error response to the client
4. WHEN the LLM API experiences repeated failures, THE LLM_Client SHALL open a circuit breaker to prevent cascade failures
5. WHILE the circuit breaker is open, THE LLM_Client SHALL return an error response without calling the LLM API
6. WHEN a structured stream encounters an error on one record, THE Structured_Tokenizer SHALL continue processing subsequent records
7. WHEN a PII field is null and the policy specifies nullable: true, THE Structured_Tokenizer SHALL skip the field without error
8. WHEN a PII field is null and the policy specifies nullable: false, THEN THE Structured_Tokenizer SHALL return an error for that record

### Requirement 13: Docker Container Build and Deployment

**User Story:** As a DevOps engineer, I want to build and deploy the service as a Docker container, so that I can run it consistently across environments.

#### Acceptance Criteria

1. THE PII_Service SHALL use python:3.12-slim as the base Docker image
2. THE Dockerfile SHALL use a multi-stage build with separate builder and runtime stages
3. THE Dockerfile SHALL create a non-root user named pii with UID 1000 and GID 1000
4. THE Dockerfile SHALL run the application as the pii user
5. THE Dockerfile SHALL include a HEALTHCHECK instruction that calls curl /health
6. THE PII_Service SHALL start both the FastAPI HTTP server on port 8000 and the gRPC server on port 50051
7. THE PII_Service SHALL start and pass health checks within 10 seconds of container startup
8. THE Docker image SHALL pass hadolint linting with no WARN-level findings
9. THE project SHALL include a docker-compose.yml file for local development and testing
10. THE docker-compose.yml SHALL include a Redis service using redis:7.2-alpine image
11. THE Redis service SHALL expose port 6379 for local development access
12. THE Redis service SHALL include a health check using redis-cli ping
13. THE Redis service SHALL use a named volume for data persistence
14. THE Redis service SHALL be configured with password authentication via environment variable
15. THE PII_Service container SHALL depend on the Redis service health check before starting
16. THE docker-compose.yml SHALL configure the PII_Service with REDIS_URL pointing to the Redis service
17. THE docker-compose.yml SHALL mount the policy configuration directory as a read-only volume

### Requirement 14: Policy Field Configuration

**User Story:** As a system administrator, I want to configure PII fields per system using flexible patterns, so that I can handle diverse data schemas.

#### Acceptance Criteria

1. THE Policy_Loader SHALL support separate structured and unstructured sections per system_id
2. THE Policy_Loader SHALL support dot-notation field paths (e.g., address.street) for nested JSON objects
3. THE Policy_Loader SHALL support nullable field configuration to allow null values
4. THE Policy_Loader SHALL support deterministic field configuration to enable consistent tokenization
5. THE Policy_Loader SHALL support token_format configuration with values uuid, deterministic, or prefixed
6. WHEN token_format is prefixed, THE Policy_Loader SHALL require a token_prefix value
7. THE Policy_Loader SHALL support a default_system fallback when the client does not provide a system_id header
8. WHEN a client provides a system_id that does not exist in the policy, THEN THE PII_Service SHALL return HTTP 400 with an error message

### Requirement 15: Performance and Throughput

**User Story:** As a client application, I want the service to process records with low latency and high throughput, so that I can anonymize large datasets quickly.

#### Acceptance Criteria

1. THE Structured_Tokenizer SHALL achieve p95 latency under 5 milliseconds for single record tokenization including Redis write
2. THE Structured_Tokenizer SHALL achieve p95 latency under 3 milliseconds for single record de-tokenization including Redis read
3. THE Structured_Tokenizer SHALL process at least 50,000 records per second via gRPC streaming on a 4 vCPU / 8 GB RAM container
4. THE PII_Service SHALL use async I/O throughout with asyncio, aioredis, and grpcio async
5. WHILE processing long streaming sessions, THE PII_Service SHALL NOT grow memory unboundedly
6. THE PII_Service SHALL process streaming batches in chunks with a configurable max chunk size (default 1000 records)

### Requirement 16: Python Project Management with UV

**User Story:** As a developer, I want to use UV for Python project management, so that I can benefit from fast dependency resolution, reproducible builds, and modern Python tooling.

#### Acceptance Criteria

1. THE project SHALL use UV for all dependency management operations
2. THE project SHALL include a pyproject.toml file with all dependencies specified using UV-compatible format
3. THE project SHALL use UV for creating and managing virtual environments
4. THE project SHALL use UV for installing dependencies in the Docker build process
5. THE project SHALL include a uv.lock file for reproducible dependency resolution
6. THE project documentation SHALL include UV installation and setup instructions
7. THE CI/CD pipeline SHALL use UV for dependency installation and testing
8. THE project SHALL NOT use pip or poetry for dependency management

### Requirement 17: Performance Benchmark Reporting

**User Story:** As a performance engineer, I want automated benchmark reports for structured data anonymization and de-anonymization, so that I can validate performance targets and detect regressions.

#### Acceptance Criteria

1. THE PII_Service SHALL include a benchmark suite for structured data anonymization operations
2. THE PII_Service SHALL include a benchmark suite for structured data de-anonymization operations
3. WHEN benchmarks are executed, THE benchmark suite SHALL generate a Benchmark_Report containing execution time metrics
4. THE Benchmark_Report SHALL include throughput measurements in records per second
5. THE Benchmark_Report SHALL include latency percentiles (p50, p95, p99, p999)
6. THE Benchmark_Report SHALL include average execution time per operation
7. THE Benchmark_Report SHALL include memory usage statistics during benchmark execution
8. THE Benchmark_Report SHALL include CPU utilization metrics during benchmark execution
9. THE Benchmark_Report SHALL test with multiple batch sizes (100, 1000, 10000, 100000 records)
10. THE Benchmark_Report SHALL test both REST streaming and gRPC streaming endpoints
11. THE Benchmark_Report SHALL be generated in JSON format for automated processing
12. THE Benchmark_Report SHALL be generated in human-readable markdown format for documentation
13. THE benchmark suite SHALL run against a local Redis instance to ensure consistent results
14. THE benchmark suite SHALL validate that p95 latency meets the 5ms target for anonymization
15. THE benchmark suite SHALL validate that p95 latency meets the 3ms target for de-anonymization
16. THE benchmark suite SHALL validate that throughput meets the 50,000 records/second target for gRPC streaming
