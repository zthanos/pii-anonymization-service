"""
UnstructuredTokenizer: Extract and tokenize PII from free-form text using LLM.

This module provides the UnstructuredTokenizer class which handles anonymization
and de-anonymization of unstructured text using LLM-assisted PII extraction.

Key Features:
- LLM-based entity extraction using LLMClient
- Rate limiting per client to prevent runaway costs
- Text length validation
- Longest-first entity replacement to handle overlaps
- Token extraction using regex patterns
- Graceful handling of unknown/expired tokens

Performance:
- Async I/O throughout
- Per-client rate limiting
- Efficient regex-based token extraction
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
import structlog

from .policy_loader import PolicyLoader
from .token_store import TokenStore, TokenMapping
from .crypto_engine import CryptoEngine
from .llm_client import LLMClient
from ..models.entity import EntitySpan


logger = structlog.get_logger()


class RateLimitExceededError(Exception):
    """Raised when client exceeds rate limit."""
    pass


class RateLimiter:
    """Per-client rate limiter for LLM API calls.
    
    Tracks requests per minute per client_id to prevent runaway LLM API costs.
    Uses a sliding window approach to count requests in the last minute.
    
    Attributes:
        requests_per_minute: Maximum requests allowed per minute per client
        client_requests: Dict mapping client_id to list of request timestamps
    """

    def __init__(self, requests_per_minute: int):
        """Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute per client
        """
        self.requests_per_minute = requests_per_minute
        self.client_requests: Dict[str, List[datetime]] = defaultdict(list)
        self.logger = logger.bind(component="rate_limiter")

    async def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limit.
        
        Removes old requests outside the sliding window and checks if the
        client has exceeded the rate limit. If within limit, records the
        current request.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if within limit, False if exceeded
            
        Example:
            >>> limiter = RateLimiter(requests_per_minute=100)
            >>> await limiter.check_rate_limit("client1")  # True
            >>> # ... 100 more requests ...
            >>> await limiter.check_rate_limit("client1")  # False (exceeded)
        """
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)

        # Remove old requests outside the sliding window
        self.client_requests[client_id] = [
            req_time for req_time in self.client_requests[client_id]
            if req_time > cutoff
        ]

        # Check if limit exceeded
        if len(self.client_requests[client_id]) >= self.requests_per_minute:
            self.logger.warning(
                "rate_limit_exceeded",
                client_id=client_id,
                request_count=len(self.client_requests[client_id]),
                limit=self.requests_per_minute,
            )
            return False

        # Record this request
        self.client_requests[client_id].append(now)

        self.logger.debug(
            "rate_limit_check_passed",
            client_id=client_id,
            request_count=len(self.client_requests[client_id]),
            limit=self.requests_per_minute,
        )

        return True


class AnonymizedText(BaseModel):
    """Result of anonymizing unstructured text.
    
    Attributes:
        anonymized_text: Text with PII replaced by tokens
        entity_map: Optional mapping of tokens to entity metadata
    """

    anonymized_text: str
    entity_map: Optional[Dict[str, EntitySpan]] = None


class UnstructuredTokenizer:
    """
    Handles unstructured text anonymization and de-anonymization.
    
    This class processes free-form text by:
    1. Using LLM to extract PII entities
    2. Generating tokens for each entity
    3. Encrypting and storing entity values
    4. Replacing entities with tokens using longest-first ordering
    5. Enforcing rate limits and text length limits
    
    Attributes:
        policy_loader: PolicyLoader instance for accessing system configurations
        token_store: TokenStore instance for Redis operations
        crypto_engine: CryptoEngine instance for encryption/decryption
        llm_client: LLMClient instance for entity extraction
        rate_limiters: Dict mapping system_id to RateLimiter instances
        logger: Structured logger instance
    
    Example:
        >>> tokenizer = UnstructuredTokenizer(
        ...     policy_loader, token_store, crypto_engine, llm_client
        ... )
        >>> result = await tokenizer.anonymize_text(
        ...     "Contact John at john@example.com",
        ...     "customer_db",
        ...     client_id="client1"
        ... )
        >>> print(result.anonymized_text)  # "Contact tok_abc at tok_xyz"
    """

    def __init__(
        self,
        policy_loader: PolicyLoader,
        token_store: TokenStore,
        crypto_engine: CryptoEngine,
        llm_client: LLMClient,
    ):
        """
        Initialize the UnstructuredTokenizer.
        
        Args:
            policy_loader: PolicyLoader instance for accessing configurations
            token_store: TokenStore instance for Redis operations
            crypto_engine: CryptoEngine instance for encryption/decryption
            llm_client: LLMClient instance for entity extraction
        """
        self.policy_loader = policy_loader
        self.token_store = token_store
        self.crypto_engine = crypto_engine
        self.llm_client = llm_client
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.logger = logger.bind(component="unstructured_tokenizer")

    def _get_rate_limiter(self, system_id: str) -> RateLimiter:
        """Get or create rate limiter for a system.
        
        Args:
            system_id: System identifier
            
        Returns:
            RateLimiter instance for the system
        """
        if system_id not in self.rate_limiters:
            config = self.policy_loader.get_system_config(system_id)
            if not config.unstructured:
                raise ValueError(
                    f"System '{system_id}' does not have unstructured configuration"
                )

            self.rate_limiters[system_id] = RateLimiter(
                requests_per_minute=config.unstructured.rate_limit_per_minute
            )

        return self.rate_limiters[system_id]

    def replace_entities(
        self,
        text: str,
        entities: List[EntitySpan],
    ) -> Tuple[str, Dict[str, EntitySpan]]:
        """
        Replace entity spans with tokens using longest-first ordering.
        
        Processes entities by length (longest first) to handle overlapping
        entities correctly. Tracks which character positions have been
        tokenized to avoid conflicts. Applies replacements in reverse order
        to maintain character positions.
        
        Args:
            text: Original text
            entities: List of EntitySpan objects with tokens assigned
            
        Returns:
            Tuple of (anonymized_text, entity_map)
            
        Example:
            >>> entities = [
            ...     EntitySpan(type="EMAIL", value="john@example.com", start=16, end=33, token="tok_123"),
            ...     EntitySpan(type="PERSON", value="John", start=8, end=12, token="tok_456"),
            ... ]
            >>> text = "Contact John at john@example.com"
            >>> anonymized, entity_map = tokenizer.replace_entities(text, entities)
            >>> print(anonymized)  # "Contact tok_456 at tok_123"
        """
        # Sort by length (longest first), then by start position
        # This ensures longer entities are processed first to handle overlaps
        sorted_entities = sorted(
            entities,
            key=lambda e: (-(e.end - e.start), e.start)
        )

        # Track which character positions are already tokenized
        tokenized_positions = set()
        entity_map = {}
        replacements = []

        for entity in sorted_entities:
            # Check for overlap with already tokenized positions
            if any(pos in tokenized_positions for pos in range(entity.start, entity.end)):
                self.logger.debug(
                    "skipping_overlapping_entity",
                    entity_type=entity.type,
                    entity_value=entity.value[:20],
                    start=entity.start,
                    end=entity.end,
                )
                continue

            # Mark positions as tokenized
            tokenized_positions.update(range(entity.start, entity.end))

            # Store replacement
            if entity.token:
                replacements.append((entity.start, entity.end, entity.token))
                entity_map[entity.token] = entity

        # Apply replacements in reverse order to maintain positions
        # Working backwards ensures earlier positions remain valid
        replacements.sort(reverse=True)
        result = text

        for start, end, token in replacements:
            result = result[:start] + token + result[end:]

        self.logger.info(
            "entities_replaced",
            total_entities=len(entities),
            replaced_count=len(replacements),
            skipped_count=len(entities) - len(replacements),
        )

        return result, entity_map

    def extract_tokens(self, text: str) -> List[str]:
        """
        Extract all token patterns from text using regex.
        
        Matches three token patterns:
        1. Prefixed tokens: prefix + UUID or HMAC (e.g., EMAIL_abc-123)
        2. UUID tokens: standard UUID v4 format
        3. HMAC tokens: 64 hex characters (SHA-256 output)
        
        Args:
            text: Text containing tokens
            
        Returns:
            List of token strings found in text
            
        Example:
            >>> text = "Contact tok_abc123 at EMAIL_def456"
            >>> tokens = tokenizer.extract_tokens(text)
            >>> print(tokens)  # ["tok_abc123", "EMAIL_def456"]
        """
        # UUID pattern (standard UUID v4 format)
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

        # HMAC-SHA256 pattern (64 hex characters)
        hmac_pattern = r'[0-9a-f]{64}'

        # Prefixed patterns (word characters + underscore + UUID or HMAC)
        # Example: EMAIL_abc-123-def or ADDR_abc123...
        prefixed_pattern = r'\w+_(?:' + uuid_pattern + '|' + hmac_pattern + ')'

        # Combine patterns with alternation (try prefixed first, then UUID, then HMAC)
        combined_pattern = f'(?:{prefixed_pattern}|{uuid_pattern}|{hmac_pattern})'

        tokens = re.findall(combined_pattern, text, re.IGNORECASE)

        self.logger.debug(
            "tokens_extracted",
            token_count=len(tokens),
            text_length=len(text),
        )

        return tokens

    async def anonymize_text(
        self,
        text: str,
        system_id: str,
        client_id: str = "default",
        return_entity_map: bool = False,
    ) -> AnonymizedText:
        """
        Anonymize PII in unstructured text.
        
        Process:
        1. Validate text length against max_text_length
        2. Check rate limit for client
        3. Extract entities using LLM
        4. Filter entities by configured entity_types
        5. Generate tokens for each entity
        6. Encrypt and store entity values in Redis
        7. Replace entities with tokens (longest-first)
        8. Return anonymized text and optional entity map
        
        Args:
            text: Free-form text containing PII
            system_id: System identifier for policy lookup
            client_id: Client identifier for rate limiting (default: "default")
            return_entity_map: Include token-to-entity mapping in response
            
        Returns:
            AnonymizedText with tokens replacing PII
            
        Raises:
            ValueError: If text exceeds max_text_length
            RateLimitExceededError: If client exceeds rate limit
            
        Example:
            >>> result = await tokenizer.anonymize_text(
            ...     "Contact John Doe at john@example.com or call 555-1234",
            ...     "customer_db",
            ...     client_id="client1",
            ...     return_entity_map=True
            ... )
            >>> print(result.anonymized_text)
            >>> print(result.entity_map)  # Dict of token -> EntitySpan
        """
        # Get system configuration
        config = self.policy_loader.get_system_config(system_id)
        encryption_key = self.policy_loader.get_encryption_key(system_id)

        if not config.unstructured:
            raise ValueError(
                f"System '{system_id}' does not have unstructured configuration"
            )

        # Validate text length
        if len(text) > config.unstructured.max_text_length:
            raise ValueError(
                f"Text length {len(text)} exceeds maximum "
                f"{config.unstructured.max_text_length}"
            )

        # Check rate limit
        rate_limiter = self._get_rate_limiter(system_id)
        if not await rate_limiter.check_rate_limit(client_id):
            raise RateLimitExceededError(
                f"Rate limit exceeded for client '{client_id}'. "
                f"Maximum {config.unstructured.rate_limit_per_minute} requests per minute."
            )

        self.logger.info(
            "anonymizing_text",
            system_id=system_id,
            client_id=client_id,
            text_length=len(text),
        )

        # Extract entities using LLM
        entities = await self.llm_client.extract_entities(
            text,
            config.unstructured.entity_types,
            config.unstructured.llm_model,
        )

        # Filter entities by configured types (LLM might return extra types)
        filtered_entities = [
            entity for entity in entities
            if entity.type in config.unstructured.entity_types
        ]

        if len(filtered_entities) < len(entities):
            self.logger.debug(
                "filtered_entities",
                original_count=len(entities),
                filtered_count=len(filtered_entities),
            )

        # Generate tokens and encrypt values
        token_mappings = []

        for entity in filtered_entities:
            # Generate token (use deterministic=False for unstructured by default)
            # Use UUID format for unstructured tokens
            import uuid
            token = str(uuid.uuid4())

            # Encrypt original value
            encrypted_value = self.crypto_engine.encrypt(
                entity.value,
                encryption_key,
            )

            # Prepare for batch storage
            # Use token_ttl_seconds from structured config if available, else 0
            ttl_seconds = config.structured.token_ttl_seconds if config.structured else 0

            token_mappings.append(TokenMapping(
                system_id=system_id,
                token=token,
                encrypted_value=encrypted_value,
                ttl_seconds=ttl_seconds,
            ))

            # Assign token to entity
            entity.token = token

        # Batch write to Redis
        if token_mappings:
            await self.token_store.store_batch(token_mappings)

        # Replace entities with tokens
        anonymized_text, entity_map = self.replace_entities(text, filtered_entities)

        self.logger.info(
            "text_anonymized",
            system_id=system_id,
            client_id=client_id,
            entity_count=len(filtered_entities),
            token_count=len(token_mappings),
        )

        return AnonymizedText(
            anonymized_text=anonymized_text,
            entity_map=entity_map if return_entity_map else None,
        )

    async def deanonymize_text(
        self,
        text: str,
        system_id: str,
    ) -> str:
        """
        Restore original PII values in tokenized text.
        
        Process:
        1. Extract all token patterns from text using regex
        2. Retrieve encrypted values from Redis (batch operation)
        3. Decrypt values
        4. Replace tokens with original values
        5. Leave unknown/expired tokens unchanged
        
        Args:
            text: Tokenized text
            system_id: System identifier for policy lookup
            
        Returns:
            De-anonymized text with original PII values
            
        Example:
            >>> tokenized = "Contact tok_abc at tok_xyz"
            >>> original = await tokenizer.deanonymize_text(tokenized, "customer_db")
            >>> print(original)  # "Contact John at john@example.com"
        """
        # Get system configuration
        config = self.policy_loader.get_system_config(system_id)
        encryption_key = self.policy_loader.get_encryption_key(system_id)

        if not config.unstructured:
            raise ValueError(
                f"System '{system_id}' does not have unstructured configuration"
            )

        self.logger.info(
            "deanonymizing_text",
            system_id=system_id,
            text_length=len(text),
        )

        # Extract all tokens from text
        tokens = self.extract_tokens(text)

        if not tokens:
            self.logger.debug(
                "no_tokens_found",
                system_id=system_id,
            )
            return text

        # Batch retrieve from Redis
        encrypted_values = await self.token_store.retrieve_batch(
            system_id,
            tokens,
        )

        # Build replacement map (token -> original value)
        replacements: Dict[str, str] = {}

        for token, encrypted_value in encrypted_values.items():
            if encrypted_value is None:
                # Token not found or expired - leave unchanged
                self.logger.debug(
                    "token_not_found",
                    system_id=system_id,
                    token=token[:8],
                )
                continue

            try:
                # Decrypt value
                original_value = self.crypto_engine.decrypt(
                    encrypted_value,
                    encryption_key,
                )
                replacements[token] = original_value
            except Exception as e:
                # Decryption failed - leave token unchanged
                self.logger.warning(
                    "token_decryption_failed",
                    system_id=system_id,
                    token=token[:8],
                    error=str(e),
                )
                continue

        # Replace tokens with original values
        # Sort by length (longest first) to handle overlapping tokens
        sorted_tokens = sorted(replacements.keys(), key=len, reverse=True)

        result = text
        for token in sorted_tokens:
            result = result.replace(token, replacements[token])

        self.logger.info(
            "text_deanonymized",
            system_id=system_id,
            total_tokens=len(tokens),
            replaced_tokens=len(replacements),
            unchanged_tokens=len(tokens) - len(replacements),
        )

        return result
