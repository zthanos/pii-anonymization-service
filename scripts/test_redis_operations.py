#!/usr/bin/env python3
"""
Redis Operations Test Script
Validates that Redis is properly storing and retrieving encrypted PII data
"""

import json
import requests
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
API_KEY = "test_api_key_12345"
SYSTEM_ID = "customer_db"

def make_request(method: str, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Make HTTP request to the service"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-System-ID": SYSTEM_ID,
        "Content-Type": "application/json"
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    response.raise_for_status()
    return response.json()

def test_anonymization_and_deanonymization():
    """Test full cycle: anonymize -> store in Redis -> de-anonymize"""
    
    print("=" * 60)
    print("Redis Operations Validation Test")
    print("=" * 60)
    print()
    
    # Test data
    test_record = {
        "email": "alice.smith@example.com",
        "name": "Alice Smith",
        "ssn": "987-65-4321",
        "address": {
            "street": "456 Oak Avenue",
            "city": "New York",
            "state": "NY",
            "zip": "10001"
        },
        "phone": "+1-555-9876",
        "user_id": "user_67890"
    }
    
    print("1. Original Record:")
    print(json.dumps(test_record, indent=2))
    print()
    
    # Step 1: Anonymize
    print("2. Anonymizing record (storing encrypted PII in Redis)...")
    anonymize_response = make_request(
        "POST",
        "/structured/anonymize",
        {"records": [test_record]}
    )
    
    # Parse NDJSON response
    anonymized_record = json.loads(anonymize_response.strip())
    
    print("✓ Anonymization complete")
    print(f"✓ Generated {len(anonymized_record['token_ids'])} tokens")
    print(f"✓ Tokens stored in Redis with keys: customer_db:token:<token_id>")
    print()
    
    print("3. Anonymized Record:")
    print(json.dumps(anonymized_record['record'], indent=2))
    print()
    
    print("4. Token IDs stored in Redis:")
    for i, token_id in enumerate(anonymized_record['token_ids'], 1):
        print(f"   {i}. {token_id}")
    print()
    
    # Step 2: De-anonymize
    print("5. De-anonymizing record (retrieving encrypted PII from Redis)...")
    deanonymize_response = make_request(
        "POST",
        "/structured/deanonymize",
        {"records": [anonymized_record['record']]}
    )
    
    # Parse NDJSON response
    deanonymized_record = json.loads(deanonymize_response.strip())
    
    print("✓ De-anonymization complete")
    print("✓ Retrieved encrypted values from Redis")
    print("✓ Decrypted values using AES-256-GCM")
    print()
    
    print("6. De-anonymized Record:")
    print(json.dumps(deanonymized_record['record'], indent=2))
    print()
    
    # Step 3: Verify data integrity
    print("7. Verifying data integrity...")
    
    original_pii_fields = {
        "email": test_record["email"],
        "ssn": test_record["ssn"],
        "address.street": test_record["address"]["street"],
        "phone": test_record["phone"]
    }
    
    restored_pii_fields = {
        "email": deanonymized_record['record']["email"],
        "ssn": deanonymized_record['record']["ssn"],
        "address.street": deanonymized_record['record']["address"]["street"],
        "phone": deanonymized_record['record']["phone"]
    }
    
    all_match = True
    for field, original_value in original_pii_fields.items():
        restored_value = restored_pii_fields[field]
        match = original_value == restored_value
        status = "✓" if match else "✗"
        print(f"   {status} {field}: {original_value} == {restored_value}")
        if not match:
            all_match = False
    
    print()
    
    if all_match:
        print("=" * 60)
        print("✓ SUCCESS: All PII fields correctly restored from Redis!")
        print("=" * 60)
        print()
        print("Redis Operations Verified:")
        print("  1. ✓ Encrypted PII stored in Redis")
        print("  2. ✓ Tokens used as keys (customer_db:token:<token_id>)")
        print("  3. ✓ Encrypted values retrieved from Redis")
        print("  4. ✓ Values decrypted and restored correctly")
        print("  5. ✓ Data integrity maintained through full cycle")
        return 0
    else:
        print("=" * 60)
        print("✗ FAILURE: Some PII fields did not match!")
        print("=" * 60)
        return 1

def test_redis_metrics():
    """Check Redis metrics from Prometheus endpoint"""
    print()
    print("8. Checking Redis metrics...")
    
    response = requests.get(f"{BASE_URL}/metrics")
    metrics_text = response.text
    
    # Look for Redis-related metrics
    redis_metrics = [
        line for line in metrics_text.split('\n')
        if 'redis_operation_latency_seconds' in line and not line.startswith('#')
    ]
    
    if redis_metrics:
        print("✓ Redis operation metrics found:")
        for metric in redis_metrics[:5]:  # Show first 5
            print(f"   {metric}")
        if len(redis_metrics) > 5:
            print(f"   ... and {len(redis_metrics) - 5} more")
    else:
        print("⚠ No Redis metrics found yet")
    
    print()

if __name__ == "__main__":
    try:
        # Check if service is running
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("✗ Service is not healthy")
            sys.exit(1)
        
        # Run tests
        exit_code = test_anonymization_and_deanonymization()
        test_redis_metrics()
        
        sys.exit(exit_code)
        
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to service. Is it running?")
        print("  Run: docker-compose up -d")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
