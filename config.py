"""
Configuration management for the Knowledge Base Search API.

Supports environment-based configuration with sensible defaults.
Uses Pydantic settings for type-safe environment variable loading.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Environment
    environment: str = Field(
        default="development", description="Environment: development|staging|production"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # FastAPI
    api_title: str = Field(default="Knowledge Base Search API", description="API title")
    api_version: str = Field(default="1.0.0", description="API version")
    api_workers: int = Field(default=4, description="Number of uvicorn workers")
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Database
    database_url: str = Field(
        default="postgresql://kb_user:password@localhost:5432/kb_db",
        description="PostgreSQL connection URL",
    )
    db_pool_size: int = Field(default=20, description="Database connection pool size")
    db_max_overflow: int = Field(default=40, description="Database pool overflow size")
    db_pool_recycle: int = Field(
        default=3600, description="Database connection recycle time (seconds)"
    )
    db_echo: bool = Field(default=False, description="Echo SQL queries to stdout")

    # Meilisearch
    meilisearch_url: str = Field(
        default="http://localhost:7700", description="Meilisearch URL"
    )
    meilisearch_key: str = Field(
        default="masterKey", description="Meilisearch master key"
    )
    meilisearch_index: str = Field(
        default="kb_documents", description="Meilisearch index name"
    )
    meilisearch_timeout: int = Field(
        default=30, description="Meilisearch request timeout (seconds)"
    )

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant URL")
    qdrant_api_key: str = Field(default="", description="Qdrant API key")
    qdrant_collection: str = Field(
        default="kb_embeddings", description="Qdrant collection name"
    )
    qdrant_timeout: int = Field(
        default=30, description="Qdrant request timeout (seconds)"
    )
    embedding_dimension: int = Field(
        default=1536, description="Embedding vector dimension"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    redis_cache_ttl: int = Field(default=3600, description="Redis cache TTL (seconds)")
    redis_embedding_ttl: int = Field(
        default=2592000, description="Embedding cache TTL (30 days in seconds)"
    )

    # LiteLLM / OpenAI
    litellm_api_key: str = Field(default="", description="LiteLLM/OpenAI API key")
    embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model name"
    )
    embedding_timeout: int = Field(
        default=60, description="Embedding request timeout (seconds)"
    )
    batch_embedding_size: int = Field(
        default=25, description="Batch size for embedding requests"
    )

    # Search behavior
    default_search_limit: int = Field(
        default=10, description="Default search result limit"
    )
    max_search_limit: int = Field(
        default=100, description="Maximum search result limit"
    )
    default_semantic_weight: float = Field(
        default=0.5, description="Default semantic weight (0-1)"
    )
    semantic_threshold: float = Field(
        default=0.6, description="Minimum similarity score for semantic results"
    )

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(
        default=1000, description="Rate limit requests per minute"
    )
    rate_limit_per_hour: int = Field(
        default=60000, description="Rate limit requests per hour"
    )

    # Circuit breaker
    circuit_breaker_enabled: bool = Field(
        default=True, description="Enable circuit breaker"
    )
    circuit_breaker_threshold: int = Field(
        default=5, description="Failure threshold before circuit opens"
    )
    circuit_breaker_timeout: int = Field(
        default=60, description="Circuit breaker timeout (seconds)"
    )

    # Indexing
    async_indexing_enabled: bool = Field(
        default=True, description="Enable async indexing"
    )
    indexing_max_retries: int = Field(
        default=3, description="Max retries for indexing operations"
    )
    indexing_retry_delay: int = Field(
        default=5, description="Retry delay for indexing (seconds)"
    )

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Get application settings (cached).

    Returns:
        Settings: Application configuration

    Example:
        >>> settings = get_settings()
        >>> print(settings.environment)
        'production'
    """
    return Settings()
