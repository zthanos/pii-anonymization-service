#!/bin/bash
# Benchmark execution script for PII Anonymization Service
# This script orchestrates the entire benchmark process:
# 1. Checks if service is running
# 2. Installs benchmark dependencies using UV
# 3. Runs structured data benchmarks
# 4. Generates benchmark report

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_URL="${SERVICE_URL:-http://localhost:8000}"
HEALTH_ENDPOINT="${SERVICE_URL}/health"
BENCHMARK_SCRIPT="benchmarks/benchmark_structured.py"
REPORT_GENERATOR="scripts/generate_benchmark_report.py"
RESULTS_FILE="benchmark_results.json"
REPORT_FILE="benchmark_report.html"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PII Anonymization Service Benchmarks${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check if service is running
echo -e "${YELLOW}[1/4] Checking if service is running...${NC}"
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_ENDPOINT}" || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Service is running at ${SERVICE_URL}${NC}"
    else
        echo -e "${RED}✗ Service health check failed (HTTP ${HTTP_CODE})${NC}"
        echo -e "${YELLOW}Please start the service with: docker-compose up -d${NC}"
        exit 1
    fi
elif command -v wget &> /dev/null; then
    if wget -q --spider "${HEALTH_ENDPOINT}"; then
        echo -e "${GREEN}✓ Service is running at ${SERVICE_URL}${NC}"
    else
        echo -e "${RED}✗ Service health check failed${NC}"
        echo -e "${YELLOW}Please start the service with: docker-compose up -d${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ Neither curl nor wget found, skipping health check${NC}"
    echo -e "${YELLOW}Assuming service is running at ${SERVICE_URL}${NC}"
fi
echo ""

# Step 2: Install benchmark dependencies using UV
echo -e "${YELLOW}[2/4] Installing benchmark dependencies...${NC}"
if ! command -v uv &> /dev/null; then
    echo -e "${RED}✗ UV is not installed${NC}"
    echo -e "${YELLOW}Please install UV: https://github.com/astral-sh/uv${NC}"
    exit 1
fi

# Install required packages for benchmarks
echo "Installing httpx, psutil, matplotlib..."
uv pip install httpx psutil matplotlib --quiet

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Step 3: Run structured data benchmarks
echo -e "${YELLOW}[3/4] Running structured data benchmarks...${NC}"
echo -e "${BLUE}This may take several minutes depending on the number of records...${NC}"
echo ""

if [ ! -f "${BENCHMARK_SCRIPT}" ]; then
    echo -e "${RED}✗ Benchmark script not found: ${BENCHMARK_SCRIPT}${NC}"
    exit 1
fi

# Run the benchmark script
if uv run python "${BENCHMARK_SCRIPT}"; then
    echo ""
    echo -e "${GREEN}✓ Benchmarks completed successfully${NC}"
else
    echo ""
    echo -e "${RED}✗ Benchmark execution failed${NC}"
    exit 1
fi
echo ""

# Step 4: Generate benchmark report
echo -e "${YELLOW}[4/4] Generating benchmark report...${NC}"

if [ ! -f "${RESULTS_FILE}" ]; then
    echo -e "${RED}✗ Benchmark results file not found: ${RESULTS_FILE}${NC}"
    exit 1
fi

if [ ! -f "${REPORT_GENERATOR}" ]; then
    echo -e "${RED}✗ Report generator script not found: ${REPORT_GENERATOR}${NC}"
    exit 1
fi

# Generate the HTML report
if uv run python "${REPORT_GENERATOR}" --input "${RESULTS_FILE}" --output "${REPORT_FILE}"; then
    echo -e "${GREEN}✓ Report generated successfully${NC}"
else
    echo -e "${RED}✗ Report generation failed${NC}"
    exit 1
fi
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Benchmark Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}Results saved to:${NC}"
echo -e "  • JSON: ${RESULTS_FILE}"
echo -e "  • HTML: ${REPORT_FILE}"
echo ""
echo -e "${YELLOW}To view the report, open ${REPORT_FILE} in your browser${NC}"
echo ""
