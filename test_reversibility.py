import asyncio
import sys
sys.path.insert(0, "src")

from pii_service.core.crypto_engine import CryptoEngine
from pii_service.core.token_store import TokenStore
from pii_service.core.policy_loader import PolicyLoader
from pii_service.core.structured_tokenizer import StructuredTokenizer

async def test_reversibility():
    print("="*60)
    print("TOKENIZATION REVERSIBILITY TEST")
    print("="*60)
    
    # Initialize components
    policy_loader = PolicyLoader()
    await policy_loader.load_policy("policies/example_policy.yaml")
    
    token_store = TokenStore(
        redis_url="redis://:redis_dev_password@localhost:6379/0",
        pool_size=10
    )
    
    crypto_engine = CryptoEngine()
    
    tokenizer = StructuredTokenizer(
        policy_loader=policy_loader,
        token_store=token_store,
        crypto_engine=crypto_engine
    )
    
    # Test data with various PII types
    original_records = [
        {
            "email": "john.doe@example.com",
            "name": "John Doe",
            "ssn": "123-45-6789",
            "phone": "+1-555-1234",
            "address": {
                "street": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "zip": "94102"
            },
            "user_id": "user_12345",
            "non_pii_field": "This should not be tokenized"
        },
        {
            "email": "jane.smith@example.com",
            "name": "Jane Smith",
            "ssn": "987-65-4321",
            "phone": "+1-555-5678",
            "address": {
                "street": "456 Oak Ave",
                "city": "New York",
                "state": "NY",
                "zip": "10001"
            },
            "user_id": "user_67890",
            "non_pii_field": "Another non-PII value"
        }
    ]
    
    print(f"\nOriginal Records: {len(original_records)}")
    for i, record in enumerate(original_records):
        print(f"\nRecord {i+1}:")
        print(f"  Email: {record['email']}")
        print(f"  Name: {record['name']}")
        print(f"  SSN: {record['ssn']}")
        print(f"  Phone: {record['phone']}")
        print(f"  Address: {record['address']['street']}, {record['address']['city']}")
        print(f"  Non-PII: {record['non_pii_field']}")
    
    # Step 1: Anonymize
    print("\n" + "="*60)
    print("STEP 1: ANONYMIZATION")
    print("="*60)
    
    anonymized_results = await tokenizer.anonymize_batch(
        original_records,
        "customer_db"
    )
    
    anonymized_records = [r.record for r in anonymized_results]
    
    print(f"\nAnonymized Records: {len(anonymized_records)}")
    for i, record in enumerate(anonymized_records):
        print(f"\nRecord {i+1}:")
        print(f"  Email (token): {record['email']}")
        print(f"  Name (token): {record['name']}")
        print(f"  SSN (token): {record['ssn']}")
        print(f"  Phone (token): {record['phone']}")
        print(f"  Address (token): {record['address']['street']}, {record['address']['city']}")
        print(f"  Non-PII (unchanged): {record['non_pii_field']}")
        print(f"  Anonymized flag: {record.get('_pii_anonymized', False)}")
    
    # Step 2: De-anonymize
    print("\n" + "="*60)
    print("STEP 2: DE-ANONYMIZATION")
    print("="*60)
    
    deanonymized_records = []
    for anonymized_record in anonymized_records:
        result = await tokenizer.deanonymize_record(
            anonymized_record,
            "customer_db"
        )
        deanonymized_records.append(result.record)
    
    print(f"\nDe-anonymized Records: {len(deanonymized_records)}")
    for i, record in enumerate(deanonymized_records):
        print(f"\nRecord {i+1}:")
        print(f"  Email: {record['email']}")
        print(f"  Name: {record['name']}")
        print(f"  SSN: {record['ssn']}")
        print(f"  Phone: {record['phone']}")
        print(f"  Address: {record['address']['street']}, {record['address']['city']}")
        print(f"  Non-PII: {record['non_pii_field']}")
    
    # Step 3: Verify data integrity
    print("\n" + "="*60)
    print("STEP 3: DATA INTEGRITY VERIFICATION")
    print("="*60)
    
    all_match = True
    for i, (original, deanonymized) in enumerate(zip(original_records, deanonymized_records)):
        print(f"\nRecord {i+1} Verification:")
        
        # Check each field
        fields_to_check = ["email", "name", "ssn", "phone", "non_pii_field"]
        for field in fields_to_check:
            original_value = original[field]
            deanonymized_value = deanonymized[field]
            match = original_value == deanonymized_value
            status = "✅" if match else "❌"
            print(f"  {field}: {status} {'MATCH' if match else 'MISMATCH'}")
            if not match:
                print(f"    Original: {original_value}")
                print(f"    De-anonymized: {deanonymized_value}")
                all_match = False
        
        # Check nested address
        address_fields = ["street", "city", "state", "zip"]
        for field in address_fields:
            original_value = original["address"][field]
            deanonymized_value = deanonymized["address"][field]
            match = original_value == deanonymized_value
            status = "✅" if match else "❌"
            print(f"  address.{field}: {status} {'MATCH' if match else 'MISMATCH'}")
            if not match:
                print(f"    Original: {original_value}")
                print(f"    De-anonymized: {deanonymized_value}")
                all_match = False
    
    # Final result
    print("\n" + "="*60)
    print("FINAL RESULT")
    print("="*60)
    
    if all_match:
        print("\n✅ SUCCESS: All data perfectly restored!")
        print("✅ NO DATA LOSS: 100% reversibility confirmed")
        print("✅ TOKENIZATION IS FULLY REVERSIBLE")
    else:
        print("\n❌ FAILURE: Data mismatch detected!")
        print("❌ DATA LOSS: Reversibility issue found")
    
    print("\n" + "="*60)
    
    await token_store.close()
    return all_match

if __name__ == "__main__":
    result = asyncio.run(test_reversibility())
    sys.exit(0 if result else 1)
