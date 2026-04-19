"""
40+ Caching patterns and best practices documentation.

This module documents all implemented caching strategies with examples.
"""

# ============================================================================
# PATTERN CATALOG (40+ patterns)
# ============================================================================

# 1. READ-THROUGH CACHE
# Pattern: Service layer reads from cache; on miss, fetches from source and caches
# Pros: Simplest, automatic cache population
# Cons: First request slow, requires write coordination
# Use case: Frequently accessed static data
PATTERN_1_READ_THROUGH = """
async def read_through_search(query: str) -> dict:
    return await cache.get(
        key=f"search:{query}",
        fetch_fn=lambda: search_service.search(query)  # Fetched on miss
    )
"""

# 2. WRITE-THROUGH CACHE
# Pattern: Update cache and source synchronously
# Pros: Cache always consistent with source
# Cons: Slower writes (2 operations)
# Use case: Critical data that must be consistent
PATTERN_2_WRITE_THROUGH = """
async def write_through_update(doc_id: str, data: dict):
    # Update both source and cache
    await source.update(doc_id, data)
    await cache.set(f"doc:{doc_id}", data)
"""

# 3. WRITE-BEHIND CACHE
# Pattern: Update cache immediately, queue source update
# Pros: Fast writes, eventual consistency
# Cons: Data loss risk, race conditions
# Use case: Analytics, logs, non-critical updates
PATTERN_3_WRITE_BEHIND = """
async def write_behind_update(doc_id: str, data: dict):
    # Update cache immediately
    await cache.set(f"doc:{doc_id}", data, strategy=CacheStrategy.WRITE_BEHIND)
    # Source updated asynchronously by flush_pending_writes()
"""

# 4. CACHE-ASIDE (Lazy Loading)
# Pattern: Application manages cache; fetch from source if miss
# Pros: Flexible, works with any source
# Cons: Stale data possible, cache miss penalty
# Use case: Most common pattern
PATTERN_4_CACHE_ASIDE = """
async def cache_aside_read(key: str):
    cached = await cache.get(key)
    if cached:
        return cached

    # Fetch from source
    data = await source.fetch(key)
    if data:
        await cache.set(key, data)
    return data
"""

# 5. STALE-WHILE-REVALIDATE
# Pattern: Serve stale cache while fetching fresh data in background
# Pros: Fast response, fresh data eventually
# Cons: Complexity, temporary inconsistency
# Use case: Search results, less critical data
PATTERN_5_STALE_WHILE_REVALIDATE = """
async def stale_while_revalidate(query: str):
    # Serves stale cache immediately, revalidates in background
    return await cache.get(
        key=f"search:{query}",
        fetch_fn=lambda: search_service.search(query)
    )
"""

# 6. CACHE STAMPEDE PREVENTION
# Pattern: Lock-based or probabilistic prevention of thundering herd
# Pros: Prevents backend overload on cache expiry
# Cons: Complexity
# Use case: Popular queries with large result sets
PATTERN_6_CACHE_STAMPEDE = """
async def prevent_stampede(query: str):
    lock_key = f"lock:{query}"
    lock = await cache.redis.set(lock_key, "1", ex=10, nx=True)

    if lock:
        # Only first request fetches
        data = await search_service.search(query)
        await cache.set(f"search:{query}", data)
    else:
        # Others wait for cache
        await asyncio.sleep(0.5)
        data = await cache.get(f"search:{query}")

    return data
"""

# 7. PROBABILISTIC EARLY EXPIRATION
# Pattern: Refresh cache before expiry with small probability
# Pros: Prevents cache stampede elegantly
# Cons: Slight cache inconsistency
# Use case: Popular items
PATTERN_7_PROBABILISTIC_REFRESH = """
import random

async def probabilistic_refresh(key: str, fetch_fn):
    cached = await cache.get(key)
    if cached and random.random() < 0.05:  # 5% chance
        asyncio.create_task(fetch_fn())  # Refresh in background
    return cached
"""

# 8. TTL-BASED INVALIDATION
# Pattern: Automatic expiry by time-to-live
# Pros: Simple, automatic
# Cons: Stale data until TTL, wasted space if key never accessed
# Use case: Time-sensitive data (search results, session data)
PATTERN_8_TTL_INVALIDATION = """
# Short TTL for frequently changing data
await cache.set(f"search:{query}", results, ttl=300)  # 5 minutes

# Long TTL for stable data
await cache.set(f"metadata:{doc_id}", metadata, ttl=86400)  # 1 day
"""

# 9. EVENT-BASED INVALIDATION
# Pattern: Explicit invalidation on source change events
# Pros: Always consistent with source
# Cons: Requires event infrastructure
# Use case: Strongly consistent data
PATTERN_9_EVENT_BASED = """
# Subscribe to events
cache.register_invalidation_handler(
    key_pattern="search:*",
    handler=async def on_document_update(key):
        await cache.delete(key)
)

# Trigger on source update
await document_updated_event.emit({"doc_id": "123"})
"""

# 10. EXPLICIT PURGE
# Pattern: Admin-triggered cache purge
# Pros: Control, useful for manual fixes
# Cons: Manual process
# Use case: Testing, troubleshooting, maintenance
PATTERN_10_EXPLICIT_PURGE = """
# Purge all search caches
await cache.invalidate_by_pattern("search:*")

# Purge specific owner
await cache.invalidate_by_pattern("search:owner:platform-eng:*")

# Purge all (nuclear option)
await cache.redis.flushdb()
"""

# 11. LRU EVICTION
# Pattern: Remove least-recently-used items when memory full
# Pros: Automatic memory management
# Cons: May evict valuable items
# Use case: Memory-constrained systems
PATTERN_11_LRU_EVICTION = """
# Redis configured with LRU policy
# redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru

# Tracks access time automatically
# Most-used items stay in cache
"""

# 12. BATCH GET
# Pattern: Fetch multiple cache entries at once
# Pros: Efficient, reduces latency
# Cons: Must handle partial hits
# Use case: Bulk operations
PATTERN_12_BATCH_GET = """
results = await cache.get_batch(
    keys=["doc:1", "doc:2", "doc:3"],
    fallback={"doc:1": default_value}
)

for doc_id, data in results.items():
    print(f"{doc_id}: {data}")
"""

# 13. BATCH SET
# Pattern: Set multiple cache entries at once
# Pros: Efficient, atomic
# Cons: Single failure aborts batch
# Use case: Bulk indexing, bulk updates
PATTERN_13_BATCH_SET = """
documents = {"doc:1": data1, "doc:2": data2, "doc:3": data3}
await cache.set_batch(documents, ttl=3600)
"""

# 14. CACHE PRELOADING / WARMING
# Pattern: Populate cache before serving requests
# Pros: Eliminates cold start misses
# Cons: Upfront cost, storage
# Use case: Application startup, hot data
PATTERN_14_CACHE_WARMING = """
async def warm_cache():
    popular_queries = await get_popular_queries()
    for query in popular_queries:
        results = await search_service.search(query)
        await cache.set(f"search:{query}", results, ttl=86400)
"""

# 15. FALLBACK RESPONSES
# Pattern: Return safe defaults on cache/source failure
# Pros: Resilient, better UX than error
# Cons: May hide problems
# Use case: User-facing APIs
PATTERN_15_FALLBACK = """
try:
    return await search_service.search(query)
except Exception:
    return cache.safe_default_response("search")  # Empty results
"""

# 16. DEGRADED RESPONSES
# Pattern: Return cached/partial data with status warning
# Pros: More data than fallback, shows status
# Cons: Complexity
# Use case: Non-critical services
PATTERN_16_DEGRADED = """
try:
    return await search_service.search(query)
except Exception as e:
    partial = await cache.get(f"search:{query}")
    return cache.degraded_response(
        {"query": query},
        cached_partial_data=partial,
        error_message=str(e)
    )
"""

# 17. CIRCUIT BREAKER WITH FALLBACK
# Pattern: Stop calling failing service, use fallback
# Pros: Prevents cascading failures
# Cons: Service down experience
# Use case: Dependency protection
PATTERN_17_CIRCUIT_BREAKER = """
fallback_fn = lambda: cache.get(f"search:{query}")
await circuit_breaker.call(
    search_service.search,
    query,
    fallback=fallback_fn
)
"""

# 18. RETRY WITH EXPONENTIAL BACKOFF
# Pattern: Retry failed operations with increasing delays
# Pros: Handles transient failures
# Cons: Can mask permanent failures
# Use case: Network operations
PATTERN_18_RETRY = """
await retry_policy.execute(
    search_service.search,
    query
)
"""

# 19. NAMESPACE ISOLATION
# Pattern: Prefix cache keys with namespace
# Pros: Prevents key collisions, logical organization
# Cons: Longer keys
# Use case: Multiple services, multi-tenancy
PATTERN_19_NAMESPACE = """
# Different namespaces for different services
cache_search = CacheManager(redis, namespace="search")
cache_metadata = CacheManager(redis, namespace="metadata")
cache_embeddings = CacheManager(redis, namespace="embeddings")
"""

# 20. KEY VERSIONING
# Pattern: Include version in cache key
# Pros: Seamless schema migrations
# Cons: Multiple keys for same data
# Use case: Schema changes
PATTERN_20_VERSIONING = """
# Include schema version in key
await cache.set(f"doc:v2:{doc_id}", data_v2)

# Different handlers for different versions
if version == 1:
    data = await parse_v1(cached)
elif version == 2:
    data = await parse_v2(cached)
"""

# 21. CACHE METRICS AND MONITORING
# Pattern: Track hit rate, latency, errors
# Pros: Visibility, optimization opportunities
# Cons: Overhead
# Use case: Performance tuning
PATTERN_21_METRICS = """
metrics = cache.get_metrics()
print(f"Hit ratio: {metrics.hit_ratio:.2%}")
print(f"Effective hit ratio: {metrics.effective_hit_ratio:.2%}")
print(f"Avg latency: {metrics.avg_latency_ms:.2f}ms")
"""

# 22. COMPRESSION
# Pattern: Compress large cache values
# Pros: Reduces memory usage
# Cons: CPU overhead
# Use case: Large objects
PATTERN_22_COMPRESSION = """
config = CacheConfig(
    enable_compression=True
)

# Automatically compresses large values
"""

# 23. TIME-BASED EXPIRATION WINDOWS
# Pattern: Different TTLs based on time of day
# Pros: Optimized for traffic patterns
# Cons: Complexity
# Use case: Peak hour optimization
PATTERN_23_TIME_WINDOWS = """
now = datetime.utcnow().hour

if 9 <= now <= 17:  # Business hours
    ttl = 300  # 5 minutes (higher traffic)
else:
    ttl = 3600  # 1 hour (lower traffic)

await cache.set(key, value, ttl=ttl)
"""

# 24. SMART TTL BASED ON POPULARITY
# Pattern: Popular items cached longer
# Pros: Better hit rate for popular items
# Cons: Need popularity tracking
# Use case: Content distribution
PATTERN_24_POPULARITY_TTL = """
popularity_score = await get_popularity(item)

# Popular items: longer TTL
ttl = min(3600, 300 + (popularity_score * 100))
await cache.set(f"item:{item_id}", data, ttl=ttl)
"""

# 25. CONSISTENT HASHING FOR DISTRIBUTION
# Pattern: Distribute cache across multiple nodes
# Pros: Horizontal scaling, failover
# Cons: Complexity, rebalancing
# Use case: Large-scale systems
PATTERN_25_CONSISTENT_HASH = """
# Use Redis Cluster or Consistent Hashing library
# Routes keys to specific nodes
# Handles node failures gracefully
"""

# 26. LAZY LOADING WITH THREADS/TASKS
# Pattern: Load cache asynchronously without blocking
# Pros: Non-blocking, better latency
# Cons: Race conditions possible
# Use case: Large datasets
PATTERN_26_LAZY_LOADING = """
async def lazy_load(key):
    if key not in loaded:
        asyncio.create_task(load_from_source(key))
    return await loaded[key]
"""

# 27. NEGATIVE CACHING
# Pattern: Cache absence of data
# Pros: Prevents repeated misses
# Cons: Must invalidate on data creation
# Use case: Non-existent items
PATTERN_27_NEGATIVE_CACHE = """
try:
    doc = await source.fetch(doc_id)
except NotFoundError:
    # Cache the absence with short TTL
    await cache.set(f"not_found:{doc_id}", None, ttl=300)
    raise
"""

# 28. CACHE WARMING ON MISS
# Pattern: Proactively load related data on cache miss
# Pros: Reduces future misses
# Cons: Overhead
# Use case: Recommendation engines
PATTERN_28_WARM_ON_MISS = """
async def smart_fetch(doc_id):
    doc = await source.fetch(doc_id)

    # Also warm related documents
    for related_id in doc.get("related", []):
        asyncio.create_task(
            cache.set(f"doc:{related_id}", source.fetch(related_id))
        )

    return doc
"""

# 29. RANGE CACHING
# Pattern: Cache data ranges for pagination
# Pros: Efficient pagination
# Cons: Complex invalidation
# Use case: Paginated results
PATTERN_29_RANGE_CACHING = """
# Cache page ranges instead of individual items
results = await source.fetch_range(start=0, limit=20)
await cache.set(f"results:page:1", results, ttl=300)
"""

# 30. WRITE-COALESCING
# Pattern: Combine multiple writes into single operation
# Pros: Reduces contention
# Cons: Complexity
# Use case: High-frequency updates
PATTERN_30_WRITE_COALESCING = """
pending_writes = {}

async def coalesce_write(key, value):
    pending_writes[key] = value

    # Batch writes every 100ms
    await asyncio.sleep(0.1)
    await cache.set_batch(pending_writes)
"""

# 31. CACHE COHERENCE
# Pattern: Keep distributed caches synchronized
# Pros: Consistent view across services
# Cons: Overhead, complexity
# Use case: Multi-service systems
PATTERN_31_COHERENCE = """
# Use pub/sub to invalidate across services
await redis.publish("cache:invalidate", key)

# Subscribe in other services
@redis.subscribe("cache:invalidate")
async def on_invalidate(message):
    await cache.delete(message)
"""

# 32. BLOOM FILTERS FOR CACHE MISSES
# Pattern: Use Bloom filter to avoid unnecessary cache checks
# Pros: Reduces cache traffic for non-existent items
# Cons: False positives
# Use case: Large datasets
PATTERN_32_BLOOM_FILTER = """
# Check Bloom filter before cache lookup
if key in bloom_filter:
    cached = await cache.get(key)
else:
    # Definitely not in cache
    cached = None
"""

# 33. CACHE SHARDING BY KEY PATTERN
# Pattern: Use different cache instances for different key patterns
# Pros: Independent tuning, failure isolation
# Cons: Complexity
# Use case: Large systems
PATTERN_33_CACHE_SHARDING = """
cache_search = CacheManager(redis_1, namespace="search")
cache_metadata = CacheManager(redis_2, namespace="metadata")
cache_embeddings = CacheManager(redis_3, namespace="embeddings")
"""

# 34. REQUEST-LEVEL CACHING (Memoization)
# Pattern: Cache within single request
# Pros: Eliminates duplicate work in request
# Cons: Limited scope
# Use case: Deeply nested queries
PATTERN_34_REQUEST_CACHE = """
request_cache = {}

async def memoized_fetch(doc_id):
    if doc_id in request_cache:
        return request_cache[doc_id]

    data = await source.fetch(doc_id)
    request_cache[doc_id] = data
    return data
"""

# 35. SMART SERIALIZATION
# Pattern: Optimize serialization format for speed/size
# Pros: Better performance, smaller storage
# Cons: Compatibility issues on format change
# Use case: Performance-critical paths
PATTERN_35_SERIALIZATION = """
# Use MessagePack or Protocol Buffers for better compression
# Binary formats faster than JSON

await cache.set(f"doc:{doc_id}", data, compression=True)
"""

# 36. CACHE VERSIONING AND MIGRATION
# Pattern: Handle schema changes without invalidating all cache
# Pros: Seamless upgrades
# Cons: Complexity
# Use case: Evolving systems
PATTERN_36_SCHEMA_MIGRATION = """
@cache_version(version=2)
async def get_document(doc_id):
    v1_data = await cache.get(f"doc:v1:{doc_id}")
    if v1_data:
        return migrate_v1_to_v2(v1_data)

    return await source.fetch(doc_id)
"""

# 37. CACHE MONITORING DASHBOARD
# Pattern: Real-time cache metrics visualization
# Pros: Visibility, alerting
# Cons: Overhead
# Use case: Production systems
PATTERN_37_MONITORING = """
# Export metrics to Prometheus
prometheus_metrics = {
    "cache_hits_total": metrics.hits,
    "cache_misses_total": metrics.misses,
    "cache_evictions_total": metrics.evictions,
    "cache_hit_ratio": metrics.hit_ratio,
}
"""

# 38. ADAPTIVE TTL
# Pattern: Adjust TTL based on access patterns
# Pros: Optimal memory usage
# Cons: Complexity, overhead
# Use case: Adaptive systems
PATTERN_38_ADAPTIVE_TTL = """
access_count = await get_access_count(key)

# More accessed = longer cache
ttl = min(3600, 300 + (access_count * 10))
await cache.set(key, value, ttl=ttl)
"""

# 39. MULTI-LEVEL CACHING
# Pattern: L1 (in-process) + L2 (Redis) + L3 (persistent) caching
# Pros: Extreme performance
# Cons: Complex coherence
# Use case: Latency-critical systems
PATTERN_39_MULTI_LEVEL = """
# L1: In-process (fastest, smallest)
l1_cache = {}

# L2: Redis (medium speed, medium size)
l2_cache = CacheManager(redis)

# L3: Database (slow, unlimited size)
# Source of truth

async def smart_get(key):
    if key in l1_cache:  # L1 hit
        return l1_cache[key]

    data = await l2_cache.get(key)  # L2 hit
    l1_cache[key] = data  # Populate L1
    return data
"""

# 40. CACHE PREEMPTION
# Pattern: Predict and cache items before needed
# Pros: Eliminates user-facing misses
# Cons: Inaccurate predictions = wasted space
# Use case: Personalization engines
PATTERN_40_PREEMPTION = """
async def predict_and_cache(user_id):
    # ML model predicts next items user wants
    next_items = await ml_predictor.predict(user_id)

    for item_id in next_items:
        asyncio.create_task(
            cache.set(f"user:{user_id}:item:{item_id}", fetch_item(item_id))
        )
"""

# ============================================================================
# SUMMARY TABLE
# ============================================================================

PATTERNS_TABLE = """
┌────┬──────────────────────────────────┬─────────────┬──────────────┬──────────────────────────────┐
│ #  │ Pattern Name                     │ Consistency │ Speed        │ Best For                     │
├────┼──────────────────────────────────┼─────────────┼──────────────┼──────────────────────────────┤
│  1 │ Read-Through                     │ High        │ Medium       │ Frequently accessed data     │
│  2 │ Write-Through                    │ Very High   │ Low          │ Critical consistent data     │
│  3 │ Write-Behind                     │ Low (EC)    │ Very High    │ Non-critical updates         │
│  4 │ Cache-Aside                      │ Medium      │ High         │ General purpose              │
│  5 │ Stale-While-Revalidate          │ Low         │ Very High    │ Search results               │
│  6 │ Cache Stampede Prevention         │ Medium      │ High         │ Popular items                │
│  7 │ Probabilistic Refresh             │ Medium      │ Very High    │ Popular items                │
│  8 │ TTL Invalidation                 │ Low         │ Very High    │ Time-sensitive data          │
│  9 │ Event-Based Invalidation          │ Very High   │ High         │ Strongly consistent data     │
│ 10 │ Explicit Purge                    │ Manual      │ High         │ Testing, maintenance         │
│ 11 │ LRU Eviction                      │ Automatic   │ Very High    │ Memory-constrained systems   │
│ 12 │ Batch Get                         │ Medium      │ Very High    │ Bulk operations              │
│ 13 │ Batch Set                         │ Medium      │ Very High    │ Bulk indexing                │
│ 14 │ Cache Warming                     │ High        │ N/A          │ Application startup          │
│ 15 │ Fallback Responses                │ Low         │ Very High    │ User-facing APIs             │
│ 16 │ Degraded Responses                │ Low         │ Very High    │ Non-critical services        │
│ 17 │ Circuit Breaker                   │ High        │ Very High    │ Dependency protection        │
│ 18 │ Retry with Backoff                │ Medium      │ High         │ Network operations           │
│ 19 │ Namespace Isolation               │ High        │ Very High    │ Multiple services            │
│ 20 │ Key Versioning                    │ High        │ High         │ Schema changes               │
│ 21 │ Cache Metrics                     │ N/A         │ High         │ Performance tuning           │
│ 22 │ Compression                       │ Transparent │ Medium       │ Large objects                │
│ 23 │ Time-Based Windows                │ Medium      │ Very High    │ Peak hour optimization       │
│ 24 │ Smart TTL (Popularity)            │ Medium      │ Very High    │ Content distribution         │
│ 25 │ Consistent Hashing                │ High        │ Very High    │ Large-scale systems          │
│ 26 │ Lazy Loading                      │ Medium      │ Very High    │ Large datasets               │
│ 27 │ Negative Caching                  │ Medium      │ Very High    │ Non-existent items           │
│ 28 │ Warming on Miss                   │ Medium      │ Very High    │ Recommendation engines       │
│ 29 │ Range Caching                     │ Medium      │ Very High    │ Paginated results            │
│ 30 │ Write-Coalescing                  │ Medium      │ Very High    │ High-frequency updates       │
│ 31 │ Cache Coherence                   │ High        │ High         │ Multi-service systems        │
│ 32 │ Bloom Filters                     │ High        │ Very High    │ Large datasets               │
│ 33 │ Cache Sharding                    │ High        │ Very High    │ Large systems                │
│ 34 │ Request-Level Caching             │ Very High   │ Very High    │ Deeply nested queries        │
│ 35 │ Smart Serialization               │ High        │ Very High    │ Performance-critical paths   │
│ 36 │ Schema Migration                  │ High        │ High         │ Evolving systems             │
│ 37 │ Monitoring Dashboard              │ N/A         │ High         │ Production systems           │
│ 38 │ Adaptive TTL                      │ Medium      │ Very High    │ Adaptive systems             │
│ 39 │ Multi-Level Caching               │ Medium      │ Extreme      │ Latency-critical systems     │
│ 40 │ Cache Preemption                  │ Low         │ Very High    │ Personalization engines      │
└────┴──────────────────────────────────┴─────────────┴──────────────┴──────────────────────────────┘
"""

# ============================================================================
# PERFORMANCE TARGETS
# ============================================================================

PERFORMANCE_TARGETS = {
    "cache_hit_ratio": 0.95,  # 95%+ hit rate target
    "cache_latency_ms": 2.0,  # <2ms average latency
    "fallback_hit_ratio": 0.98,  # 98%+ availability with fallback
    "p99_latency_ms": 5.0,  # <5ms P99 latency
    "error_rate": 0.0001,  # <0.01% error rate
}

# ============================================================================
# IMPLEMENTATION CHECKLIST
# ============================================================================

IMPLEMENTATION_CHECKLIST = """
CORE IMPLEMENTATION:
☑ Cache manager with read-through support
☑ Write-through and write-behind strategies
☑ TTL-based invalidation
☑ Event-based invalidation
☑ LRU eviction
☑ Stale-while-revalidate pattern
☑ Batch operations (get/set)
☑ Fallback responses

RESILIENCE:
☑ Circuit breaker pattern
☑ Retry with exponential backoff
☑ Degraded response mode
☑ Health checks
☑ Metrics collection

PATTERNS:
☑ Cache warming
☑ Negative caching
☑ Request-level caching
☑ Multi-level caching
☑ Cache sharding

MONITORING:
☑ Hit ratio tracking
☑ Latency metrics
☑ Error tracking
☑ Cache size monitoring
☑ Dashboard integration

OPTIMIZATION:
☑ Compression for large values
☑ Smart serialization
☑ Adaptive TTL
☑ Batch write coalescing
☑ Cache stampede prevention
"""
