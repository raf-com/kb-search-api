"""
Hybrid search service combining Meilisearch (keyword) and Qdrant (semantic).

Implements Reciprocal Rank Fusion for combining results from multiple sources.
"""

import hashlib
import json
import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

import meilisearch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from redis.asyncio import Redis

from config import get_settings
from models import SearchFilters, SearchResultItem
from search_utils import SearchUtils

logger = logging.getLogger(__name__)


class SearchService:
    """Service for hybrid full-text and semantic search."""

    def __init__(self, redis_client: Redis):
        """
        Initialize search service.

        Args:
            redis_client: Redis client for caching
        """
        self.settings = get_settings()
        self.redis = redis_client

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
        Perform hybrid search across full-text and semantic indexes.

        Args:
            query: Search query string
            filters: Optional search filters
            limit: Maximum results to return
            offset: Result offset for pagination
            semantic_weight: Weight for semantic search (0=keyword only, 1=semantic only)
            highlight: Include highlighted excerpts

        Returns:
            dict: Search results with metadata

        Example:
            >>> results = await search_service.search(
            ...     "postgresql replication",
            ...     filters=SearchFilters(owner="platform-eng"),
            ...     limit=10
            ... )
            >>> print(results['total_count'])
            42
        """
        start_time = time.time()

        # Check cache first
        cache_key = self._get_cache_key(query, filters, limit, offset, semantic_weight)
        cached_results = await self.redis.get(cache_key)
        if cached_results:
            logger.debug(f"Cache hit for query: {query}")
            return json.loads(cached_results)

        results = []

        try:
            # For hybrid search pagination, we fetch (limit + offset) from each source
            # and then slice the final combined results.
            fetch_limit = limit + offset

            if semantic_weight < 1.0:
                # Full-text search (Meilisearch)
                # Pass offset=0 to fetch from the top for better fusion
                keyword_results = await self._meilisearch_search(
                    query, filters, fetch_limit, 0, highlight
                )
                results.extend(keyword_results)

            if semantic_weight > 0.0:
                # Semantic search (Qdrant)
                semantic_results = await self._qdrant_search(query, filters, fetch_limit)
                results.extend(semantic_results)

            # Combine and rank results using Reciprocal Rank Fusion
            combined_results = SearchUtils.reciprocal_rank_fusion(
                results, semantic_weight, limit, offset
            )

            # Build response
            response = {
                "query": query,
                "results": combined_results,
                "total_count": len(combined_results),
                "limit": limit,
                "offset": offset,
                "execution_time_ms": round((time.time() - start_time) * 1000, 2),
            }

            # Cache results
            await self.redis.setex(
                cache_key,
                self.settings.redis_cache_ttl,
                json.dumps(response),  # JSON serialization
            )

            return response

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise

    async def _meilisearch_search(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
        offset: int,
        highlight: bool,
    ) -> List[Dict[str, Any]]:
        """
        Search using Meilisearch (full-text).

        Args:
            query: Search query
            filters: Search filters
            limit: Result limit
            offset: Result offset
            highlight: Include highlights

        Returns:
            list: Search results from Meilisearch
        """
        try:
            # Build filter expression
            filter_expr = None
            if filters:
                filter_expr = self._build_meilisearch_filter(filters)

            # Build search options dict (Meilisearch client expects opt_params dict)
            search_options = {
                "limit": limit,
                "offset": offset,
            }

            if filter_expr:
                search_options["filter"] = filter_expr

            # Add highlight
            if highlight:
                search_options["attributesToHighlight"] = ["title", "content"]

            logger.debug(
                f"Meilisearch query: query={query}, index={self.settings.meilisearch_index}, options={search_options}"
            )
            response = self.meilisearch.index(self.settings.meilisearch_index).search(
                query, opt_params=search_options
            )
            logger.debug(f"Meilisearch response: {response}")

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
                    "relevance_score": 1.0 / (1 + i),  # Estimate relevance from rank
                    "search_type": "keyword",
                    "excerpt": hit.get("content", "")[:200],
                    "highlighted_excerpt": hit.get("_formatted", {}).get("content"),
                    "topics": hit.get("topics", []),
                }
                results.append(result)

            logger.debug(f"Meilisearch returned {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Meilisearch search failed: {e}", exc_info=True)
            return []

    async def _qdrant_search(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Search using Qdrant (semantic).

        Args:
            query: Search query
            filters: Search filters
            limit: Result limit

        Returns:
            list: Semantic search results from Qdrant
        """
        try:
            from embedding_service import EmbeddingService

            embedding_service = EmbeddingService(self.redis)
            query_embedding = await embedding_service.embed_text(query)

            # Build filter
            qdrant_filter = None
            if filters:
                qdrant_filter = self._build_qdrant_filter(filters)

            # Search in Qdrant
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

            logger.debug(f"Qdrant returned {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _build_meilisearch_filter(self, filters: SearchFilters) -> Optional[str]:
        """
        Build Meilisearch filter expression (string format).

        Args:
            filters: Search filters

        Returns:
            str: Meilisearch filter expression string

        Example:
            >>> filters = SearchFilters(owner="platform-eng", classification="internal")
            >>> filter_expr = service._build_meilisearch_filter(filters)
            >>> print(filter_expr)
            owner = 'platform-eng' AND classification = 'internal'
        """
        conditions = []

        if filters.owner:
            conditions.append(f"owner = '{filters.owner}'")
        if filters.classification:
            conditions.append(f"classification = '{filters.classification}'")
        if filters.status:
            conditions.append(f"status = '{filters.status}'")
        if filters.topics:
            for topic in filters.topics:
                conditions.append(f"topics = '{topic}'")
        if filters.created_after:
            conditions.append(
                f"created_date >= {int(filters.created_after.timestamp())}"
            )
        if filters.created_before:
            conditions.append(
                f"created_date <= {int(filters.created_before.timestamp())}"
            )

        return " AND ".join(conditions) if conditions else None

    def _build_qdrant_filter(self, filters: SearchFilters) -> Optional[Filter]:
        """
        Build Qdrant filter expression.

        Args:
            filters: Search filters

        Returns:
            Filter: Qdrant filter object

        Example:
            >>> filters = SearchFilters(owner="platform-eng")
            >>> filter_obj = service._build_qdrant_filter(filters)
        """
        must_conditions = []

        if filters.owner:
            must_conditions.append(
                FieldCondition(key="owner", match=MatchValue(value=filters.owner))
            )
        if filters.classification:
            must_conditions.append(
                FieldCondition(
                    key="classification", match=MatchValue(value=filters.classification)
                )
            )
        if filters.status:
            must_conditions.append(
                FieldCondition(key="status", match=MatchValue(value=filters.status))
            )

        return Filter(must=must_conditions) if must_conditions else None

    def _get_cache_key(
        self,
        query: str,
        filters: Optional[SearchFilters],
        limit: int,
        offset: int,
        semantic_weight: float,
    ) -> str:
        """
        Generate cache key for search query.

        Args:
            query: Search query
            filters: Search filters
            limit: Result limit
            offset: Result offset
            semantic_weight: Semantic weight

        Returns:
            str: Cache key

        Example:
            >>> key = service._get_cache_key("test", None, 10, 0, 0.5)
            >>> print(key)
            search:7d8f7s9f8a7s9f87as9f78a9s7f9a8s
        """
        cache_params = f"{query}:{filters}:{limit}:{offset}:{semantic_weight}"
        hash_val = hashlib.md5(cache_params.encode()).hexdigest()
        return f"search:{hash_val}"

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of search services.

        Returns:
            dict: Health status

        Example:
            >>> health = await search_service.health_check()
            >>> print(health['meilisearch'])
            {'status': 'ok', 'latency_ms': 12}
        """
        health = {}

        # Meilisearch
        try:
            start = time.time()
            self.meilisearch.health()
            latency = round((time.time() - start) * 1000)
            health["meilisearch"] = {
                "status": "ok",
                "latency_ms": latency,
            }
        except Exception as e:
            logger.error(f"Meilisearch health check failed: {e}")
            health["meilisearch"] = {"status": "error", "error": str(e)}

        # Qdrant
        try:
            start = time.time()
            # Check health by trying to list collections
            collections = self.qdrant.get_collections()
            latency = round((time.time() - start) * 1000)
            collection_count = (
                len(collections.collections)
                if hasattr(collections, "collections")
                else len(collections) if isinstance(collections, list) else 0
            )
            health["qdrant"] = {
                "status": "ok",
                "latency_ms": latency,
                "collections": collection_count,
            }
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            health["qdrant"] = {"status": "error", "error": str(e)}

        return health
