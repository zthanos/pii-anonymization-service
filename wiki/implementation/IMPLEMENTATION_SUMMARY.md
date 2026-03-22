# Implementation Summary

This document describes the current implementation shape of the service.

## Current Architecture Snapshot

### Structured subsystem

- REST and gRPC support
- Policy-driven field tokenization
- Reversible token store backed by Redis
- High-throughput batch and streaming paths

### Unstructured subsystem

- No external LLM dependency in the hot path
- Detector-driven pipeline
- Deterministic recognizers for format-bound identifiers
- Optional local semantic detection via Hugging Face model
- Generic findings pipeline inside the unstructured tokenizer

Current unstructured flow:

```text
text -> detector pipeline -> findings -> overlap resolution -> tokenize/redact
```

## Major Components

### Core services

- FastAPI server
- Structured gRPC server
- Policy loader
- Crypto engine
- Redis token store
- Structured tokenizer
- Unstructured tokenizer

### Unstructured detectors

Current detector layer lives under [src/pii_service/core/detectors](/C:/Users/thano/projects/anomymization/src/pii_service/core/detectors):

- `base.py`
- `deterministic.py`
- `greek_ner.py`
- `hybrid.py`

### Policy model

The unstructured policy schema is detector-centric.

Key concepts:

- `detector`
- `prefilter`
- `semantic_detector`
- `entities`
- `overlap_resolution`

## Deployment

### Single instance

- [docker-compose.yml](/C:/Users/thano/projects/anomymization/docker-compose.yml)
- one service instance
- one Redis instance
- REST on `8000`
- structured gRPC on `50051`

### Multi instance

- [docker-compose.multi.yml](/C:/Users/thano/projects/anomymization/docker-compose.multi.yml)
- four service instances
- Nginx for REST load balancing
- Envoy for structured gRPC load balancing
- shared Redis backend

## Environment and Secrets

The example policy currently expects keys for:

- `CUSTOMER_DB_KEY`
- `ANALYTICS_DB_KEY`
- `HR_SYSTEM_KEY`

Authentication is controlled via:

- `API_KEY`

## Benchmarking Support

### Structured

- [benchmarks/benchmark_structured.py](/C:/Users/thano/projects/anomymization/benchmarks/benchmark_structured.py)

### Unstructured

- [benchmarks/benchmark_unstructured.py](/C:/Users/thano/projects/anomymization/benchmarks/benchmark_unstructured.py)

### Clean benchmark wrappers

- [Run-StructuredSingleBenchmark.ps1](/C:/Users/thano/projects/anomymization/scripts/Run-StructuredSingleBenchmark.ps1)
- [Run-StructuredMultiBenchmark.ps1](/C:/Users/thano/projects/anomymization/scripts/Run-StructuredMultiBenchmark.ps1)
- [Run-UnstructuredSingleBenchmark.ps1](/C:/Users/thano/projects/anomymization/scripts/Run-UnstructuredSingleBenchmark.ps1)
- [Run-UnstructuredMultiBenchmark.ps1](/C:/Users/thano/projects/anomymization/scripts/Run-UnstructuredMultiBenchmark.ps1)

## Important Current Constraints

- Unstructured gRPC is not implemented.
- Unstructured semantic detection may incur cold-start/model-load latency.
- Structured and unstructured performance claims should be evaluated separately.

## Recommended Entry Points

- [README](/C:/Users/thano/projects/anomymization/README.md)
- [Quick Start](/C:/Users/thano/projects/anomymization/wiki/implementation/QUICKSTART.md)
- [Benchmarking Guide](/C:/Users/thano/projects/anomymization/wiki/benchmarks/BENCHMARKING.md)
