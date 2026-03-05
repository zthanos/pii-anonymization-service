"""
CryptoEngine: AES-256-GCM encryption/decryption for PII values.

This module provides secure encryption and decryption of PII data using
AES-256-GCM (Galois/Counter Mode), which provides both confidentiality
and authenticity through authenticated encryption.

Security Features:
- AES-256-GCM authenticated encryption
- Unique 96-bit nonce per encryption operation
- Cryptographically secure random nonce generation
- Authentication tag verification on decryption
- No plaintext PII logging

Format:
    Encrypted data format: nonce (12 bytes) + ciphertext + tag (16 bytes)
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DataCorruptionError(Exception):
    """Raised when decryption fails due to corrupted data or invalid authentication tag."""
    pass


class CryptoEngine:
    """
    AES-256-GCM encryption engine for PII data.
    
    This class provides methods to encrypt and decrypt PII values using
    AES-256-GCM authenticated encryption. Each encryption operation generates
    a unique nonce to ensure security.
    
    Constants:
        NONCE_SIZE: 12 bytes (96 bits) - standard for GCM
        KEY_SIZE: 32 bytes (256 bits) - AES-256
        TAG_SIZE: 16 bytes (128 bits) - GCM authentication tag
    
    Example:
        >>> engine = CryptoEngine()
        >>> key = os.urandom(32)  # 256-bit key
        >>> encrypted = engine.encrypt("sensitive@email.com", key)
        >>> decrypted = engine.decrypt(encrypted, key)
        >>> assert decrypted == "sensitive@email.com"
    """

    NONCE_SIZE = 12  # 96 bits - standard for GCM
    KEY_SIZE = 32    # 256 bits - AES-256
    TAG_SIZE = 16    # 128 bits - GCM authentication tag

    def __init__(self):
        """Initialize the CryptoEngine."""
        pass

    def generate_nonce(self) -> bytes:
        """
        Generate a cryptographically secure random nonce.
        
        Uses os.urandom() to generate a 96-bit (12-byte) nonce suitable
        for AES-GCM encryption. Each nonce MUST be unique for a given key
        to maintain security guarantees.
        
        Returns:
            bytes: 12-byte random nonce
            
        Note:
            Never reuse a nonce with the same key. Each encryption operation
            should generate a fresh nonce.
        """
        return os.urandom(self.NONCE_SIZE)

    def encrypt(self, plaintext: str, key: bytes, value_type: str = "str") -> bytes:
        """
        Encrypt plaintext with AES-256-GCM, preserving type information.
        
        Encrypts the provided plaintext string using AES-256-GCM authenticated
        encryption. A unique nonce is generated for each encryption operation.
        The output format is: nonce || type_byte || ciphertext || tag
        
        Args:
            plaintext: String to encrypt (PII value)
            key: 32-byte (256-bit) encryption key
            value_type: Type of the original value ("str", "int", "float", "bool")
            
        Returns:
            bytes: Encrypted data in format: nonce (12) + type_byte (1) + ciphertext + tag (16)
            
        Raises:
            ValueError: If key is not exactly 32 bytes
            
        Example:
            >>> engine = CryptoEngine()
            >>> key = os.urandom(32)
            >>> encrypted = engine.encrypt("user@example.com", key, "str")
            >>> len(encrypted) >= 12 + 1 + 16  # At least nonce + type + tag
            True
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes, got {len(key)}")

        # Map type names to single byte identifiers
        type_map = {"str": b"s", "int": b"i", "float": b"f", "bool": b"b"}
        type_byte = type_map.get(value_type, b"s")  # Default to string

        # Create AESGCM cipher with the provided key
        aesgcm = AESGCM(key)

        # Generate unique nonce for this encryption
        nonce = self.generate_nonce()

        # Encrypt and authenticate
        # AESGCM.encrypt returns ciphertext with tag appended
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode('utf-8'),
            None  # No additional authenticated data (AAD)
        )

        # Prepend nonce and type byte to ciphertext+tag
        # Format: nonce (12 bytes) + type_byte (1 byte) + ciphertext + tag (16 bytes)
        return nonce + type_byte + ciphertext

    def decrypt(self, ciphertext: bytes, key: bytes) -> tuple[str, str]:
        """
        Decrypt ciphertext with AES-256-GCM and return value with type information.
        
        Decrypts data encrypted with the encrypt() method. Verifies the GCM
        authentication tag to ensure data integrity and authenticity. Returns
        both the decrypted value and its original type.
        
        Args:
            ciphertext: Encrypted data (nonce + type_byte + ciphertext + tag)
            key: 32-byte (256-bit) encryption key (must match encryption key)
            
        Returns:
            tuple: (decrypted_value, value_type) where value_type is "str", "int", "float", or "bool"
            
        Raises:
            ValueError: If key is not exactly 32 bytes
            DataCorruptionError: If ciphertext is too short, GCM tag verification
                fails, or data is corrupted
                
        Example:
            >>> engine = CryptoEngine()
            >>> key = os.urandom(32)
            >>> encrypted = engine.encrypt("secret", key, "str")
            >>> decrypted, value_type = engine.decrypt(encrypted, key)
            >>> assert decrypted == "secret" and value_type == "str"
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes, got {len(key)}")

        # Validate minimum ciphertext length
        # Must have at least: nonce (12) + type_byte (1) + tag (16) = 29 bytes
        min_length = self.NONCE_SIZE + 1 + self.TAG_SIZE
        if len(ciphertext) < min_length:
            # Handle legacy format without type byte (backwards compatibility)
            if len(ciphertext) >= self.NONCE_SIZE + self.TAG_SIZE:
                # Extract nonce from the beginning
                nonce = ciphertext[:self.NONCE_SIZE]
                encrypted_data = ciphertext[self.NONCE_SIZE:]
                
                # Create AESGCM cipher with the provided key
                aesgcm = AESGCM(key)
                
                try:
                    plaintext_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
                    return plaintext_bytes.decode('utf-8'), "str"
                except Exception as e:
                    raise DataCorruptionError(
                        f"Decryption failed - data may be corrupted or key is incorrect: {str(e)}"
                    )
            else:
                raise DataCorruptionError(
                    f"Ciphertext too short: expected at least {min_length} bytes, "
                    f"got {len(ciphertext)}"
                )

        # Extract nonce from the beginning
        nonce = ciphertext[:self.NONCE_SIZE]
        
        # Extract type byte
        type_byte = ciphertext[self.NONCE_SIZE:self.NONCE_SIZE + 1]
        
        # Map type bytes back to type names
        type_map = {b"s": "str", b"i": "int", b"f": "float", b"b": "bool"}
        value_type = type_map.get(type_byte, "str")  # Default to string

        # Extract ciphertext+tag (everything after nonce and type byte)
        encrypted_data = ciphertext[self.NONCE_SIZE + 1:]

        # Create AESGCM cipher with the provided key
        aesgcm = AESGCM(key)

        try:
            # Decrypt and verify authentication tag
            # This will raise an exception if the tag is invalid
            plaintext_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
            return plaintext_bytes.decode('utf-8'), value_type
        except Exception as e:
            # Any decryption failure indicates corrupted data or wrong key
            raise DataCorruptionError(
                f"Decryption failed - data may be corrupted or key is incorrect: {str(e)}"
            )
