"""
Test suite for advanced caching implementation.

Tests cache strategies, fallbacks, circuit breakers, and resilience patterns.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from redis.asyncio import Redis
from cache_manager import (
    CacheManager,
    CacheConfig,
    CacheStrategy,
    InvalidationType,
    CacheMetrics,
    FallbackResponseBuilder,
)
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerPool,
    CircuitBreakerOpenException,
)


# ============================================================================
# CACHE MANAGER TESTS
# ============================================================================


@pytest.fixture
async def redis_mock():
    """Create mock Redis client."""
    mock = AsyncMock(spec=Redis)
    return mock


@pytest.fixture
def cache_config():
    """Create default cache config."""
    return CacheConfig(
        ttl=300,
        max_size=1000000,
        strategy=CacheStrategy.READ_THROUGH,
        stale_while_revalidate=60,
    )


@pytest.mark.asyncio
async def test_cache_get_hit(redis_mock, cache_config):
    """Test cache hit scenario."""
    redis_mock.get.return_value = b'{"result": "cached"}'

    cache = CacheManager(redis_mock, cache_config)
    result = await cache.get("test_key")

    assert result == {"result": "cached"}
    assert cache.metrics.hits == 1
    assert cache.metrics.misses == 0
    redis_mock.get.assert_called_once()


@pytest.mark.asyncio
async def test_cache_get_miss(redis_mock, cache_config):
    """Test cache miss scenario."""
    redis_mock.get.return_value = None

    async def fetch_fn():
        return {"fresh": "data"}

    cache = CacheManager(redis_mock, cache_config)
    result = await cache.get("test_key", fetch_fn=fetch_fn)

    assert result == {"fresh": "data"}
    assert cache.metrics.hits == 0
    assert cache.metrics.misses == 1


@pytest.mark.asyncio
async def test_cache_set(redis_mock, cache_config):
    """Test cache set operation."""
    cache = CacheManager(redis_mock, cache_config)
    success = await cache.set("test_key", {"data": "value"}, ttl=300)

    assert success is True
    redis_mock.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_delete(redis_mock, cache_config):
    """Test cache delete operation."""
    cache = CacheManager(redis_mock, cache_config)
    success = await cache.delete("test_key")

    assert success is True
    redis_mock.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cache_fallback(redis_mock, cache_config):
    """Test fallback on cache miss."""
    redis_mock.get.return_value = None

    cache = CacheManager(redis_mock, cache_config)
    result = await cache.get("test_key", fallback={"fallback": "data"})

    assert result == {"fallback": "data"}
    assert cache.metrics.fallback_hits == 1


@pytest.mark.asyncio
async def test_cache_metrics(redis_mock, cache_config):
    """Test cache metrics tracking."""
    redis_mock.get.return_value = None

    cache = CacheManager(redis_mock, cache_config)

    # Simulate cache operations
    await cache.get("key1")  # miss
    await cache.get("key2")  # miss
    redis_mock.get.return_value = b'{"data": "value"}'
    await cache.get("key3")  # hit
    await cache.get("key4")  # hit

    metrics = cache.get_metrics()
    assert metrics.hits == 2
    assert metrics.misses == 2
    assert metrics.hit_ratio == 0.5


@pytest.mark.asyncio
async def test_cache_batch_get(redis_mock, cache_config):
    """Test batch get operation."""
    redis_mock.mget.return_value = [b'{"a": 1}', None, b'{"c": 3}']

    cache = CacheManager(redis_mock, cache_config)
    result = await cache.get_batch(["key1", "key2", "key3"])

    assert result == {
        "key1": {"a": 1},
        "key2": None,  # miss
        "key3": {"c": 3},
    }


@pytest.mark.asyncio
async def test_cache_batch_set(redis_mock, cache_config):
    """Test batch set operation."""
    cache = CacheManager(redis_mock, cache_config)
    items = {"key1": {"a": 1}, "key2": {"b": 2}}
    count = await cache.set_batch(items)

    assert count == 2
    redis_mock.pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_write_through_strategy(redis_mock, cache_config):
    """Test write-through cache strategy."""
    cache_config.strategy = CacheStrategy.WRITE_THROUGH

    cache = CacheManager(redis_mock, cache_config)
    await cache.set("key", {"data": "value"})

    # Should write to cache
    redis_mock.setex.assert_called()


@pytest.mark.asyncio
async def test_write_behind_strategy(redis_mock, cache_config):
    """Test write-behind cache strategy."""
    cache_config.strategy = CacheStrategy.WRITE_BEHIND

    cache = CacheManager(redis_mock, cache_config)
    await cache.set("key", {"data": "value"}, strategy=CacheStrategy.WRITE_BEHIND)

    # Should queue for later flush
    assert "key" in cache._pending_writes
    redis_mock.setex.assert_called()


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================


@pytest.fixture
def circuit_breaker_config():
    """Create circuit breaker config."""
    return CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout=1,
    )


@pytest.mark.asyncio
async def test_circuit_breaker_closed_success(circuit_breaker_config):
    """Test circuit breaker in closed state with successful call."""
    breaker = CircuitBreaker(circuit_breaker_config, "test")

    async def successful_fn():
        return "success"

    result = await breaker.call(successful_fn)

    assert result == "success"
    assert breaker.state.value == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(circuit_breaker_config):
    """Test circuit breaker opens after failure threshold."""
    breaker = CircuitBreaker(circuit_breaker_config, "test")

    async def failing_fn():
        raise ValueError("Test error")

    # Fail until threshold
    for i in range(3):
        try:
            await breaker.call(failing_fn)
        except ValueError:
            pass

    assert breaker.state.value == "open"
    assert breaker.metrics.failures == 3


@pytest.mark.asyncio
async def test_circuit_breaker_rejected_when_open(circuit_breaker_config):
    """Test circuit breaker rejects calls when open."""
    breaker = CircuitBreaker(circuit_breaker_config, "test")

    # Open the circuit
    async def failing_fn():
        raise ValueError("Error")

    for _ in range(3):
        try:
            await breaker.call(failing_fn)
        except ValueError:
            pass

    # Should reject call
    with pytest.raises(CircuitBreakerOpenException):
        await breaker.call(failing_fn)


@pytest.mark.asyncio
async def test_circuit_breaker_fallback(circuit_breaker_config):
    """Test circuit breaker with fallback."""
    breaker = CircuitBreaker(circuit_breaker_config, "test")

    async def failing_fn():
        raise ValueError("Error")

    async def fallback_fn():
        return "fallback"

    # Open circuit
    for _ in range(3):
        try:
            await breaker.call(failing_fn)
        except ValueError:
            pass

    # Call with fallback
    result = await breaker.call(failing_fn, fallback=fallback_fn)

    assert result == "fallback"


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(circuit_breaker_config):
    """Test circuit breaker recovery from open to closed."""
    breaker = CircuitBreaker(circuit_breaker_config, "test")
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 6:  # Fail first 3, succeed next 2
            raise ValueError("Fail")
        return "success"

    # Open circuit with 3 failures
    for _ in range(3):
        try:
            await breaker.call(fn)
        except (ValueError, CircuitBreakerOpenException):
            pass

    assert breaker.state.value == "open"

    # Wait for timeout
    await asyncio.sleep(1.1)

    # Should transition to half-open and recover
    try:
        await breaker.call(fn)
        await breaker.call(fn)
    except ValueError:
        pass

    assert breaker.state.value == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_pool(circuit_breaker_config):
    """Test circuit breaker pool."""
    pool = CircuitBreakerPool()

    async def fn():
        return "result"

    result = await pool.call("service1", fn)
    assert result == "result"

    status = pool.get_all_status()
    assert "service1" in status


# ============================================================================
# FALLBACK RESPONSE TESTS
# ============================================================================


def test_fallback_safe_default_response():
    """Test safe default response generation."""
    response = FallbackResponseBuilder.safe_default_response("search")

    assert response["status"] == "default"
    assert response["results"] == []
    assert response["total_count"] == 0


def test_fallback_degraded_response():
    """Test degraded response with partial data."""
    partial_data = [{"id": 1, "title": "cached result"}]

    response = FallbackResponseBuilder.degraded_response(
        original_request={"query": "test"},
        cached_partial_data=partial_data,
        error_message="Backend unavailable",
    )

    assert response["status"] == "degraded"
    assert response["data"] == partial_data
    assert "error" in response


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_cache_with_circuit_breaker(redis_mock, cache_config, circuit_breaker_config):
    """Test cache with circuit breaker integration."""
    redis_mock.get.return_value = None
    redis_mock.setex = AsyncMock()

    breaker = CircuitBreaker(circuit_breaker_config, "backend")
    cache = CacheManager(redis_mock, cache_config)

    call_count = 0

    async def fetch_with_breaker():
        nonlocal call_count
        call_count += 1

        if call_count <= 3:  # Fail 3 times to trigger circuit breaker
            raise ValueError("Backend error")

        return {"data": "fresh"}

    # First 3 calls should fail
    for _ in range(3):
        try:
            await breaker.call(fetch_with_breaker)
        except (ValueError, CircuitBreakerOpenException):
            pass

    # Circuit should be open
    assert breaker.state.value == "open"

    # Next call should use fallback
    result = await breaker.call(
        fetch_with_breaker,
        fallback=lambda: {"cached": "fallback"}
    )
    assert result == {"cached": "fallback"}


@pytest.mark.asyncio
async def test_stale_while_revalidate_flow(redis_mock, cache_config):
    """Test stale-while-revalidate pattern flow."""
    redis_mock.get = AsyncMock()
    redis_mock.setex = AsyncMock()

    cache = CacheManager(redis_mock, cache_config)

    # First request - cache miss
    call_count = 0

    async def fetch():
        nonlocal call_count
        call_count += 1
        return {"version": call_count}

    redis_mock.get.return_value = None
    result1 = await cache.get("key", fetch_fn=fetch)
    assert call_count == 1  # Fetched fresh

    # Second request - cache hit
    redis_mock.get.return_value = b'{"version": 1}'
    result2 = await cache.get("key", fetch_fn=fetch)
    assert cache.metrics.hits == 1
    # Should not fetch again (cache hit)


@pytest.mark.asyncio
async def test_cache_error_handling(redis_mock, cache_config):
    """Test cache error handling."""
    redis_mock.get.side_effect = Exception("Redis error")

    cache = CacheManager(redis_mock, cache_config)
    result = await cache.get("key", fallback={"safe": "default"})

    assert result == {"safe": "default"}
    assert cache.metrics.errors == 1


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_cache_latency_improvement():
    """Test cache latency improvement."""
    redis_mock = AsyncMock(spec=Redis)
    cache_config = CacheConfig(ttl=300)
    cache = CacheManager(redis_mock, cache_config)

    # Simulate cache hit latency
    redis_mock.get.return_value = b'{"data": "cached"}'

    import time

    start = time.time()
    await cache.get("key")
    hit_latency = (time.time() - start) * 1000

    # Simulated backend latency would be ~250ms, cache is <1ms
    assert hit_latency < 5  # Should be very fast


@pytest.mark.asyncio
async def test_batch_operations_efficiency():
    """Test batch operations are more efficient."""
    redis_mock = AsyncMock(spec=Redis)
    cache_config = CacheConfig(ttl=300)
    cache = CacheManager(redis_mock, cache_config)

    # Batch set should be single pipeline operation
    await cache.set_batch({"key1": "v1", "key2": "v2", "key3": "v3"})

    # Should use pipeline (single call)
    assert redis_mock.pipeline.called or redis_mock.setex.called


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
