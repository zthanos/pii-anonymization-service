# Design Document: PII Anonymization Service

## 1. Overview

The PII Anonymization Service is a high-performance Python 3.12 microservice that provides tokenization and de-tokenization capabilities for both structured and unstructured data containing personally identifiable information (PII). The service operates as a stateless application layer with Redis as the persistence backend, supporting both REST and gRPC streaming protocols for maximum flexibility and performance.

### 1.1 Core Capabilities

- **Structured Data Tokenization**: Process JSON records at 50k+ records/second via gRPC streaming with <5ms p95 latency
- **Unstructured Data Tokenization**: LLM-assisted PII extraction from free-form text using Anthropic API
- **Reversible Tokenization**: AES-256-GCM encrypted storage enabling secure de-tokenization
- **Policy-Driven Configuration**: YAML-based multi-tenant configuration with hot-reload support
- **Production-Ready**: Health checks, Prometheus metrics, structured logging, circuit breakers, and retry logic

### 1.2 Design Principles

1. **Performance First**: Async I/O throughout, connection pooling, pipelining, and streaming to achieve 50k+ records/sec
2. **Security by Default**: All PII encrypted at rest, no plaintext logging, non-root container execution
3. **Operational Excellence**: Health checks, metrics, graceful degradation, circuit breakers
4. **Developer Experience**: UV for fast builds, comprehensive error messages, hot-reload configuration

### 1.3 Technology Stack Summary

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Runtime | Python | 3.12 | Async I/O, type hints, performance |
| Package Manager | UV | Latest | Fast dependency resolution |
| Web Framework | FastAPI | 0.109+ | REST API with streaming |
| RPC Framework | gRPC | 1.60+ | High-throughput bidirectional streaming |
| Storage | Redis | 7.2+ | Token persistence with TTL |
| Encryption | cryptography | 42.0+ | AES-256-GCM implementation |
| LLM Integration | anthropic | 0.18+ | Claude API client |
| Validation | Pydantic | 2.6+ | Data models and validation |
| Metrics | prometheus-client | 0.19+ | Metrics exposition |
| Logging | structlog | 24.1+ | Structured JSON logging |
| Container | Docker | 24.0+ | Multi-stage builds |

---

## 2. High-Level Architecture

### 2.1 System Components Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Client Applications                                 │
│                                                                              │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐       │
│  │ REST Client  │         │ gRPC Client  │         │  Admin CLI   │       │
│  └──────┬───────┘         └──────┬───────┘         └──────┬───────┘       │
└─────────┼────────────────────────┼────────────────────────┼────────────────┘
          │                        │                        │
          │                        │                        │
┌─────────┼────────────────────────┼────────────────────────┼────────────────┐
│         │    PII Anonymization Service Container                           │
│         │                        │                        │                 │
│  ┌──────▼──────┐          ┌──────▼──────┐        ┌──────▼──────┐          │
│  │   FastAPI   │          │    gRPC     │        │    Admin    │          │
│  │   Server    │          │   Server    │        │  Endpoints  │          │
│  │  Port 8000  │          │  Port 50051 │        │             │          │
│  └──────┬──────┘          └──────┬──────┘        └──────┬──────┘          │
│         │                        │                       │                  │
│         └────────────┬───────────┴───────────────────────┘                  │
│                      │                                                       │
│         ┌────────────▼────────────┐                                         │
│         │   Authentication        │                                         │
│         │   Middleware            │                                         │
│         └────────────┬────────────┘                                         │
│                      │                                                       │
│         ┌────────────▼────────────────────────────────┐                     │
│         │          Core Processing Layer              │                     │
│         │                                              │                     │
│         │  ┌──────────────┐      ┌─────────────────┐ │                     │
│         │  │   Policy     │      │   Structured    │ │                     │
│         │  │   Loader     │◄─────┤   Tokenizer     │ │                     │
│         │  │              │      │                 │ │                     │
│         │  └──────▲───────┘      └────────┬────────┘ │                     │
│         │         │                       │           │                     │
│         │         │              ┌────────▼────────┐  │                     │
│         │         │              │  Unstructured   │  │                     │
│         │         └──────────────┤   Tokenizer     │  │                     │
│         │                        │                 │  │                     │
│         │                        └────────┬────────┘  │                     │
│         └─────────────────────────────────┼───────────┘                     │
│                                            │                                 │
│         ┌──────────────────────────────────▼───────────────┐                │
│         │          Crypto & Storage Layer                  │                │
│         │                                                   │                │
│         │  ┌──────────────┐      ┌─────────────────┐      │                │
│         │  │    Crypto    │◄─────┤   Token Store   │      │                │
│         │  │    Engine    │      │   (Redis Client)│      │                │
│         │  │  AES-256-GCM │      │                 │      │                │
│         │  └──────────────┘      └────────┬────────┘      │                │
│         └─────────────────────────────────┼───────────────┘                │
│                                            │                                 │
│         ┌──────────────────────────────────▼───────────────┐                │
│         │          External Integration Layer              │                │
│         │                                                   │                │
│         │  ┌──────────────┐                                │                │
│         │  │  LLM Client  │                                │                │
│         │  │  (Anthropic) │                                │                │
│         │  └──────────────┘                                │                │
│         └───────────────────────────────────────────────────┘                │
│                                                                              │
│         ┌────────────────────────────────────────────────────┐              │
│         │          Observability Layer                       │              │
│         │                                                     │              │
│         │  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │              │
│         │  │ Metrics  │  │  Logging │  │    Health    │    │              │
│         │  │/metrics  │  │  stdout  │  │   /health    │    │              │
│         │  └──────────┘  └──────────┘  └──────────────┘    │              │
│         └────────────────────────────────────────────────────┘              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼─────────┐  ┌───────▼────────┐  ┌───────▼────────┐
│  Redis Cluster    │  │  Anthropic API │  │   Prometheus   │
│  (Token Storage)  │  │  (Claude LLM)  │  │   (Metrics)    │
│  Port 6379        │  │                │  │                │
└───────────────────┘  └────────────────┘  └────────────────┘
```

### 2.2 Data Flow for Structured Tokenization

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. POST /structured/anonymize
       │    Header: system-id: customer_db
       │    Body: [{email: "user@example.com", name: "John"}]
       ▼
┌──────────────────┐
│  FastAPI/gRPC    │
│  API Gateway     │
└──────┬───────────┘
       │ 2. Authenticate API key
       │ 3. Validate system_id
       ▼
┌──────────────────┐
│ Policy Loader    │◄──── YAML Policy File
└──────┬───────────┘
       │ 4. Get PII fields for system_id
       │    Returns: [email: deterministic, name: non-deterministic]
       ▼
┌──────────────────┐
│   Structured     │
│   Tokenizer      │
└──────┬───────────┘
       │ 5. For each record:
       │    a. Extract PII field values
       │    b. Generate tokens (UUID/HMAC)
       │
       ├─────────────────────────────────┐
       │                                 │
       ▼                                 ▼
┌──────────────────┐            ┌──────────────────┐
│  Crypto Engine   │            │   Token Store    │
│  AES-256-GCM     │            │   (Redis)        │
└──────┬───────────┘            └──────┬───────────┘
       │ 6. Encrypt PII value          │
       │    nonce + ciphertext          │
       └────────────────►──────────────┘
                         │ 7. Store mapping
                         │    Key: customer_db:token:abc123
                         │    Value: <encrypted_email>
                         │    TTL: 86400 seconds
                         ▼
                  ┌──────────────────┐
                  │   Redis Server   │
                  └──────────────────┘
       
       │ 8. Replace field with token
       │    {email: "tok_abc123", name: "tok_xyz789"}
       ▼
┌──────────────────┐
│  Stream Response │
│  to Client       │
└──────────────────┘
```

### 2.3 Data Flow for Unstructured Tokenization

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. POST /unstructured/anonymize
       │    Body: {text: "Contact John at john@example.com"}
       ▼
┌──────────────────┐
│  FastAPI Server  │
└──────┬───────────┘
       │ 2. Rate limit check
       │ 3. Text length validation
       ▼
┌──────────────────┐
│ Unstructured     │
│ Tokenizer        │
└──────┬───────────┘
       │ 4. Send to LLM for entity extraction
       ▼
┌──────────────────┐
│   LLM Client     │
└──────┬───────────┘
       │ 5. Call Anthropic API
       │    Prompt: "Extract PERSON, EMAIL entities"
       ▼
┌──────────────────┐
│  Anthropic API   │
│  (Claude)        │
└──────┬───────────┘
       │ 6. Return JSON entity spans
       │    [{type: "PERSON", value: "John", start: 8, end: 12},
       │     {type: "EMAIL", value: "john@example.com", start: 16, end: 33}]
       ▼
┌──────────────────┐
│ Unstructured     │
│ Tokenizer        │
└──────┬───────────┘
       │ 7. For each entity:
       │    a. Generate token
       │    b. Encrypt value
       │    c. Store in Redis
       │
       │ 8. Replace entities (longest-first)
       │    "Contact tok_abc123 at tok_xyz789"
       ▼
┌──────────────────┐
│  Return Response │
│  + Entity Map    │
└──────────────────┘
```

### 2.4 Component Interactions

```
┌──────────────────────────────────────────────────────────────────┐
│                     Request Processing Flow                       │
└──────────────────────────────────────────────────────────────────┘

1. Authentication Flow:
   Client → API Gateway → Auth Middleware → [Validate Bearer Token]
                                           ↓
                                    [401 Unauthorized] or [Continue]

2. Policy Resolution:
   API Gateway → Policy Loader → [Get system_id config]
                               ↓
                        [400 Invalid System] or [Return Config]

3. Tokenization Flow:
   Tokenizer → Policy Loader → [Get PII fields]
           ↓
           → Crypto Engine → [Encrypt value]
           ↓
           → Token Store → Redis → [Store encrypted value]
           ↓
           → [Return anonymized data]

4. De-tokenization Flow:
   Tokenizer → Token Store → Redis → [Retrieve encrypted value]
           ↓
           → Crypto Engine → [Decrypt value]
           ↓
           → [Return original data]

5. Error Handling Flow:
   Any Component → [Error Occurs]
                 ↓
                 → Retry Logic (if transient)
                 ↓
                 → Circuit Breaker (if repeated failures)
                 ↓
                 → Structured Error Response
                 ↓
                 → Metrics Counter Increment
                 ↓
                 → Structured Log Entry
```

---

## 3. Component Design

### 3.1 Policy Loader

**Responsibility**: Load, validate, and manage YAML policy configurations with hot-reload capability.

**Key Interfaces:**

```python
class PolicyLoader:
    """Manages policy configuration lifecycle."""
    
    async def load_policy(self, path: str) -> Policy:
        """
        Load and validate policy from YAML file.
        
        Args:
            path: File path to YAML policy
            
        Returns:
            Validated Policy object
            
        Raises:
            PolicyValidationError: Invalid YAML or schema
            KeyResolutionError: Cannot resolve encryption key reference
        """
        
    async def reload_policy(self) -> None:
        """
        Reload policy from disk with validation.
        Atomic swap - keeps current policy if reload fails.
        """
        
    def get_system_config(self, system_id: str) -> SystemConfig:
        """
        Get configuration for a specific system_id.
        
        Args:
            system_id: System identifier
            
        Returns:
            SystemConfig for the system
            
        Raises:
            SystemNotFoundError: system_id not in policy
        """
        
    def resolve_encryption_key(self, key_ref: str) -> bytes:
        """
        Resolve encryption key from env: or file: reference.
        
        Args:
            key_ref: Reference string (env:VAR_NAME or file:/path)
            
        Returns:
            32-byte encryption key
            
        Raises:
            KeyResolutionError: Cannot resolve reference
        """
```

**Implementation Details:**

- **YAML Parsing**: Uses `pyyaml` with `safe_load` to prevent code execution
- **Schema Validation**: Pydantic models validate structure and types
- **Key Resolution**:
  - `env:VAR_NAME` → `os.environ[VAR_NAME]`
  - `file:/path/to/key` → Read file contents
  - Keys must be exactly 32 bytes (256 bits) for AES-256
- **Hot Reload Mechanism**:
  - Listens for SIGHUP signal
  - Exposes `/admin/policy/reload` endpoint
  - Uses RWLock for thread-safe policy swapping
  - Validates new policy before swapping
  - Retains current policy if validation fails
- **Startup Validation**:
  - Validates all required fields present
  - Checks encryption key references are resolvable
  - Validates field paths and token formats
  - Halts startup on any validation error

**Policy YAML Schema:**

```yaml
systems:
  - system_id: "customer_db"
    encryption_key_ref: "env:CUSTOMER_DB_KEY"  # or file:/run/secrets/key
    
    structured:
      pii_fields:
        - name: "email"
          deterministic: true
          token_format: "uuid"
          nullable: false
          
        - name: "address.street"  # Dot-notation for nested fields
          deterministic: false
          token_format: "prefixed"
          token_prefix: "ADDR_"
          nullable: true
          
        - name: "ssn"
          deterministic: true
          token_format: "deterministic"  # HMAC-SHA256
          nullable: false
          
      token_ttl_seconds: 86400  # 24 hours, 0 = no expiry
    
    unstructured:
      llm_model: "claude-3-haiku-20240307"
      entity_types: ["PERSON", "EMAIL", "PHONE", "SSN", "ADDRESS"]
      rate_limit_per_minute: 100
      max_text_length: 50000
  
  - system_id: "analytics_db"
    encryption_key_ref: "file:/run/secrets/analytics_key"
    structured:
      pii_fields:
        - name: "user_id"
          deterministic: true
          token_format: "deterministic"
          nullable: false
      token_ttl_seconds: 0  # Never expire

default_system: "customer_db"
```

**Pydantic Models:**

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
import time

class PIIField(BaseModel):
    name: str
    deterministic: bool = False
    token_format: Literal["uuid", "deterministic", "prefixed"] = "uuid"
    token_prefix: Optional[str] = None
    nullable: bool = False
    
    @validator('token_prefix')
    def validate_prefix(cls, v, values):
        if values.get('token_format') == 'prefixed' and not v:
            raise ValueError("token_prefix required when token_format is 'prefixed'")
        return v

class StructuredConfig(BaseModel):
    pii_fields: List[PIIField]
    token_ttl_seconds: int = Field(default=0, ge=0)

class UnstructuredConfig(BaseModel):
    llm_model: str = "claude-3-haiku-20240307"
    entity_types: List[str]
    rate_limit_per_minute: int = Field(default=100, gt=0)
    max_text_length: int = Field(default=50000, gt=0)

class SystemConfig(BaseModel):
    system_id: str
    encryption_key_ref: str
    structured: Optional[StructuredConfig] = None
    unstructured: Optional[UnstructuredConfig] = None
    
    @validator('encryption_key_ref')
    def validate_key_ref(cls, v):
        if not (v.startswith('env:') or v.startswith('file:')):
            raise ValueError("encryption_key_ref must start with 'env:' or 'file:'")
        return v

class Policy(BaseModel):
    systems: List[SystemConfig]
    default_system: Optional[str] = None
    version: str = Field(default_factory=lambda: str(int(time.time())))
    
    @validator('systems')
    def validate_unique_system_ids(cls, v):
        system_ids = [s.system_id for s in v]
        if len(system_ids) != len(set(system_ids)):
            raise ValueError("Duplicate system_id values found")
        return v
```


### 3.2 Structured Tokenizer

**Responsibility**: Tokenize and de-tokenize structured JSON records based on policy-defined PII fields.

**Key Interfaces:**

```python
class StructuredTokenizer:
    """Handles structured data anonymization and de-anonymization."""
    
    async def anonymize_record(
        self, 
        record: dict, 
        system_id: str
    ) -> AnonymizedRecord:
        """
        Anonymize a single JSON record.
        
        Args:
            record: JSON object with PII fields
            system_id: System identifier for policy lookup
            
        Returns:
            AnonymizedRecord with tokens and metadata
        """
        
    async def anonymize_stream(
        self, 
        records: AsyncIterator[dict], 
        system_id: str
    ) -> AsyncIterator[AnonymizedRecord]:
        """
        Anonymize a stream of records with immediate response.
        Processes records asynchronously without buffering.
        """
        
    async def deanonymize_record(
        self, 
        record: dict, 
        system_id: str
    ) -> DeanonymizedRecord:
        """
        Restore original PII values in a tokenized record.
        """
        
    def extract_field_value(self, record: dict, field_path: str) -> Any:
        """
        Extract value using dot-notation path.
        Example: "address.street" → record["address"]["street"]
        """
        
    def set_field_value(self, record: dict, field_path: str, value: Any) -> None:
        """
        Set value using dot-notation path.
        Creates intermediate dicts if needed.
        """
        
    def generate_token(
        self, 
        value: str, 
        deterministic: bool, 
        key: bytes,
        token_format: str,
        token_prefix: Optional[str] = None
    ) -> str:
        """
        Generate token based on configuration.
        
        - uuid: UUID v4 (non-deterministic)
        - deterministic: HMAC-SHA256(key, value)
        - prefixed: prefix + UUID/HMAC
        """
```

**Implementation Details:**

**Dot-Notation Field Extraction:**
```python
def extract_field_value(self, record: dict, field_path: str) -> Any:
    """Navigate nested JSON using dot-notation."""
    parts = field_path.split('.')
    value = record
    for part in parts:
        if not isinstance(value, dict):
            raise ValueError(f"Cannot navigate to {field_path}: {part} is not a dict")
        value = value.get(part)
        if value is None:
            return None
    return value
```

**Token Generation:**
```python
import uuid
import hmac
import hashlib

def generate_token(
    self, 
    value: str, 
    deterministic: bool, 
    key: bytes,
    token_format: str,
    token_prefix: Optional[str] = None
) -> str:
    """Generate token based on policy configuration."""
    
    if token_format == "uuid" or (token_format == "prefixed" and not deterministic):
        token = str(uuid.uuid4())
    elif token_format == "deterministic" or (token_format == "prefixed" and deterministic):
        # HMAC-SHA256 for deterministic tokens
        h = hmac.new(key, value.encode('utf-8'), hashlib.sha256)
        token = h.hexdigest()
    else:
        token = str(uuid.uuid4())
    
    if token_format == "prefixed" and token_prefix:
        return f"{token_prefix}{token}"
    
    return token
```

**Streaming Processing:**
```python
async def anonymize_stream(
    self, 
    records: AsyncIterator[dict], 
    system_id: str
) -> AsyncIterator[AnonymizedRecord]:
    """Process records with immediate streaming response."""
    
    config = self.policy_loader.get_system_config(system_id)
    
    async for record in records:
        try:
            anonymized = await self.anonymize_record(record, system_id)
            yield anonymized
        except Exception as e:
            # Return error for this record, continue processing
            yield AnonymizedRecord(
                record=record,
                token_ids=[],
                error=str(e),
                _pii_anonymized=False
            )
```

**Batch Redis Operations:**
```python
async def anonymize_record(self, record: dict, system_id: str) -> AnonymizedRecord:
    """Anonymize single record with batch Redis writes."""
    
    config = self.policy_loader.get_system_config(system_id)
    anonymized_record = record.copy()
    token_mappings = []
    token_ids = []
    
    # Generate all tokens first
    for field_config in config.structured.pii_fields:
        value = self.extract_field_value(record, field_config.name)
        
        if value is None:
            if not field_config.nullable:
                raise ValueError(f"Field {field_config.name} is null but not nullable")
            continue
        
        token = self.generate_token(
            str(value),
            field_config.deterministic,
            config.encryption_key,
            field_config.token_format,
            field_config.token_prefix
        )
        
        encrypted_value = self.crypto_engine.encrypt(str(value), config.encryption_key)
        
        token_mappings.append(TokenMapping(
            system_id=system_id,
            token=token,
            encrypted_value=encrypted_value,
            ttl_seconds=config.structured.token_ttl_seconds
        ))
        
        self.set_field_value(anonymized_record, field_config.name, token)
        token_ids.append(token)
    
    # Batch write to Redis
    await self.token_store.store_batch(token_mappings)
    
    anonymized_record['_pii_anonymized'] = True
    
    return AnonymizedRecord(
        record=anonymized_record,
        token_ids=token_ids,
        error=None,
        _pii_anonymized=True
    )
```

**Performance Optimizations:**
- Async I/O for all Redis operations
- Batch writes using Redis pipelining
- No buffering - stream records immediately
- Connection pooling for Redis
- Minimal memory footprint per record

### 3.3 Unstructured Tokenizer

**Responsibility**: Extract and tokenize PII from free-form text using LLM assistance.

**Key Interfaces:**

```python
class UnstructuredTokenizer:
    """Handles unstructured text anonymization."""
    
    async def anonymize_text(
        self, 
        text: str, 
        system_id: str,
        return_entity_map: bool = False
    ) -> AnonymizedText:
        """
        Anonymize PII in unstructured text.
        
        Args:
            text: Free-form text containing PII
            system_id: System identifier
            return_entity_map: Include token-to-entity mapping
            
        Returns:
            AnonymizedText with tokens replacing PII
        """
        
    async def deanonymize_text(
        self, 
        text: str, 
        system_id: str
    ) -> str:
        """
        Restore original PII values in tokenized text.
        Leaves unknown/expired tokens unchanged.
        """
        
    def replace_entities(
        self, 
        text: str, 
        entities: List[EntitySpan]
    ) -> Tuple[str, Dict[str, EntitySpan]]:
        """
        Replace entity spans with tokens.
        Uses longest-span-first ordering to handle overlaps.
        """
        
    def extract_tokens(self, text: str) -> List[str]:
        """
        Extract all token patterns from text.
        Matches UUID and HMAC patterns.
        """
```

**Implementation Details:**

**Rate Limiting:**
```python
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Per-client rate limiter for LLM API calls."""
    
    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.client_requests = defaultdict(list)
    
    async def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limit."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        
        # Remove old requests
        self.client_requests[client_id] = [
            req_time for req_time in self.client_requests[client_id]
            if req_time > cutoff
        ]
        
        if len(self.client_requests[client_id]) >= self.requests_per_minute:
            return False
        
        self.client_requests[client_id].append(now)
        return True
```

**Entity Replacement (Longest-First):**
```python
def replace_entities(
    self, 
    text: str, 
    entities: List[EntitySpan]
) -> Tuple[str, Dict[str, EntitySpan]]:
    """
    Replace entities with tokens, handling overlaps.
    Processes longest spans first to avoid conflicts.
    """
    
    # Sort by length (longest first), then by start position
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
            continue
        
        # Mark positions as tokenized
        tokenized_positions.update(range(entity.start, entity.end))
        
        # Store replacement
        replacements.append((entity.start, entity.end, entity.token))
        entity_map[entity.token] = entity
    
    # Apply replacements in reverse order to maintain positions
    replacements.sort(reverse=True)
    result = text
    
    for start, end, token in replacements:
        result = result[:start] + token + result[end:]
    
    return result, entity_map
```

**Token Extraction for De-anonymization:**
```python
import re

def extract_tokens(self, text: str) -> List[str]:
    """Extract all token patterns from text."""
    
    # UUID pattern
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    
    # HMAC-SHA256 pattern (64 hex chars)
    hmac_pattern = r'[0-9a-f]{64}'
    
    # Prefixed patterns (prefix + UUID or HMAC)
    prefixed_pattern = r'\w+_(?:' + uuid_pattern + '|' + hmac_pattern + ')'
    
    # Combine patterns
    combined_pattern = f'(?:{prefixed_pattern}|{uuid_pattern}|{hmac_pattern})'
    
    return re.findall(combined_pattern, text, re.IGNORECASE)
```

**Text Length Validation:**
```python
async def anonymize_text(
    self, 
    text: str, 
    system_id: str,
    return_entity_map: bool = False
) -> AnonymizedText:
    """Anonymize text with validation."""
    
    config = self.policy_loader.get_system_config(system_id)
    
    # Validate text length
    if len(text) > config.unstructured.max_text_length:
        raise ValueError(
            f"Text length {len(text)} exceeds maximum "
            f"{config.unstructured.max_text_length}"
        )
    
    # Extract entities using LLM
    entities = await self.llm_client.extract_entities(
        text,
        config.unstructured.entity_types,
        config.unstructured.llm_model
    )
    
    # Generate tokens and encrypt values
    for entity in entities:
        token = self.generate_token(entity.value, config)
        encrypted_value = self.crypto_engine.encrypt(
            entity.value, 
            config.encryption_key
        )
        
        await self.token_store.store_token(
            system_id,
            token,
            encrypted_value,
            config.structured.token_ttl_seconds if config.structured else 0
        )
        
        entity.token = token
    
    # Replace entities with tokens
    anonymized_text, entity_map = self.replace_entities(text, entities)
    
    return AnonymizedText(
        anonymized_text=anonymized_text,
        entity_map=entity_map if return_entity_map else None
    )
```

### 3.4 LLM Client

**Responsibility**: Interface with Anthropic API for PII entity extraction.

**Key Interfaces:**

```python
class LLMClient:
    """Anthropic API client for entity extraction."""
    
    async def extract_entities(
        self, 
        text: str, 
        entity_types: List[str],
        model: str
    ) -> List[EntitySpan]:
        """
        Extract PII entities from text using Claude.
        
        Args:
            text: Input text
            entity_types: List of entity types to extract
            model: Claude model identifier
            
        Returns:
            List of EntitySpan objects
            
        Raises:
            LLMAPIError: API call failed
            LLMResponseError: Invalid JSON response
        """
        
    def parse_llm_response(self, response: str) -> List[EntitySpan]:
        """
        Parse JSON response into EntitySpan objects.
        Validates structure and required fields.
        """
        
    async def health_check(self) -> bool:
        """Check if Anthropic API is reachable."""
```

**Implementation Details:**

**Prompt Template:**
```python
def build_extraction_prompt(self, text: str, entity_types: List[str]) -> str:
    """Build prompt for entity extraction."""
    
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
```

**API Call with Circuit Breaker:**
```python
from anthropic import AsyncAnthropic
import json

class CircuitBreaker:
    """Simple circuit breaker for API resilience."""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self):
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    def can_attempt(self) -> bool:
        if self.state == "closed":
            return True
        
        if self.state == "open":
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout_seconds):
                self.state = "half-open"
                return True
            return False
        
        # half-open state
        return True

class LLMClient:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.circuit_breaker = CircuitBreaker()
    
    async def extract_entities(
        self, 
        text: str, 
        entity_types: List[str],
        model: str
    ) -> List[EntitySpan]:
        """Extract entities with circuit breaker protection."""
        
        if not self.circuit_breaker.can_attempt():
            raise LLMAPIError("Circuit breaker is open - too many recent failures")
        
        try:
            prompt = self.build_extraction_prompt(text, entity_types)
            
            response = await self.client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.content[0].text
            entities = self.parse_llm_response(response_text)
            
            self.circuit_breaker.record_success()
            return entities
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise LLMAPIError(f"LLM API call failed: {str(e)}")
    
    def parse_llm_response(self, response: str) -> List[EntitySpan]:
        """Parse and validate JSON response."""
        
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"Invalid JSON response: {str(e)}")
        
        if not isinstance(data, list):
            raise LLMResponseError("Response must be a JSON array")
        
        entities = []
        for item in data:
            try:
                entity = EntitySpan(
                    type=item['type'],
                    value=item['value'],
                    start=item['start'],
                    end=item['end']
                )
                entities.append(entity)
            except (KeyError, TypeError) as e:
                # Skip malformed entities
                continue
        
        return entities
```

**Metrics Tracking:**
```python
from prometheus_client import Counter, Histogram

llm_api_calls_total = Counter(
    'llm_api_calls_total',
    'Total LLM API calls',
    ['model', 'status']
)

llm_api_errors_total = Counter(
    'llm_api_errors_total',
    'Total LLM API errors',
    ['error_type']
)

llm_api_latency_seconds = Histogram(
    'llm_api_latency_seconds',
    'LLM API call latency',
    ['model']
)
```

### 3.5 Crypto Engine

**Responsibility**: Encrypt and decrypt PII values using AES-256-GCM.

**Key Interfaces:**

```python
class CryptoEngine:
    """AES-256-GCM encryption/decryption."""
    
    def encrypt(self, plaintext: str, key: bytes) -> bytes:
        """
        Encrypt plaintext with AES-256-GCM.
        
        Args:
            plaintext: String to encrypt
            key: 32-byte encryption key
            
        Returns:
            nonce (12 bytes) + ciphertext + tag (16 bytes)
        """
        
    def decrypt(self, ciphertext: bytes, key: bytes) -> str:
        """
        Decrypt ciphertext with AES-256-GCM.
        
        Args:
            ciphertext: nonce + ciphertext + tag
            key: 32-byte encryption key
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            DataCorruptionError: GCM tag verification failed
        """
        
    def generate_nonce(self) -> bytes:
        """Generate 96-bit (12-byte) nonce using os.urandom."""
```

**Implementation Details:**

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class CryptoEngine:
    """AES-256-GCM encryption engine."""
    
    NONCE_SIZE = 12  # 96 bits
    KEY_SIZE = 32    # 256 bits
    TAG_SIZE = 16    # 128 bits
    
    def __init__(self):
        pass
    
    def generate_nonce(self) -> bytes:
        """Generate cryptographically secure nonce."""
        return os.urandom(self.NONCE_SIZE)
    
    def encrypt(self, plaintext: str, key: bytes) -> bytes:
        """
        Encrypt with AES-256-GCM.
        
        Format: nonce (12) + ciphertext + tag (16)
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes")
        
        aesgcm = AESGCM(key)
        nonce = self.generate_nonce()
        
        # Encrypt and authenticate
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode('utf-8'),
            None  # No additional authenticated data
        )
        
        # Prepend nonce to ciphertext
        return nonce + ciphertext
    
    def decrypt(self, ciphertext: bytes, key: bytes) -> str:
        """
        Decrypt with AES-256-GCM.
        
        Verifies authentication tag.
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes")
        
        if len(ciphertext) < self.NONCE_SIZE + self.TAG_SIZE:
            raise DataCorruptionError("Ciphertext too short")
        
        # Extract nonce and ciphertext
        nonce = ciphertext[:self.NONCE_SIZE]
        encrypted_data = ciphertext[self.NONCE_SIZE:]
        
        aesgcm = AESGCM(key)
        
        try:
            plaintext_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
            return plaintext_bytes.decode('utf-8')
        except Exception as e:
            raise DataCorruptionError(f"Decryption failed - data may be corrupted: {str(e)}")
```

**Security Considerations:**
- Unique nonce per encryption (never reuse)
- GCM provides authenticated encryption (detects tampering)
- Keys loaded from environment or secrets, never hardcoded
- No plaintext PII ever logged
- Constant-time operations where possible

3.6 Token Store (Redis Client)
Responsibility: Manage Redis connections and operations for storing/retrieving encrypted tokens with connection pooling, retry logic, and batch operations.

Key Interfaces:

class TokenStore:
    """Redis client for token storage with connection pooling."""
    
    async def store_token(
        self,
        system_id: str,
        token: str,
        encrypted_value: bytes,
        ttl_seconds: int
    ) -> None:
        """
        Store a single token-to-encrypted-value mapping.
        
        Args:
            system_id: System identifier for namespacing
            token: Token string
            encrypted_value: AES-256-GCM encrypted PII value
            ttl_seconds: Time-to-live in seconds (0 = no expiry)
        """
        
    async def store_batch(
        self,
        mappings: List[TokenMapping]
    ) -> None:
        """
        Store multiple tokens using Redis pipeline for efficiency.
        
        Args:
            mappings: List of TokenMapping objects
        """
        
    async def retrieve_token(
        self,
        system_id: str,
        token: str
    ) -> Optional[bytes]:
        """
        Retrieve encrypted value for a token.
        
        Args:
            system_id: System identifier
            token: Token string
            
        Returns:
            Encrypted value bytes or None if not found/expired
        """
        
    async def retrieve_batch(
        self,
        system_id: str,
        tokens: List[str]
    ) -> Dict[str, Optional[bytes]]:
        """
        Retrieve multiple tokens using Redis pipeline.
        
        Returns:
            Dict mapping token to encrypted value (None if not found)
        """
        
    async def health_check(self) -> bool:
        """Check Redis connectivity with PING command."""
        
    def build_key(self, system_id: str, token: str) -> str:
        """Build Redis key: {system_id}:token:{token}"""
Implementation Details:

Connection Pool Setup:

from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

logger = structlog.get_logger()

class TokenStore:
    """Redis token store with connection pooling and retry logic."""
    
    def __init__(
        self,
        redis_url: str,
        pool_size: int = 50,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5
    ):
        """
        Initialize Redis connection pool.
        
        Args:
            redis_url: Redis connection URL (redis://host:port/db)
            pool_size: Maximum connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.pool = ConnectionPool.from_url(
            redis_url,
            max_connections=pool_size,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            decode_responses=False,  # We work with bytes
            retry=Retry(ExponentialBackoff(), 3)
        )
        self.redis = Redis(connection_pool=self.pool)
        self.logger = logger.bind(component="token_store")
    
    async def close(self):
        """Close Redis connection pool."""
        await self.redis.close()
        await self.pool.disconnect()
Key Naming Convention:

def build_key(self, system_id: str, token: str) -> str:
    """
    Build namespaced Redis key.
    
    Format: {system_id}:token:{token}
    Example: customer_db:token:abc123-def456-789
    """
    return f"{system_id}:token:{token}"
Single Token Storage with Retry:

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
async def store_token(
    self,
    system_id: str,
    token: str,
    encrypted_value: bytes,
    ttl_seconds: int
) -> None:
    """Store token with automatic retry on transient failures."""
    
    key = self.build_key(system_id, token)
    
    try:
        if ttl_seconds > 0:
            await self.redis.setex(key, ttl_seconds, encrypted_value)
            self.logger.info(
                "stored_token_with_ttl",
                system_id=system_id,
                token=token[:8],  # Log only prefix
                ttl_seconds=ttl_seconds
            )
        else:
            await self.redis.set(key, encrypted_value)
            self.logger.info(
                "stored_token_no_expiry",
                system_id=system_id,
                token=token[:8]
            )
    except Exception as e:
        self.logger.error(
            "store_token_failed",
            system_id=system_id,
            token=token[:8],
            error=str(e)
        )
        raise
Batch Storage with Pipeline:

async def store_batch(
    self,
    mappings: List[TokenMapping]
) -> None:
    """
    Store multiple tokens using Redis pipeline for efficiency.
    
    Pipeline reduces round-trips from N to 1.
    """
    if not mappings:
        return
    
    try:
        async with self.redis.pipeline(transaction=False) as pipe:
            for mapping in mappings:
                key = self.build_key(mapping.system_id, mapping.token)
                
                if mapping.ttl_seconds > 0:
                    pipe.setex(key, mapping.ttl_seconds, mapping.encrypted_value)
                else:
                    pipe.set(key, mapping.encrypted_value)
            
            await pipe.execute()
            
        self.logger.info(
            "stored_batch",
            count=len(mappings),
            system_id=mappings[0].system_id if mappings else None
        )
    except Exception as e:
        self.logger.error(
            "store_batch_failed",
            count=len(mappings),
            error=str(e)
        )
        raise
Token Retrieval:

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
async def retrieve_token(
    self,
    system_id: str,
    token: str
) -> Optional[bytes]:
    """Retrieve encrypted value with retry logic."""
    
    key = self.build_key(system_id, token)
    
    try:
        value = await self.redis.get(key)
        
        if value is None:
            self.logger.debug(
                "token_not_found",
                system_id=system_id,
                token=token[:8]
            )
        else:
            self.logger.debug(
                "token_retrieved",
                system_id=system_id,
                token=token[:8]
            )
        
        return value
    except Exception as e:
        self.logger.error(
            "retrieve_token_failed",
            system_id=system_id,
            token=token[:8],
            error=str(e)
        )
        raise
Batch Retrieval with Pipeline:

async def retrieve_batch(
    self,
    system_id: str,
    tokens: List[str]
) -> Dict[str, Optional[bytes]]:
    """Retrieve multiple tokens efficiently using pipeline."""
    
    if not tokens:
        return {}
    
    try:
        async with self.redis.pipeline(transaction=False) as pipe:
            for token in tokens:
                key = self.build_key(system_id, token)
                pipe.get(key)
            
            values = await pipe.execute()
        
        result = dict(zip(tokens, values))
        
        found_count = sum(1 for v in values if v is not None)
        self.logger.info(
            "retrieved_batch",
            total=len(tokens),
            found=found_count,
            system_id=system_id
        )
        
        return result
    except Exception as e:
        self.logger.error(
            "retrieve_batch_failed",
            count=len(tokens),
            system_id=system_id,
            error=str(e)
        )
        raise
Health Check:

async def health_check(self) -> bool:
    """
    Check Redis connectivity.
    
    Returns:
        True if Redis responds to PING within timeout
    """
    try:
        response = await self.redis.ping()
        return response is True
    except Exception as e:
        self.logger.error("health_check_failed", error=str(e))
        return False
Data Models:

from dataclasses import dataclass

@dataclass
class TokenMapping:
    """Token-to-encrypted-value mapping for batch operations."""
    system_id: str
    token: str
    encrypted_value: bytes
    ttl_seconds: int
Metrics Integration:

from prometheus_client import Counter, Histogram
import time

redis_operations_total = Counter(
    'redis_operations_total',
    'Total Redis operations',
    ['operation', 'status']
)

redis_operation_latency_seconds = Histogram(
    'redis_operation_latency_seconds',
    'Redis operation latency',
    ['operation']
)

# Usage in methods:
async def store_token(self, system_id: str, token: str, encrypted_value: bytes, ttl_seconds: int) -> None:
    start_time = time.time()
    try:
        # ... storage logic ...
        redis_operations_total.labels(operation='store', status='success').inc()
    except Exception as e:
        redis_operations_total.labels(operation='store', status='error').inc()
        raise
    finally:
        duration = time.time() - start_time
        redis_operation_latency_seconds.labels(operation='store').observe(duration)
Configuration:

from pydantic import BaseSettings

class RedisConfig(BaseSettings):
    """Redis configuration from environment variables."""
    
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 50
    redis_socket_timeout: int = 5
    redis_socket_connect_timeout: int = 5
    
    class Config:
        env_file = ".env"
Performance Considerations:

Connection pooling prevents connection overhead (50 connections default)
Pipeline operations reduce network round-trips by ~10x
Retry logic with exponential backoff handles transient failures
Async I/O prevents blocking on Redis operations
Binary protocol (decode_responses=False) for efficiency
Error Handling:

Transient errors: Automatic retry with exponential backoff (max 3 attempts)
Connection errors: Logged and re-raised for upstream handling
Timeout errors: Configurable socket timeouts prevent hanging
Missing tokens: Return None rather than raising exception

3.7 API Gateway and Authentication
Responsibility: Manage HTTP/gRPC servers, route requests, and enforce authentication.

Key Interfaces:

class APIGateway:
    """FastAPI and gRPC server management."""
    
    async def start_servers(self) -> None:
        """Start both FastAPI and gRPC servers concurrently."""
        
    async def shutdown_servers(self) -> None:
        """Gracefully shutdown both servers."""
        
    def create_fastapi_app(self) -> FastAPI:
        """Create and configure FastAPI application."""
        
    def create_grpc_server(self) -> grpc.aio.Server:
        """Create and configure gRPC async server."""
FastAPI Application Setup:

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

logger = structlog.get_logger()

def create_fastapi_app(
    policy_loader: PolicyLoader,
    structured_tokenizer: StructuredTokenizer,
    unstructured_tokenizer: UnstructuredTokenizer
) -> FastAPI:
    """Create FastAPI application with all routes and middleware."""
    
    app = FastAPI(
        title="PII Anonymization Service",
        version="1.0.0",
        description="High-performance PII tokenization service"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Authentication middleware
    @app.middleware("http")
    async def authenticate_request(request: Request, call_next):
        """Validate API key for all non-health endpoints."""
        
        # Skip auth for health and metrics
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Extract Bearer token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        
        api_key = auth_header[7:]  # Remove "Bearer " prefix
        
        # Validate API key (implement your validation logic)
        if not validate_api_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Add client_id to request state for rate limiting
        request.state.client_id = extract_client_id(api_key)
        
        return await call_next(request)
    
    # Error handling middleware
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all unhandled exceptions."""
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)}
        )
    
    # Include routers
    from .routers import structured, unstructured, admin, health
    
    app.include_router(structured.router, prefix="/structured", tags=["structured"])
    app.include_router(unstructured.router, prefix="/unstructured", tags=["unstructured"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(health.router, tags=["health"])
    
    return app
gRPC Server Setup:

import grpc
from grpc import aio
from concurrent import futures

async def create_grpc_server(
    structured_tokenizer: StructuredTokenizer,
    port: int = 50051
) -> aio.Server:
    """Create gRPC async server with bidirectional streaming."""
    
    server = aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ('grpc.so_reuseport', 1),
            ('grpc.use_local_subchannel_pool', 1),
        ]
    )
    
    # Add servicer
    from .grpc.servicer import StructuredAnonymizerServicer
    servicer = StructuredAnonymizerServicer(structured_tokenizer)
    
    from .proto import pii_service_pb2_grpc
    pii_service_pb2_grpc.add_StructuredAnonymizerServicer_to_server(servicer, server)
    
    server.add_insecure_port(f'[::]:{port}')
    
    return server
Concurrent Server Startup:

import asyncio

async def start_servers(
    fastapi_app: FastAPI,
    grpc_server: aio.Server,
    http_port: int = 8000,
    grpc_port: int = 50051
):
    """Start both servers concurrently."""
    
    # Start gRPC server
    await grpc_server.start()
    logger.info("grpc_server_started", port=grpc_port)
    
    # Start FastAPI with uvicorn
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=http_port,
        log_config=None,  # Use structlog instead
        access_log=False
    )
    server = uvicorn.Server(config)
    
    logger.info("fastapi_server_started", port=http_port)
    
    # Run both servers
    await asyncio.gather(
        server.serve(),
        grpc_server.wait_for_termination()
    )
Authentication Helper Functions:

import hashlib
import hmac
from typing import Optional

# In production, load from secure storage
API_KEYS = {
    "client_1": "hashed_key_1",
    "client_2": "hashed_key_2"
}

def validate_api_key(api_key: str) -> bool:
    """Validate API key against stored keys."""
    hashed = hashlib.sha256(api_key.encode()).hexdigest()
    return hashed in API_KEYS.values()

def extract_client_id(api_key: str) -> str:
    """Extract client ID from API key for rate limiting."""
    hashed = hashlib.sha256(api_key.encode()).hexdigest()
    for client_id, stored_hash in API_KEYS.items():
        if stored_hash == hashed:
            return client_id
    return "unknown"
4. API Specifications
4.1 REST API Endpoints
POST /structured/anonymize

Anonymize structured records with streaming response.

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
import json

router = APIRouter()

@router.post("/anonymize")
async def anonymize_structured(
    records: List[Dict[str, Any]],
    system_id: str = Header(..., alias="X-System-ID"),
    structured_tokenizer: StructuredTokenizer = Depends(get_tokenizer)
):
    """
    Anonymize structured records.
    
    Request:
        - Header: X-System-ID (required)
        - Body: Array of JSON records
    
    Response:
        - Streaming NDJSON (one JSON object per line)
        - Each record includes _pii_anonymized field
    """
    
    async def generate_anonymized_records():
        async for anonymized in structured_tokenizer.anonymize_stream(
            iter(records), 
            system_id
        ):
            yield json.dumps(anonymized.dict()) + "\n"
    
    return StreamingResponse(
        generate_anonymized_records(),
        media_type="application/x-ndjson"
    )
POST /structured/deanonymize

De-tokenize structured records.

@router.post("/deanonymize")
async def deanonymize_structured(
    records: List[Dict[str, Any]],
    system_id: str = Header(..., alias="X-System-ID"),
    structured_tokenizer: StructuredTokenizer = Depends(get_tokenizer)
):
    """
    De-anonymize structured records.
    
    Request:
        - Header: X-System-ID (required)
        - Body: Array of JSON records with tokens
    
    Response:
        - Streaming NDJSON with original PII values restored
    """
    
    async def generate_deanonymized_records():
        for record in records:
            deanonymized = await structured_tokenizer.deanonymize_record(
                record, 
                system_id
            )
            yield json.dumps(deanonymized.dict()) + "\n"
    
    return StreamingResponse(
        generate_deanonymized_records(),
        media_type="application/x-ndjson"
    )
POST /unstructured/anonymize

Anonymize unstructured text using LLM.

from pydantic import BaseModel

class UnstructuredRequest(BaseModel):
    text: str
    return_entity_map: bool = False

class UnstructuredResponse(BaseModel):
    anonymized_text: str
    entity_map: Optional[Dict[str, Dict[str, Any]]] = None

@router.post("/anonymize", response_model=UnstructuredResponse)
async def anonymize_unstructured(
    request: UnstructuredRequest,
    system_id: str = Header(..., alias="X-System-ID"),
    client_id: str = Depends(get_client_id),
    unstructured_tokenizer: UnstructuredTokenizer = Depends(get_tokenizer)
):
    """
    Anonymize unstructured text.
    
    Request:
        - Header: X-System-ID (required)
        - Body: {text: str, return_entity_map: bool}
    
    Response:
        - anonymized_text: Text with PII replaced by tokens
        - entity_map: Optional mapping of tokens to entity metadata
    """
    
    # Rate limit check
    if not await rate_limiter.check_rate_limit(client_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    result = await unstructured_tokenizer.anonymize_text(
        request.text,
        system_id,
        request.return_entity_map
    )
    
    return result
POST /unstructured/deanonymize

De-tokenize unstructured text.

class DeanonymizeRequest(BaseModel):
    text: str

@router.post("/deanonymize")
async def deanonymize_unstructured(
    request: DeanonymizeRequest,
    system_id: str = Header(..., alias="X-System-ID"),
    unstructured_tokenizer: UnstructuredTokenizer = Depends(get_tokenizer)
):
    """
    De-anonymize unstructured text.
    
    Request:
        - Header: X-System-ID (required)
        - Body: {text: str} (text containing tokens)
    
    Response:
        - text: Text with tokens replaced by original PII values
    """
    
    deanonymized_text = await unstructured_tokenizer.deanonymize_text(
        request.text,
        system_id
    )
    
    return {"text": deanonymized_text}
GET /health

Health check endpoint.

from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str
    redis_connected: bool
    policy_version: str

@router.get("/health", response_model=HealthResponse)
async def health_check(
    token_store: TokenStore = Depends(get_token_store),
    policy_loader: PolicyLoader = Depends(get_policy_loader)
):
    """
    Health check endpoint.
    
    Response:
        - status: "healthy" or "unhealthy"
        - redis_connected: Boolean
        - policy_version: Current policy version
    """
    
    redis_ok = await token_store.health_check()
    policy = policy_loader.get_current_policy()
    
    status = "healthy" if redis_ok else "unhealthy"
    status_code = 200 if redis_ok else 503
    
    return Response(
        content=json.dumps({
            "status": status,
            "redis_connected": redis_ok,
            "policy_version": policy.version
        }),
        status_code=status_code,
        media_type="application/json"
    )
GET /metrics

Prometheus metrics endpoint.

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@router.get("/metrics")
async def metrics():
    """Expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
POST /admin/policy/reload

Reload policy configuration.

@router.post("/policy/reload")
async def reload_policy(
    policy_loader: PolicyLoader = Depends(get_policy_loader)
):
    """
    Reload policy from disk.
    
    Response:
        - success: Boolean
        - message: Status message
        - version: New policy version (if successful)
    """
    
    try:
        await policy_loader.reload_policy()
        policy = policy_loader.get_current_policy()
        
        return {
            "success": True,
            "message": "Policy reloaded successfully",
            "version": policy.version
        }
    except Exception as e:
        logger.error("policy_reload_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Policy reload failed: {str(e)}"
        )
4.2 gRPC Service Definition
pii_service.proto

syntax = "proto3";

package pii;

// Structured data anonymization service
service StructuredAnonymizer {
  // Bidirectional streaming anonymization
  rpc Anonymize(stream AnonymizeRequest) returns (stream AnonymizeResponse);
  
  // Bidirectional streaming de-anonymization
  rpc Deanonymize(stream DeanonymizeRequest) returns (stream DeanonymizeResponse);
}

// Request to anonymize a single record
message AnonymizeRequest {
  string system_id = 1;      // System identifier for policy lookup
  string record_id = 2;      // Client-provided correlation ID
  bytes record_json = 3;     // JSON-serialized record
}

// Response with anonymized record
message AnonymizeResponse {
  string record_id = 1;           // Echo of request record_id
  bytes anonymized_json = 2;      // JSON-serialized anonymized record
  repeated string token_ids = 3;  // List of generated tokens
  string error = 4;               // Non-empty if error occurred
}

// Request to de-anonymize a single record
message DeanonymizeRequest {
  string system_id = 1;      // System identifier
  string record_id = 2;      // Client-provided correlation ID
  bytes record_json = 3;     // JSON-serialized record with tokens
}

// Response with de-anonymized record
message DeanonymizeResponse {
  string record_id = 1;           // Echo of request record_id
  bytes deanonymized_json = 2;    // JSON-serialized record with original PII
  string error = 3;               // Non-empty if error occurred
}
gRPC Servicer Implementation:

import grpc
from grpc import aio
import json
from .proto import pii_service_pb2, pii_service_pb2_grpc

class StructuredAnonymizerServicer(pii_service_pb2_grpc.StructuredAnonymizerServicer):
    """gRPC servicer for structured data anonymization."""
    
    def __init__(self, structured_tokenizer: StructuredTokenizer):
        self.tokenizer = structured_tokenizer
    
    async def Anonymize(
        self,
        request_iterator: AsyncIterator[pii_service_pb2.AnonymizeRequest],
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[pii_service_pb2.AnonymizeResponse]:
        """Bidirectional streaming anonymization."""
        
        async for request in request_iterator:
            try:
                # Parse JSON record
                record = json.loads(request.record_json)
                
                # Anonymize
                anonymized = await self.tokenizer.anonymize_record(
                    record,
                    request.system_id
                )
                
                # Build response
                response = pii_service_pb2.AnonymizeResponse(
                    record_id=request.record_id,
                    anonymized_json=json.dumps(anonymized.record).encode('utf-8'),
                    token_ids=anonymized.token_ids,
                    error=""
                )
                
                yield response
                
            except Exception as e:
                # Return error response
                yield pii_service_pb2.AnonymizeResponse(
                    record_id=request.record_id,
                    anonymized_json=request.record_json,  # Return original
                    token_ids=[],
                    error=str(e)
                )
    
    async def Deanonymize(
        self,
        request_iterator: AsyncIterator[pii_service_pb2.DeanonymizeRequest],
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[pii_service_pb2.DeanonymizeResponse]:
        """Bidirectional streaming de-anonymization."""
        
        async for request in request_iterator:
            try:
                # Parse JSON record
                record = json.loads(request.record_json)
                
                # De-anonymize
                deanonymized = await self.tokenizer.deanonymize_record(
                    record,
                    request.system_id
                )
                
                # Build response
                response = pii_service_pb2.DeanonymizeResponse(
                    record_id=request.record_id,
                    deanonymized_json=json.dumps(deanonymized.record).encode('utf-8'),
                    error=""
                )
                
                yield response
                
            except Exception as e:
                # Return error response
                yield pii_service_pb2.DeanonymizeResponse(
                    record_id=request.record_id,
                    deanonymized_json=request.record_json,  # Return original
                    error=str(e)
                )
5. Data Models
5.1 Pydantic Request/Response Models
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Structured anonymization models
class AnonymizedRecord(BaseModel):
    """Result of anonymizing a single record."""
    record: Dict[str, Any]
    token_ids: List[str]
    error: Optional[str] = None
    _pii_anonymized: bool = True

class DeanonymizedRecord(BaseModel):
    """Result of de-anonymizing a single record."""
    record: Dict[str, Any]
    error: Optional[str] = None

# Unstructured anonymization models
class EntitySpan(BaseModel):
    """PII entity extracted from text."""
    type: str
    value: str
    start: int
    end: int
    token: Optional[str] = None

class AnonymizedText(BaseModel):
    """Result of anonymizing unstructured text."""
    anonymized_text: str
    entity_map: Optional[Dict[str, Dict[str, Any]]] = None

# Health check model
class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="healthy or unhealthy")
    redis_connected: bool
    policy_version: str

# Error response model
class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    field: Optional[str] = None
5.2 Redis Storage Format
Key Format:

{system_id}:token:{token_value}

Examples:
- customer_db:token:abc123-def456-789
- analytics_db:token:ADDR_xyz789
Value Format:

[12 bytes nonce][variable length ciphertext][16 bytes GCM tag]

Total: 28 + len(plaintext) bytes minimum
Example:

# Storing a token
key = "customer_db:token:abc123-def456-789"
value = b'\x01\x02...\x0c' + b'encrypted_email_data' + b'\xaa\xbb...\xff'
#       ^12-byte nonce    ^ciphertext              ^16-byte tag

# TTL (if configured)
ttl = 86400  # 24 hours
6. Security Architecture
6.1 Encryption Key Management
Key Resolution Flow:

def resolve_encryption_key(key_ref: str) -> bytes:
    """
    Resolve encryption key from reference.
    
    Supports:
    - env:VAR_NAME - Load from environment variable
    - file:/path/to/key - Load from file
    """
    
    if key_ref.startswith("env:"):
        var_name = key_ref[4:]
        key_str = os.environ.get(var_name)
        if not key_str:
            raise KeyResolutionError(f"Environment variable {var_name} not found")
        
        # Decode from base64
        try:
            key_bytes = base64.b64decode(key_str)
        except Exception as e:
            raise KeyResolutionError(f"Invalid base64 key in {var_name}: {e}")
        
        if len(key_bytes) != 32:
            raise KeyResolutionError(f"Key must be 32 bytes, got {len(key_bytes)}")
        
        return key_bytes
    
    elif key_ref.startswith("file:"):
        file_path = key_ref[5:]
        try:
            with open(file_path, 'rb') as f:
                key_bytes = f.read()
        except Exception as e:
            raise KeyResolutionError(f"Cannot read key file {file_path}: {e}")
        
        if len(key_bytes) != 32:
            raise KeyResolutionError(f"Key must be 32 bytes, got {len(key_bytes)}")
        
        return key_bytes
    
    else:
        raise KeyResolutionError(f"Invalid key reference format: {key_ref}")
Key Generation (for setup):

# Generate a 256-bit (32-byte) key
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# Output example:
# 7x8y9z0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6=
Environment Variable Setup:

# .env file
CUSTOMER_DB_KEY=7x8y9z0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6=
ANALYTICS_DB_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0=
Docker Secrets (Production):

# docker-compose.yml
services:
  pii-service:
    secrets:
      - customer_db_key
      - analytics_db_key

secrets:
  customer_db_key:
    file: ./secrets/customer_db_key.bin
  analytics_db_key:
    file: ./secrets/analytics_db_key.bin
6.2 Authentication Flow
┌─────────┐
│ Client  │
└────┬────┘
     │ 1. Request with Authorization: Bearer <api_key>
     ▼
┌──────────────────┐
│ Auth Middleware  │
└────┬─────────────┘
     │ 2. Extract Bearer token
     │ 3. Hash API key
     │ 4. Lookup in API_KEYS
     ▼
┌──────────────────┐
│ Validation       │
└────┬─────────────┘
     │
     ├─── Valid ────► Continue to endpoint
     │
     └─── Invalid ──► 401 Unauthorized
API Key Storage (Production):

# Load from secure storage (e.g., AWS Secrets Manager, HashiCorp Vault)
import boto3

def load_api_keys() -> Dict[str, str]:
    """Load API keys from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='pii-service/api-keys')
    return json.loads(response['SecretString'])
6.3 TLS Configuration
Production Deployment:

# main.py
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        ssl_keyfile="/path/to/key.pem",
        ssl_certfile="/path/to/cert.pem",
        ssl_ca_certs="/path/to/ca.pem"  # For mTLS
    )
gRPC TLS:

import grpc

# Server-side
server_credentials = grpc.ssl_server_credentials(
    [(private_key, certificate_chain)],
    root_certificates=ca_cert,
    require_client_auth=True  # For mTLS
)

server.add_secure_port('[::]:50051', server_credentials)
7. Performance Design
7.1 Async I/O Architecture
Event Loop Management:

import asyncio
import uvloop

# Use uvloop for better performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

async def main():
    """Main application entry point."""
    
    # Initialize components
    policy_loader = PolicyLoader(config.policy_path)
    await policy_loader.load_policy()
    
    token_store = TokenStore(config.redis_url, config.redis_pool_size)
    crypto_engine = CryptoEngine()
    
    # Create tokenizers
    structured_tokenizer = StructuredTokenizer(
        policy_loader,
        token_store,
        crypto_engine
    )
    
    # Start servers
    await start_servers(...)

if __name__ == "__main__":
    asyncio.run(main())
Async Patterns:

# Concurrent operations
async def process_batch(records: List[dict]) -> List[AnonymizedRecord]:
    """Process multiple records concurrently."""
    
    tasks = [
        anonymize_record(record, system_id)
        for record in records
    ]
    
    return await asyncio.gather(*tasks, return_exceptions=True)

# Streaming without buffering
async def stream_records(records: AsyncIterator[dict]):
    """Stream records without accumulating in memory."""
    
    async for record in records:
        anonymized = await anonymize_record(record)
        yield anonymized  # Immediate yield, no buffering
7.2 Connection Pooling Strategy
Redis Connection Pool:

# Optimal pool size calculation
# pool_size = (num_workers * 2) + spare_connections
# For 4 workers: (4 * 2) + 10 = 18 connections minimum
# Default: 50 connections for headroom

pool = ConnectionPool.from_url(
    redis_url,
    max_connections=50,
    socket_keepalive=True,
    socket_keepalive_options={
        socket.TCP_KEEPIDLE: 60,
        socket.TCP_KEEPINTVL: 10,
        socket.TCP_KEEPCNT: 3
    }
)
HTTP Connection Pool (for LLM API):

import httpx

# Reuse HTTP client across requests
http_client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=100,
        keepalive_expiry=30.0
    ),
    timeout=httpx.Timeout(30.0)
)
7.3 Memory Management
Streaming Chunk Size:

# Process records in chunks to limit memory
CHUNK_SIZE = 1000

async def process_large_batch(records: List[dict]):
    """Process large batches in chunks."""
    
    for i in range(0, len(records), CHUNK_SIZE):
        chunk = records[i:i + CHUNK_SIZE]
        
        # Process chunk
        results = await process_batch(chunk)
        
        # Yield results immediately
        for result in results:
            yield result
        
        # Allow garbage collection
        del chunk, results
Memory Limits:

# Uvicorn configuration
uvicorn.run(
    app,
    limit_concurrency=1000,  # Max concurrent connections
    limit_max_requests=10000,  # Restart worker after N requests
    timeout_keep_alive=5
)

8. Technology Stack and UV Integration
8.1 UV Package Manager
UV is a fast Python package installer and resolver written in Rust, providing significant performance improvements over pip.

Benefits:

10-100x faster than pip for dependency resolution
Built-in virtual environment management
Lock file support for reproducible builds
Compatible with pip and requirements.txt
Single binary installation
8.2 Project Structure
pii-anonymization-service/
├── pyproject.toml           # UV project configuration
├── uv.lock                  # Locked dependencies
├── .python-version          # Python version specification
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── src/
│   └── pii_service/
│       ├── __init__.py
│       ├── main.py          # Application entry point
│       ├── config.py        # Configuration management
│       ├── api/
│       │   ├── __init__.py
│       │   ├── rest.py      # FastAPI REST endpoints
│       │   └── grpc.py      # gRPC service implementation
│       ├── core/
│       │   ├── __init__.py
│       │   ├── policy_loader.py
│       │   ├── structured_tokenizer.py
│       │   ├── unstructured_tokenizer.py
│       │   ├── crypto_engine.py
│       │   ├── token_store.py
│       │   └── llm_client.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── policy.py    # Pydantic policy models
│       │   ├── requests.py  # API request models
│       │   └── responses.py # API response models
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── auth.py      # Authentication middleware
│       │   └── logging.py   # Request logging
│       └── observability/
│           ├── __init__.py
│           ├── metrics.py   # Prometheus metrics
│           ├── logging.py   # Structured logging setup
│           └── health.py    # Health check endpoints
├── proto/
│   └── pii_service.proto    # gRPC protocol definitions
├── policies/
│   └── example_policy.yaml  # Example policy configuration
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures
│   ├── unit/
│   │   ├── test_policy_loader.py
│   │   ├── test_structured_tokenizer.py
│   │   ├── test_unstructured_tokenizer.py
│   │   ├── test_crypto_engine.py
│   │   └── test_token_store.py
│   ├── integration/
│   │   ├── test_rest_api.py
│   │   ├── test_grpc_api.py
│   │   └── test_redis_integration.py
│   └── benchmarks/
│       ├── benchmark_structured.py
│       └── benchmark_unstructured.py
└── scripts/
    ├── generate_key.py      # Encryption key generator
    └── run_benchmarks.sh    # Benchmark execution script
8.3 pyproject.toml Configuration
[project]
name = "pii-anonymization-service"
version = "1.0.0"
description = "High-performance PII tokenization microservice"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
authors = [
    {name = "Your Team", email = "team@example.com"}
]

dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "grpcio>=1.60.0",
    "grpcio-tools>=1.60.0",
    "redis[hiredis]>=5.0.0",
    "cryptography>=42.0.0",
    "anthropic>=0.18.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "pyyaml>=6.0.1",
    "structlog>=24.1.0",
    "prometheus-client>=0.19.0",
    "tenacity>=8.2.3",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "faker>=22.0.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
    "black>=24.0.0",
]

benchmark = [
    "locust>=2.20.0",
    "psutil>=5.9.0",
    "matplotlib>=3.8.0",
    "pandas>=2.2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "faker>=22.0.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
    "black>=24.0.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--cov=src/pii_service",
    "--cov-report=term-missing",
    "--cov-report=html",
]

[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.black]
line-length = 100
target-version = ["py312"]
8.4 UV Commands
Setup and Installation:

# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Install with benchmark dependencies
uv pip install -e ".[benchmark]"
Development Workflow:

# Sync dependencies from pyproject.toml
uv pip sync

# Add a new dependency
uv pip install <package>
# Then update pyproject.toml manually

# Run tests
pytest

# Run with coverage
pytest --cov=src/pii_service --cov-report=html

# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/
Running the Service:

# REST API only
uvicorn pii_service.main:app --host 0.0.0.0 --port 8000 --reload

# With gRPC (requires separate process or main.py orchestration)
python -m pii_service.main
8.5 Dependency Management
Lock File Generation:

# UV automatically generates uv.lock on install
uv pip install -e .

# Update all dependencies
uv pip install --upgrade -e .

# Update specific package
uv pip install --upgrade <package>
Reproducible Builds:

uv.lock contains exact versions and hashes
Commit uv.lock to version control
CI/CD uses uv pip sync for exact reproduction
9. Infrastructure Design
9.1 Dockerfile (Multi-Stage Build)
# Stage 1: Builder
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache -e .

# Stage 2: Runtime
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ /app/src/
COPY proto/ /app/proto/
COPY policies/ /app/policies/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose ports
EXPOSE 8000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Default command (can be overridden)
CMD ["python", "-m", "pii_service.main"]
9.2 docker-compose.yml
version: '3.9'

services:
  pii-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: pii-anonymization-service
    ports:
      - "8000:8000"   # REST API
      - "50051:50051" # gRPC
    environment:
      # Redis Configuration
      - REDIS_URL=redis://:redis_password@redis:6379/0
      - REDIS_POOL_SIZE=50
      - REDIS_SOCKET_TIMEOUT=5
      
      # Policy Configuration
      - POLICY_PATH=/app/policies/policy.yaml
      
      # Encryption Keys (use Docker secrets in production)
      - CUSTOMER_DB_KEY=${CUSTOMER_DB_KEY}
      - ANALYTICS_DB_KEY=${ANALYTICS_DB_KEY}
      
      # Anthropic API
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      
      # Logging
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
      
      # Performance
      - UVICORN_WORKERS=4
      - GRPC_WORKERS=4
    volumes:
      - ./policies:/app/policies:ro
      - ./logs:/app/logs
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - pii-network
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  redis:
    image: redis:7.2-alpine
    container_name: pii-redis
    command: >
      redis-server
      --requirepass redis_password
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save 60 1000
      --appendonly yes
      --appendfsync everysec
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
      - ./redis.conf:/usr/local/etc/redis/redis.conf:ro
    restart: unless-stopped
    networks:
      - pii-network
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  prometheus:
    image: prom/prometheus:latest
    container_name: pii-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    restart: unless-stopped
    networks:
      - pii-network

  grafana:
    image: grafana/grafana:latest
    container_name: pii-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
    depends_on:
      - prometheus
    restart: unless-stopped
    networks:
      - pii-network

volumes:
  redis-data:
    driver: local
  prometheus-data:
    driver: local
  grafana-data:
    driver: local

networks:
  pii-network:
    driver: bridge
9.3 .env.example
# Redis Configuration
REDIS_URL=redis://:redis_password@localhost:6379/0
REDIS_POOL_SIZE=50
REDIS_SOCKET_TIMEOUT=5

# Policy Configuration
POLICY_PATH=./policies/policy.yaml

# Encryption Keys (32 bytes base64 encoded)
# Generate with: python scripts/generate_key.py
CUSTOMER_DB_KEY=your-32-byte-base64-encoded-key-here
ANALYTICS_DB_KEY=your-32-byte-base64-encoded-key-here

# Anthropic API
ANTHROPIC_API_KEY=sk-ant-your-api-key-here

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Performance
UVICORN_WORKERS=4
GRPC_WORKERS=4

# API Authentication
API_KEY_HEADER=X-API-Key
VALID_API_KEYS=key1,key2,key3
9.4 Deployment Commands
# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f pii-service

# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Scale service (horizontal scaling)
docker-compose up -d --scale pii-service=3

# Restart service
docker-compose restart pii-service

# Execute command in container
docker-compose exec pii-service python -m pii_service.cli --help
9.5 Kubernetes Deployment (Optional)
deployment.yaml:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: pii-anonymization-service
  labels:
    app: pii-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pii-service
  template:
    metadata:
      labels:
        app: pii-service
    spec:
      containers:
      - name: pii-service
        image: pii-anonymization-service:1.0.0
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 50051
          name: grpc
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: pii-secrets
              key: redis-url
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: pii-secrets
              key: anthropic-api-key
        - name: CUSTOMER_DB_KEY
          valueFrom:
            secretKeyRef:
              name: pii-secrets
              key: customer-db-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: pii-service
spec:
  selector:
    app: pii-service
  ports:
  - name: http
    port: 80
    targetPort: 8000
  - name: grpc
    port: 50051
    targetPort: 50051
  type: LoadBalancer
10. Benchmark Suite Design
10.1 Benchmark Objectives
Measure structured data anonymization throughput (records/sec)
Measure latency percentiles (p50, p95, p99, p999)
Measure memory usage under load
Measure CPU utilization
Validate 50k+ records/sec target
Validate <5ms p95 latency target
10.2 Benchmark Implementation
benchmarks/benchmark_structured.py:

import asyncio
import time
import psutil
import statistics
from typing import List, Dict
import json
from dataclasses import dataclass, asdict
import httpx

@dataclass
class BenchmarkResult:
    """Benchmark execution results."""
    total_records: int
    execution_time_seconds: float
    throughput_records_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_p999_ms: float
    memory_usage_mb: float
    cpu_utilization_percent: float
    errors: int

class StructuredBenchmark:
    """Benchmark for structured data anonymization."""
    
    def __init__(self, base_url: str, system_id: str):
        self.base_url = base_url
        self.system_id = system_id
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def generate_test_record(self) -> dict:
        """Generate a test record with PII."""
        return {
            "email": f"user{time.time_ns()}@example.com",
            "name": f"User {time.time_ns()}",
            "ssn": f"{time.time_ns() % 1000000000:09d}",
            "address": {
                "street": f"{time.time_ns() % 10000} Main St",
                "city": "San Francisco",
                "state": "CA",
                "zip": "94102"
            }
        }
    
    async def anonymize_record(self, record: dict) -> float:
        """
        Anonymize a single record and return latency in milliseconds.
        
        Returns:
            Latency in milliseconds
        """
        start = time.perf_counter()
        
        try:
            response = await self.client.post(
                f"{self.base_url}/structured/anonymize",
                json={"records": [record]},
                headers={"system-id": self.system_id}
            )
            response.raise_for_status()
            
            end = time.perf_counter()
            return (end - start) * 1000  # Convert to milliseconds
        except Exception as e:
            print(f"Error: {e}")
            return -1  # Indicate error
    
    async def run_benchmark(
        self, 
        num_records: int, 
        concurrency: int = 100
    ) -> BenchmarkResult:
        """
        Run benchmark with specified parameters.
        
        Args:
            num_records: Total number of records to process
            concurrency: Number of concurrent requests
            
        Returns:
            BenchmarkResult with metrics
        """
        print(f"Starting benchmark: {num_records} records, concurrency={concurrency}")
        
        # Track system metrics
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate test records
        print("Generating test records...")
        records = [await self.generate_test_record() for _ in range(num_records)]
        
        # Run benchmark
        print("Running anonymization...")
        start_time = time.perf_counter()
        cpu_start = process.cpu_percent()
        
        latencies: List[float] = []
        errors = 0
        
        # Process records with concurrency limit
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_record(record: dict):
            async with semaphore:
                latency = await self.anonymize_record(record)
                if latency < 0:
                    nonlocal errors
                    errors += 1
                else:
                    latencies.append(latency)
        
        tasks = [process_record(record) for record in records]
        await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        cpu_end = process.cpu_percent()
        
        # Calculate metrics
        execution_time = end_time - start_time
        throughput = num_records / execution_time
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = final_memory - initial_memory
        cpu_utilization = (cpu_start + cpu_end) / 2
        
        # Calculate latency percentiles
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        result = BenchmarkResult(
            total_records=num_records,
            execution_time_seconds=execution_time,
            throughput_records_per_sec=throughput,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            latency_p999_ms=percentile(latencies, 0.999),
            memory_usage_mb=memory_usage,
            cpu_utilization_percent=cpu_utilization,
            errors=errors
        )
        
        return result
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

async def main():
    """Run benchmark suite."""
    benchmark = StructuredBenchmark(
        base_url="http://localhost:8000",
        system_id="customer_db"
    )
    
    try:
        # Run multiple benchmark scenarios
        scenarios = [
            (1000, 10),      # 1k records, 10 concurrent
            (10000, 50),     # 10k records, 50 concurrent
            (50000, 100),    # 50k records, 100 concurrent
            (100000, 200),   # 100k records, 200 concurrent
        ]
        
        results = []
        
        for num_records, concurrency in scenarios:
            print(f"\n{'='*60}")
            print(f"Scenario: {num_records} records, {concurrency} concurrent")
            print(f"{'='*60}")
            
            result = await benchmark.run_benchmark(num_records, concurrency)
            results.append(result)
            
            # Print results
            print(f"\nResults:")
            print(f"  Total Records: {result.total_records:,}")
            print(f"  Execution Time: {result.execution_time_seconds:.2f}s")
            print(f"  Throughput: {result.throughput_records_per_sec:,.0f} records/sec")
            print(f"  Latency p50: {result.latency_p50_ms:.2f}ms")
            print(f"  Latency p95: {result.latency_p95_ms:.2f}ms")
            print(f"  Latency p99: {result.latency_p99_ms:.2f}ms")
            print(f"  Latency p999: {result.latency_p999_ms:.2f}ms")
            print(f"  Memory Usage: {result.memory_usage_mb:.2f}MB")
            print(f"  CPU Utilization: {result.cpu_utilization_percent:.1f}%")
            print(f"  Errors: {result.errors}")
            
            # Check if targets met
            if result.throughput_records_per_sec >= 50000:
                print(f"  ✓ Throughput target met (>50k records/sec)")
            else:
                print(f"  ✗ Throughput target NOT met (<50k records/sec)")
            
            if result.latency_p95_ms <= 5.0:
                print(f"  ✓ Latency target met (<5ms p95)")
            else:
                print(f"  ✗ Latency target NOT met (>5ms p95)")
        
        # Save results to JSON
        with open("benchmark_results.json", "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        
        print(f"\n{'='*60}")
        print("Benchmark results saved to benchmark_results.json")
        print(f"{'='*60}")
        
    finally:
        await benchmark.close()

if __name__ == "__main__":
    asyncio.run(main())
10.3 Benchmark Execution Script
scripts/run_benchmarks.sh:

#!/bin/bash

set -e

echo "PII Anonymization Service - Benchmark Suite"
echo "==========================================="
echo ""

# Check if service is running
echo "Checking if service is running..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "Error: Service is not running on http://localhost:8000"
    echo "Start the service with: docker-compose up -d"
    exit 1
fi

echo "Service is running ✓"
echo ""

# Install benchmark dependencies
echo "Installing benchmark dependencies..."
uv pip install -e ".[benchmark]"
echo ""

# Run structured data benchmark
echo "Running structured data benchmark..."
python tests/benchmarks/benchmark_structured.py
echo ""

# Generate report
echo "Generating benchmark report..."
python scripts/generate_benchmark_report.py
echo ""

echo "Benchmark suite completed!"
echo "Results saved to:"
echo "  - benchmark_results.json"
echo "  - benchmark_report.html"

10.4 Benchmark Report Generator
scripts/generate_benchmark_report.py:

import json
import matplotlib.pyplot as plt
from datetime import datetime

def generate_report():
    """Generate HTML report from benchmark results."""
    
    # Load results
    with open("benchmark_results.json", "r") as f:
        results = json.load(f)
    
    # Create plots
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Throughput plot
    records = [r["total_records"] for r in results]
    throughput = [r["throughput_records_per_sec"] for r in results]
    axes[0, 0].plot(records, throughput, marker='o')
    axes[0, 0].axhline(y=50000, color='r', linestyle='--', label='Target: 50k/sec')
    axes[0, 0].set_xlabel('Total Records')
    axes[0, 0].set_ylabel('Throughput (records/sec)')
    axes[0, 0].set_title('Throughput vs Record Count')
    axes[0, 0].legend()
    axes[0, 0].grid(True)
    
    # Latency plot
    latency_p50 = [r["latency_p50_ms"] for r in results]
    latency_p95 = [r["latency_p95_ms"] for r in results]
    latency_p99 = [r["latency_p99_ms"] for r in results]
    axes[0, 1].plot(records, latency_p50, marker='o', label='p50')
    axes[0, 1].plot(records, latency_p95, marker='s', label='p95')
    axes[0, 1].plot(records, latency_p99, marker='^', label='p99')
    axes[0, 1].axhline(y=5.0, color='r', linestyle='--', label='Target: 5ms p95')
    axes[0, 1].set_xlabel('Total Records')
    axes[0, 1].set_ylabel('Latency (ms)')
    axes[0, 1].set_title('Latency Percentiles')
    axes[0, 1].legend()
    axes[0, 1].grid(True)
    
    # Memory usage plot
    memory = [r["memory_usage_mb"] for r in results]
    axes[1, 0].plot(records, memory, marker='o', color='green')
    axes[1, 0].set_xlabel('Total Records')
    axes[1, 0].set_ylabel('Memory Usage (MB)')
    axes[1, 0].set_title('Memory Usage vs Record Count')
    axes[1, 0].grid(True)
    
    # CPU utilization plot
    cpu = [r["cpu_utilization_percent"] for r in results]
    axes[1, 1].plot(records, cpu, marker='o', color='orange')
    axes[1, 1].set_xlabel('Total Records')
    axes[1, 1].set_ylabel('CPU Utilization (%)')
    axes[1, 1].set_title('CPU Utilization vs Record Count')
    axes[1, 1].grid(True)
    
    plt.tight_layout()
    plt.savefig('benchmark_plots.png', dpi=300)
    
    # Generate HTML report
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PII Anonymization Service - Benchmark Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; margin-top: 30px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #4CAF50; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .pass {{ color: green; font-weight: bold; }}
            .fail {{ color: red; font-weight: bold; }}
            .summary {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            img {{ max-width: 100%; height: auto; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <h1>PII Anonymization Service - Benchmark Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <h2>Summary</h2>
            <p>This report contains performance benchmarks for the PII Anonymization Service.</p>
            <p><strong>Performance Targets:</strong></p>
            <ul>
                <li>Throughput: ≥50,000 records/second</li>
                <li>Latency (p95): ≤5ms</li>
            </ul>
        </div>
        
        <h2>Benchmark Results</h2>
        <table>
            <tr>
                <th>Records</th>
                <th>Execution Time (s)</th>
                <th>Throughput (rec/s)</th>
                <th>Latency p50 (ms)</th>
                <th>Latency p95 (ms)</th>
                <th>Latency p99 (ms)</th>
                <th>Memory (MB)</th>
                <th>CPU (%)</th>
                <th>Errors</th>
                <th>Status</th>
            </tr>
    """
    
    for r in results:
        throughput_pass = r["throughput_records_per_sec"] >= 50000
        latency_pass = r["latency_p95_ms"] <= 5.0
        overall_pass = throughput_pass and latency_pass
        status_class = "pass" if overall_pass else "fail"
        status_text = "PASS" if overall_pass else "FAIL"
        
        html += f"""
            <tr>
                <td>{r["total_records"]:,}</td>
                <td>{r["execution_time_seconds"]:.2f}</td>
                <td>{r["throughput_records_per_sec"]:,.0f}</td>
                <td>{r["latency_p50_ms"]:.2f}</td>
                <td>{r["latency_p95_ms"]:.2f}</td>
                <td>{r["latency_p99_ms"]:.2f}</td>
                <td>{r["memory_usage_mb"]:.2f}</td>
                <td>{r["cpu_utilization_percent"]:.1f}</td>
                <td>{r["errors"]}</td>
                <td class="{status_class}">{status_text}</td>
            </tr>
        """
    
    html += """
        </table>
        
        <h2>Performance Visualizations</h2>
        <img src="benchmark_plots.png" alt="Benchmark Plots">
        
        <h2>Interpretation</h2>
        <ul>
            <li><strong>Throughput:</strong> Number of records processed per second. Higher is better.</li>
            <li><strong>Latency p50:</strong> Median latency - 50% of requests complete faster than this.</li>
            <li><strong>Latency p95:</strong> 95th percentile - 95% of requests complete faster than this.</li>
            <li><strong>Latency p99:</strong> 99th percentile - 99% of requests complete faster than this.</li>
            <li><strong>Memory Usage:</strong> Additional memory consumed during benchmark execution.</li>
            <li><strong>CPU Utilization:</strong> Average CPU usage during benchmark.</li>
        </ul>
    </body>
    </html>
    """
    
    with open("benchmark_report.html", "w") as f:
        f.write(html)
    
    print("Report generated: benchmark_report.html")
    print("Plots saved: benchmark_plots.png")

if __name__ == "__main__":
    generate_report()
10.5 Continuous Benchmarking
Integration with CI/CD:

# .github/workflows/benchmark.yml
name: Performance Benchmarks

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7.2-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Install UV
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e ".[benchmark]"
      
      - name: Start service
        run: |
          source .venv/bin/activate
          python -m pii_service.main &
          sleep 10
        env:
          REDIS_URL: redis://localhost:6379/0
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      
      - name: Run benchmarks
        run: |
          source .venv/bin/activate
          bash scripts/run_benchmarks.sh
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: |
            benchmark_results.json
            benchmark_report.html
            benchmark_plots.png
      
      - name: Check performance targets
        run: |
          source .venv/bin/activate
          python scripts/check_performance_targets.py
11. Observability
11.1 Metrics
Prometheus Metrics Exposition:

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST
from fastapi import Response

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Tokenization metrics
tokenization_operations_total = Counter(
    'tokenization_operations_total',
    'Total tokenization operations',
    ['operation', 'system_id', 'status']
)

tokenization_duration_seconds = Histogram(
    'tokenization_duration_seconds',
    'Tokenization operation duration',
    ['operation', 'system_id']
)

tokens_generated_total = Counter(
    'tokens_generated_total',
    'Total tokens generated',
    ['system_id', 'token_type']
)

# Redis metrics
redis_operations_total = Counter(
    'redis_operations_total',
    'Total Redis operations',
    ['operation', 'status']
)

redis_operation_duration_seconds = Histogram(
    'redis_operation_duration_seconds',
    'Redis operation duration',
    ['operation']
)

redis_connection_pool_size = Gauge(
    'redis_connection_pool_size',
    'Current Redis connection pool size'
)

# LLM metrics
llm_api_calls_total = Counter(
    'llm_api_calls_total',
    'Total LLM API calls',
    ['model', 'status']
)

llm_api_duration_seconds = Histogram(
    'llm_api_duration_seconds',
    'LLM API call duration',
    ['model']
)

llm_tokens_used_total = Counter(
    'llm_tokens_used_total',
    'Total LLM tokens consumed',
    ['model']
)

llm_circuit_breaker_state = Gauge(
    'llm_circuit_breaker_state',
    'LLM circuit breaker state (0=closed, 1=open, 2=half-open)'
)

# System metrics
active_requests = Gauge(
    'active_requests',
    'Number of active requests'
)

policy_reload_total = Counter(
    'policy_reload_total',
    'Total policy reload attempts',
    ['status']
)

policy_version = Gauge(
    'policy_version',
    'Current policy version timestamp'
)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
11.2 Structured Logging
Logging Configuration:

import structlog
import logging
import sys

def configure_logging(log_level: str = "INFO", log_format: str = "json"):
    """Configure structured logging."""
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage in application
logger = structlog.get_logger()

# Log examples
logger.info(
    "tokenization_started",
    system_id="customer_db",
    record_count=1000,
    operation="anonymize"
)

logger.error(
    "redis_connection_failed",
    error=str(e),
    redis_url=redis_url,
    retry_attempt=3
)

logger.debug(
    "token_generated",
    system_id="customer_db",
    token_prefix=token[:8],
    deterministic=True
)
Request Logging Middleware:
import time
import uuid
from fastapi import Request
from structlog import get_logger

logger = get_logger()

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests with structured data."""
    
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Add request ID to context
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host
    )
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
    
    except Exception as e:
        duration = time.time() - start_time
        
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration_seconds=duration
        )
        raise
    
    finally:
        structlog.contextvars.clear_contextvars()
11.3 Health Checks
Health Check Endpoints:

from fastapi import status
from pydantic import BaseModel
from typing import Dict, Optional

class HealthStatus(BaseModel):
    status: str
    version: str
    checks: Dict[str, bool]
    details: Optional[Dict[str, str]] = None

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> HealthStatus:
    """
    Basic health check - returns 200 if service is running.
    Used by load balancers and container orchestrators.
    """
    return HealthStatus(
        status="healthy",
        version="1.0.0",
        checks={}
    )

@app.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> HealthStatus:
    """
    Readiness check - verifies all dependencies are available.
    Returns 503 if any dependency is unavailable.
    """
    checks = {}
    details = {}
    
    # Check Redis
    try:
        redis_healthy = await token_store.health_check()
        checks["redis"] = redis_healthy
        if not redis_healthy:
            details["redis"] = "Connection failed"
    except Exception as e:
        checks["redis"] = False
        details["redis"] = str(e)
    
    # Check LLM API
    try:
        llm_healthy = await llm_client.health_check()
        checks["llm_api"] = llm_healthy
        if not llm_healthy:
            details["llm_api"] = "API unreachable"
    except Exception as e:
        checks["llm_api"] = False
        details["llm_api"] = str(e)
    
    # Check policy loaded
    try:
        policy_healthy = policy_loader.is_loaded()
        checks["policy"] = policy_healthy
        if not policy_healthy:
            details["policy"] = "Policy not loaded"
    except Exception as e:
        checks["policy"] = False
        details["policy"] = str(e)
    
    # Determine overall status
    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return HealthStatus(
        status="ready" if all_healthy else "not_ready",
        version="1.0.0",
        checks=checks,
        details=details if not all_healthy else None
    )

@app.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> HealthStatus:
    """
    Liveness check - verifies service is not deadlocked.
    Returns 200 if service can respond to requests.
    """
    return HealthStatus(
        status="alive",
        version="1.0.0",
        checks={}
    )
11.4 Distributed Tracing (Optional)
OpenTelemetry Integration:

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def configure_tracing(service_name: str, jaeger_host: str, jaeger_port: int):
    """Configure distributed tracing with Jaeger."""
    
    # Create tracer provider
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    
    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=jaeger_port,
    )
    
    # Add span processor
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument Redis
    RedisInstrumentor().instrument()
    
    return tracer

# Usage in code
tracer = trace.get_tracer(__name__)

async def anonymize_record(record: dict, system_id: str):
    with tracer.start_as_current_span("anonymize_record") as span:
        span.set_attribute("system_id", system_id)
        span.set_attribute("record_fields", len(record))
        
        # ... tokenization logic ...
        
        span.set_attribute("tokens_generated", len(token_ids))
11.5 Alerting Rules
Prometheus Alerting Rules (prometheus_alerts.yml):

groups:
  - name: pii_service_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"
      
      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, 
            rate(http_request_duration_seconds_bucket[5m])
          ) > 0.005
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
          description: "P95 latency is {{ $value }}s (target: 5ms)"
      
      # Redis connection issues
      - alert: RedisConnectionFailures
        expr: |
          rate(redis_operations_total{status="error"}[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Redis connection failures"
          description: "Redis error rate: {{ $value }} errors/sec"
      
      # LLM API failures
      - alert: LLMAPIFailures
        expr: |
          rate(llm_api_calls_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM API failures detected"
          description: "LLM API error rate: {{ $value }} errors/sec"
      
      # Circuit breaker open
      - alert: CircuitBreakerOpen
        expr: llm_circuit_breaker_state == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "LLM circuit breaker is open"
          description: "Circuit breaker has opened due to repeated failures"
      
      # Low throughput
      - alert: LowThroughput
        expr: |
          rate(tokenization_operations_total[5m]) < 10000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low tokenization throughput"
          description: "Throughput is {{ $value }} ops/sec (target: 50k/sec)"
11.6 Grafana Dashboard
Dashboard JSON (grafana/dashboards/pii-service.json):

{
  "dashboard": {
    "title": "PII Anonymization Service",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m])"
          }
        ]
      },
      {
        "title": "Latency Percentiles",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "p50"
          },
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "p95"
          },
          {
            "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "p99"
          }
        ]
      },
      {
        "title": "Tokenization Throughput",
        "targets": [
          {
            "expr": "rate(tokenization_operations_total[5m])"
          }
        ]
      },
      {
        "title": "Redis Operations",
        "targets": [
          {
            "expr": "rate(redis_operations_total[5m])"
          }
        ]
      },
      {
        "title": "LLM API Calls",
        "targets": [
          {
            "expr": "rate(llm_api_calls_total[5m])"
          }
        ]
      }
    ]
  }
}
End of Design Document