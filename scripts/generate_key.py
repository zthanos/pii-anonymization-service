#!/usr/bin/env python3
"""Generate a 32-byte encryption key for AES-256-GCM."""

import os
import base64


def generate_key() -> str:
    """
    Generate a cryptographically secure 32-byte key.
    
    Returns:
        Base64-encoded key string
    """
    # Generate 32 random bytes (256 bits)
    key_bytes = os.urandom(32)
    
    # Encode as base64 for easy storage in environment variables
    key_b64 = base64.b64encode(key_bytes).decode('utf-8')
    
    return key_b64


if __name__ == "__main__":
    key = generate_key()
    print("Generated 32-byte encryption key (base64-encoded):")
    print(key)
    print()
    print("Add this to your .env file:")
    print(f"CUSTOMER_DB_KEY={key}")
    print(f"ANALYTICS_DB_KEY={key}")
