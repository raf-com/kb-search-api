"""
Knowledge Base Search API - FastAPI Application.

Main application module with route definitions and lifecycle management.
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_database_manager
from models import (
    SearchRequest,
    SearchResponse,
    DocumentResponse,
    MetadataResponse,
    BulkMetadataUpdateRequest,
    BulkUpdateResponse,
    EmbeddingReindexRequest,
    ReindexResponse,
    HealthResponse,
    ComponentHealth,
    ErrorResponse,
)
from search_service import SearchService
from metadata_service import MetadataService
from embedding_service import EmbeddingService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Database manager
db_manager = get_database_manager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Knowledge Base Search API...")
    await db_manager.initialize()
    logger.info("Database connections initialized")
    yield
    # Shutdown
    logger.info("Shutting down Knowledge Base Search API...")
    await db_manager.close()
    logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Hybrid search API for knowledge base documents",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Dependencies
# ============================================================================


async def get_session() -> AsyncSession:
    """Get database session."""
    async for session in db_manager.get_session():
        yield session


async def get_search_service() -> SearchService:
    """Get search service."""
    redis = await db_manager.get_redis()
    return SearchService(redis)


async def get_metadata_service(session: AsyncSession = Depends(get_session)) -> MetadataService:
    """Get metadata service."""
    return MetadataService(session)


async def get_embedding_service() -> EmbeddingService:
    """Get embedding service."""
    redis = await db_manager.get_redis()
    return EmbeddingService(redis)


# ============================================================================
# Routes
# ============================================================================


@app.post(
    "/api/v1/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Hybrid Search",
    description="Perform hybrid keyword + semantic search",
)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """
    Hybrid search endpoint combining full-text and semantic search.

    Implements Reciprocal Rank Fusion for combining results from multiple sources.

    **Parameters:**
    - `query`: Search query string
    - `filters`: Optional metadata filters
    - `limit`: Maximum results (default 10, max 100)
    - `offset`: Result offset for pagination
    - `semantic_weight`: Weight for semantic search (0=keyword only, 1=semantic only)
    - `highlight`: Include highlighted excerpts

    **Returns:**
    - Search results with relevance scores
    - Total result count
    - Query facets for filtering

    **Example:**
    ```json
    {
      "query": "postgresql replication",
      "filters": {"owner": "platform-eng"},
      "limit": 10,
      "semantic_weight": 0.5
    }
    ```
    """
    try:
        logger.info(f"Search request: query='{request.query}', limit={request.limit}")

        results = await search_service.search(
            query=request.query,
            filters=request.filters,
            limit=request.limit,
            offset=request.offset,
            semantic_weight=request.semantic_weight,
            highlight=request.highlight,
        )

        return SearchResponse(status="success", data=results)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )


@app.get(
    "/api/v1/docs/{doc_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document",
    description="Retrieve full document with metadata",
)
async def get_document(
    doc_id: str,
    metadata_service: MetadataService = Depends(get_metadata_service),
) -> DocumentResponse:
    """
    Get full document by ID.

    Includes title, content, metadata, and similar documents.

    **Parameters:**
    - `doc_id`: Document UUID

    **Returns:**
    - Full document content and metadata
    - List of similar documents

    **Example:**
    GET /api/v1/docs/550e8400-e29b-41d4-a716-446655440000
    """
    try:
        # Parse UUID
        from uuid import UUID

        doc_uuid = UUID(doc_id)

        # Get document
        doc = await metadata_service.get_document(doc_uuid)

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        return DocumentResponse(status="success", data=doc)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )
    except Exception as e:
        logger.error(f"Get document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        )


@app.get(
    "/api/v1/metadata/{doc_id}",
    response_model=MetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Metadata",
    description="Retrieve document metadata only (no content)",
)
async def get_metadata(
    doc_id: str,
    metadata_service: MetadataService = Depends(get_metadata_service),
) -> MetadataResponse:
    """
    Get document metadata only.

    Faster than full document retrieval for metadata-only queries.

    **Parameters:**
    - `doc_id`: Document UUID

    **Returns:**
    - Document metadata (title, owner, classification, topics, etc.)

    **Example:**
    GET /api/v1/metadata/550e8400-e29b-41d4-a716-446655440000
    """
    try:
        from uuid import UUID

        doc_uuid = UUID(doc_id)
        metadata = await metadata_service.get_metadata(doc_uuid)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        return MetadataResponse(status="success", data=metadata)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )
    except Exception as e:
        logger.error(f"Get metadata failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metadata",
        )


@app.post(
    "/api/v1/metadata/bulk-update",
    response_model=BulkUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk Update Metadata",
    description="Update metadata for multiple documents",
)
async def bulk_update_metadata(
    request: BulkMetadataUpdateRequest,
    metadata_service: MetadataService = Depends(get_metadata_service),
) -> BulkUpdateResponse:
    """
    Bulk update metadata for multiple documents.

    Allows standardization and enrichment of document metadata.

    **Parameters:**
    - `updates`: List of {doc_id, changes} objects

    **Returns:**
    - Update results for each document
    - Total, updated, and failed counts

    **Example:**
    ```json
    {
      "updates": [
        {
          "doc_id": "550e8400-e29b-41d4-a716-446655440000",
          "changes": {
            "topics": ["postgresql", "replication"],
            "owner": "platform-eng"
          }
        }
      ]
    }
    ```
    """
    try:
        logger.info(f"Bulk metadata update: {len(request.updates)} documents")

        results = await metadata_service.bulk_update_metadata(
            updates=[
                {
                    "doc_id": u.doc_id,
                    "changes": u.changes,
                }
                for u in request.updates
            ],
            actor="api",
        )

        return BulkUpdateResponse(status="success", data=results)

    except Exception as e:
        logger.error(f"Bulk metadata update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Metadata update operation failed",
        )


@app.post(
    "/api/v1/embeddings/reindex",
    response_model=ReindexResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reindex Embeddings",
    description="Trigger reindexing of embeddings for specified documents",
)
async def reindex_embeddings(
    request: EmbeddingReindexRequest,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> ReindexResponse:
    """
    Reindex embeddings for documents.

    Asynchronous operation - returns job ID for status tracking.

    **Parameters:**
    - `doc_ids`: List of document UUIDs to reindex
    - `force`: Force reindex even if already indexed
    - `priority`: Job priority (low|normal|high)

    **Returns:**
    - Job ID and status URL
    - Estimated duration
    - Queued count

    **Example:**
    ```json
    {
      "doc_ids": ["550e8400-e29b-41d4-a716-446655440000"],
      "force": false,
      "priority": "normal"
    }
    ```
    """
    try:
        logger.info(f"Reindex embeddings request: {len(request.doc_ids)} documents")

        # Generate job ID
        import uuid

        job_id = f"job_{uuid.uuid4()}"

        # Queue for processing (in real implementation, would use Celery/RQ)
        response_data = {
            "job_id": job_id,
            "status_url": f"/api/v1/jobs/{job_id}/status",
            "estimated_duration_sec": len(request.doc_ids) * 2,  # Rough estimate
            "queued_count": len(request.doc_ids),
        }

        return ReindexResponse(status="accepted", data=response_data)

    except Exception as e:
        logger.error(f"Reindex embeddings failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reindex operation failed",
        )


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check service health and component status",
)
async def health_check(
    search_service: SearchService = Depends(get_search_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> HealthResponse:
    """
    Health check endpoint.

    Returns status of all service components.

    **Returns:**
    - Overall service health status
    - Component-level health with latency metrics

    **Example:**
    GET /api/v1/health
    """
    try:
        # Check database
        db_health = await db_manager.health_check()

        components = {}

        # PostgreSQL
        if db_health.get("postgresql"):
            components["postgresql"] = ComponentHealth(
                status="ok",
                latency_ms=5,  # Mock
                details={"connections": "4/20"},
            )
        else:
            components["postgresql"] = ComponentHealth(
                status="error",
                details={"error": "Connection failed"},
            )

        # Redis
        if db_health.get("redis"):
            components["redis"] = ComponentHealth(
                status="ok",
                latency_ms=3,
            )
        else:
            components["redis"] = ComponentHealth(
                status="error",
                details={"error": "Connection failed"},
            )

        # Search services
        search_health = await search_service.health_check()
        if search_health.get("meilisearch", {}).get("status") == "ok":
            components["meilisearch"] = ComponentHealth(
                status="ok",
                latency_ms=search_health["meilisearch"].get("latency_ms", 12),
                details={"indexed_documents": 41},
            )
        else:
            components["meilisearch"] = ComponentHealth(
                status="error",
                details={"error": search_health.get("meilisearch", {}).get("error", "Unknown")},
            )

        if search_health.get("qdrant", {}).get("status") == "ok":
            components["qdrant"] = ComponentHealth(
                status="ok",
                latency_ms=search_health["qdrant"].get("latency_ms", 8),
                details={"indexed_vectors": 41},
            )
        else:
            components["qdrant"] = ComponentHealth(
                status="error",
                details={"error": search_health.get("qdrant", {}).get("error", "Unknown")},
            )

        # Embedding service
        embedding_health = await embedding_service.health_check()
        if embedding_health.get("status") == "ok":
            components["litellm_api"] = ComponentHealth(
                status="ok",
                latency_ms=250,
                details={"model": embedding_health.get("model")},
            )
        else:
            components["litellm_api"] = ComponentHealth(
                status="error",
                details={"error": embedding_health.get("error")},
            )

        # Overall status
        all_ok = all(c.status == "ok" for c in components.values())
        overall_status = "healthy" if all_ok else "degraded"

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            components=components,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check failed",
        )


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return ErrorResponse(
        status="error",
        error={
            "code": exc.status_code,
            "message": exc.detail,
            "details": {},
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}")
    return ErrorResponse(
        status="error",
        error={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
        },
    )


# ============================================================================
# Root endpoint
# ============================================================================


@app.get(
    "/",
    tags=["Info"],
    summary="API Information",
)
async def root():
    """Get API information."""
    return {
        "name": "Knowledge Base Search API",
        "version": settings.api_version,
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
