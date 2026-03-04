# Implementation Plan: PII Anonymization Service

## Overview

This implementation plan breaks down the PII Anonymization Service into discrete, actionable tasks. The service is a high-performance Python 3.12 microservice providing tokenization and de-tokenization capabilities for structured and unstructured data containing PII. The implementation follows a bottom-up approach, building core components first, then integrating them into API endpoints, and finally adding observability and deployment infrastructure.

## Technology Stack

- Python 3.12 with UV package manager
- FastAPI for REST API
- gRPC for high-throughput streaming
- Redis 7.2+ for token storage
- Anthropic API for LLM-assisted PII extraction
- Docker for containerization

## Performance Targets

- Throughput: 50,000+ records/second via gRPC
- Latency: <5ms p95 for anonymization, <3ms p95 for de-anonymization
- Memory: Bounded memory usage with streaming processing

## Tasks

- [x] 1. Set up project structure and dependencies with UV
  - Create project directory structure with src/pii_service layout
  - Create pyproject.toml with all dependencies (FastAPI, gRPC, Redis, cryptography, anthropic, pydantic, structlog, prometheus-client)
  - Create .python-version file specifying Python 3.12
  - Create uv.lock file for reproducible builds
  - Create .env.example with configuration template
  - Create .gitignore for Python projects
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

- [x] 2. Implement core cryptography engine
  - [x] 2.1 Create CryptoEngine class with AES-256-GCM encryption
    - Implement encrypt() method that generates 96-bit nonce and returns nonce + ciphertext + tag
    - Implement decrypt() method that extracts nonce, verifies GCM tag, and returns plaintext
    - Implement generate_nonce() using os.urandom for cryptographically secure nonces
    - Handle encryption/decryption errors with DataCorruptionError exception
    - _Requirements: 5.1, 5.2, 5.3, 5.9, 5.10, 11.1, 11.2_

- [x] 3. Implement policy loader and configuration management
  - [x] 3.1 Create Pydantic models for policy configuration
    - Create PIIField model with name, deterministic, token_format, token_prefix, nullable fields
    - Create StructuredConfig model with pii_fields list and token_ttl_seconds
    - Create UnstructuredConfig model with llm_model, entity_types, rate_limit_per_minute, max_text_length
    - Create SystemConfig model with system_id, encryption_key_ref, structured, unstructured sections
    - Create Policy model with systems list, default_system, and version
    - Add validators for unique system_ids, encryption_key_ref format, and token_prefix requirements
    - _Requirements: 1.3, 1.4, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [x] 3.2 Create PolicyLoader class with YAML loading and validation
    - Implement load_policy() method that reads YAML file and validates against Pydantic models
    - Implement resolve_encryption_key() method supporting env: and file: references
    - Implement get_system_config() method that returns configuration for a system_id
    - Handle missing environment variables and file paths with descriptive errors
    - Halt startup on any validation error with clear error messages
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 11.3, 11.4, 14.7, 14.8_

  - [x] 3.3 Implement policy hot-reload functionality
    - Add reload_policy() method that reloads from disk with validation
    - Implement SIGHUP signal handler for policy reload
    - Use RWLock or similar mechanism for thread-safe policy swapping
    - Retain current policy if reload fails
    - Continue processing requests during reload using current policy
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 4. Implement Redis token store with connection pooling
  - [x] 4.1 Create TokenStore class with async Redis client
    - Initialize Redis connection pool with configurable size (default 50)
    - Implement build_key() method for namespaced keys: {system_id}:token:{token}
    - Implement store_token() method with TTL support and retry logic (3 attempts, exponential backoff)
    - Implement retrieve_token() method with retry logic
    - Implement health_check() method using Redis PING command
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 12.1, 12.2_

  - [x] 4.2 Implement batch operations for performance
    - Implement store_batch() method using Redis pipeline for multiple tokens
    - Implement retrieve_batch() method using Redis pipeline
    - Minimize round-trips by batching all operations in a single pipeline
    - _Requirements: 5.7, 15.1, 15.2, 15.4_

- [x] 5. Checkpoint - Ensure core components work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement structured data tokenizer
  - [x] 6.1 Create StructuredTokenizer class with field extraction
    - Implement extract_field_value() method supporting dot-notation paths (e.g., address.street)
    - Implement set_field_value() method that creates intermediate dicts as needed
    - Handle null values based on nullable configuration
    - _Requirements: 3.3, 12.7, 12.8, 14.2, 14.3_

  - [x] 6.2 Implement token generation with multiple formats
    - Implement generate_token() method supporting UUID, deterministic (HMAC-SHA256), and prefixed formats
    - Use uuid.uuid4() for non-deterministic tokens
    - Use HMAC-SHA256 with system encryption key for deterministic tokens
    - Support token_prefix configuration for prefixed format
    - _Requirements: 3.4, 3.5, 3.6, 14.5, 14.6_

  - [x] 6.3 Implement single record anonymization
    - Implement anonymize_record() method that processes one record
    - Extract all PII field values based on policy configuration
    - Generate tokens for each PII field
    - Encrypt original values using CryptoEngine
    - Store encrypted values in TokenStore using batch operations
    - Replace PII field values with tokens in the record
    - Add _pii_anonymized: true field to processed records
    - Return AnonymizedRecord with record, token_ids, and error fields
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9_

  - [x] 6.4 Implement streaming anonymization
    - Implement anonymize_stream() method that yields records immediately
    - Process records asynchronously without buffering
    - Continue processing subsequent records if one fails
    - Return error in record's error field without failing entire stream
    - _Requirements: 3.7, 3.9, 3.10, 12.6, 15.4, 15.5, 15.6_

  - [x] 6.5 Implement de-tokenization for structured data
    - Implement deanonymize_record() method that restores original PII values
    - Retrieve encrypted values from TokenStore for all token fields
    - Decrypt values using CryptoEngine
    - Replace tokens with decrypted original values
    - Handle missing/expired tokens gracefully with field-level errors
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

- [x] 7. Implement LLM client for entity extraction
  - [x] 7.1 Create LLMClient class with Anthropic API integration
    - Initialize AsyncAnthropic client with API key
    - Implement build_extraction_prompt() method that creates structured prompt for entity extraction
    - Implement extract_entities() method that calls Claude API and returns EntitySpan list
    - Implement parse_llm_response() method that validates JSON response structure
    - Handle invalid JSON responses with LLMResponseError
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.2 Implement circuit breaker for resilience
    - Create CircuitBreaker class with failure threshold (default 5) and timeout (default 60s)
    - Track failure count and last failure time
    - Implement states: closed, open, half-open
    - Open circuit breaker after threshold failures
    - Transition to half-open after timeout period
    - Integrate circuit breaker into LLMClient.extract_entities()
    - Return error immediately when circuit breaker is open
    - _Requirements: 12.3, 12.4, 12.5_

- [x] 8. Implement unstructured data tokenizer
  - [x] 8.1 Create UnstructuredTokenizer class with text processing
    - Implement anonymize_text() method that extracts entities using LLMClient
    - Validate text length against max_text_length configuration
    - Generate tokens for each extracted entity
    - Encrypt and store entity values in TokenStore
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.11_

  - [x] 8.2 Implement entity replacement with longest-first ordering
    - Implement replace_entities() method that replaces entity spans with tokens
    - Sort entities by length (longest first) to handle overlaps
    - Track tokenized character positions to avoid conflicts
    - Apply replacements in reverse order to maintain positions
    - Return anonymized text and entity map
    - _Requirements: 6.7, 6.8, 6.9_

  - [x] 8.3 Implement rate limiting for LLM API calls
    - Create RateLimiter class with per-client tracking
    - Track requests per minute per client_id
    - Implement check_rate_limit() method that enforces limits
    - Integrate rate limiter into anonymize_text() method
    - Return 429 error when rate limit exceeded
    - _Requirements: 6.10_

  - [x] 8.4 Implement de-tokenization for unstructured text
    - Implement extract_tokens() method using regex patterns for UUID and HMAC tokens
    - Support prefixed token patterns
    - Implement deanonymize_text() method that replaces tokens with original values
    - Leave unknown/expired tokens unchanged in text
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 9. Checkpoint - Ensure tokenization components work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement FastAPI REST endpoints
  - [x] 10.1 Create FastAPI application with middleware
    - Create FastAPI app with title, version, and description
    - Add CORS middleware with appropriate configuration
    - Implement authentication middleware that validates Bearer tokens
    - Skip authentication for /health and /metrics endpoints
    - Extract client_id from API key for rate limiting
    - Add global exception handler for unhandled errors
    - _Requirements: 11.5, 11.6_

  - [x] 10.2 Implement structured data anonymization endpoint
    - Create POST /structured/anonymize endpoint
    - Accept X-System-ID header and list of records in body
    - Stream responses as NDJSON (one JSON object per line)
    - Use StructuredTokenizer.anonymize_stream() for processing
    - Return StreamingResponse with application/x-ndjson media type
    - _Requirements: 3.1, 3.2, 3.7, 3.8, 3.9_

  - [x] 10.3 Implement structured data de-anonymization endpoint
    - Create POST /structured/deanonymize endpoint
    - Accept X-System-ID header and list of tokenized records
    - Stream responses as NDJSON
    - Use StructuredTokenizer.deanonymize_record() for processing
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 10.4 Implement unstructured data anonymization endpoint
    - Create POST /unstructured/anonymize endpoint
    - Accept X-System-ID header and UnstructuredRequest body (text, return_entity_map)
    - Check rate limit before processing
    - Use UnstructuredTokenizer.anonymize_text() for processing
    - Return UnstructuredResponse with anonymized_text and optional entity_map
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9, 6.10_

  - [x] 10.5 Implement unstructured data de-anonymization endpoint
    - Create POST /unstructured/deanonymize endpoint
    - Accept X-System-ID header and DeanonymizeRequest body (text)
    - Use UnstructuredTokenizer.deanonymize_text() for processing
    - Return response with de-anonymized text
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 10.6 Implement health check endpoints
    - Create GET /health endpoint that checks Redis connectivity
    - Return 200 with status "healthy" if Redis responds to PING within 2 seconds
    - Return 503 with status "unhealthy" if Redis is unreachable
    - Include current policy version in response
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 10.7 Implement admin endpoints
    - Create POST /admin/policy/reload endpoint
    - Call PolicyLoader.reload_policy() method
    - Return success response with new policy version
    - Return error response if reload fails, keeping current policy
    - _Requirements: 2.2, 2.3, 2.4_

- [x] 11. Implement gRPC service
  - [x] 11.1 Create protobuf definitions
    - Create pii_service.proto with StructuredAnonymizer service
    - Define AnonymizeRequest message with system_id, record_id, record_json fields
    - Define AnonymizeResponse message with record_id, anonymized_json, token_ids, error fields
    - Define DeanonymizeRequest and DeanonymizeResponse messages
    - Define bidirectional streaming RPCs for Anonymize and Deanonymize
    - Generate Python code using grpcio-tools
    - _Requirements: 4.1, 4.2_

  - [x] 11.2 Implement gRPC servicer
    - Create StructuredAnonymizerServicer class
    - Implement Anonymize() method for bidirectional streaming
    - Parse record_json as JSON for each request
    - Use StructuredTokenizer.anonymize_record() for processing
    - Yield AnonymizeResponse immediately for each record
    - Return error in response without failing stream if record fails
    - Implement Deanonymize() method similarly
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 11.3 Create gRPC server with async support
    - Create async gRPC server with ThreadPoolExecutor
    - Configure max message size (100MB send/receive)
    - Add StructuredAnonymizerServicer to server
    - Listen on port 50051
    - Support concurrent bidirectional streaming
    - _Requirements: 4.7, 4.8, 15.4_

- [x] 12. Implement observability layer
  - [x] 12.1 Set up structured logging with structlog
    - Configure structlog with JSON output format
    - Add log level, timestamp, and exception info processors
    - Support LOG_LEVEL environment variable
    - Never log plaintext PII values at any log level
    - Log token values (prefixes only) for debugging
    - _Requirements: 10.7, 10.8, 10.9, 10.10_

  - [x] 12.2 Implement Prometheus metrics
    - Create GET /metrics endpoint exposing Prometheus format
    - Implement records_processed_total counter with system_id and operation labels
    - Implement tokenization_latency_seconds histogram with system_id label
    - Implement redis_operation_latency_seconds histogram with operation label
    - Implement llm_api_calls_total counter with model and status labels
    - Implement llm_api_errors_total counter with error_type label
    - Track metrics in all tokenization and storage operations
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 12.3 Implement request logging middleware
    - Add middleware that logs all HTTP requests with structured data
    - Generate unique request_id for each request
    - Log request method, path, client IP at start
    - Log response status code and duration at completion
    - Add request_id to response headers (X-Request-ID)
    - Use structlog context variables for request_id
    - _Requirements: 10.7_

- [x] 13. Implement Docker containerization
  - [x] 13.1 Create multi-stage Dockerfile
    - Use python:3.12-slim as base image
    - Create builder stage that installs UV and dependencies
    - Create runtime stage with minimal dependencies
    - Create non-root user 'pii' with UID 1000
    - Copy virtual environment from builder stage
    - Set PATH to include virtual environment
    - Expose ports 8000 (HTTP) and 50051 (gRPC)
    - Add HEALTHCHECK instruction calling /health endpoint
    - Run as non-root user
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 11.8, 11.9_

  - [x] 13.2 Create docker-compose.yml for local development
    - Define pii-service container with build context
    - Define Redis service using redis:7.2-alpine image
    - Configure Redis with password authentication
    - Add Redis health check using redis-cli ping
    - Create named volume for Redis data persistence
    - Configure pii-service to depend on Redis health check
    - Mount policy directory as read-only volume
    - Expose ports for REST API, gRPC, and Redis
    - _Requirements: 13.9, 13.10, 13.11, 13.12, 13.13, 13.14, 13.15, 13.16, 13.17_

  - [x] 13.3 Pass hadolint linting
    - Run hadolint on Dockerfile
    - Fix any WARN-level findings
    - Ensure best practices for layer caching and security
    - _Requirements: 13.8_

- [x] 14. Implement application entry point and server orchestration
  - [x] 14.1 Create main.py with async server startup
    - Initialize PolicyLoader and load policy at startup
    - Initialize TokenStore with Redis connection pool
    - Initialize CryptoEngine
    - Create StructuredTokenizer, UnstructuredTokenizer, and LLMClient instances
    - Create FastAPI app with all dependencies
    - Create gRPC server with servicer
    - Start both FastAPI and gRPC servers concurrently using asyncio.gather()
    - Handle graceful shutdown on SIGTERM and SIGINT
    - _Requirements: 13.6, 13.7, 15.4_

  - [x] 14.2 Implement configuration management
    - Create config.py with Pydantic BaseSettings
    - Load configuration from environment variables
    - Support REDIS_URL, REDIS_POOL_SIZE, POLICY_PATH, ANTHROPIC_API_KEY, LOG_LEVEL
    - Provide sensible defaults for all optional settings
    - _Requirements: 16.2_

- [x] 15. Create example policy configuration
  - Create policies/example_policy.yaml with sample configuration
  - Include example system_id configurations for structured and unstructured tokenization
  - Document all configuration options with comments
  - Include examples of env: and file: encryption key references
  - _Requirements: 1.1, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 16. Checkpoint - Ensure service starts and responds
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Implement benchmark suite
  - [x] 17.1 Create structured data benchmark script
    - Create benchmarks/benchmark_structured.py with StructuredBenchmark class
    - Implement generate_test_record() method that creates records with PII
    - Implement anonymize_record() method that measures single-record latency
    - Implement run_benchmark() method that processes multiple records with concurrency control
    - Track throughput (records/sec), latency percentiles (p50, p95, p99, p999), memory usage, CPU utilization
    - Test with multiple batch sizes (1000, 10000, 50000, 100000 records)
    - Validate that throughput meets 50k records/sec target
    - Validate that p95 latency meets 5ms target
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.14, 17.15_

  - [x] 17.2 Create de-anonymization benchmark
    - Add de-anonymization benchmark to benchmark_structured.py
    - Measure de-anonymization throughput and latency
    - Validate that p95 latency meets 3ms target for de-anonymization
    - _Requirements: 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.15_

  - [x] 17.3 Create benchmark report generator
    - Create scripts/generate_benchmark_report.py
    - Load benchmark results from JSON file
    - Generate performance plots using matplotlib (throughput, latency, memory, CPU)
    - Generate HTML report with results table and visualizations
    - Highlight pass/fail status for performance targets
    - _Requirements: 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.11, 17.12_

  - [x] 17.4 Create benchmark execution script
    - Create scripts/run_benchmarks.sh
    - Check if service is running before starting benchmarks
    - Install benchmark dependencies using UV
    - Run structured data benchmarks
    - Generate benchmark report
    - Save results to benchmark_results.json and benchmark_report.html
    - _Requirements: 17.13_

  - [x] 17.5 Test REST and gRPC endpoints in benchmarks
    - Add gRPC streaming benchmark to benchmark suite
    - Compare REST vs gRPC performance
    - Validate gRPC meets 50k records/sec target
    - _Requirements: 17.10, 17.16_

- [x] 18. Create documentation and helper scripts
  - [x] 18.1 Create README.md with setup instructions
    - Document UV installation and setup
    - Document environment variable configuration
    - Document how to generate encryption keys
    - Document how to run the service locally with docker-compose
    - Document API endpoints and usage examples
    - Document performance targets and benchmarking
    - _Requirements: 16.6_

  - [x] 18.2 Create encryption key generator script
    - Create scripts/generate_key.py
    - Generate 32-byte random key using os.urandom
    - Output base64-encoded key for environment variables
    - _Requirements: 11.3_

  - [x] 18.3 Create .env.example file
    - Document all environment variables with examples
    - Include Redis configuration, policy path, encryption keys, Anthropic API key, logging settings
    - _Requirements: 16.2_

- [x] 19. Integration and final wiring
  - [x] 19.1 Wire all components together in main.py
    - Ensure PolicyLoader is initialized and policy loaded before other components
    - Pass PolicyLoader to StructuredTokenizer and UnstructuredTokenizer
    - Pass TokenStore and CryptoEngine to tokenizers
    - Pass LLMClient to UnstructuredTokenizer
    - Inject dependencies into FastAPI endpoints using Depends()
    - Inject dependencies into gRPC servicer constructor
    - _Requirements: All requirements_

  - [x] 19.2 Implement dependency injection for FastAPI
    - Create dependency functions for PolicyLoader, TokenStore, StructuredTokenizer, UnstructuredTokenizer
    - Use FastAPI Depends() to inject dependencies into endpoint handlers
    - Ensure single instances are shared across requests
    - _Requirements: 15.4_

  - [x] 19.3 Add TLS support configuration
    - Add SSL configuration options to config.py
    - Support ssl_keyfile, ssl_certfile, ssl_ca_certs environment variables
    - Configure uvicorn with TLS when certificates provided
    - Configure gRPC server with TLS credentials when certificates provided
    - _Requirements: 11.7_

- [x] 20. Final checkpoint - End-to-end testing
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The implementation follows a bottom-up approach: core components → API layer → observability → deployment
- All async I/O operations use asyncio for non-blocking performance
- Connection pooling and batch operations are used throughout for optimal performance
- Security is built-in: encryption at rest, no plaintext PII logging, non-root container execution
- The service is designed to meet performance targets: 50k+ records/sec throughput, <5ms p95 latency
