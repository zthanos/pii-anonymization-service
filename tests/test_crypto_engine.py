"""
Unit tests for CryptoEngine class.

Tests cover:
- Basic encryption/decryption round-trip
- Nonce generation uniqueness
- Key validation
- Error handling for corrupted data
- Edge cases (empty strings, special characters)
"""

import os
import pytest
from src.pii_service.core.crypto_engine import CryptoEngine, DataCorruptionError


class TestCryptoEngine:
    """Test suite for CryptoEngine AES-256-GCM encryption."""
    
    @pytest.fixture
    def engine(self):
        """Create a CryptoEngine instance."""
        return CryptoEngine()
    
    @pytest.fixture
    def valid_key(self):
        """Generate a valid 32-byte key."""
        return os.urandom(32)
    
    def test_encrypt_decrypt_round_trip(self, engine, valid_key):
        """Test that encryption followed by decryption returns original plaintext."""
        plaintext = "user@example.com"
        
        encrypted = engine.encrypt(plaintext, valid_key)
        decrypted = engine.decrypt(encrypted, valid_key)
        
        assert decrypted == plaintext
    
    def test_encrypt_returns_bytes(self, engine, valid_key):
        """Test that encrypt returns bytes."""
        plaintext = "test"
        encrypted = engine.encrypt(plaintext, valid_key)
        
        assert isinstance(encrypted, bytes)
    
    def test_encrypted_data_includes_nonce_and_tag(self, engine, valid_key):
        """Test that encrypted data is at least nonce + tag size."""
        plaintext = "x"
        encrypted = engine.encrypt(plaintext, valid_key)
        
        # Minimum size: nonce (12) + plaintext (1) + tag (16) = 29 bytes
        assert len(encrypted) >= engine.NONCE_SIZE + engine.TAG_SIZE
    
    def test_generate_nonce_returns_correct_size(self, engine):
        """Test that generate_nonce returns 12 bytes."""
        nonce = engine.generate_nonce()
        
        assert len(nonce) == 12
        assert isinstance(nonce, bytes)
    
    def test_generate_nonce_produces_unique_values(self, engine):
        """Test that generate_nonce produces different values each time."""
        nonces = [engine.generate_nonce() for _ in range(100)]
        
        # All nonces should be unique
        assert len(set(nonces)) == 100
    
    def test_encrypt_with_invalid_key_size_raises_error(self, engine):
        """Test that encrypt raises ValueError for invalid key size."""
        invalid_key = os.urandom(16)  # Wrong size (128-bit instead of 256-bit)
        
        with pytest.raises(ValueError, match="Key must be 32 bytes"):
            engine.encrypt("test", invalid_key)
    
    def test_decrypt_with_invalid_key_size_raises_error(self, engine, valid_key):
        """Test that decrypt raises ValueError for invalid key size."""
        plaintext = "test"
        encrypted = engine.encrypt(plaintext, valid_key)
        
        invalid_key = os.urandom(16)
        
        with pytest.raises(ValueError, match="Key must be 32 bytes"):
            engine.decrypt(encrypted, invalid_key)
    
    def test_decrypt_with_wrong_key_raises_corruption_error(self, engine):
        """Test that decrypt raises DataCorruptionError with wrong key."""
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        
        encrypted = engine.encrypt("test", key1)
        
        with pytest.raises(DataCorruptionError, match="Decryption failed"):
            engine.decrypt(encrypted, key2)
    
    def test_decrypt_with_corrupted_data_raises_error(self, engine, valid_key):
        """Test that decrypt raises DataCorruptionError for corrupted data."""
        plaintext = "test"
        encrypted = engine.encrypt(plaintext, valid_key)
        
        # Corrupt the ciphertext by flipping a bit
        corrupted = bytearray(encrypted)
        corrupted[-1] ^= 0x01  # Flip last bit (in the tag)
        
        with pytest.raises(DataCorruptionError, match="Decryption failed"):
            engine.decrypt(bytes(corrupted), valid_key)
    
    def test_decrypt_with_too_short_ciphertext_raises_error(self, engine, valid_key):
        """Test that decrypt raises DataCorruptionError for too short ciphertext."""
        too_short = b"short"
        
        with pytest.raises(DataCorruptionError, match="Ciphertext too short"):
            engine.decrypt(too_short, valid_key)
    
    def test_encrypt_empty_string(self, engine, valid_key):
        """Test encryption of empty string."""
        plaintext = ""
        
        encrypted = engine.encrypt(plaintext, valid_key)
        decrypted = engine.decrypt(encrypted, valid_key)
        
        assert decrypted == plaintext
    
    def test_encrypt_unicode_characters(self, engine, valid_key):
        """Test encryption of unicode characters."""
        plaintext = "Hello 世界 🌍"
        
        encrypted = engine.encrypt(plaintext, valid_key)
        decrypted = engine.decrypt(encrypted, valid_key)
        
        assert decrypted == plaintext
    
    def test_encrypt_long_string(self, engine, valid_key):
        """Test encryption of long string."""
        plaintext = "a" * 10000
        
        encrypted = engine.encrypt(plaintext, valid_key)
        decrypted = engine.decrypt(encrypted, valid_key)
        
        assert decrypted == plaintext
    
    def test_encrypt_special_characters(self, engine, valid_key):
        """Test encryption of special characters."""
        plaintext = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        
        encrypted = engine.encrypt(plaintext, valid_key)
        decrypted = engine.decrypt(encrypted, valid_key)
        
        assert decrypted == plaintext
    
    def test_same_plaintext_produces_different_ciphertext(self, engine, valid_key):
        """Test that encrypting same plaintext twice produces different ciphertext."""
        plaintext = "test"
        
        encrypted1 = engine.encrypt(plaintext, valid_key)
        encrypted2 = engine.encrypt(plaintext, valid_key)
        
        # Different nonces should produce different ciphertexts
        assert encrypted1 != encrypted2
        
        # But both should decrypt to same plaintext
        assert engine.decrypt(encrypted1, valid_key) == plaintext
        assert engine.decrypt(encrypted2, valid_key) == plaintext
    
    def test_constants_are_correct(self, engine):
        """Test that class constants have correct values."""
        assert engine.NONCE_SIZE == 12
        assert engine.KEY_SIZE == 32
        assert engine.TAG_SIZE == 16
    
    def test_encrypt_pii_examples(self, engine, valid_key):
        """Test encryption of realistic PII examples."""
        pii_examples = [
            "john.doe@example.com",
            "555-123-4567",
            "123-45-6789",
            "123 Main St, Anytown, USA",
            "John Doe"
        ]
        
        for pii in pii_examples:
            encrypted = engine.encrypt(pii, valid_key)
            decrypted = engine.decrypt(encrypted, valid_key)
            assert decrypted == pii
