"""LLM client for PII entity extraction using OpenAI API (LM Studio)."""

import json
from datetime import datetime, timedelta
from typing import List

import structlog
from openai import AsyncOpenAI

from ..models.entity import EntitySpan


logger = structlog.get_logger()


class LLMResponseError(Exception):
    """Raised when LLM response is invalid or cannot be parsed."""

    pass


class LLMAPIError(Exception):
    """Raised when LLM API call fails."""

    pass


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and requests are blocked."""

    pass


class CircuitBreaker:
    """Simple circuit breaker for API resilience.
    
    The circuit breaker prevents cascade failures by tracking API failures
    and temporarily blocking requests when too many failures occur.
    
    States:
        - closed: Normal operation, requests pass through
        - open: Too many failures, requests are blocked
        - half-open: Testing if service recovered, single request allowed
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        timeout_seconds: Seconds to wait before transitioning to half-open
        failure_count: Current count of consecutive failures
        last_failure_time: Timestamp of last failure
        state: Current circuit breaker state
    """

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit (default 5)
            timeout_seconds: Seconds to wait before transitioning to half-open (default 60)
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = "closed"  # closed, open, half-open
        self.logger = logger.bind(component="circuit_breaker")

    def record_success(self) -> None:
        """Record successful API call.
        
        Resets failure count and closes the circuit.
        """
        self.failure_count = 0
        self.state = "closed"
        self.logger.info("circuit_breaker_success", state=self.state)

    def record_failure(self) -> None:
        """Record failed API call.
        
        Increments failure count and opens circuit if threshold reached.
        """
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.logger.warning(
                "circuit_breaker_opened",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )
        else:
            self.logger.info(
                "circuit_breaker_failure_recorded",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

    def can_attempt(self) -> bool:
        """Check if request can be attempted.
        
        Returns:
            True if request should be attempted, False if blocked
        """
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if timeout has elapsed
            if self.last_failure_time is not None:
                elapsed = datetime.now() - self.last_failure_time
                if elapsed > timedelta(seconds=self.timeout_seconds):
                    self.state = "half-open"
                    self.logger.info(
                        "circuit_breaker_half_open",
                        elapsed_seconds=elapsed.total_seconds(),
                    )
                    return True
            return False

        # half-open state - allow single attempt
        return True


class LLMClient:
    """OpenAI API client for entity extraction using LM Studio.
    
    This client interfaces with LM Studio's OpenAI-compatible API
    to extract PII entities from unstructured text.
    
    Attributes:
        client: AsyncOpenAI client configured for LM Studio
        base_url: LM Studio API base URL
        model: Model identifier to use for extraction
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        model: str = "openai/gpt-oss-20b",
        api_key: str = "not-needed",  # LM Studio doesn't require API key
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60,
    ):
        """Initialize LLM client for LM Studio.
        
        Args:
            base_url: LM Studio API base URL
            model: Model identifier
            api_key: API key (not needed for LM Studio but required by client)
            circuit_breaker_threshold: Number of failures before opening circuit (default 5)
            circuit_breaker_timeout: Seconds to wait before transitioning to half-open (default 60)
        """
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            timeout_seconds=circuit_breaker_timeout,
        )
        self.logger = logger.bind(component="llm_client", model=model)

    def build_extraction_prompt(self, text: str, entity_types: List[str]) -> str:
        """Build prompt for entity extraction.
        
        Creates a structured prompt that instructs the LLM to extract
        PII entities and return them in JSON format.
        
        Args:
            text: Input text to analyze
            entity_types: List of entity types to extract
            
        Returns:
            Formatted prompt string
        """
        entity_types_str = ", ".join(entity_types)

        prompt = f"""Extract personally identifiable information (PII) entities from the following text.

Return a JSON array of objects with these fields:
- type: The entity type (must be one of: {entity_types_str})
- value: The extracted text value
- start: Character offset where the entity starts (0-indexed)
- end: Character offset where the entity ends (exclusive)

Only extract entities matching these types: {entity_types_str}

Rules:
1. Return ONLY valid JSON, no additional text or explanation
2. If no entities found, return an empty array: []
3. Ensure start/end offsets are accurate
4. Do not extract entities not in the specified types

Text to analyze:
{text}

JSON output:"""

        return prompt

    def parse_llm_response(self, response: str) -> List[EntitySpan]:
        """Parse and validate JSON response from LLM.
        
        Validates that the response is valid JSON and contains the
        required fields for each entity.
        
        Args:
            response: Raw response text from LLM
            
        Returns:
            List of EntitySpan objects
            
        Raises:
            LLMResponseError: If response is not valid JSON or has invalid structure
        """
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            self.logger.error("invalid_json_response", error=str(e), response=response[:200])
            raise LLMResponseError(f"Invalid JSON response: {str(e)}")

        if not isinstance(data, list):
            self.logger.error("response_not_array", response_type=type(data).__name__)
            raise LLMResponseError("Response must be a JSON array")

        entities = []
        for item in data:
            try:
                entity = EntitySpan(
                    type=item["type"],
                    value=item["value"],
                    start=item["start"],
                    end=item["end"],
                )
                entities.append(entity)
            except (KeyError, TypeError) as e:
                # Skip malformed entities but log the issue
                self.logger.warning(
                    "skipping_malformed_entity",
                    error=str(e),
                    item=item,
                )
                continue

        self.logger.info("parsed_entities", count=len(entities))
        return entities

    async def extract_entities(
        self,
        text: str,
        entity_types: List[str],
        model: str | None = None,
    ) -> List[EntitySpan]:
        """Extract PII entities from text using LM Studio.
        
        Sends the text to LM Studio's OpenAI-compatible API and parses
        the response to extract entity spans. Uses circuit breaker to
        prevent cascade failures.
        
        Args:
            text: Input text to analyze
            entity_types: List of entity types to extract
            model: Model to use (defaults to instance model)
            
        Returns:
            List of EntitySpan objects
            
        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            LLMAPIError: If API call fails
            LLMResponseError: If response is invalid
        """
        # Check circuit breaker before attempting request
        if not self.circuit_breaker.can_attempt():
            self.logger.warning(
                "circuit_breaker_blocking_request",
                state=self.circuit_breaker.state,
                failure_count=self.circuit_breaker.failure_count,
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker is open - too many recent failures"
            )

        model_to_use = model or self.model

        try:
            prompt = self.build_extraction_prompt(text, entity_types)

            self.logger.info(
                "calling_llm_api",
                model=model_to_use,
                text_length=len(text),
                entity_types=entity_types,
            )

            response = await self.client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.0,  # Deterministic output
                max_tokens=4096,
            )

            response_text = response.choices[0].message.content

            if not response_text:
                self.logger.warning("empty_llm_response")
                # Empty response is not a failure - record success
                self.circuit_breaker.record_success()
                return []

            entities = self.parse_llm_response(response_text)

            # Record success on successful extraction
            self.circuit_breaker.record_success()

            self.logger.info(
                "llm_extraction_complete",
                model=model_to_use,
                entities_found=len(entities),
            )

            return entities

        except LLMResponseError:
            # Response parsing errors are not API failures - don't affect circuit breaker
            # Re-raise response errors as-is
            raise
        except Exception as e:
            # Record failure for circuit breaker
            self.circuit_breaker.record_failure()

            self.logger.error(
                "llm_api_call_failed",
                model=model_to_use,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise LLMAPIError(f"LLM API call failed: {str(e)}")
