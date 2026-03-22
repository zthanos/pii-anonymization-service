"""
UnstructuredTokenizer: detector-driven anonymization for free-form text.

This module provides the UnstructuredTokenizer class which handles anonymization
and de-anonymization of unstructured text using pluggable detector backends.
"""

import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel
import structlog

from .detectors import (
    DeterministicDetector,
    GreekNERDetector,
    HybridDetector,
    PIIDetector,
)
from .policy_loader import PolicyLoader
from .token_store import TokenStore, TokenMapping
from .crypto_engine import CryptoEngine
from ..models.entity import DetectionFinding, EntitySpan


logger = structlog.get_logger()


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
        1. Using the configured detector pipeline to extract PII findings
        2. Generating tokens for each entity
        3. Encrypting and storing entity values
        4. Replacing entities with tokens using longest-first ordering
        5. Enforcing rate limits and text length limits
    
    Attributes:
        policy_loader: PolicyLoader instance for accessing system configurations
        token_store: TokenStore instance for Redis operations
        crypto_engine: CryptoEngine instance for encryption/decryption
        detector: PIIDetector instance for entity extraction
        logger: Structured logger instance
    
    Example:
        >>> tokenizer = UnstructuredTokenizer(
        ...     policy_loader, token_store, crypto_engine
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
        detector: Optional[PIIDetector] = None,
    ):
        """
        Initialize the UnstructuredTokenizer.
        
        Args:
            policy_loader: PolicyLoader instance for accessing configurations
            token_store: TokenStore instance for Redis operations
            crypto_engine: CryptoEngine instance for encryption/decryption
            detector: Optional detector implementation override
        """
        self.policy_loader = policy_loader
        self.token_store = token_store
        self.crypto_engine = crypto_engine
        self.detector = detector or HybridDetector(
            deterministic_detector=DeterministicDetector(),
            semantic_detector=GreekNERDetector(),
        )
        self.logger = logger.bind(component="unstructured_tokenizer")

    def resolve_findings(
        self,
        text: str,
        findings: List[DetectionFinding],
    ) -> List[DetectionFinding]:
        """
        Resolve finding overlaps using the configured longest-first strategy.
        
        Processes entities by length (longest first) to handle overlapping
        entities correctly. Tracks which character positions have been
        tokenized to avoid conflicts. Applies replacements in reverse order
        to maintain character positions.
        
        Args:
            text: Original text
            findings: List of DetectionFinding objects
            
        Returns:
            List of non-overlapping findings
        """
        sorted_findings = sorted(
            findings,
            key=lambda e: (-(e.end - e.start), e.start)
        )

        tokenized_positions = set()
        resolved_findings: List[DetectionFinding] = []

        for finding in sorted_findings:
            if any(pos in tokenized_positions for pos in range(finding.start, finding.end)):
                self.logger.debug(
                    "skipping_overlapping_finding",
                    entity_type=finding.type,
                    entity_value=finding.value[:20],
                    start=finding.start,
                    end=finding.end,
                )
                continue

            tokenized_positions.update(range(finding.start, finding.end))
            resolved_findings.append(finding)

        self.logger.info(
            "findings_resolved",
            total_findings=len(findings),
            kept_count=len(resolved_findings),
            skipped_count=len(findings) - len(resolved_findings),
        )

        return resolved_findings

    def apply_transformations(
        self,
        text: str,
        findings: List[DetectionFinding],
    ) -> Tuple[str, Dict[str, EntitySpan]]:
        """Apply redact or tokenize actions to resolved findings."""
        replacements = []
        entity_map: Dict[str, EntitySpan] = {}

        for finding in findings:
            replacement = finding.token or f"[REDACTED:{finding.type}]"
            replacements.append((finding.start, finding.end, replacement))
            if finding.action == "tokenize" and finding.token:
                entity_map[finding.token] = finding.to_entity_span()

        replacements.sort(reverse=True)
        result = text
        for start, end, replacement in replacements:
            result = result[:start] + replacement + result[end:]

        return result, entity_map

    def replace_entities(
        self,
        text: str,
        entities: List[EntitySpan],
    ) -> Tuple[str, Dict[str, EntitySpan]]:
        """Backward-compatible wrapper for legacy tests and callers."""
        findings = [
            DetectionFinding(
                type=entity.type,
                value=entity.value,
                start=entity.start,
                end=entity.end,
                detector="legacy",
                confidence=None,
                action="tokenize",
                token=entity.token,
            )
            for entity in entities
        ]
        resolved = self.resolve_findings(text, findings)
        return self.apply_transformations(text, resolved)

    def _get_detector_for_config(self, config) -> PIIDetector:
        """Select a detector implementation for the current policy."""
        detector_name = config.unstructured.detector
        if detector_name == "deterministic":
            return DeterministicDetector()
        if detector_name == "semantic":
            return GreekNERDetector()
        return self.detector

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
        2. Extract findings using the configured local detector pipeline
        3. Generate tokens for each tokenized finding
        4. Encrypt and store entity values in Redis
        5. Replace findings with tokens or redactions (longest-first)
        6. Return anonymized text and optional entity map
        
        Args:
            text: Free-form text containing PII
            system_id: System identifier for policy lookup
            client_id: Client identifier for rate limiting (default: "default")
            return_entity_map: Include token-to-entity mapping in response
            
        Returns:
            AnonymizedText with tokens replacing PII
            
        Raises:
            ValueError: If text exceeds max_text_length
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

        self.logger.info(
            "anonymizing_text",
            system_id=system_id,
            client_id=client_id,
            text_length=len(text),
        )

        detector = self._get_detector_for_config(config)
        findings = await detector.detect(text, config.unstructured)
        configured_types = {rule.type for rule in config.unstructured.entities}
        filtered_findings = [
            finding for finding in findings if finding.type in configured_types
        ]

        if len(filtered_findings) < len(findings):
            self.logger.debug(
                "filtered_findings",
                original_count=len(findings),
                filtered_count=len(filtered_findings),
            )

        token_mappings = []
        resolved_findings = self.resolve_findings(text, filtered_findings)

        for finding in resolved_findings:
            if finding.action != "tokenize":
                continue

            import uuid
            token = str(uuid.uuid4())

            encrypted_value = self.crypto_engine.encrypt(
                finding.value,
                encryption_key,
            )

            ttl_seconds = config.structured.token_ttl_seconds if config.structured else 0

            token_mappings.append(TokenMapping(
                system_id=system_id,
                token=token,
                encrypted_value=encrypted_value,
                ttl_seconds=ttl_seconds,
            ))

            finding.token = token

        if token_mappings:
            await self.token_store.store_batch(token_mappings)

        anonymized_text, entity_map = self.apply_transformations(text, resolved_findings)

        self.logger.info(
            "text_anonymized",
            system_id=system_id,
            client_id=client_id,
            entity_count=len(resolved_findings),
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
                original_value, _value_type = self.crypto_engine.decrypt(
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
