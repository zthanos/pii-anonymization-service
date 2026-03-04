#!/usr/bin/env python3
"""Run the service locally with py-spy profiling."""

import subprocess
import time
import sys
import signal
from pathlib import Path

print("=" * 60)
print("Local Service Profiling")
print("=" * 60)
print()

# Start the service in background
print("Starting PII service locally...")
service_process = subprocess.Popen(
    ["uv", "run", "python", "-m", "pii_service.main"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Wait for service to start
print("Waiting for service to start...")
time.sleep(10)

# Check if service is running
if service_process.poll() is not None:
    print("Error: Service failed to start")
    stdout, stderr = service_process.communicate()
    print("STDOUT:", stdout)
    print("STDERR:", stderr)
    sys.exit(1)

print(f"Service started with PID: {service_process.pid}")
print()

# Start profiling
print("Starting py-spy profiler...")
print("Profiling for 60 seconds while running benchmark...")
print()

profile_process = subprocess.Popen(
    [
        "uv", "run", "py-spy", "record",
        "--pid", str(service_process.pid),
        "--output", "profile.svg",
        "--duration", "60",
        "--rate", "100",
        "--subprocesses"
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Wait a bit for profiler to start
time.sleep(3)

# Run benchmark to generate load
print("Running benchmark to generate load...")
try:
    benchmark_result = subprocess.run(
        [
            "uv", "run", "python", "scripts/benchmark_grpc.py",
            "-i", "data/test_data/test_data_10k.ndjson",
            "-o", "anonymize",
            "--results-json", "data/profiling/profile_benchmark_results.json"
        ],
        timeout=120,
        capture_output=True,
        text=True
    )
    print(benchmark_result.stdout)
except subprocess.TimeoutExpired:
    print("Benchmark timed out")
except Exception as e:
    print(f"Benchmark error: {e}")

# Wait for profiler to finish
print()
print("Waiting for profiler to complete...")
profile_process.wait()

# Stop the service
print("Stopping service...")
service_process.send_signal(signal.SIGTERM)
service_process.wait(timeout=10)

# Check if profile was created
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
        webbrowser.open(f"file:///{profile_path}")
        print("Opening profile in browser...")
    except:
        pass
else:
    print("Error: Profile file not found")
    # Print profiler output
    stdout, stderr = profile_process.communicate()
    print("Profiler STDOUT:", stdout)
    print("Profiler STDERR:", stderr)
    sys.exit(1)
