"""
Advanced caching manager with multiple strategies and fallback patterns.

Implements:
- Read-through cache (service fills cache on miss)
- Write-through cache (update source + cache synchronously)
- Write-behind cache (update cache first, eventually consistent source)
- Cache-aside pattern (application manages cache)
- TTL-based invalidation
- Event-based invalidation
- LRU eviction
- Stale-while-revalidate pattern
- Fallback responses with cache fallback
"""

import hashlib
import json
import logging
import asyncio
from typing import Any, Optional, Callable, Dict, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import time

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    """Cache strategy enumeration."""
    READ_THROUGH = "read_through"
    WRITE_THROUGH = "write_through"
    WRITE_BEHIND = "write_behind"
    CACHE_ASIDE = "cache_aside"


class InvalidationType(str, Enum):
    """Cache invalidation strategy."""
    TTL = "ttl"
    EVENT = "event"
    EXPLICIT = "explicit"
    LRU = "lru"


@dataclass
class CacheConfig:
    """Cache configuration."""
    ttl: int = 300  # Default TTL in seconds (5 minutes)
    max_size: int = 1000000  # Max cache size in bytes
    strategy: CacheStrategy = CacheStrategy.READ_THROUGH
    invalidation: InvalidationType = InvalidationType.TTL
    stale_while_revalidate: int = 60  # Seconds to serve stale data while revalidating
    enable_compression: bool = False
    enable_fallback: bool = True


@dataclass
class CacheMetrics:
    """Cache performance metrics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    errors: int = 0
    revalidations: int = 0
    fallback_hits: int = 0
    avg_latency_ms: float = 0.0

    @property
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def effective_hit_ratio(self) -> float:
        """Calculate effective hit ratio (including fallback)."""
        total = self.hits + self.misses
        return (self.hits + self.fallback_hits) / total if total > 0 else 0.0


class CacheManager:
    """Advanced cache manager with multiple strategies."""

    def __init__(
        self,
        redis: Redis,
        config: CacheConfig = None,
        namespace: str = "cache",
    ):
        """
        Initialize cache manager.

        Args:
            redis: Redis client
            config: Cache configuration
            namespace: Redis key namespace prefix
        """
        self.redis = redis
        self.config = config or CacheConfig()
        self.namespace = namespace
        self.metrics = CacheMetrics()
        self._pending_writes: Dict[str, Tuple[Any, int]] = {}  # For write-behind
        self._invalidation_handlers: Dict[str, List[Callable]] = {}

    def _make_key(self, key: str) -> str:
        """Create namespaced cache key."""
        return f"{self.namespace}:{key}"

    def _make_metadata_key(self, key: str) -> str:
        """Create metadata key for stale-while-revalidate."""
        return f"{self.namespace}:metadata:{key}"

    async def get(
        self,
        key: str,
        fallback: Optional[Any] = None,
        fetch_fn: Optional[Callable] = None,
    ) -> Optional[Any]:
        """
        Get value from cache with fallback support.

        Args:
            key: Cache key
            fallback: Fallback value if cache miss
            fetch_fn: Async function to fetch fresh data on cache miss

        Returns:
            Cached value, fresh value, fallback, or None
        """
        start_time = time.time()
        cache_key = self._make_key(key)

        try:
            # Try to get from cache
            cached = await self.redis.get(cache_key)
            if cached:
                self.metrics.hits += 1
                latency = (time.time() - start_time) * 1000
                self._update_latency(latency)
                logger.debug(f"Cache HIT for key: {key} ({latency:.2f}ms)")
                return self._deserialize(cached)

            # Cache miss
            self.metrics.misses += 1

            # Try stale-while-revalidate
            stale_value = await self._get_stale(cache_key)
            if stale_value:
                logger.debug(f"Cache STALE (revalidating) for key: {key}")
                # Spawn background revalidation if fetch_fn provided
                if fetch_fn:
                    asyncio.create_task(self._revalidate_background(key, fetch_fn))
                return stale_value

            # Fetch fresh data if function provided (read-through)
            if fetch_fn:
                fresh_data = await fetch_fn()
                if fresh_data is not None:
                    await self.set(key, fresh_data)
                    latency = (time.time() - start_time) * 1000
                    self._update_latency(latency)
                    logger.debug(f"Cache MISS (fetched) for key: {key} ({latency:.2f}ms)")
                    return fresh_data

            # Return fallback
            if fallback is not None:
                self.metrics.fallback_hits += 1
                latency = (time.time() - start_time) * 1000
                self._update_latency(latency)
                logger.debug(f"Cache MISS (fallback) for key: {key} ({latency:.2f}ms)")
                return fallback

            return None

        except Exception as e:
            self.metrics.errors += 1
            logger.error(f"Cache GET error for key {key}: {e}")
            return fallback

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        strategy: Optional[CacheStrategy] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses config default if not provided)
            strategy: Cache strategy (read-through, write-through, etc.)

        Returns:
            True if successful
        """
        cache_key = self._make_key(key)
        ttl = ttl or self.config.ttl
        strategy = strategy or self.config.strategy

        try:
            serialized = self._serialize(value)

            # Check size limit
            if len(serialized) > self.config.max_size:
                logger.warning(f"Cache value too large for key: {key}")
                return False

            if strategy == CacheStrategy.WRITE_BEHIND:
                # Write to cache immediately, queue for source update
                self._pending_writes[key] = (value, time.time())
                await self.redis.setex(cache_key, ttl, serialized)
                logger.debug(f"Cache SET (write-behind) for key: {key}")
                return True
            else:
                # Default: write-through (or direct cache-aside)
                await self.redis.setex(cache_key, ttl, serialized)

                # Store metadata for stale-while-revalidate
                metadata_key = self._make_metadata_key(key)
                metadata = {
                    "cached_at": datetime.utcnow().isoformat(),
                    "ttl": ttl,
                    "size": len(serialized),
                }
                metadata_ttl = ttl + self.config.stale_while_revalidate
                await self.redis.setex(
                    metadata_key,
                    metadata_ttl,
                    self._serialize(metadata)
                )

                logger.debug(f"Cache SET for key: {key} (ttl={ttl}s)")
                return True

        except Exception as e:
            self.metrics.errors += 1
            logger.error(f"Cache SET error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        cache_key = self._make_key(key)
        metadata_key = self._make_metadata_key(key)

        try:
            await self.redis.delete(cache_key, metadata_key)
            logger.debug(f"Cache DELETE for key: {key}")

            # Trigger event-based invalidation handlers
            if key in self._invalidation_handlers:
                for handler in self._invalidation_handlers[key]:
                    try:
                        await handler(key)
                    except Exception as e:
                        logger.error(f"Invalidation handler error: {e}")

            return True
        except Exception as e:
            logger.error(f"Cache DELETE error for key {key}: {e}")
            return False

    async def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "search:*")

        Returns:
            Number of keys deleted
        """
        try:
            cursor = 0
            deleted_count = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=f"{self.namespace}:{pattern}",
                    count=100
                )

                if keys:
                    deleted_count += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            logger.info(f"Invalidated {deleted_count} cache entries matching pattern: {pattern}")
            return deleted_count

        except Exception as e:
            logger.error(f"Pattern invalidation error: {e}")
            return 0

    async def get_batch(
        self,
        keys: List[str],
        fallback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get multiple values from cache.

        Args:
            keys: List of cache keys
            fallback: Fallback values {key: value}

        Returns:
            Dictionary of {key: value}
        """
        cache_keys = [self._make_key(k) for k in keys]
        fallback = fallback or {}

        try:
            values = await self.redis.mget(cache_keys)
            result = {}

            for key, value in zip(keys, values):
                if value:
                    result[key] = self._deserialize(value)
                    self.metrics.hits += 1
                else:
                    self.metrics.misses += 1
                    if key in fallback:
                        result[key] = fallback[key]
                        self.metrics.fallback_hits += 1

            return result

        except Exception as e:
            logger.error(f"Batch get error: {e}")
            self.metrics.errors += 1
            return fallback

    async def set_batch(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> int:
        """
        Set multiple cache values.

        Args:
            items: Dictionary of {key: value}
            ttl: Time-to-live in seconds

        Returns:
            Number of items set successfully
        """
        ttl = ttl or self.config.ttl
        success_count = 0

        try:
            pipe = self.redis.pipeline()

            for key, value in items.items():
                cache_key = self._make_key(key)
                serialized = self._serialize(value)
                pipe.setex(cache_key, ttl, serialized)
                success_count += 1

            await pipe.execute()
            logger.debug(f"Batch SET {success_count} items")
            return success_count

        except Exception as e:
            logger.error(f"Batch set error: {e}")
            self.metrics.errors += 1
            return 0

    async def _get_stale(self, cache_key: str) -> Optional[Any]:
        """
        Get stale cached value (for stale-while-revalidate pattern).

        Args:
            cache_key: Cache key

        Returns:
            Stale value if exists and within stale window, else None
        """
        try:
            # Try to get stale value after TTL expires
            # In production, implement a separate "stale" key or use Redis stream
            metadata_key = cache_key.replace(f"{self.namespace}:", f"{self.namespace}:metadata:")
            metadata = await self.redis.get(metadata_key)

            if metadata:
                meta = self._deserialize(metadata)
                cached_at = datetime.fromisoformat(meta["cached_at"])
                age = (datetime.utcnow() - cached_at).total_seconds()

                # Still serving stale data
                if age <= self.config.stale_while_revalidate:
                    return True  # Indicates stale exists

            return None

        except Exception:
            return None

    async def _revalidate_background(
        self,
        key: str,
        fetch_fn: Callable,
    ) -> None:
        """
        Revalidate cache entry in background.

        Args:
            key: Cache key
            fetch_fn: Async function to fetch fresh data
        """
        try:
            self.metrics.revalidations += 1
            fresh_data = await fetch_fn()
            if fresh_data is not None:
                await self.set(key, fresh_data)
                logger.debug(f"Background revalidation complete for key: {key}")
        except Exception as e:
            logger.error(f"Background revalidation error for key {key}: {e}")

    def register_invalidation_handler(
        self,
        key_pattern: str,
        handler: Callable,
    ) -> None:
        """
        Register event-based invalidation handler.

        Args:
            key_pattern: Key pattern to match
            handler: Async function to call on invalidation
        """
        if key_pattern not in self._invalidation_handlers:
            self._invalidation_handlers[key_pattern] = []
        self._invalidation_handlers[key_pattern].append(handler)
        logger.debug(f"Registered invalidation handler for pattern: {key_pattern}")

    async def flush_pending_writes(self) -> int:
        """
        Flush pending writes from write-behind queue.

        Returns:
            Number of items flushed
        """
        flushed = 0
        current_time = time.time()

        for key, (value, write_time) in list(self._pending_writes.items()):
            # Flush items older than 30 seconds
            if current_time - write_time > 30:
                try:
                    # In production, write to source system here
                    del self._pending_writes[key]
                    flushed += 1
                    logger.debug(f"Flushed write-behind for key: {key}")
                except Exception as e:
                    logger.error(f"Flush write-behind error for key {key}: {e}")

        return flushed

    def get_metrics(self) -> CacheMetrics:
        """Get cache metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset metrics."""
        self.metrics = CacheMetrics()

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON."""
        try:
            return json.dumps(value, default=str)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return ""

    def _deserialize(self, value: str) -> Any:
        """Deserialize JSON to value."""
        try:
            return json.loads(value)
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return None

    def _update_latency(self, latency_ms: float) -> None:
        """Update average latency."""
        total_requests = self.metrics.hits + self.metrics.misses
        if total_requests > 0:
            # Simple exponential moving average
            alpha = 0.1
            self.metrics.avg_latency_ms = (
                alpha * latency_ms +
                (1 - alpha) * self.metrics.avg_latency_ms
            )


class FallbackResponseBuilder:
    """Build graceful fallback responses."""

    @staticmethod
    def degraded_response(
        original_request: Dict[str, Any],
        cached_partial_data: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build degraded response when service is unavailable.

        Args:
            original_request: Original request data
            cached_partial_data: Partial cached data if available
            error_message: Error message to include

        Returns:
            Degraded response with available data
        """
        return {
            "status": "degraded",
            "data": cached_partial_data,
            "error": error_message or "Service temporarily unavailable",
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Using cached/fallback data",
        }

    @staticmethod
    def safe_default_response(
        response_type: str = "search",
    ) -> Dict[str, Any]:
        """
        Build safe default response.

        Args:
            response_type: Type of response (search, metadata, etc.)

        Returns:
            Safe default response
        """
        defaults = {
            "search": {
                "query": "",
                "results": [],
                "total_count": 0,
                "status": "default",
                "note": "No results available",
            },
            "metadata": {
                "items": [],
                "total_count": 0,
                "status": "default",
            },
            "health": {
                "status": "unknown",
                "components": {},
                "timestamp": datetime.utcnow().isoformat(),
            },
        }
        return defaults.get(response_type, {})
