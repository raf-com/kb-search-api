"""
Embedding service for generating and managing vector embeddings.

Uses LiteLLM to generate embeddings with caching via Redis.
"""

import logging
import json
import hashlib
from typing import List, Dict, Any
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating and managing embeddings."""

    def __init__(self, redis_client: Redis):
        """
        Initialize embedding service.

        Args:
            redis_client: Redis client for caching embeddings
        """
        self.settings = get_settings()
        self.redis = redis_client

        # Import litellm
        try:
            import litellm

            self.litellm = litellm
        except ImportError:
            raise ImportError("litellm is required. Install with: pip install litellm")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for text.

        Uses Redis caching to avoid re-embedding same text.
        Implements exponential backoff retry on failure.

        Args:
            text: Text to embed

        Returns:
            list: Embedding vector (1536 dimensions)

        Raises:
            Exception: If embedding generation fails after retries

        Example:
            >>> embedding = await embedding_service.embed_text("postgresql replication")
            >>> len(embedding)
            1536
        """
        # Check cache first
        cache_key = self._get_cache_key(text)
        cached_embedding = await self.redis.get(cache_key)
        if cached_embedding:
            logger.debug(f"Cache hit for embedding: {text[:50]}")
            return json.loads(cached_embedding)

        try:
            # Generate embedding via LiteLLM
            response = await self.litellm.aembedding(
                model=self.settings.embedding_model,
                input=text,
                api_key=self.settings.litellm_api_key,
                timeout=self.settings.embedding_timeout,
            )

            embedding = response.data[0]["embedding"]

            # Validate embedding
            if (
                not isinstance(embedding, list)
                or len(embedding) != self.settings.embedding_dimension
            ):
                raise ValueError(
                    f"Invalid embedding dimension: {len(embedding)} "
                    f"(expected {self.settings.embedding_dimension})"
                )

            # Cache result
            await self.redis.setex(
                cache_key,
                self.settings.redis_embedding_ttl,
                json.dumps(embedding),
            )

            logger.debug(f"Generated embedding for text: {text[:50]}")
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        More efficient than individual calls for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            list: List of embedding vectors

        Example:
            >>> texts = ["document 1", "document 2"]
            >>> embeddings = await embedding_service.embed_batch(texts)
            >>> len(embeddings)
            2
        """
        if not texts:
            return []

        # Check cache for texts already embedded
        cached_embeddings = {}
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            cached = await self.redis.get(cache_key)
            if cached:
                cached_embeddings[i] = json.loads(cached)
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts
        embeddings_map = {}
        if uncached_texts:
            try:
                response = await self.litellm.aembedding(
                    model=self.settings.embedding_model,
                    input=uncached_texts,
                    api_key=self.settings.litellm_api_key,
                    timeout=self.settings.embedding_timeout,
                )

                for idx, embedding_data in enumerate(response.data):
                    embedding = embedding_data["embedding"]
                    original_idx = uncached_indices[idx]
                    embeddings_map[original_idx] = embedding

                    # Cache individual embeddings
                    cache_key = self._get_cache_key(uncached_texts[idx])
                    await self.redis.setex(
                        cache_key,
                        self.settings.redis_embedding_ttl,
                        json.dumps(embedding),
                    )

                logger.debug(f"Generated {len(uncached_texts)} embeddings in batch")

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                raise

        # Combine cached and newly generated embeddings
        result = []
        for i in range(len(texts)):
            if i in cached_embeddings:
                result.append(cached_embeddings[i])
            elif i in embeddings_map:
                result.append(embeddings_map[i])

        return result

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key for embedding.

        Args:
            text: Text to embed

        Returns:
            str: Cache key

        Example:
            >>> key = embedding_service._get_cache_key("test")
            >>> print(key)
            embedding:098f6bcd4621d373cade4e832627b4f6
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{text_hash}"

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of embedding service.

        Returns:
            dict: Health status

        Example:
            >>> health = await embedding_service.health_check()
            >>> print(health['status'])
            'ok'
        """
        # Skip health check if no API key is configured (development mode)
        if not self.settings.litellm_api_key:
            logger.info(
                "Embedding service health check skipped (no API key configured)"
            )
            return {
                "status": "ok",
                "model": self.settings.embedding_model,
                "note": "API key not configured",
            }

        try:
            # Test embedding generation
            response = await self.litellm.aembedding(
                model=self.settings.embedding_model,
                input="test",
                api_key=self.settings.litellm_api_key,
                timeout=5,  # Short timeout for health check
            )

            if (
                response.data
                and len(response.data[0]["embedding"])
                == self.settings.embedding_dimension
            ):
                return {"status": "ok", "model": self.settings.embedding_model}

            return {"status": "error", "error": "Invalid embedding dimension"}

        except Exception as e:
            logger.error(f"Embedding service health check failed: {e}")
            return {"status": "error", "error": str(e)}
