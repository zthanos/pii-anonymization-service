#!/usr/bin/env python3
"""
Generate test data for PII anonymization benchmarks.

This script generates large datasets of realistic PII records for performance testing.
Supports generating millions of records with configurable output formats.
"""

import json
import random
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any
import time


# Sample data for realistic record generation
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
]

STREET_NAMES = [
    "Main", "Oak", "Pine", "Maple", "Cedar", "Elm", "Washington", "Lake",
    "Hill", "Park", "River", "Sunset", "First", "Second", "Third", "Fourth",
    "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Broadway", "Lincoln",
    "Madison", "Jefferson", "Adams", "Jackson", "Franklin", "Church", "Spring", "Center",
]

STREET_TYPES = ["St", "Ave", "Blvd", "Dr", "Ln", "Rd", "Way", "Ct", "Pl", "Ter"]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
    "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
    "Fort Worth", "Columbus", "Charlotte", "San Francisco", "Indianapolis", "Seattle",
    "Denver", "Washington", "Boston", "Nashville", "Detroit", "Portland",
    "Las Vegas", "Memphis", "Louisville", "Baltimore", "Milwaukee", "Albuquerque",
]

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


class TestDataGenerator:
    """Generate realistic test data for PII anonymization."""
    
    def __init__(self, seed: int = 42):
        """
        Initialize generator with random seed.
        
        Args:
            seed: Random seed for reproducibility
        """
        random.seed(seed)
        self.record_count = 0
    
    def generate_ssn(self) -> str:
        """Generate a random SSN in format XXX-XX-XXXX."""
        area = random.randint(1, 899)  # Avoid 000, 666, 900-999
        if area == 666:
            area = 667
        group = random.randint(1, 99)
        serial = random.randint(1, 9999)
        return f"{area:03d}-{group:02d}-{serial:04d}"
    
    def generate_phone(self) -> str:
        """Generate a random US phone number."""
        area_code = random.randint(200, 999)
        exchange = random.randint(200, 999)
        number = random.randint(0, 9999)
        return f"+1-{area_code}-{exchange}-{number:04d}"
    
    def generate_email(self, first_name: str, last_name: str) -> str:
        """Generate an email address."""
        domains = ["example.com", "test.com", "demo.com", "sample.com", "mail.com"]
        separators = [".", "_", ""]
        
        separator = random.choice(separators)
        domain = random.choice(domains)
        
        # Add random number sometimes
        if random.random() < 0.3:
            number = random.randint(1, 999)
            return f"{first_name.lower()}{separator}{last_name.lower()}{number}@{domain}"
        else:
            return f"{first_name.lower()}{separator}{last_name.lower()}@{domain}"
    
    def generate_address(self) -> Dict[str, str]:
        """Generate a random US address."""
        street_number = random.randint(1, 9999)
        street_name = random.choice(STREET_NAMES)
        street_type = random.choice(STREET_TYPES)
        city = random.choice(CITIES)
        state = random.choice(STATES)
        zip_code = random.randint(10000, 99999)
        
        return {
            "street": f"{street_number} {street_name} {street_type}",
            "city": city,
            "state": state,
            "zip": str(zip_code),
        }
    
    def generate_record(self) -> Dict[str, Any]:
        """
        Generate a single test record with PII.
        
        Returns:
            Dictionary with PII fields matching the policy configuration
        """
        self.record_count += 1
        
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"
        
        return {
            "email": self.generate_email(first_name, last_name),
            "name": full_name,
            "ssn": self.generate_ssn(),
            "address": self.generate_address(),
            "phone": self.generate_phone(),
            "user_id": f"user_{self.record_count:010d}",
            # Add some non-PII fields
            "account_type": random.choice(["premium", "standard", "basic"]),
            "status": random.choice(["active", "inactive", "pending"]),
            "created_at": f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
        }
    
    def generate_batch(self, count: int) -> List[Dict[str, Any]]:
        """
        Generate a batch of records.
        
        Args:
            count: Number of records to generate
            
        Returns:
            List of records
        """
        return [self.generate_record() for _ in range(count)]
    
    def save_json(self, records: List[Dict[str, Any]], output_file: Path):
        """
        Save records as JSON array.
        
        Args:
            records: List of records
            output_file: Output file path
        """
        with open(output_file, 'w') as f:
            json.dump(records, f, indent=2)
    
    def save_ndjson(self, records: List[Dict[str, Any]], output_file: Path):
        """
        Save records as NDJSON (newline-delimited JSON).
        
        Args:
            records: List of records
            output_file: Output file path
        """
        with open(output_file, 'w') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')
    
    def save_streaming(self, count: int, output_file: Path, format: str = 'ndjson'):
        """
        Generate and save records in streaming fashion (memory efficient).
        
        Args:
            count: Number of records to generate
            output_file: Output file path
            format: Output format ('json' or 'ndjson')
        """
        with open(output_file, 'w') as f:
            if format == 'json':
                f.write('[\n')
            
            for i in range(count):
                record = self.generate_record()
                
                if format == 'json':
                    f.write('  ' + json.dumps(record))
                    if i < count - 1:
                        f.write(',\n')
                    else:
                        f.write('\n')
                else:  # ndjson
                    f.write(json.dumps(record) + '\n')
                
                # Progress indicator
                if (i + 1) % 10000 == 0:
                    print(f"  Generated {i + 1:,} / {count:,} records...", end='\r')
            
            if format == 'json':
                f.write(']\n')
            
            print(f"  Generated {count:,} / {count:,} records... Done!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate test data for PII anonymization benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 1 million records as NDJSON (memory efficient)
  python generate_test_data.py -n 1000000 -o test_data_1m.ndjson
  
  # Generate 10k records as JSON array
  python generate_test_data.py -n 10000 -o test_data_10k.json -f json
  
  # Generate with custom seed for reproducibility
  python generate_test_data.py -n 100000 -o test_data.ndjson -s 12345
        """
    )
    
    parser.add_argument(
        '-n', '--num-records',
        type=int,
        required=True,
        help='Number of records to generate'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help='Output file path'
    )
    
    parser.add_argument(
        '-f', '--format',
        type=str,
        choices=['json', 'ndjson'],
        default='ndjson',
        help='Output format (default: ndjson)'
    )
    
    parser.add_argument(
        '-s', '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=None,
        help='Generate in batches (for small datasets, loads all in memory)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.num_records <= 0:
        print("Error: Number of records must be positive", file=sys.stderr)
        sys.exit(1)
    
    output_path = Path(args.output)
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize generator
    generator = TestDataGenerator(seed=args.seed)
    
    print(f"Generating {args.num_records:,} test records...")
    print(f"Output file: {output_path}")
    print(f"Format: {args.format}")
    print(f"Random seed: {args.seed}")
    print()
    
    start_time = time.time()
    
    # Generate data
    if args.batch_size:
        # Batch mode (loads in memory)
        print(f"Using batch mode (batch size: {args.batch_size:,})")
        all_records = []
        
        for i in range(0, args.num_records, args.batch_size):
            batch_size = min(args.batch_size, args.num_records - i)
            batch = generator.generate_batch(batch_size)
            all_records.extend(batch)
            print(f"  Generated {len(all_records):,} / {args.num_records:,} records...", end='\r')
        
        print(f"  Generated {len(all_records):,} / {args.num_records:,} records... Done!")
        
        # Save to file
        print(f"\nSaving to {output_path}...")
        if args.format == 'json':
            generator.save_json(all_records, output_path)
        else:
            generator.save_ndjson(all_records, output_path)
    else:
        # Streaming mode (memory efficient)
        print("Using streaming mode (memory efficient)")
        generator.save_streaming(args.num_records, output_path, args.format)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Print summary
    file_size = output_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    
    print()
    print("=" * 60)
    print("Generation Complete!")
    print("=" * 60)
    print(f"Records generated: {args.num_records:,}")
    print(f"Output file: {output_path}")
    print(f"File size: {file_size_mb:.2f} MB")
    print(f"Time elapsed: {elapsed:.2f} seconds")
    print(f"Generation rate: {args.num_records / elapsed:,.0f} records/second")
    print()
    
    # Show sample record
    print("Sample record:")
    sample = generator.generate_record()
    print(json.dumps(sample, indent=2))


if __name__ == "__main__":
    main()
