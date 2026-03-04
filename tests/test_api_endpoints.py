"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.pii_service.api.app import create_app
from src.pii_service.api.endpoints import set_dependencies
from src.pii_service.core.structured_tokenizer import AnonymizedRecord, DeanonymizedRecord
from src.pii_service.core.unstructured_tokenizer import AnonymizedText
from src.pii_service.models.policy import Policy, SystemConfig, StructuredConfig, PIIField


@pytest.fixture
def mock_policy_loader():
    """Create a mock PolicyLoader."""
    loader = MagicMock()
    loader.get_policy_version.return_value = "test-version-1"
    
    # Mock system config
    system_config = MagicMock()
    system_config.system_id = "test_system"
    loader.get_system_config.return_value = system_config
    
    return loader


@pytest.fixture
def mock_structured_tokenizer():
    """Create a mock StructuredTokenizer."""
    tokenizer = MagicMock()
    
    # Mock anonymize_record
    async def mock_anonymize(record, system_id):
        return AnonymizedRecord(
            record={"email": "tok_123", "_pii_anonymized": True},
            token_ids=["tok_123"],
            error=None,
            _pii_anonymized=True,
        )
    
    tokenizer.anonymize_record = AsyncMock(side_effect=mock_anonymize)
    
    # Mock deanonymize_record
    async def mock_deanonymize(record, system_id):
        return DeanonymizedRecord(
            record={"email": "user@example.com"},
            error=None,
        )
    
    tokenizer.deanonymize_record = AsyncMock(side_effect=mock_deanonymize)
    
    return tokenizer


@pytest.fixture
def mock_unstructured_tokenizer():
    """Create a mock UnstructuredTokenizer."""
    tokenizer = MagicMock()
    
    # Mock anonymize_text
    async def mock_anonymize_text(text, system_id, client_id, return_entity_map):
        # Create a proper entity map with EntitySpan-like objects
        entity_map = None
        if return_entity_map:
            from src.pii_service.models.entity import EntitySpan
            entity_map = {
                "tok_123": EntitySpan(
                    type="EMAIL",
                    value="user@example.com",
                    start=8,
                    end=24,
                    token="tok_123"
                )
            }
        
        return AnonymizedText(
            anonymized_text="Contact tok_123",
            entity_map=entity_map,
        )
    
    tokenizer.anonymize_text = AsyncMock(side_effect=mock_anonymize_text)
    
    # Mock deanonymize_text
    async def mock_deanonymize_text(text, system_id):
        return "Contact user@example.com"
    
    tokenizer.deanonymize_text = AsyncMock(side_effect=mock_deanonymize_text)
    
    return tokenizer


@pytest.fixture
def mock_token_store():
    """Create a mock TokenStore."""
    store = MagicMock()
    
    # Mock health_check
    async def mock_health():
        return True
    
    store.health_check = AsyncMock(side_effect=mock_health)
    
    return store


@pytest.fixture
def client(mock_policy_loader, mock_structured_tokenizer, mock_unstructured_tokenizer, mock_token_store):
    """Create a test client with mocked dependencies."""
    app = create_app(
        policy_loader=mock_policy_loader,
        token_store=mock_token_store,
        structured_tokenizer=mock_structured_tokenizer,
        unstructured_tokenizer=mock_unstructured_tokenizer,
    )
    
    return TestClient(app)


def test_health_check_healthy(client, mock_token_store):
    """Test health check endpoint when Redis is healthy."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["policy_version"] == "test-version-1"


def test_health_check_unhealthy(client, mock_token_store):
    """Test health check endpoint when Redis is unhealthy."""
    # Make health_check return False
    async def mock_unhealthy():
        return False
    
    mock_token_store.health_check = AsyncMock(side_effect=mock_unhealthy)
    
    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"


def test_metrics_endpoint(client):
    """Test metrics endpoint returns Prometheus format."""
    response = client.get("/metrics")
    
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_structured_anonymize_requires_auth(client):
    """Test that structured anonymize requires authentication."""
    response = client.post(
        "/structured/anonymize",
        json=[{"email": "user@example.com"}],
        headers={"X-System-ID": "test_system"},
    )
    
    assert response.status_code == 401


def test_structured_anonymize_with_auth(client):
    """Test structured anonymize endpoint with authentication."""
    response = client.post(
        "/structured/anonymize",
        json=[{"email": "user@example.com"}],
        headers={
            "X-System-ID": "test_system",
            "Authorization": "Bearer test-api-key",
        },
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    
    # Parse NDJSON response
    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    
    result = json.loads(lines[0])
    assert result["_pii_anonymized"] is True
    assert "tok_123" in result["token_ids"]


def test_structured_deanonymize_with_auth(client):
    """Test structured de-anonymize endpoint with authentication."""
    response = client.post(
        "/structured/deanonymize",
        json=[{"email": "tok_123"}],
        headers={
            "X-System-ID": "test_system",
            "Authorization": "Bearer test-api-key",
        },
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    
    # Parse NDJSON response
    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    
    result = json.loads(lines[0])
    # The mock returns the original email
    assert "email" in result["record"]


def test_unstructured_anonymize_with_auth(client):
    """Test unstructured anonymize endpoint with authentication."""
    response = client.post(
        "/unstructured/anonymize",
        json={"text": "Contact user@example.com", "return_entity_map": True},
        headers={
            "X-System-ID": "test_system",
            "Authorization": "Bearer test-api-key",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["anonymized_text"] == "Contact tok_123"
    assert data["entity_map"] is not None


def test_unstructured_deanonymize_with_auth(client):
    """Test unstructured de-anonymize endpoint with authentication."""
    response = client.post(
        "/unstructured/deanonymize",
        json={"text": "Contact tok_123"},
        headers={
            "X-System-ID": "test_system",
            "Authorization": "Bearer test-api-key",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Contact user@example.com"


def test_policy_reload_endpoint(client, mock_policy_loader):
    """Test policy reload endpoint."""
    # Mock reload_policy
    async def mock_reload():
        pass
    
    mock_policy_loader.reload_policy = AsyncMock(side_effect=mock_reload)
    
    response = client.post(
        "/admin/policy/reload",
        headers={"Authorization": "Bearer test-api-key"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["policy_version"] == "test-version-1"
