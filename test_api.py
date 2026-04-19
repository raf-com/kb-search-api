"""
Comprehensive test suite for Knowledge Base Search API.

Tests cover:
- Search endpoints (keyword, semantic, hybrid)
- Metadata operations (CRUD, bulk updates)
- Embedding operations
- Health checks
- Error handling
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import app
from models import (
    SearchRequest,
    SearchFilters,
    MetadataUpdate,
    BulkMetadataUpdateRequest,
)
from search_service import SearchService
from metadata_service import MetadataService
from embedding_service import EmbeddingService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def mock_session():
    """Create mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
async def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.setex.return_value = True
    redis.ping.return_value = True
    return redis


@pytest.fixture
async def search_service(mock_redis):
    """Create search service with mocked Redis."""
    service = SearchService(mock_redis)
    # Mock external services
    service.meilisearch = AsyncMock()
    service.qdrant = AsyncMock()
    return service


@pytest.fixture
async def metadata_service(mock_session):
    """Create metadata service with mocked session."""
    return MetadataService(mock_session)


@pytest.fixture
async def embedding_service(mock_redis):
    """Create embedding service with mocked Redis."""
    return EmbeddingService(mock_redis)


@pytest.fixture
def sample_search_request():
    """Create sample search request."""
    return SearchRequest(
        query="postgresql replication",
        filters=SearchFilters(
            owner="platform-eng",
            classification="internal",
        ),
        limit=10,
        semantic_weight=0.5,
    )


@pytest.fixture
def sample_metadata_updates():
    """Create sample metadata updates."""
    return BulkMetadataUpdateRequest(
        updates=[
            MetadataUpdate(
                doc_id=uuid4(),
                changes={"owner": "new-team", "topics": ["database", "replication"]},
            ),
            MetadataUpdate(
                doc_id=uuid4(),
                changes={"status": "archived"},
            ),
        ]
    )


# ============================================================================
# Search Tests
# ============================================================================


@pytest.mark.asyncio
async def test_search_keyword_only(search_service):
    """Test keyword-only search (semantic_weight=0.0)."""
    query = "postgresql replication"

    # Mock Meilisearch response
    search_service.meilisearch.index.return_value.search.return_value = {
        "hits": [
            {
                "id": str(uuid4()),
                "title": "PostgreSQL Replication Best Practices",
                "content": "Guide to streaming replication...",
                "source": "/docs/postgres-replication.md",
                "owner": "platform-eng",
                "classification": "internal",
                "created_date": datetime.now().isoformat(),
                "topics": ["postgresql", "replication"],
                "_formatted": {"content": "Guide to streaming <em>replication</em>..."},
            }
        ],
        "totalHits": 1,
        "processingTimeMs": 12,
    }

    result = await search_service.search(
        query=query,
        semantic_weight=0.0,
        limit=10,
    )

    assert result["query"] == query
    assert len(result["results"]) == 1
    assert result["results"][0]["search_type"] == "keyword"
    assert result["results"][0]["title"] == "PostgreSQL Replication Best Practices"


@pytest.mark.asyncio
async def test_search_semantic_only(search_service, mock_redis):
    """Test semantic-only search (semantic_weight=1.0)."""
    query = "database failover"

    # Mock embedding service
    with patch("search_service.EmbeddingService") as mock_embedding_class:
        mock_embedding_service = AsyncMock()
        mock_embedding_class.return_value = mock_embedding_service
        mock_embedding_service.embed_text.return_value = [0.1] * 1536

        # Mock Qdrant response
        mock_point = MagicMock()
        mock_point.payload = {
            "doc_id": str(uuid4()),
            "title": "HA Architecture",
            "source": "/docs/ha-architecture.md",
            "owner": "platform-eng",
            "classification": "internal",
            "created_date": int(datetime.now().timestamp()),
            "topics": ["ha", "failover"],
            "summary": "High availability architecture guide",
        }
        mock_point.score = 0.87

        search_service.qdrant.search.return_value = [mock_point]

        result = await search_service.search(
            query=query,
            semantic_weight=1.0,
            limit=10,
        )

        assert result["query"] == query
        assert len(result["results"]) > 0
        # Verify semantic search was called
        assert mock_embedding_service.embed_text.called


@pytest.mark.asyncio
async def test_search_with_filters(search_service):
    """Test search with metadata filters."""
    query = "postgresql"
    filters = SearchFilters(
        owner="platform-eng",
        classification="internal",
        status="active",
    )

    # Mock Meilisearch with filter support
    search_service.meilisearch.index.return_value.search.return_value = {
        "hits": [
            {
                "id": str(uuid4()),
                "title": "PostgreSQL Guide",
                "content": "...",
                "source": "/docs/postgres.md",
                "owner": "platform-eng",
                "classification": "internal",
                "created_date": datetime.now().isoformat(),
                "topics": ["postgresql"],
            }
        ],
        "totalHits": 1,
    }

    result = await search_service.search(
        query=query,
        filters=filters,
        semantic_weight=0.0,
    )

    # Verify filter was applied
    assert search_service.meilisearch.index.called
    call_kwargs = search_service.meilisearch.index.return_value.search.call_args[1]
    assert "filter" in call_kwargs


@pytest.mark.asyncio
async def test_search_pagination(search_service):
    """Test search result pagination."""
    results_page1 = await search_service.search(
        query="test",
        limit=10,
        offset=0,
        semantic_weight=0.0,
    )

    results_page2 = await search_service.search(
        query="test",
        limit=10,
        offset=10,
        semantic_weight=0.0,
    )

    # Pages should have different offsets
    assert results_page1["offset"] == 0
    assert results_page2["offset"] == 10


@pytest.mark.asyncio
async def test_search_caching(search_service, mock_redis):
    """Test search result caching."""
    query = "cached query"

    # First call - cache miss
    mock_redis.get.return_value = None
    result1 = await search_service.search(query=query, semantic_weight=0.0)

    # Second call - cache hit
    cached_result = json.dumps(result1)
    mock_redis.get.return_value = cached_result
    result2 = await search_service.search(query=query, semantic_weight=0.0)

    # Verify cache was called
    assert mock_redis.get.called
    assert mock_redis.setex.called


@pytest.mark.asyncio
async def test_search_empty_query(search_service):
    """Test search with empty query."""
    with pytest.raises(ValueError):
        await search_service.search(query="", semantic_weight=0.5)


@pytest.mark.asyncio
async def test_reciprocal_rank_fusion(search_service):
    """Test RRF ranking algorithm."""
    results = [
        {
            "doc_id": uuid4(),
            "rank": 1,
            "title": "Doc 1",
            "source": "/doc1",
            "owner": "team",
            "classification": "internal",
            "created_date": datetime.now(),
            "relevance_score": 0.9,
            "search_type": "keyword",
            "excerpt": "...",
            "highlighted_excerpt": None,
            "topics": [],
        },
        {
            "doc_id": uuid4(),
            "rank": 2,
            "title": "Doc 2",
            "source": "/doc2",
            "owner": "team",
            "classification": "internal",
            "created_date": datetime.now(),
            "relevance_score": 0.8,
            "search_type": "semantic",
            "excerpt": "...",
            "highlighted_excerpt": None,
            "topics": [],
        },
    ]

    combined = search_service._reciprocal_rank_fusion(results, 0.5, 10)

    assert len(combined) == 2
    assert combined[0]["rank"] == 1
    assert combined[0]["search_type"] == "hybrid"


# ============================================================================
# Metadata Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_document(metadata_service, mock_session):
    """Test getting a document by ID."""
    doc_id = uuid4()

    # Mock database response
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.title = "Test Document"
    mock_doc.content = "Test content..."
    mock_doc.source = "/test.md"
    mock_doc.owner = "team"
    mock_doc.classification = "internal"
    mock_doc.status = "active"
    mock_doc.created_date = datetime.now()
    mock_doc.updated_date = datetime.now()
    mock_doc.created_by = "user1"
    mock_doc.updated_by = "user2"
    mock_doc.external_id = "alert_123"

    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_doc

    doc = await metadata_service.get_document(doc_id)

    assert doc is not None
    assert doc["title"] == "Test Document"
    assert doc["owner"] == "team"


@pytest.mark.asyncio
async def test_get_metadata_only(metadata_service, mock_session):
    """Test getting metadata without content."""
    doc_id = uuid4()

    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.title = "Test"
    mock_doc.source = "/test.md"
    mock_doc.owner = "team"
    mock_doc.classification = "internal"
    mock_doc.status = "active"
    mock_doc.created_date = datetime.now()
    mock_doc.updated_date = datetime.now()

    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_doc

    metadata = await metadata_service.get_metadata(doc_id)

    assert metadata is not None
    assert "title" in metadata
    assert "content" not in metadata


@pytest.mark.asyncio
async def test_update_metadata(metadata_service, mock_session):
    """Test updating document metadata."""
    doc_id = uuid4()

    mock_doc = MagicMock()
    mock_doc.id = doc_id

    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_doc

    updates = {"owner": "new-team", "status": "archived"}
    success = await metadata_service.update_metadata(doc_id, updates, actor="test_user")

    assert success is True
    assert mock_session.execute.called
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_bulk_update_metadata(metadata_service, sample_metadata_updates):
    """Test bulk metadata updates."""
    with patch.object(
        metadata_service,
        "update_metadata",
        return_value=True,
    ):
        updates_list = [
            {"doc_id": u.doc_id, "changes": u.changes}
            for u in sample_metadata_updates.updates
        ]

        result = await metadata_service.bulk_update_metadata(updates_list)

        assert result["total"] == 2
        assert result["updated"] == 2
        assert result["failed"] == 0


@pytest.mark.asyncio
async def test_update_nonexistent_document(metadata_service, mock_session):
    """Test updating a non-existent document."""
    doc_id = uuid4()

    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    success = await metadata_service.update_metadata(doc_id, {"owner": "team"})

    assert success is False


# ============================================================================
# Embedding Tests
# ============================================================================


@pytest.mark.asyncio
async def test_embed_text(embedding_service, mock_redis):
    """Test embedding generation."""
    with patch("embedding_service.litellm") as mock_litellm:
        text = "test document"
        mock_embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [{"embedding": mock_embedding}]

        embedding_service.litellm.aembedding = AsyncMock(return_value=mock_response)

        result = await embedding_service.embed_text(text)

        assert len(result) == 1536
        assert result[0] == 0.1


@pytest.mark.asyncio
async def test_embed_text_caching(embedding_service, mock_redis):
    """Test embedding caching."""
    text = "cached text"
    cached_embedding = [0.2] * 1536

    # First call - miss
    mock_redis.get.return_value = None
    with patch("embedding_service.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.data = [{"embedding": cached_embedding}]
        embedding_service.litellm.aembedding = AsyncMock(return_value=mock_response)

        result1 = await embedding_service.embed_text(text)

    # Second call - hit
    mock_redis.get.return_value = json.dumps(cached_embedding)
    result2 = await embedding_service.embed_text(text)

    assert result2 == cached_embedding


@pytest.mark.asyncio
async def test_embed_batch(embedding_service, mock_redis):
    """Test batch embedding generation."""
    texts = ["doc1", "doc2", "doc3"]

    with patch("embedding_service.litellm") as mock_litellm:
        embeddings = [[0.1] * 1536] * 3

        mock_response = MagicMock()
        mock_response.data = [{"embedding": emb} for emb in embeddings]

        embedding_service.litellm.aembedding = AsyncMock(return_value=mock_response)

        result = await embedding_service.embed_batch(texts)

        assert len(result) == 3
        assert all(len(emb) == 1536 for emb in result)


@pytest.mark.asyncio
async def test_embed_empty_batch(embedding_service):
    """Test batch embedding with empty list."""
    result = await embedding_service.embed_batch([])
    assert result == []


# ============================================================================
# API Integration Tests
# ============================================================================


def test_search_endpoint(client, sample_search_request):
    """Test POST /api/v1/search endpoint."""
    with patch("main.get_search_service") as mock_service:
        mock_search_service = AsyncMock()
        mock_search_service.search.return_value = {
            "query": "test",
            "results": [],
            "total_count": 0,
            "execution_time_ms": 45,
        }
        mock_service.return_value = mock_search_service

        response = client.post(
            "/api/v1/search",
            json=sample_search_request.dict(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


def test_get_document_endpoint(client):
    """Test GET /api/v1/docs/{doc_id} endpoint."""
    doc_id = str(uuid4())

    with patch("main.get_metadata_service") as mock_service:
        mock_metadata_service = AsyncMock()
        mock_metadata_service.get_document.return_value = {
            "id": doc_id,
            "title": "Test Doc",
            "content": "...",
            "owner": "team",
        }
        mock_service.return_value = mock_metadata_service

        response = client.get(f"/api/v1/docs/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


def test_get_metadata_endpoint(client):
    """Test GET /api/v1/metadata/{doc_id} endpoint."""
    doc_id = str(uuid4())

    with patch("main.get_metadata_service") as mock_service:
        mock_metadata_service = AsyncMock()
        mock_metadata_service.get_metadata.return_value = {
            "id": doc_id,
            "title": "Test",
            "owner": "team",
        }
        mock_service.return_value = mock_metadata_service

        response = client.get(f"/api/v1/metadata/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


def test_bulk_update_endpoint(client, sample_metadata_updates):
    """Test POST /api/v1/metadata/bulk-update endpoint."""
    with patch("main.get_metadata_service") as mock_service:
        mock_metadata_service = AsyncMock()
        mock_metadata_service.bulk_update_metadata.return_value = {
            "total": 2,
            "updated": 2,
            "failed": 0,
            "results": [],
        }
        mock_service.return_value = mock_metadata_service

        response = client.post(
            "/api/v1/metadata/bulk-update",
            json=sample_metadata_updates.dict(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["updated"] == 2


def test_health_endpoint(client):
    """Test GET /api/v1/health endpoint."""
    with patch("main.get_search_service") as mock_search_service, patch(
        "main.get_embedding_service"
    ) as mock_embedding_service:

        mock_search_svc = AsyncMock()
        mock_search_svc.health_check.return_value = {
            "meilisearch": {"status": "ok", "latency_ms": 12},
            "qdrant": {"status": "ok", "latency_ms": 8},
        }

        mock_embedding_svc = AsyncMock()
        mock_embedding_svc.health_check.return_value = {
            "status": "ok",
            "model": "text-embedding-3-small",
        }

        mock_search_service.return_value = mock_search_svc
        mock_embedding_service.return_value = mock_embedding_svc

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data


def test_invalid_doc_id_format(client):
    """Test error handling for invalid doc ID format."""
    response = client.get("/api/v1/docs/invalid-uuid")
    assert response.status_code == 400


def test_document_not_found(client):
    """Test 404 error for non-existent document."""
    with patch("main.get_metadata_service") as mock_service:
        mock_metadata_service = AsyncMock()
        mock_metadata_service.get_document.return_value = None
        mock_service.return_value = mock_metadata_service

        doc_id = str(uuid4())
        response = client.get(f"/api/v1/docs/{doc_id}")

        assert response.status_code == 404


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_search_service_error(search_service):
    """Test search service error handling."""
    search_service.meilisearch.index.side_effect = Exception("Service unavailable")

    with pytest.raises(Exception):
        await search_service.search(query="test", semantic_weight=0.0)


@pytest.mark.asyncio
async def test_invalid_embedding_dimension(embedding_service):
    """Test invalid embedding dimension handling."""
    with patch("embedding_service.litellm") as mock_litellm:
        # Return wrong dimension
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 512}]  # Wrong size
        embedding_service.litellm.aembedding = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError):
            await embedding_service.embed_text("test")


# ============================================================================
# Test Execution
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
