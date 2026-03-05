# README Updates Summary

## Changes Made

### 1. Removed HR Scenario References
- ✅ Removed "HR Realistic Scenario Benchmark" section
- ✅ Removed references to `scripts/run_hr_benchmark.sh`
- ✅ Removed expected results for HR benchmark
- ✅ Removed link to HR documentation

### 2. Added gRPC API Reference Section
- ✅ Added comprehensive gRPC API documentation
- ✅ Documented V2 Batch API (recommended)
- ✅ Documented V1 Streaming API (legacy)
- ✅ Added links to proto files:
  - `src/pii_service/proto/pii_service_v2.proto` (V2 Batch API)
  - `src/pii_service/proto/pii_service.proto` (V1 Streaming API)

### 3. Updated gRPC Usage Examples
- ✅ Primary example: V2 Batch API with orjson
  - Shows proper message size configuration
  - Demonstrates batch processing (up to 2000 records)
  - Includes error handling and statistics
- ✅ Secondary example: V1 Streaming API (legacy)
  - Bidirectional streaming example
  - Backward compatibility note

### 4. Added Multi-Instance Deployment Section
- ✅ Added "Option 2: Multi-Instance Deployment (Production)"
- ✅ Included 3 commands:
  ```bash
  docker-compose -f docker-compose.multi.yml up -d
  docker-compose -f docker-compose.multi.yml logs -f
  docker-compose -f docker-compose.multi.yml down
  ```
- ✅ Added architecture diagram showing:
  - Client Apps
  - Nginx load balancer (port 8000) for REST
  - Envoy load balancer (port 50051) for gRPC
  - 4 service instances
  - Redis backend
- ✅ Added client connection examples for both REST and gRPC
- ✅ Included performance metrics:
  - Single instance: ~5,000 rec/sec
  - Multi-instance (4x): ~15,000-20,000 rec/sec

### 5. Added Authentication & Metadata Section
- ✅ Added "Authentication" subsection under "API Usage"
- ✅ Documented REST headers:
  - `Authorization: Bearer your-api-key`
  - `X-System-ID: customer_db`
- ✅ Documented gRPC metadata keys:
  - `authorization`
  - `x-system-id`
- ✅ Added gRPC client interceptor example:
  - `AuthInterceptor` class implementation
  - Shows how to add authentication to all requests
  - Demonstrates metadata injection

### 6. Fixed License
- ✅ Changed from placeholder `[Your License Here]` to MIT License
- ✅ Added full MIT License text with copyright notice

## File Structure

The updated README now has the following structure:

1. Title & Description
2. Features
3. Performance Targets
4. Prerequisites
5. Installation
6. Configuration
7. Running the Service
   - Option 1: Docker Compose (Recommended)
   - Option 2: Multi-Instance Deployment (Production) ← NEW
   - Option 3: Local Development
8. API Usage
   - Authentication ← NEW
   - Health Check
   - Structured Data Anonymization (REST)
   - Structured Data De-anonymization (REST)
   - Unstructured Data Anonymization
   - Policy Hot-Reload
   - Prometheus Metrics
9. gRPC Usage ← UPDATED
   - gRPC API Reference ← NEW
   - Batch API Example (Recommended) ← NEW
   - Legacy Streaming API Example ← NEW
   - gRPC Metadata and Authentication ← NEW
10. Development
11. Benchmarking ← UPDATED (HR scenario removed)
12. Architecture
13. Security
14. Troubleshooting
15. Documentation
16. Data Directory
17. License ← UPDATED
18. Support

## Summary

All requested changes have been implemented:
- ✅ HR scenario references removed
- ✅ gRPC API Reference section added with proto file links
- ✅ gRPC usage updated with primary (Batch API) and secondary (Streaming API) examples
- ✅ Multi-instance deployment section added with commands, diagram, and client examples
- ✅ Authentication & metadata section added for both REST and gRPC
- ✅ License fixed (MIT License)

The README is now more focused on the core API documentation and production deployment patterns.
