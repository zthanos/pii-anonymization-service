#!/usr/bin/env python3
"""Profile the PII service to identify performance bottlenecks."""

import subprocess
import time
import sys
from pathlib import Path

print("=" * 60)
print("Service Profiling")
print("=" * 60)
print()

# Check if service is running
print("Checking service status...")
result = subprocess.run(
    ["docker-compose", "ps"],
    capture_output=True,
    text=True
)

if "pii-service" not in result.stdout or "Up" not in result.stdout:
    print("Service not running. Starting...")
    subprocess.run(["docker-compose", "up", "-d"])
    time.sleep(15)

print()
print("Starting profiler...")
print("This will profile the service for 60 seconds while running a benchmark")
print()

# Start profiling in background
profile_process = subprocess.Popen(
    [
        "docker", "exec", "pii-service",
        "py-spy", "record",
        "--pid", "1",
        "--output", "/app/profile.svg",
        "--duration", "60",
        "--rate", "100",
        "--subprocesses"
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Wait a bit for profiler to start
time.sleep(5)

# Run benchmark to generate load
print("Running benchmark to generate load...")
try:
    subprocess.run(
        [
            "uv", "run", "python", "scripts/benchmark_grpc.py",
            "-i", "test_data_10k.ndjson",
            "-o", "anonymize",
            "--results-json", "profile_benchmark_results.json"
        ],
        timeout=120
    )
except subprocess.TimeoutExpired:
    print("Benchmark timed out")

# Wait for profiler to finish
print()
print("Waiting for profiler to complete...")
profile_process.wait()

# Copy profile from container
print("Copying profile from container...")
subprocess.run(
    ["docker", "cp", "pii-service:/app/profile.svg", "./profile.svg"]
)

if Path("profile.svg").exists():
    print()
    print("=" * 60)
    print("Profile complete!")
    print("=" * 60)
    print("Profile saved to: profile.svg")
    print("Open this file in a web browser to view the flame graph")
    print()
    
    # Try to open in browser
    try:
        import webbrowser
        profile_path = Path("profile.svg").absolute()
        webbrowser.open(f"file://{profile_path}")
        print("Opening profile in browser...")
    except:
        pass
else:
    print("Error: Profile file not found")
    sys.exit(1)
