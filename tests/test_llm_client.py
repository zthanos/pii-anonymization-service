"""Tests for LLM client."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pii_service.core.llm_client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    LLMAPIError,
    LLMClient,
    LLMResponseError,
)
from src.pii_service.models.entity import EntitySpan


@pytest.fixture
def llm_client():
    """Create LLM client for testing."""
    return LLMClient(
        base_url="http://127.0.0.1:1234",
        model="openai/gpt-oss-20b",
    )


class TestBuildExtractionPrompt:
    """Tests for build_extraction_prompt method."""
    
    def test_builds_prompt_with_entity_types(self, llm_client):
        """Test that prompt includes entity types."""
        text = "Contact John at john@example.com"
        entity_types = ["PERSON", "EMAIL"]
        
        prompt = llm_client.build_extraction_prompt(text, entity_types)
        
        assert "PERSON, EMAIL" in prompt
        assert text in prompt
        assert "JSON" in prompt
        assert "start" in prompt
        assert "end" in prompt
    
    def test_builds_prompt_with_single_entity_type(self, llm_client):
        """Test prompt with single entity type."""
        text = "Call 555-1234"
        entity_types = ["PHONE"]
        
        prompt = llm_client.build_extraction_prompt(text, entity_types)
        
        assert "PHONE" in prompt
        assert text in prompt
    
    def test_builds_prompt_with_multiple_entity_types(self, llm_client):
        """Test prompt with multiple entity types."""
        text = "Test text"
        entity_types = ["PERSON", "EMAIL", "PHONE", "SSN", "ADDRESS"]
        
        prompt = llm_client.build_extraction_prompt(text, entity_types)
        
        for entity_type in entity_types:
            assert entity_type in prompt


class TestParseLLMResponse:
    """Tests for parse_llm_response method."""
    
    def test_parses_valid_json_response(self, llm_client):
        """Test parsing valid JSON response."""
        response = json.dumps([
            {
                "type": "PERSON",
                "value": "John",
                "start": 8,
                "end": 12,
            },
            {
                "type": "EMAIL",
                "value": "john@example.com",
                "start": 16,
                "end": 33,
            },
        ])
        
        entities = llm_client.parse_llm_response(response)
        
        assert len(entities) == 2
        assert entities[0].type == "PERSON"
        assert entities[0].value == "John"
        assert entities[0].start == 8
        assert entities[0].end == 12
        assert entities[1].type == "EMAIL"
        assert entities[1].value == "john@example.com"
        assert entities[1].start == 16
        assert entities[1].end == 33
    
    def test_parses_empty_array(self, llm_client):
        """Test parsing empty array response."""
        response = "[]"
        
        entities = llm_client.parse_llm_response(response)
        
        assert entities == []
    
    def test_raises_error_on_invalid_json(self, llm_client):
        """Test that invalid JSON raises LLMResponseError."""
        response = "This is not JSON"
        
        with pytest.raises(LLMResponseError, match="Invalid JSON response"):
            llm_client.parse_llm_response(response)
    
    def test_raises_error_on_non_array_response(self, llm_client):
        """Test that non-array JSON raises LLMResponseError."""
        response = json.dumps({"error": "not an array"})
        
        with pytest.raises(LLMResponseError, match="Response must be a JSON array"):
            llm_client.parse_llm_response(response)
    
    def test_skips_malformed_entities(self, llm_client):
        """Test that malformed entities are skipped."""
        response = json.dumps([
            {
                "type": "PERSON",
                "value": "John",
                "start": 8,
                "end": 12,
            },
            {
                "type": "EMAIL",
                # Missing value field
                "start": 16,
                "end": 33,
            },
            {
                "type": "PHONE",
                "value": "555-1234",
                "start": 40,
                "end": 48,
            },
        ])
        
        entities = llm_client.parse_llm_response(response)
        
        # Should skip the malformed entity
        assert len(entities) == 2
        assert entities[0].type == "PERSON"
        assert entities[1].type == "PHONE"
    
    def test_handles_entity_with_zero_offsets(self, llm_client):
        """Test entity at start of text."""
        response = json.dumps([
            {
                "type": "PERSON",
                "value": "John",
                "start": 0,
                "end": 4,
            },
        ])
        
        entities = llm_client.parse_llm_response(response)
        
        assert len(entities) == 1
        assert entities[0].start == 0
        assert entities[0].end == 4


class TestExtractEntities:
    """Tests for extract_entities method."""
    
    @pytest.mark.asyncio
    async def test_extracts_entities_successfully(self, llm_client):
        """Test successful entity extraction."""
        text = "Contact John at john@example.com"
        entity_types = ["PERSON", "EMAIL"]
        
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {
                            "type": "PERSON",
                            "value": "John",
                            "start": 8,
                            "end": 12,
                        },
                        {
                            "type": "EMAIL",
                            "value": "john@example.com",
                            "start": 16,
                            "end": 33,
                        },
                    ])
                )
            )
        ]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            entities = await llm_client.extract_entities(text, entity_types)
        
        assert len(entities) == 2
        assert entities[0].type == "PERSON"
        assert entities[0].value == "John"
        assert entities[1].type == "EMAIL"
        assert entities[1].value == "john@example.com"
    
    @pytest.mark.asyncio
    async def test_handles_empty_response(self, llm_client):
        """Test handling of empty entity list."""
        text = "No PII here"
        entity_types = ["PERSON", "EMAIL"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            entities = await llm_client.extract_entities(text, entity_types)
        
        assert entities == []
    
    @pytest.mark.asyncio
    async def test_handles_none_response_content(self, llm_client):
        """Test handling of None response content."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            entities = await llm_client.extract_entities(text, entity_types)
        
        assert entities == []
    
    @pytest.mark.asyncio
    async def test_raises_llm_api_error_on_api_failure(self, llm_client):
        """Test that API failures raise LLMAPIError."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API connection failed"),
        ):
            with pytest.raises(LLMAPIError, match="LLM API call failed"):
                await llm_client.extract_entities(text, entity_types)
    
    @pytest.mark.asyncio
    async def test_raises_llm_response_error_on_invalid_json(self, llm_client):
        """Test that invalid JSON response raises LLMResponseError."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Not valid JSON"))
        ]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with pytest.raises(LLMResponseError, match="Invalid JSON response"):
                await llm_client.extract_entities(text, entity_types)
    
    @pytest.mark.asyncio
    async def test_uses_custom_model_when_provided(self, llm_client):
        """Test that custom model parameter is used."""
        text = "Test text"
        entity_types = ["PERSON"]
        custom_model = "custom-model"
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        mock_create = AsyncMock(return_value=mock_response)
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            mock_create,
        ):
            await llm_client.extract_entities(text, entity_types, model=custom_model)
        
        # Verify the custom model was used
        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == custom_model
    
    @pytest.mark.asyncio
    async def test_uses_default_model_when_not_provided(self, llm_client):
        """Test that default model is used when not specified."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        mock_create = AsyncMock(return_value=mock_response)
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            mock_create,
        ):
            await llm_client.extract_entities(text, entity_types)
        
        # Verify the default model was used
        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == llm_client.model
    
    @pytest.mark.asyncio
    async def test_sends_correct_api_parameters(self, llm_client):
        """Test that API is called with correct parameters."""
        text = "Test text"
        entity_types = ["PERSON", "EMAIL"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        mock_create = AsyncMock(return_value=mock_response)
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            mock_create,
        ):
            await llm_client.extract_entities(text, entity_types)
        
        # Verify API call parameters
        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == llm_client.model
        assert call_args.kwargs["temperature"] == 0.0
        assert call_args.kwargs["max_tokens"] == 4096
        assert len(call_args.kwargs["messages"]) == 1
        assert call_args.kwargs["messages"][0]["role"] == "user"
        assert text in call_args.kwargs["messages"][0]["content"]


class TestLLMClientInitialization:
    """Tests for LLMClient initialization."""
    
    def test_initializes_with_default_parameters(self):
        """Test initialization with default parameters."""
        client = LLMClient()
        
        assert client.base_url == "http://127.0.0.1:1234"
        assert client.model == "openai/gpt-oss-20b"
        assert client.client is not None
    
    def test_initializes_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        custom_url = "http://localhost:8080"
        custom_model = "custom-model"
        
        client = LLMClient(base_url=custom_url, model=custom_model)
        
        assert client.base_url == custom_url
        assert client.model == custom_model
    
    def test_client_configured_with_base_url(self):
        """Test that OpenAI client is configured with correct base URL."""
        custom_url = "http://localhost:8080"
        client = LLMClient(base_url=custom_url)
        
        # OpenAI client normalizes URLs, so just check it starts with the base
        assert str(client.client.base_url).startswith(custom_url)



class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""
    
    def test_initializes_with_default_parameters(self):
        """Test circuit breaker initialization with defaults."""
        cb = CircuitBreaker()
        
        assert cb.failure_threshold == 5
        assert cb.timeout_seconds == 60
        assert cb.failure_count == 0
        assert cb.last_failure_time is None
        assert cb.state == "closed"
    
    def test_initializes_with_custom_parameters(self):
        """Test circuit breaker initialization with custom parameters."""
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=30)
        
        assert cb.failure_threshold == 3
        assert cb.timeout_seconds == 30
        assert cb.state == "closed"
    
    def test_can_attempt_when_closed(self):
        """Test that requests are allowed when circuit is closed."""
        cb = CircuitBreaker()
        
        assert cb.can_attempt() is True
        assert cb.state == "closed"
    
    def test_record_success_resets_failure_count(self):
        """Test that recording success resets failure count."""
        cb = CircuitBreaker()
        cb.failure_count = 3
        
        cb.record_success()
        
        assert cb.failure_count == 0
        assert cb.state == "closed"
    
    def test_record_failure_increments_count(self):
        """Test that recording failure increments count."""
        cb = CircuitBreaker(failure_threshold=5)
        
        cb.record_failure()
        
        assert cb.failure_count == 1
        assert cb.state == "closed"
        assert cb.last_failure_time is not None
    
    def test_opens_circuit_after_threshold_failures(self):
        """Test that circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        
        # Record failures up to threshold
        cb.record_failure()
        assert cb.state == "closed"
        
        cb.record_failure()
        assert cb.state == "closed"
        
        cb.record_failure()
        assert cb.state == "open"
        assert cb.failure_count == 3
    
    def test_blocks_requests_when_open(self):
        """Test that requests are blocked when circuit is open."""
        cb = CircuitBreaker(failure_threshold=2)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == "open"
        assert cb.can_attempt() is False
    
    def test_transitions_to_half_open_after_timeout(self):
        """Test that circuit transitions to half-open after timeout."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        
        # Set last failure time to past
        cb.last_failure_time = datetime.now() - timedelta(seconds=2)
        
        # Should transition to half-open
        assert cb.can_attempt() is True
        assert cb.state == "half-open"
    
    def test_allows_attempt_in_half_open_state(self):
        """Test that single attempt is allowed in half-open state."""
        cb = CircuitBreaker()
        cb.state = "half-open"
        
        assert cb.can_attempt() is True
    
    def test_success_in_half_open_closes_circuit(self):
        """Test that success in half-open state closes circuit."""
        cb = CircuitBreaker()
        cb.state = "half-open"
        cb.failure_count = 5
        
        cb.record_success()
        
        assert cb.state == "closed"
        assert cb.failure_count == 0
    
    def test_failure_in_half_open_reopens_circuit(self):
        """Test that failure in half-open state reopens circuit."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.state = "half-open"
        cb.failure_count = 2
        
        cb.record_failure()
        
        assert cb.state == "open"
        assert cb.failure_count == 3


class TestLLMClientCircuitBreaker:
    """Tests for circuit breaker integration in LLMClient."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_initialized(self):
        """Test that circuit breaker is initialized with client."""
        client = LLMClient()
        
        assert client.circuit_breaker is not None
        assert client.circuit_breaker.failure_threshold == 5
        assert client.circuit_breaker.timeout_seconds == 60
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_custom_parameters(self):
        """Test circuit breaker with custom parameters."""
        client = LLMClient(
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=30,
        )
        
        assert client.circuit_breaker.failure_threshold == 3
        assert client.circuit_breaker.timeout_seconds == 30
    
    @pytest.mark.asyncio
    async def test_records_success_on_successful_extraction(self, llm_client):
        """Test that successful extraction records success in circuit breaker."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            await llm_client.extract_entities(text, entity_types)
        
        assert llm_client.circuit_breaker.failure_count == 0
        assert llm_client.circuit_breaker.state == "closed"
    
    @pytest.mark.asyncio
    async def test_records_failure_on_api_error(self, llm_client):
        """Test that API errors record failure in circuit breaker."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            with pytest.raises(LLMAPIError):
                await llm_client.extract_entities(text, entity_types)
        
        assert llm_client.circuit_breaker.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_opens_circuit_after_threshold_failures(self, llm_client):
        """Test that circuit opens after threshold failures."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        # Configure low threshold for testing
        llm_client.circuit_breaker.failure_threshold = 3
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            # Record failures up to threshold
            for _ in range(3):
                with pytest.raises(LLMAPIError):
                    await llm_client.extract_entities(text, entity_types)
        
        assert llm_client.circuit_breaker.state == "open"
        assert llm_client.circuit_breaker.failure_count == 3
    
    @pytest.mark.asyncio
    async def test_blocks_requests_when_circuit_open(self, llm_client):
        """Test that requests are blocked when circuit is open."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        # Open the circuit
        llm_client.circuit_breaker.state = "open"
        llm_client.circuit_breaker.failure_count = 5
        llm_client.circuit_breaker.last_failure_time = datetime.now()
        
        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker is open"):
            await llm_client.extract_entities(text, entity_types)
    
    @pytest.mark.asyncio
    async def test_allows_request_after_timeout(self, llm_client):
        """Test that requests are allowed after timeout period."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        # Open the circuit
        llm_client.circuit_breaker.state = "open"
        llm_client.circuit_breaker.failure_count = 5
        llm_client.circuit_breaker.timeout_seconds = 1
        llm_client.circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=2)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            # Should transition to half-open and allow request
            entities = await llm_client.extract_entities(text, entity_types)
        
        assert entities == []
        assert llm_client.circuit_breaker.state == "closed"
        assert llm_client.circuit_breaker.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_response_error_does_not_affect_circuit_breaker(self, llm_client):
        """Test that response parsing errors don't affect circuit breaker."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        initial_failure_count = llm_client.circuit_breaker.failure_count
        
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Invalid JSON"))
        ]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with pytest.raises(LLMResponseError):
                await llm_client.extract_entities(text, entity_types)
        
        # Failure count should not increase for response errors
        assert llm_client.circuit_breaker.failure_count == initial_failure_count
    
    @pytest.mark.asyncio
    async def test_empty_response_records_success(self, llm_client):
        """Test that empty response is treated as success."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            entities = await llm_client.extract_entities(text, entity_types)
        
        assert entities == []
        assert llm_client.circuit_breaker.failure_count == 0
        assert llm_client.circuit_breaker.state == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_state_transitions(self, llm_client):
        """Test complete circuit breaker state transition cycle."""
        text = "Test text"
        entity_types = ["PERSON"]
        
        # Configure for testing
        llm_client.circuit_breaker.failure_threshold = 2
        llm_client.circuit_breaker.timeout_seconds = 1
        
        # Initial state: closed
        assert llm_client.circuit_breaker.state == "closed"
        
        # Cause failures to open circuit
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            for _ in range(2):
                with pytest.raises(LLMAPIError):
                    await llm_client.extract_entities(text, entity_types)
        
        # State: open
        assert llm_client.circuit_breaker.state == "open"
        
        # Requests should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            await llm_client.extract_entities(text, entity_types)
        
        # Wait for timeout
        llm_client.circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=2)
        
        # Successful request should close circuit
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[]"))]
        
        with patch.object(
            llm_client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            await llm_client.extract_entities(text, entity_types)
        
        # State: closed
        assert llm_client.circuit_breaker.state == "closed"
        assert llm_client.circuit_breaker.failure_count == 0
