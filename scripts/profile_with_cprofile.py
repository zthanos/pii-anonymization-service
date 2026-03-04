#!/usr/bin/env python3
"""Profile the service using cProfile (built-in Python profiler)."""

import cProfile
import pstats
import io
import asyncio
import sys
import os
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pii_service.config import settings
from pii_service.core.policy_loader import PolicyLoader
from pii_service.core.token_store import TokenStore
from pii_service.core.crypto_engine import CryptoEngine
from pii_service.core.structured_tokenizer import StructuredTokenizer

print("=" * 60)
print("cProfile Performance Analysis")
print("=" * 60)
print()

async def profile_anonymization():
    """Profile the anonymization process."""
    # Initialize components
    print("Initializing components...")
    policy_loader = PolicyLoader()
    await policy_loader.load_policy(settings.POLICY_PATH)
    
    token_store = TokenStore(
        redis_url=settings.REDIS_URL,
        pool_size=settings.REDIS_POOL_SIZE,
    )
    
    crypto_engine = CryptoEngine()
    
    structured_tokenizer = StructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine,
    )
    
    # Load test data
    print("Loading test data...")
    import orjson
    records = []
    with open("data/test_data/test_data_10k.ndjson", "r") as f:
        for line in f:
            if line.strip():
                records.append(orjson.loads(line))
    
    print(f"Loaded {len(records)} records")
    print()
    
    # Profile anonymization
    print("Profiling anonymization...")
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Process records in batches (simulating gRPC behavior)
    batch_size = 200
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        results = await structured_tokenizer.anonymize_batch(batch, "customer_db")
    
    profiler.disable()
    
    # Save profile stats
    print("Saving profile stats...")
    profiler.dump_stats("data/profiling/profile.stats")
    
    # Print top functions by cumulative time
    print()
    print("=" * 60)
    print("TOP 20 FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 60)
    print()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.strip_dirs()
    ps.sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())
    
    # Print top functions by total time
    print()
    print("=" * 60)
    print("TOP 20 FUNCTIONS BY TOTAL TIME")
    print("=" * 60)
    print()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.strip_dirs()
    ps.sort_stats('tottime')
    ps.print_stats(20)
    print(s.getvalue())
    
    # Save detailed report
    with open("profile_report.txt", "w") as f:
        ps = pstats.Stats(profiler, stream=f)
        ps.strip_dirs()
        ps.sort_stats('cumulative')
        ps.print_stats()
    
    print()
    print("=" * 60)
    print("Profile complete!")
    print("=" * 60)
    print("Stats saved to: data/profiling/profile.stats")
    print("Report saved to: profile_report.txt")
    print()
    print("To view the profile interactively:")
    print("  python -m pstats data/profiling/profile.stats")
    print()

if __name__ == "__main__":
    asyncio.run(profile_anonymization())
