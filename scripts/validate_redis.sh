#!/bin/bash

# Redis Validation Script for PII Anonymization Service
# This script validates that Redis is being properly utilized

set -e

echo "=========================================="
echo "Redis Validation for PII Service"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get Redis password from .env or use default
REDIS_PASSWORD=${REDIS_PASSWORD:-redis_dev_password}

echo "1. Checking Redis container status..."
if docker ps | grep -q pii-redis; then
    echo -e "${GREEN}✓ Redis container is running${NC}"
else
    echo -e "${RED}✗ Redis container is not running${NC}"
    exit 1
fi

echo ""
echo "2. Checking Redis connectivity..."
if docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" PING 2>/dev/null | grep -q PONG; then
    echo -e "${GREEN}✓ Redis is responding to PING${NC}"
else
    echo -e "${RED}✗ Redis is not responding${NC}"
    exit 1
fi

echo ""
echo "3. Checking stored keys..."
KEY_COUNT=$(docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" DBSIZE 2>/dev/null)
echo -e "${GREEN}✓ Redis has $KEY_COUNT keys stored${NC}"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo ""
    echo "4. Sample keys (first 10):"
    docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" KEYS "*" 2>/dev/null | head -10 | while read key; do
        echo "   - $key"
    done
    
    echo ""
    echo "5. Checking key patterns..."
    CUSTOMER_DB_KEYS=$(docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" KEYS "customer_db:token:*" 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ Found $CUSTOMER_DB_KEYS keys for customer_db system${NC}"
    
    echo ""
    echo "6. Checking TTL on a sample key..."
    SAMPLE_KEY=$(docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" KEYS "customer_db:token:*" 2>/dev/null | head -1)
    if [ ! -z "$SAMPLE_KEY" ]; then
        TTL=$(docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" TTL "$SAMPLE_KEY" 2>/dev/null)
        TTL_HOURS=$((TTL / 3600))
        echo -e "${GREEN}✓ Sample key TTL: ${TTL}s (~${TTL_HOURS} hours)${NC}"
        echo "   Key: $SAMPLE_KEY"
    fi
    
    echo ""
    echo "7. Verifying data encryption..."
    if [ ! -z "$SAMPLE_KEY" ]; then
        VALUE=$(docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" GET "$SAMPLE_KEY" 2>/dev/null)
        # Check if value contains non-printable characters (encrypted)
        if echo "$VALUE" | grep -q '[^[:print:]]'; then
            echo -e "${GREEN}✓ Data is encrypted (contains non-printable characters)${NC}"
        else
            echo -e "${YELLOW}⚠ Data might not be encrypted${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⚠ No keys found in Redis. Try making some API requests first.${NC}"
fi

echo ""
echo "8. Redis connection statistics..."
docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" INFO stats 2>/dev/null | grep -E "total_connections_received|total_commands_processed|instantaneous_ops_per_sec" | while read line; do
    echo "   $line"
done

echo ""
echo "9. Redis memory usage..."
docker exec pii-redis redis-cli -a "$REDIS_PASSWORD" INFO memory 2>/dev/null | grep -E "used_memory_human|used_memory_peak_human" | while read line; do
    echo "   $line"
done

echo ""
echo "=========================================="
echo -e "${GREEN}Redis Validation Complete!${NC}"
echo "=========================================="
