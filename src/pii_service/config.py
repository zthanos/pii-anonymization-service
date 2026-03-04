"""Configuration management using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Redis configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 200  # Increased for high concurrency

    # Policy configuration
    POLICY_PATH: str = "policies/example_policy.yaml"

    # LLM configuration
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = "not-needed"
    OPENAI_BASE_URL: Optional[str] = "http://host.docker.internal:1234/v1"
    OPENAI_MODEL: Optional[str] = "openai/gpt-oss-20b"

    # Logging configuration
    LOG_LEVEL: str = "INFO"

    # Server configuration
    HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000
    GRPC_PORT: int = 50051
    GRPC_MAX_WORKERS: int = 50
    GRPC_MAX_CONCURRENT_REQUESTS: int = 1000

    # TLS configuration (optional)
    SSL_KEYFILE: Optional[str] = None
    SSL_CERTFILE: Optional[str] = None
    SSL_CA_CERTS: Optional[str] = None

    # API authentication (optional)
    API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
