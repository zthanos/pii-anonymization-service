# Wiki Structure

This document shows the organization of the documentation wiki.

## Directory Tree

```
wiki/
├── README.md                          # Wiki index and navigation
├── STRUCTURE.md                       # This file
│
├── optimization/                      # Performance optimization journey
│   ├── OPTIMIZATION_JOURNEY_COMPLETE.md      # Complete optimization story (MAIN)
│   ├── OPTIMIZATION_JOURNEY.md               # Earlier optimization journey
│   ├── OPTIMIZATION_COMPLETE.md              # Optimization completion notes
│   ├── ADVANCED_OPTIMIZATION_PLAN.md         # Original optimization roadmap
│   ├── COMPLETE_OPTIMIZATION_SUMMARY.md      # Comprehensive summary
│   ├── PERFORMANCE_IMPROVEMENTS.md           # Performance improvement details
│   │
│   ├── PHASE_1_COMPLETE.md                   # Phase 1: Batch Messages (5.2x)
│   ├── PHASE_1_BATCH_MESSAGES_IMPLEMENTATION.md  # Phase 1 implementation
│   ├── PHASE_1_STATUS.md                     # Phase 1 development status
│   ├── PHASE_1_READY_TO_TEST.md              # Phase 1 testing readiness
│   │
│   ├── PHASE_2_ANALYSIS.md                   # Phase 2: Worker Pool (rejected)
│   │
│   ├── PHASE_3_MULTI_INSTANCE_COMPLETE.md    # Phase 3: Multi-Instance (3.2x)
│   └── PHASE_3_OPTIMIZATION_SUMMARY.md       # Phase 3 summary
│
├── benchmarks/                        # Performance benchmarking
│   ├── BATCH_SIZE_OPTIMIZATION_RESULTS.md    # Batch size analysis
│   ├── BENCHMARK_SUMMARY.md                  # Benchmark summary
│   └── BENCHMARKING.md                       # Benchmarking methodology
│
├── implementation/                    # Technical implementation guides
│   ├── GRPC_OPTIMIZATION_GUIDE.md            # gRPC tuning guide
│   ├── IMPLEMENTATION_SUMMARY.md             # Implementation overview
│   └── QUICKSTART.md                         # Quick start guide
│
├── analysis/                          # Technical analysis
│   ├── CQRS_ANALYSIS.md                      # CQRS pattern evaluation
│   ├── PROFILING_ANALYSIS.md                 # Performance profiling
│   ├── REDIS_OPTIMIZATION_RESULTS.md         # Redis tuning analysis
│   ├── STREAMING_OPTIMIZATION_SUMMARY.md     # Streaming API optimization
│   └── FINAL_OPTIMIZATION_SUMMARY.md         # Final optimization results
│
└── deployment/                        # Deployment guides
    ├── DEPLOYMENT_TEST_RESULTS.md            # Deployment testing
    └── UNSTRUCTURED_TEST_RESULTS.md          # Unstructured data tests
```

## Document Categories

### 🚀 Optimization (13 files)
The complete journey from 3,585 to 59,151 records/sec, including all phases and analysis.

**Start here:** `optimization/OPTIMIZATION_JOURNEY_COMPLETE.md`

### 📊 Benchmarks (3 files)
Performance benchmarking methodology and results.

**Key file:** `benchmarks/BATCH_SIZE_OPTIMIZATION_RESULTS.md`

### 🔧 Implementation (3 files)
Technical implementation guides and best practices.

**Key file:** `implementation/GRPC_OPTIMIZATION_GUIDE.md`

### 🔍 Analysis (5 files)
Technical analysis and architectural decisions.

**Key file:** `analysis/CQRS_ANALYSIS.md`

### 🚢 Deployment (2 files)
Deployment guides and test results.

## Navigation Tips

1. **New to the project?** Start with `README.md` in the wiki root
2. **Want the full story?** Read `optimization/OPTIMIZATION_JOURNEY_COMPLETE.md`
3. **Need implementation details?** Check the `implementation/` folder
4. **Looking for specific phase?** Go to `optimization/PHASE_X_*.md`
5. **Want performance data?** See `benchmarks/` and `analysis/` folders

## File Naming Conventions

- `*_COMPLETE.md` - Final, comprehensive documents
- `*_SUMMARY.md` - Summary documents
- `*_ANALYSIS.md` - Technical analysis documents
- `*_RESULTS.md` - Test/benchmark results
- `*_GUIDE.md` - How-to guides
- `PHASE_X_*.md` - Phase-specific documents

## Related Documentation

- [Main README](../README.md) - Project overview
- [Spec Requirements](../.kiro/specs/pii-anonymization-service/requirements.md)
- [Spec Design](../.kiro/specs/pii-anonymization-service/design.md)
- [Spec Tasks](../.kiro/specs/pii-anonymization-service/tasks.md)

---

**Last Updated:** 2026-03-04  
**Total Documents:** 26 markdown files
