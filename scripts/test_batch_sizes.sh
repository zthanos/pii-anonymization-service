#!/bin/bash
# Test different batch sizes to find optimal performance

echo "=========================================="
echo "Batch Size Optimization Test"
echo "=========================================="
echo ""

# Test data file
TEST_FILE="test_data_10k.ndjson"

# Batch sizes to test
BATCH_SIZES=(50 100 200 500)

# Results file
RESULTS_FILE="batch_size_results.txt"
echo "Batch Size Optimization Results - $(date)" > $RESULTS_FILE
echo "Test file: $TEST_FILE" >> $RESULTS_FILE
echo "========================================" >> $RESULTS_FILE
echo "" >> $RESULTS_FILE

for BATCH_SIZE in "${BATCH_SIZES[@]}"; do
    echo "Testing batch_size=$BATCH_SIZE..."
    echo "----------------------------------------" >> $RESULTS_FILE
    echo "Batch Size: $BATCH_SIZE" >> $RESULTS_FILE
    echo "----------------------------------------" >> $RESULTS_FILE
    
    # Update config with new batch size
    export GRPC_BATCH_SIZE=$BATCH_SIZE
    
    # Restart service
    echo "  Restarting service with batch_size=$BATCH_SIZE..."
    docker-compose down > /dev/null 2>&1
    docker-compose up -d --build > /dev/null 2>&1
    
    # Wait for service to be ready
    echo "  Waiting for service to be ready..."
    sleep 10
    
    # Run benchmark
    echo "  Running benchmark..."
    uv run python scripts/benchmark_grpc.py \
        -i $TEST_FILE \
        -o anonymize \
        --results-json "results_batch_${BATCH_SIZE}.json" \
        2>&1 | tee -a $RESULTS_FILE
    
    echo "" >> $RESULTS_FILE
    echo ""
done

echo ""
echo "=========================================="
echo "All tests complete!"
echo "Results saved to: $RESULTS_FILE"
echo "=========================================="
echo ""
echo "Summary:"
grep "Throughput:" $RESULTS_FILE
