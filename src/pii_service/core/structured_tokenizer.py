"""
StructuredTokenizer: Tokenize and de-tokenize structured JSON records.

This module provides the StructuredTokenizer class which handles anonymization
and de-anonymization of structured JSON records based on policy-defined PII fields.

Key Features:
- Dot-notation field path support (e.g., address.street)
- Multiple token formats (UUID, deterministic HMAC-SHA256, prefixed)
- Streaming processing with immediate response
- Batch Redis operations for performance
- Field-level error handling
- Nullable field support

Performance:
- Async I/O throughout
- Redis pipelining for batch operations
- No buffering - stream records immediately
- Target: 50k+ records/sec via gRPC, <5ms p95 latency
"""

import uuid
import hmac
import hashlib
from typing import Any, Optional, List, Dict, AsyncIterator
from pydantic import BaseModel
import structlog

from .policy_loader import PolicyLoader
from .token_store import TokenStore, TokenMapping
from .crypto_engine import CryptoEngine


logger = structlog.get_logger()


class AnonymizedRecord(BaseModel):
    """Result of anonymizing a single record.
    
    Attributes:
        record: Anonymized record with tokens replacing PII values
        token_ids: List of generated token IDs
        error: Error message if anonymization failed, None otherwise
        _pii_anonymized: Flag indicating successful anonymization
    """

    record: dict
    token_ids: List[str]
    error: Optional[str] = None
    _pii_anonymized: bool = True


class DeanonymizedRecord(BaseModel):
    """Result of de-anonymizing a single record.
    
    Attributes:
        record: De-anonymized record with original PII values restored
        errors: Dict mapping field paths to error messages for failed fields
    """

    record: dict
    errors: Dict[str, str] = {}


class StructuredTokenizer:
    """
    Handles structured data anonymization and de-anonymization.
    
    This class processes JSON records by extracting PII fields based on policy
    configuration, generating tokens, encrypting original values, and storing
    them in Redis. Supports streaming processing for high throughput.
    
    Attributes:
        policy_loader: PolicyLoader instance for accessing system configurations
        token_store: TokenStore instance for Redis operations
        crypto_engine: CryptoEngine instance for encryption/decryption
        logger: Structured logger instance
    
    Example:
        >>> tokenizer = StructuredTokenizer(policy_loader, token_store, crypto_engine)
        >>> record = {"email": "user@example.com", "name": "John Doe"}
        >>> result = await tokenizer.anonymize_record(record, "customer_db")
        >>> print(result.record)  # {"email": "tok_abc123", "name": "tok_xyz789", "_pii_anonymized": true}
    """

    def __init__(
        self,
        policy_loader: PolicyLoader,
        token_store: TokenStore,
        crypto_engine: CryptoEngine,
    ):
        """
        Initialize the StructuredTokenizer.
        
        Args:
            policy_loader: PolicyLoader instance for accessing configurations
            token_store: TokenStore instance for Redis operations
            crypto_engine: CryptoEngine instance for encryption/decryption
        """
        self.policy_loader = policy_loader
        self.token_store = token_store
        self.crypto_engine = crypto_engine
        self.logger = logger.bind(component="structured_tokenizer")

    def extract_field_value(self, record: dict, field_path: str) -> Any:
        """
        Extract value using dot-notation path.
        
        Navigates nested JSON objects using dot-separated field names.
        Example: "address.street" → record["address"]["street"]
        
        Args:
            record: JSON object to extract from
            field_path: Dot-notation field path (e.g., "address.street")
            
        Returns:
            Field value or None if not found
            
        Raises:
            ValueError: If path navigation fails (non-dict intermediate value)
            
        Example:
            >>> record = {"address": {"street": "123 Main St"}}
            >>> tokenizer.extract_field_value(record, "address.street")
            "123 Main St"
        """
        parts = field_path.split('.')
        value = record

        for part in parts:
            if not isinstance(value, dict):
                raise ValueError(
                    f"Cannot navigate to {field_path}: '{part}' is not a dict"
                )

            value = value.get(part)
            if value is None:
                return None

        return value

    def set_field_value(self, record: dict, field_path: str, value: Any) -> None:
        """
        Set value using dot-notation path.
        
        Creates intermediate dictionaries as needed to set the value at the
        specified path. Modifies the record in-place.
        
        Args:
            record: JSON object to modify
            field_path: Dot-notation field path (e.g., "address.street")
            value: Value to set
            
        Example:
            >>> record = {}
            >>> tokenizer.set_field_value(record, "address.street", "123 Main St")
            >>> print(record)  # {"address": {"street": "123 Main St"}}
        """
        parts = field_path.split('.')
        current = record

        # Navigate to the parent of the target field, creating dicts as needed
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                # If intermediate value exists but is not a dict, we can't navigate
                raise ValueError(
                    f"Cannot set {field_path}: '{part}' exists but is not a dict"
                )
            current = current[part]

        # Set the final value
        current[parts[-1]] = value

    def generate_token(
        self,
        value: str,
        deterministic: bool,
        key: bytes,
        token_format: str,
        token_prefix: Optional[str] = None,
    ) -> str:
        """
        Generate token based on configuration.
        
        Supports three token formats:
        - uuid: UUID v4 (non-deterministic, ignores deterministic flag)
        - deterministic: HMAC-SHA256(key, value) as hex (always deterministic)
        - prefixed: prefix + (UUID if non-deterministic, HMAC if deterministic)
        
        Args:
            value: PII value to tokenize
            deterministic: Whether to use deterministic tokenization (only for prefixed format)
            key: Encryption key for deterministic tokens
            token_format: Format type ("uuid", "deterministic", "prefixed")
            token_prefix: Prefix for "prefixed" format
            
        Returns:
            Generated token string
            
        Example:
            >>> token = tokenizer.generate_token(
            ...     "user@example.com",
            ...     deterministic=True,
            ...     key=encryption_key,
            ...     token_format="prefixed",
            ...     token_prefix="EMAIL_"
            ... )
            >>> token.startswith("EMAIL_")
            True
        """
        # Generate base token based on format
        if token_format == "uuid":
            # UUID format is always non-deterministic
            token = str(uuid.uuid4())
        elif token_format == "deterministic":
            # Deterministic format always uses HMAC
            h = hmac.new(key, value.encode('utf-8'), hashlib.sha256)
            token = h.hexdigest()
        elif token_format == "prefixed":
            # Prefixed format uses deterministic flag to choose
            if deterministic:
                h = hmac.new(key, value.encode('utf-8'), hashlib.sha256)
                token = h.hexdigest()
            else:
                token = str(uuid.uuid4())

            # Add prefix
            if token_prefix:
                return f"{token_prefix}{token}"
        else:
            # Default to UUID
            token = str(uuid.uuid4())

        return token

    async def anonymize_record(
        self,
        record: dict,
        system_id: str,
    ) -> AnonymizedRecord:
        """
        Anonymize a single JSON record.
        
        Processes one record by:
        1. Extracting all PII field values based on policy
        2. Generating tokens for each PII field
        3. Encrypting original values
        4. Storing encrypted values in Redis (batch operation)
        5. Replacing PII values with tokens
        6. Adding _pii_anonymized flag
        
        Args:
            record: JSON object with PII fields
            system_id: System identifier for policy lookup
            
        Returns:
            AnonymizedRecord with tokens and metadata
            
        Example:
            >>> record = {"email": "user@example.com", "name": "John"}
            >>> result = await tokenizer.anonymize_record(record, "customer_db")
            >>> print(result.record["email"])  # Token string
            >>> print(result.token_ids)  # List of generated tokens
        """
        try:
            # Get system configuration
            config = self.policy_loader.get_system_config(system_id)
            encryption_key = self.policy_loader.get_encryption_key(system_id)

            if not config.structured:
                raise ValueError(
                    f"System '{system_id}' does not have structured configuration"
                )

            # Create a copy of the record to modify
            anonymized_record = record.copy()
            token_mappings = []
            token_ids = []

            # Process each PII field
            for field_config in config.structured.pii_fields:
                try:
                    # Extract field value
                    value = self.extract_field_value(record, field_config.name)

                    # Handle null values
                    if value is None:
                        if not field_config.nullable:
                            raise ValueError(
                                f"Field '{field_config.name}' is null but not nullable"
                            )
                        # Skip null nullable fields
                        continue

                    # Determine value type for preservation
                    value_type = type(value).__name__
                    if value_type not in ("str", "int", "float", "bool"):
                        value_type = "str"  # Default to string for other types

                    # Generate token
                    token = self.generate_token(
                        str(value),
                        field_config.deterministic,
                        encryption_key,
                        field_config.token_format,
                        field_config.token_prefix,
                    )

                    # Encrypt original value with type information
                    encrypted_value = self.crypto_engine.encrypt(
                        str(value),
                        encryption_key,
                        value_type,
                    )

                    # Prepare for batch storage
                    token_mappings.append(TokenMapping(
                        system_id=system_id,
                        token=token,
                        encrypted_value=encrypted_value,
                        ttl_seconds=config.structured.token_ttl_seconds,
                    ))

                    # Replace field value with token
                    self.set_field_value(anonymized_record, field_config.name, token)
                    token_ids.append(token)

                except Exception as e:
                    # Log field-level error but continue processing
                    self.logger.warning(
                        "field_anonymization_failed",
                        system_id=system_id,
                        field=field_config.name,
                        error=str(e),
                    )
                    # Re-raise to fail the entire record
                    raise ValueError(
                        f"Failed to anonymize field '{field_config.name}': {str(e)}"
                    )

            # Batch write to Redis
            if token_mappings:
                await self.token_store.store_batch(token_mappings)

            # Add anonymization flag
            anonymized_record['_pii_anonymized'] = True

            return AnonymizedRecord(
                record=anonymized_record,
                token_ids=token_ids,
                error=None,
                _pii_anonymized=True,
            )

        except Exception as e:
            # Return error record
            self.logger.error(
                "record_anonymization_failed",
                system_id=system_id,
                error=str(e),
            )

            # Return error record with _pii_anonymized=False in the record itself
            error_record = record.copy()
            error_record['_pii_anonymized'] = False

            return AnonymizedRecord(
                record=error_record,
                token_ids=[],
                error=str(e),
                _pii_anonymized=False,
            )

    async def anonymize_batch(
        self,
        records: List[dict],
        system_id: str,
    ) -> List[AnonymizedRecord]:
        """
        Anonymize multiple records in a single batch operation.
        
        This method processes multiple records together and uses a single
        Redis pipeline for all token storage operations, significantly
        reducing network overhead compared to processing records individually.
        
        Args:
            records: List of JSON objects with PII fields
            system_id: System identifier for policy lookup
            
        Returns:
            List of AnonymizedRecord results (one per input record)
            
        Example:
            >>> records = [
            ...     {"email": "user1@example.com", "name": "John"},
            ...     {"email": "user2@example.com", "name": "Jane"}
            ... ]
            >>> results = await tokenizer.anonymize_batch(records, "customer_db")
            >>> len(results)
            2
        """
        try:
            # Get system configuration once for all records
            config = self.policy_loader.get_system_config(system_id)
            encryption_key = self.policy_loader.get_encryption_key(system_id)

            if not config.structured:
                raise ValueError(
                    f"System '{system_id}' does not have structured configuration"
                )

            # Collect all token mappings from all records
            all_token_mappings = []
            results = []

            # Process each record
            for record in records:
                try:
                    # Create a copy of the record to modify
                    anonymized_record = record.copy()
                    token_ids = []

                    # Process each PII field
                    for field_config in config.structured.pii_fields:
                        try:
                            # Extract field value
                            value = self.extract_field_value(record, field_config.name)

                            # Handle null values
                            if value is None:
                                if not field_config.nullable:
                                    raise ValueError(
                                        f"Field '{field_config.name}' is null but not nullable"
                                    )
                                # Skip null nullable fields
                                continue

                            # Determine value type for preservation
                            value_type = type(value).__name__
                            if value_type not in ("str", "int", "float", "bool"):
                                value_type = "str"  # Default to string for other types

                            # Generate token
                            token = self.generate_token(
                                str(value),
                                field_config.deterministic,
                                encryption_key,
                                field_config.token_format,
                                field_config.token_prefix,
                            )

                            # Encrypt original value with type information
                            encrypted_value = self.crypto_engine.encrypt(
                                str(value),
                                encryption_key,
                                value_type,
                            )

                            # Prepare for batch storage
                            all_token_mappings.append(TokenMapping(
                                system_id=system_id,
                                token=token,
                                encrypted_value=encrypted_value,
                                ttl_seconds=config.structured.token_ttl_seconds,
                            ))

                            # Replace field value with token
                            self.set_field_value(anonymized_record, field_config.name, token)
                            token_ids.append(token)

                        except Exception as e:
                            # Log field-level error but continue processing
                            self.logger.warning(
                                "field_anonymization_failed",
                                system_id=system_id,
                                field=field_config.name,
                                error=str(e),
                            )
                            # Re-raise to fail the entire record
                            raise ValueError(
                                f"Failed to anonymize field '{field_config.name}': {str(e)}"
                            )

                    # Add anonymization flag
                    anonymized_record['_pii_anonymized'] = True

                    results.append(AnonymizedRecord(
                        record=anonymized_record,
                        token_ids=token_ids,
                        error=None,
                        _pii_anonymized=True,
                    ))

                except Exception as e:
                    # Return error record for this record
                    error_record = record.copy()
                    error_record['_pii_anonymized'] = False

                    results.append(AnonymizedRecord(
                        record=error_record,
                        token_ids=[],
                        error=str(e),
                        _pii_anonymized=False,
                    ))

            # Single batch write to Redis for all tokens from all records
            if all_token_mappings:
                await self.token_store.store_batch(all_token_mappings)

            return results

        except Exception as e:
            # Return error for all records
            self.logger.error(
                "batch_anonymization_failed",
                system_id=system_id,
                error=str(e),
            )

            # Return error records for all inputs
            error_results = []
            for record in records:
                error_record = record.copy()
                error_record['_pii_anonymized'] = False
                error_results.append(AnonymizedRecord(
                    record=error_record,
                    token_ids=[],
                    error=str(e),
                    _pii_anonymized=False,
                ))

            return error_results

    async def anonymize_stream(
        self,
        records: AsyncIterator[dict],
        system_id: str,
    ) -> AsyncIterator[AnonymizedRecord]:
        """
        Anonymize a stream of records with immediate response.
        
        Processes records asynchronously without buffering. Each record is
        yielded immediately after processing. If one record fails, subsequent
        records continue to be processed.
        
        Args:
            records: Async iterator of JSON records
            system_id: System identifier for policy lookup
            
        Yields:
            AnonymizedRecord for each input record
            
        Example:
            >>> async def record_generator():
            ...     yield {"email": "user1@example.com"}
            ...     yield {"email": "user2@example.com"}
            >>> async for result in tokenizer.anonymize_stream(record_generator(), "customer_db"):
            ...     print(result.record)
        """
        async for record in records:
            try:
                anonymized = await self.anonymize_record(record, system_id)
                yield anonymized
            except Exception as e:
                # Return error for this record, continue processing
                self.logger.error(
                    "stream_record_failed",
                    system_id=system_id,
                    error=str(e),
                )

                # Return error record with _pii_anonymized=False in the record itself
                error_record = record.copy()
                error_record['_pii_anonymized'] = False

                yield AnonymizedRecord(
                    record=error_record,
                    token_ids=[],
                    error=str(e),
                    _pii_anonymized=False,
                )

    async def deanonymize_record(
        self,
        record: dict,
        system_id: str,
    ) -> DeanonymizedRecord:
        """
        Restore original PII values in a tokenized record.
        
        Processes one record by:
        1. Identifying all PII fields based on policy
        2. Retrieving encrypted values from Redis (batch operation)
        3. Decrypting values
        4. Replacing tokens with original values
        5. Handling missing/expired tokens gracefully
        
        Args:
            record: Tokenized JSON record
            system_id: System identifier for policy lookup
            
        Returns:
            DeanonymizedRecord with original values and field-level errors
            
        Example:
            >>> tokenized = {"email": "tok_abc123", "name": "tok_xyz789"}
            >>> result = await tokenizer.deanonymize_record(tokenized, "customer_db")
            >>> print(result.record["email"])  # "user@example.com"
            >>> print(result.errors)  # {} if all successful
        """
        try:
            # Get system configuration
            config = self.policy_loader.get_system_config(system_id)
            encryption_key = self.policy_loader.get_encryption_key(system_id)

            if not config.structured:
                raise ValueError(
                    f"System '{system_id}' does not have structured configuration"
                )

            # Create a deep copy of the record to modify (needed for nested dicts)
            import copy
            deanonymized_record = copy.deepcopy(record)
            errors: Dict[str, str] = {}

            # Collect all tokens to retrieve
            tokens_to_retrieve: List[str] = []
            field_to_token: Dict[str, str] = {}

            for field_config in config.structured.pii_fields:
                try:
                    # Extract token value
                    token = self.extract_field_value(record, field_config.name)

                    # Skip null values
                    if token is None:
                        continue

                    # Store mapping for later
                    tokens_to_retrieve.append(str(token))
                    field_to_token[field_config.name] = str(token)

                except Exception as e:
                    errors[field_config.name] = f"Failed to extract token: {str(e)}"

            # Batch retrieve from Redis
            if tokens_to_retrieve:
                encrypted_values = await self.token_store.retrieve_batch(
                    system_id,
                    tokens_to_retrieve,
                )

                # Decrypt and replace tokens with original values
                for field_name, token in field_to_token.items():
                    try:
                        encrypted_value = encrypted_values.get(token)

                        if encrypted_value is None:
                            errors[field_name] = "Token not found or expired"
                            continue

                        # Decrypt value and get type information
                        original_value_str, value_type = self.crypto_engine.decrypt(
                            encrypted_value,
                            encryption_key,
                        )

                        # Convert back to original type
                        if value_type == "int":
                            original_value = int(original_value_str)
                        elif value_type == "float":
                            original_value = float(original_value_str)
                        elif value_type == "bool":
                            original_value = original_value_str.lower() == "true"
                        else:  # "str" or default
                            original_value = original_value_str

                        # Replace token with original value
                        self.set_field_value(
                            deanonymized_record,
                            field_name,
                            original_value,
                        )

                    except Exception as e:
                        errors[field_name] = f"Decryption failed: {str(e)}"

            # Remove _pii_anonymized flag if present
            deanonymized_record.pop('_pii_anonymized', None)

            return DeanonymizedRecord(
                record=deanonymized_record,
                errors=errors,
            )

        except Exception as e:
            # Return error
            self.logger.error(
                "record_deanonymization_failed",
                system_id=system_id,
                error=str(e),
            )

            return DeanonymizedRecord(
                record=record,
                errors={"_global": str(e)},
            )
