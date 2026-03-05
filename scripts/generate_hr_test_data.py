#!/usr/bin/env python3
"""
Generate realistic HR test data for benchmarking.

Creates 360,000 employee records with 12 properties including:
- Employee identification (employee_id, ssn, email, phone)
- Personal information (first_name, last_name, date_of_birth)
- Payroll information (salary, bank_account)
- Position information (position, department)
- Benefits information (emergency_contact)
"""

import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path


# Realistic data pools
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Shirley", "Eric", "Angela", "Jonathan", "Helen", "Stephen", "Anna",
    "Larry", "Brenda", "Justin", "Pamela", "Scott", "Nicole", "Brandon", "Emma",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory", "Debra",
    "Frank", "Rachel", "Alexander", "Catherine", "Patrick", "Carolyn", "Raymond", "Janet",
    "Jack", "Ruth", "Dennis", "Maria", "Jerry", "Heather", "Tyler", "Diane"
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
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza",
    "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers",
    "Long", "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry", "Russell"
]

DEPARTMENTS = [
    "Engineering", "Sales", "Marketing", "Human Resources", "Finance", "Operations",
    "Customer Support", "Product Management", "Legal", "IT", "Research & Development",
    "Quality Assurance", "Business Development", "Administration", "Procurement",
    "Logistics", "Manufacturing", "Design", "Analytics", "Security"
]

POSITIONS = [
    "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer",
    "Engineering Manager", "Director of Engineering", "VP of Engineering", "CTO",
    "Sales Representative", "Account Executive", "Sales Manager", "VP of Sales",
    "Marketing Specialist", "Marketing Manager", "CMO", "Product Manager",
    "Senior Product Manager", "Director of Product", "VP of Product", "CEO",
    "HR Specialist", "HR Manager", "CHRO", "Financial Analyst", "Accountant",
    "Controller", "CFO", "Operations Manager", "COO", "Support Specialist",
    "Support Manager", "QA Engineer", "QA Manager", "Business Analyst",
    "Data Analyst", "Data Scientist", "Security Engineer", "DevOps Engineer",
    "Designer", "Senior Designer", "Design Manager", "Legal Counsel", "Paralegal",
    "Procurement Specialist", "Logistics Coordinator", "Manufacturing Technician",
    "Research Scientist", "Administrative Assistant", "Executive Assistant"
]


def generate_ssn():
    """Generate a realistic SSN format."""
    return f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"


def generate_email(first_name, last_name, employee_id):
    """Generate a corporate email address."""
    domains = ["company.com", "corp.com", "enterprise.com"]
    return f"{first_name.lower()}.{last_name.lower()}{employee_id % 1000}@{random.choice(domains)}"


def generate_phone():
    """Generate a US phone number."""
    return f"+1-{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}"


def generate_date_of_birth():
    """Generate a date of birth (age 22-65)."""
    today = datetime.now()
    years_ago = random.randint(22, 65)
    days_offset = random.randint(0, 365)
    dob = today - timedelta(days=years_ago * 365 + days_offset)
    return dob.strftime("%Y-%m-%d")


def generate_salary():
    """Generate a realistic salary based on position level."""
    # Salary ranges from $40k to $500k
    base = random.randint(40000, 500000)
    # Round to nearest $1000
    return round(base / 1000) * 1000


def generate_bank_account():
    """Generate a bank account number."""
    return f"{random.randint(100000000, 999999999)}"


def generate_emergency_contact():
    """Generate an emergency contact name and phone."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    phone = generate_phone()
    return f"{first} {last} - {phone}"


def generate_employee_record(employee_id):
    """Generate a single employee record with 12 properties."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    
    return {
        "employee_id": f"E{employee_id:06d}",
        "ssn": generate_ssn(),
        "email": generate_email(first_name, last_name, employee_id),
        "phone": generate_phone() if random.random() > 0.05 else None,  # 5% no phone
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": generate_date_of_birth(),
        "salary": generate_salary(),
        "bank_account": generate_bank_account(),
        "position": random.choice(POSITIONS),
        "department": random.choice(DEPARTMENTS),
        "emergency_contact": generate_emergency_contact() if random.random() > 0.02 else None  # 2% no contact
    }


def generate_hr_dataset(num_records=360000, output_file="data/test_data/hr_test_data_360k.ndjson"):
    """Generate HR test dataset and save as NDJSON."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating {num_records:,} employee records...")
    print(f"Output file: {output_file}")
    
    with open(output_path, 'w') as f:
        for i in range(1, num_records + 1):
            record = generate_employee_record(i)
            f.write(json.dumps(record) + '\n')
            
            if i % 10000 == 0:
                print(f"  Generated {i:,} records ({i/num_records*100:.1f}%)")
    
    print(f"\n✅ Successfully generated {num_records:,} records")
    
    # Print sample record
    print("\nSample record:")
    sample = generate_employee_record(1)
    print(json.dumps(sample, indent=2))
    
    # Print file size
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nFile size: {file_size_mb:.2f} MB")
    print(f"Average record size: {file_size_mb * 1024 / num_records:.2f} KB")


if __name__ == "__main__":
    import sys
    
    num_records = 360000
    if len(sys.argv) > 1:
        num_records = int(sys.argv[1])
    
    generate_hr_dataset(num_records)
