#!/bin/bash
# Profile the PII service to identify performance bottlenecks

echo "=========================================="
echo "Service Profiling"
echo "=========================================="
echo ""

# Make sure service is running
echo "Checking service status..."
docker-compose ps | grep pii-service

if [ $? -ne 0 ]; then
    echo "Service not running. Starting..."
    docker-compose up -d
    sleep 10
fi

echo ""
echo "Starting profiler..."
echo "This will profile the service for 60 seconds while running a benchmark"
echo ""

# Start profiling in background
docker exec pii-service py-spy record \
    --pid 1 \
    --output /app/profile.svg \
    --duration 60 \
    --rate 100 \
    --subprocesses &

PROFILE_PID=$!

# Wait a bit for profiler to start
sleep 5

# Run benchmark to generate load
echo "Running benchmark to generate load..."
uv run python scripts/benchmark_grpc.py \
    -i test_data_10k.ndjson \
    -o anonymize \
    --results-json profile_benchmark_results.json

# Wait for profiler to finish
echo ""
echo "Waiting for profiler to complete..."
wait $PROFILE_PID

# Copy profile from container
echo "Copying profile from container..."
docker cp pii-service:/app/profile.svg ./profile.svg

if [ -f "profile.svg" ]; then
    echo ""
    echo "=========================================="
    echo "Profile complete!"
    echo "=========================================="
    echo "Profile saved to: profile.svg"
    echo "Open this file in a web browser to view the flame graph"
    echo ""
else
    echo "Error: Profile file not found"
fi
