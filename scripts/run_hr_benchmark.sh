#!/bin/bash
# Run HR realistic scenario benchmark

set -e

echo "=========================================="
echo "HR Realistic Scenario Benchmark Setup"
echo "=========================================="

# Check if service is running
echo ""
echo "Checking if PII service is running..."
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ PII service is not running!"
    echo ""
    echo "Please start the service first:"
    echo "  docker-compose up -d"
    echo ""
    echo "Or for multi-instance:"
    echo "  docker-compose -f docker-compose.multi.yml up -d"
    exit 1
fi
echo "✅ Service is running"

# Check if HR_SYSTEM_KEY is set
echo ""
echo "Checking environment variables..."
if [ -z "$HR_SYSTEM_KEY" ]; then
    echo "⚠️  HR_SYSTEM_KEY not set, generating one..."
    export HR_SYSTEM_KEY=$(python scripts/generate_key.py)
    echo "Generated key: $HR_SYSTEM_KEY"
    echo ""
    echo "Add this to your .env file:"
    echo "HR_SYSTEM_KEY=$HR_SYSTEM_KEY"
    echo ""
    
    # Add to .env if it exists
    if [ -f .env ]; then
        if ! grep -q "HR_SYSTEM_KEY" .env; then
            echo "HR_SYSTEM_KEY=$HR_SYSTEM_KEY" >> .env
            echo "✅ Added HR_SYSTEM_KEY to .env"
        fi
    fi
else
    echo "✅ HR_SYSTEM_KEY is set"
fi

# Generate test data if it doesn't exist
echo ""
echo "Checking test data..."
if [ ! -f "data/test_data/hr_test_data_360k.ndjson" ]; then
    echo "📊 Generating 360,000 employee records..."
    echo "This will take a few minutes..."
    python scripts/generate_hr_test_data.py 360000
else
    echo "✅ Test data already exists"
    FILE_SIZE=$(du -h data/test_data/hr_test_data_360k.ndjson | cut -f1)
    echo "   File size: $FILE_SIZE"
fi

# Restart service to load new policy
echo ""
echo "Restarting service to load HR system policy..."
if docker-compose ps | grep -q "pii-service"; then
    docker-compose restart pii-service
    echo "Waiting for service to be ready..."
    sleep 5
elif docker-compose -f docker-compose.multi.yml ps | grep -q "pii-service"; then
    docker-compose -f docker-compose.multi.yml restart
    echo "Waiting for services to be ready..."
    sleep 10
fi

# Verify service health
echo ""
echo "Verifying service health..."
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "healthy"; then
    echo "✅ Service is healthy"
else
    echo "❌ Service health check failed"
    echo "$HEALTH"
    exit 1
fi

# Run benchmark
echo ""
echo "=========================================="
echo "Starting HR Benchmark"
echo "=========================================="
echo ""
python benchmarks/benchmark_hr_realistic.py

echo ""
echo "=========================================="
echo "Benchmark Complete!"
echo "=========================================="
echo ""
echo "Results saved to: data/benchmark_results/hr_realistic_benchmark.json"
echo ""
