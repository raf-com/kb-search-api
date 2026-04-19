"""
Enhanced search service with advanced caching, fallback, and resilience patterns.

Integrates:
- Multiple cache strategies (read-through, write-through, write-behind, cache-aside)
- Stale-while-revalidate for fast responses
- Circuit breaker for fault tolerance
- Fallback responses and degraded mode
- Metrics and monitoring
"""

import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

import meilisearch
from qdrant_client import QdrantClient
from redis.asyncio import Redis

from config import get_settings
from models import SearchFilters
from cache_manager import (
    CacheManager,
    CacheConfig,
    CacheStrategy,
    FallbackResponseBuilder,
)
from circuit_breaker import CircuitBreakerConfig, CircuitBreakerPool

logger = logging.getLogger(__name__)


class EnhancedSearchService:
    """
    Enhanced search service with caching and resilience.

    Features:
    - Read-through cache for all search queries
    - Stale-while-revalidate for faster responses
    - Circuit breaker for backend failure protection
    - Graceful fallback and degraded responses
    - Comprehensive metrics and monitoring
    """

    def __init__(self, redis_client: Redis):
        """
        Initialize enhanced search service.

        Args:
            redis_client: Redis client for caching
        """
        self.settings = get_settings()
        self.redis = redis_client

        # Initialize cache manager with stale-while-revalidate
        cache_config = CacheConfig(
            ttl=self.settings.redis_cache_ttl,
            strategy=CacheStrategy.READ_THROUGH,
            stale_while_revalidate=60,  # Serve stale for 60 seconds
            enable_fallback=True,
        )
        self.cache = CacheManager(redis_client, cache_config, namespace="search")

        # Meilisearch client
        self.meilisearch = meilisearch.Client(
            url=self.settings.meilisearch_url,
            api_key=self.settings.meilisearch_key,
        )

        # Qdrant client
        self.qdrant = QdrantClient(
            url=self.settings.qdrant_url,
            api_key=(
                self.settings.qdrant_api_key if self.settings.qdrant_api_key else None
            ),
            timeout=self.settings.qdrant_timeout,
        )

        # Circuit breakers for each backend
        cb_config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout=60,
        )
        self.cb_pool = CircuitBreakerPool()
        self._meilisearch_breaker = self.cb_pool.get_or_create("meilisearch", cb_config)
        self._qdrant_breaker = self.cb_pool.get_or_create("qdrant", cb_config)

        logger.info("Enhanced Search Service initialized")

    async def search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        limit: int = 10,
        offset: int = 0,
        semantic_weight: float = 0.5,
        highlight: bool = True,
    ) -> Dict[str, Any]:
        """
        Perform hybrid search with caching and fallback.

        Features:
        - Cache hit: returns in <2ms
        - Cache miss: fetches from backends with circuit breaker protection
        - Backend error: returns cached/fallback response
        - Stale cache: serves immediately, revalidates in background

        Args:
            query: Search query string
            filters: Optional search filters
            limit: Maximum results to return
            offset: Result offset for pagination
            semantic_weight: Weight for semantic search (0-1)
            highlight: Include highlighted excerpts

        Returns:
            Search results with metadata

        Example:
            >>> service = EnhancedSearchService(redis)
            >>> results = await service.search(
            ...     "postgresql replication",
            ...     filters=SearchFilters(owner="platform-eng"),
            ...     limit=10
            ... )
            >>> print(f"Got {results['total_count']} results in {results['execution_time_ms']}ms")
        """
        start_time = time.time()
        cache_key = self._get_cache_key(query, filters, limit, offset, semantic_weight)

        # Attempt to fetch from cache (read-through)
        async def fetch_fresh_results():
            """Fetch fresh results from backends."""
            return await self._fetch_from_backends(
                query, filters, limit, offset, semantic_weight, highlight
            )

        try:
            # Try cache with stale-while-revalidate
            results = await self.cache.get(
                key=cache_key,
                fallback=FallbackResponseBuilder.safe_default_response("search"),
                fetch_fn=fetch_fresh_results,
            )

            if results and "status" not in results:
                # Valid results
                results["execution_time_ms"] = round(
                    (time.time() - start_time) * 1000, 2
                )
                results["cache_status"] = "hit"
                return results

            # Fallback was used
            results["cache_status"] = "miss_fallback"
            results["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
            return results

        except Exception as e:
            logger.error(f"Search error: {e}")
            # Return safe default
            return FallbackResponseBuilder.safe_default_response("search")

    async def _fetch_from_backends(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
        offset: int,
        semantic_weight: float,
        highlight: bool,
    ) -> Dict[str, Any]:
        """
        Fetch results from backends with circuit breaker protection.

        Args:
            query: Search query
            filters: Filters
            limit: Result limit
            offset: Result offset
            semantic_weight: Semantic weight
            highlight: Include highlights

        Returns:
            Combined search results
        """
        results = []
        start_time = time.time()

        try:
            # Keyword search with circuit breaker
            if semantic_weight < 1.0:
                keyword_results = await self._cb_pool.call(
                    "meilisearch",
                    self._meilisearch_search,
                    query,
                    filters,
                    limit,
                    offset,
                    highlight,
                    fallback=self._fallback_keyword_search,
                )
                if keyword_results:
                    results.extend(keyword_results)

            # Semantic search with circuit breaker
            if semantic_weight > 0.0:
                semantic_results = await self._cb_pool.call(
                    "qdrant",
                    self._qdrant_search,
                    query,
                    filters,
                    limit,
                    fallback=self._fallback_semantic_search,
                )
                if semantic_results:
                    results.extend(semantic_results)

            # Combine and rank
            combined = self._reciprocal_rank_fusion(results, semantic_weight, limit)

            return {
                "query": query,
                "results": combined,
                "total_count": len(combined),
                "limit": limit,
                "offset": offset,
                "execution_time_ms": round((time.time() - start_time) * 1000, 2),
            }

        except Exception as e:
            logger.error(f"Backend fetch error: {e}")
            return FallbackResponseBuilder.safe_default_response("search")

    async def _meilisearch_search(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
        offset: int,
        highlight: bool,
    ) -> List[Dict[str, Any]]:
        """Search using Meilisearch with error handling."""
        try:
            search_params = {
                "q": query,
                "limit": limit,
                "offset": offset,
            }

            if filters:
                filter_expr = self._build_meilisearch_filter(filters)
                if filter_expr:
                    search_params["filter"] = filter_expr

            if highlight:
                search_params["attributesToHighlight"] = ["title", "content"]

            response = self.meilisearch.index(self.settings.meilisearch_index).search(
                **search_params
            )

            results = []
            for i, hit in enumerate(response.get("hits", [])):
                result = {
                    "doc_id": hit.get("id"),
                    "rank": offset + i + 1,
                    "title": hit.get("title"),
                    "source": hit.get("source"),
                    "owner": hit.get("owner"),
                    "classification": hit.get("classification"),
                    "created_date": datetime.fromisoformat(
                        hit.get("created_date", datetime.now().isoformat())
                    ),
                    "relevance_score": 1.0 / (1 + i),
                    "search_type": "keyword",
                    "excerpt": hit.get("content", "")[:200],
                    "highlighted_excerpt": hit.get("_formatted", {}).get("content"),
                    "topics": hit.get("topics", []),
                }
                results.append(result)

            logger.debug(f"Meilisearch returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Meilisearch search failed: {e}")
            raise

    async def _qdrant_search(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search using Qdrant with error handling."""
        try:
            from embedding_service import EmbeddingService

            embedding_service = EmbeddingService(self.redis)
            query_embedding = await embedding_service.embed_text(query)

            qdrant_filter = None
            if filters:
                qdrant_filter = self._build_qdrant_filter(filters)

            search_results = self.qdrant.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=query_embedding,
                query_filter=qdrant_filter,
                limit=limit,
                score_threshold=self.settings.semantic_threshold,
            )

            results = []
            for i, point in enumerate(search_results):
                result = {
                    "doc_id": point.payload.get("doc_id"),
                    "rank": i + 1,
                    "title": point.payload.get("title"),
                    "source": point.payload.get("source", ""),
                    "owner": point.payload.get("owner"),
                    "classification": point.payload.get("classification"),
                    "created_date": datetime.fromtimestamp(
                        point.payload.get("created_date", 0)
                    ),
                    "relevance_score": point.score,
                    "search_type": "semantic",
                    "excerpt": point.payload.get("summary", "")[:200],
                    "highlighted_excerpt": None,
                    "topics": point.payload.get("topics", []),
                }
                results.append(result)

            logger.debug(f"Qdrant returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise

    async def _fallback_keyword_search(self) -> List[Dict[str, Any]]:
        """Fallback when Meilisearch fails."""
        logger.warning("Using Meilisearch fallback")
        return []

    async def _fallback_semantic_search(self) -> List[Dict[str, Any]]:
        """Fallback when Qdrant fails."""
        logger.warning("Using Qdrant fallback")
        return []

    def _build_meilisearch_filter(self, filters: SearchFilters) -> Optional[List]:
        """Build Meilisearch filter expression."""
        conditions = []

        if filters.owner:
            conditions.append(["owner", "=", filters.owner])
        if filters.classification:
            conditions.append(["classification", "=", filters.classification])
        if filters.status:
            conditions.append(["status", "=", filters.status])
        if filters.topics:
            for topic in filters.topics:
                conditions.append(["topics", "IN", [topic]])
        if filters.created_after:
            conditions.append(
                ["created_date", ">=", int(filters.created_after.timestamp())]
            )
        if filters.created_before:
            conditions.append(
                ["created_date", "<=", int(filters.created_before.timestamp())]
            )

        return conditions if conditions else None

    def _build_qdrant_filter(self, filters: SearchFilters) -> Optional[Any]:
        """Build Qdrant filter expression."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        must_conditions = []

        if filters.owner:
            must_conditions.append(
                FieldCondition(key="owner", match=MatchValue(value=filters.owner))
            )
        if filters.classification:
            must_conditions.append(
                FieldCondition(
                    key="classification",
                    match=MatchValue(value=filters.classification),
                )
            )
        if filters.status:
            must_conditions.append(
                FieldCondition(key="status", match=MatchValue(value=filters.status))
            )

        return Filter(must=must_conditions) if must_conditions else None

    def _reciprocal_rank_fusion(
        self,
        results: List[Dict[str, Any]],
        semantic_weight: float,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Combine results using Reciprocal Rank Fusion."""
        # Group by doc_id
        doc_scores = {}

        for result in results:
            doc_id = result["doc_id"]
            rank = result["rank"]
            is_semantic = result["search_type"] == "semantic"

            # RRF formula: 1 / (k + rank)
            k = 60
            rrf_score = 1.0 / (k + rank)

            # Apply semantic weight
            if is_semantic:
                rrf_score *= semantic_weight
            else:
                rrf_score *= 1.0 - semantic_weight

            if doc_id not in doc_scores:
                doc_scores[doc_id] = {"score": 0, "result": result}

            doc_scores[doc_id]["score"] += rrf_score

        # Sort by combined score
        sorted_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )

        # Return top limit results
        return [item[1]["result"] for item in sorted_docs[:limit]]

    def _get_cache_key(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
        offset: int,
        semantic_weight: float,
    ) -> str:
        """Generate cache key from search parameters."""
        parts = [query, str(limit), str(offset), f"{semantic_weight:.1f}"]

        if filters:
            if filters.owner:
                parts.append(f"owner:{filters.owner}")
            if filters.classification:
                parts.append(f"class:{filters.classification}")
            if filters.status:
                parts.append(f"status:{filters.status}")

        return ":".join(parts)

    def get_cache_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics."""
        metrics = self.cache.get_metrics()
        return {
            "hits": metrics.hits,
            "misses": metrics.misses,
            "hit_ratio": f"{metrics.hit_ratio:.2%}",
            "effective_hit_ratio": f"{metrics.effective_hit_ratio:.2%}",
            "avg_latency_ms": round(metrics.avg_latency_ms, 2),
            "fallback_hits": metrics.fallback_hits,
            "errors": metrics.errors,
        }

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return self.cb_pool.get_all_status()

    async def invalidate_cache(self, pattern: str = "*") -> int:
        """Invalidate cache entries by pattern."""
        return await self.cache.invalidate_by_pattern(pattern)
