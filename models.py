"""
Pydantic models for the Knowledge Base Search API.

Includes request/response schemas, data models, and validation rules.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator, HttpUrl
from uuid import UUID


# ============================================================================
# Request Models
# ============================================================================


class SearchFilters(BaseModel):
    """Filters for search queries."""

    owner: Optional[str] = Field(default=None, description="Filter by document owner")
    classification: Optional[Literal["public", "internal", "confidential"]] = Field(
        default=None, description="Filter by classification level"
    )
    topics: Optional[List[str]] = Field(default=None, description="Filter by topics")
    status: Optional[Literal["active", "archived", "deprecated"]] = Field(
        default=None, description="Filter by status"
    )
    created_after: Optional[datetime] = Field(default=None, description="Filter documents created after this date")
    created_before: Optional[datetime] = Field(default=None, description="Filter documents created before this date")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "owner": "platform-eng",
                "classification": "internal",
                "topics": ["postgresql", "replication"],
                "status": "active",
            }
        }


class SearchRequest(BaseModel):
    """Request model for hybrid search endpoint."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    filters: Optional[SearchFilters] = Field(default=None, description="Search filters")
    limit: int = Field(default=10, ge=1, le=100, description="Result limit")
    offset: int = Field(default=0, ge=0, description="Result offset for pagination")
    semantic_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for semantic search (0=keyword only, 1=semantic only)"
    )
    highlight: bool = Field(default=True, description="Include highlighted excerpts")
    include_similar: bool = Field(default=False, description="Include similar documents")

    @validator("limit")
    def validate_limit(cls, v):
        """Validate result limit."""
        return min(v, 100)

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "query": "postgresql replication",
                "filters": {
                    "owner": "platform-eng",
                    "classification": "internal",
                },
                "limit": 10,
                "offset": 0,
                "semantic_weight": 0.5,
                "highlight": True,
                "include_similar": False,
            }
        }


class MetadataUpdate(BaseModel):
    """Single metadata update."""

    doc_id: UUID = Field(..., description="Document ID")
    changes: Dict[str, Any] = Field(..., description="Fields to update")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                "changes": {
                    "topics": ["postgresql", "replication"],
                    "owner": "platform-eng",
                },
            }
        }


class BulkMetadataUpdateRequest(BaseModel):
    """Request model for bulk metadata updates."""

    updates: List[MetadataUpdate] = Field(..., min_items=1, max_items=100, description="List of metadata updates")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "updates": [
                    {
                        "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                        "changes": {"topics": ["postgresql", "replication"]},
                    }
                ]
            }
        }


class EmbeddingReindexRequest(BaseModel):
    """Request model for reindexing embeddings."""

    doc_ids: List[UUID] = Field(..., min_items=1, max_items=1000, description="Document IDs to reindex")
    force: bool = Field(default=False, description="Force reindex even if already indexed")
    priority: Literal["low", "normal", "high"] = Field(default="normal", description="Job priority")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "doc_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                "force": False,
                "priority": "normal",
            }
        }


# ============================================================================
# Response Models
# ============================================================================


class SearchResultItem(BaseModel):
    """Single search result item."""

    doc_id: UUID = Field(..., description="Document ID")
    rank: int = Field(..., description="Result rank")
    title: str = Field(..., description="Document title")
    source: str = Field(..., description="Document source/filepath")
    owner: str = Field(..., description="Document owner")
    classification: str = Field(..., description="Classification level")
    created_date: datetime = Field(..., description="Creation date")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0-1)")
    search_type: Literal["hybrid", "keyword", "semantic"] = Field(..., description="Type of search that found this result")
    excerpt: str = Field(..., description="Document excerpt")
    highlighted_excerpt: Optional[str] = Field(default=None, description="Highlighted excerpt with <mark> tags")
    topics: List[str] = Field(default_factory=list, description="Document topics")

    class Config:
        """Pydantic configuration."""
        json_encoders = {UUID: str, datetime: lambda v: v.isoformat()}


class FacetValue(BaseModel):
    """Facet count for search results."""

    value: str = Field(..., description="Facet value")
    count: int = Field(..., ge=0, description="Result count for this facet value")


class SearchFacets(BaseModel):
    """Faceted counts from search results."""

    owner: Optional[List[FacetValue]] = Field(default=None, description="Owner facet")
    classification: Optional[List[FacetValue]] = Field(default=None, description="Classification facet")
    topics: Optional[List[FacetValue]] = Field(default=None, description="Topics facet")
    status: Optional[List[FacetValue]] = Field(default=None, description="Status facet")


class SearchResponse(BaseModel):
    """Response model for search endpoint."""

    status: Literal["success", "error"] = Field(..., description="Response status")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "query": "postgresql replication",
                    "results": [],
                    "total_count": 0,
                    "limit": 10,
                    "offset": 0,
                    "facets": {},
                    "execution_time_ms": 45,
                },
            }
        }


class DocumentMetadata(BaseModel):
    """Document metadata model."""

    id: UUID = Field(..., description="Document ID")
    title: str = Field(..., description="Document title")
    source: str = Field(..., description="Document source")
    owner: str = Field(..., description="Document owner")
    classification: str = Field(..., description="Classification level")
    status: str = Field(..., description="Document status")
    created_date: datetime = Field(..., description="Creation date")
    updated_date: datetime = Field(..., description="Update date")
    created_by: Optional[str] = Field(default=None, description="Creator username")
    updated_by: Optional[str] = Field(default=None, description="Last updater username")
    topics: List[str] = Field(default_factory=list, description="Document topics")
    external_id: Optional[str] = Field(default=None, description="External ID for linking")

    class Config:
        """Pydantic configuration."""
        json_encoders = {UUID: str, datetime: lambda v: v.isoformat()}


class DocumentResponse(BaseModel):
    """Response model for get document endpoint."""

    status: Literal["success", "error"] = Field(..., description="Response status")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Document data")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "PostgreSQL Replication Best Practices",
                    "content": "...",
                    "summary": "...",
                    "source": "/docs/databases/postgres-replication.md",
                    "owner": "platform-eng",
                    "classification": "internal",
                },
            }
        }


class MetadataResponse(BaseModel):
    """Response model for metadata endpoint."""

    status: Literal["success", "error"] = Field(..., description="Response status")
    data: Optional[DocumentMetadata] = Field(default=None, description="Metadata only")

    class Config:
        """Pydantic configuration."""
        json_encoders = {UUID: str, datetime: lambda v: v.isoformat()}


class BulkUpdateResult(BaseModel):
    """Result of a single bulk update."""

    doc_id: UUID = Field(..., description="Document ID")
    status: Literal["updated", "failed", "not_found"] = Field(..., description="Update status")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class BulkUpdateResponse(BaseModel):
    """Response model for bulk metadata update endpoint."""

    status: Literal["success", "error"] = Field(..., description="Response status")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Update results")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "total": 2,
                    "updated": 2,
                    "failed": 0,
                    "results": [
                        {
                            "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                            "status": "updated",
                        }
                    ],
                },
            }
        }


class ReindexResponse(BaseModel):
    """Response model for reindex endpoint."""

    status: Literal["accepted", "error"] = Field(..., description="Response status")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Job information")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "accepted",
                "data": {
                    "job_id": "job_550e8400...",
                    "status_url": "/api/v1/jobs/job_550e8400.../status",
                    "estimated_duration_sec": 12,
                    "queued_count": 1,
                },
            }
        }


class ComponentHealth(BaseModel):
    """Health status of a service component."""

    status: Literal["ok", "degraded", "error"] = Field(..., description="Component status")
    latency_ms: Optional[int] = Field(default=None, description="Response latency in milliseconds")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional component details")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Overall health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    components: Dict[str, ComponentHealth] = Field(..., description="Component health details")

    class Config:
        """Pydantic configuration."""
        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2026-04-18T14:30:00Z",
                "components": {
                    "postgresql": {"status": "ok", "latency_ms": 5},
                    "meilisearch": {"status": "ok", "latency_ms": 12},
                    "qdrant": {"status": "ok", "latency_ms": 8},
                    "litellm_api": {"status": "ok", "latency_ms": 250},
                },
            }
        }


class ErrorResponse(BaseModel):
    """Error response model."""

    status: Literal["error"] = Field(default="error", description="Response status")
    error: Dict[str, Any] = Field(..., description="Error details")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "error",
                "error": {
                    "code": "INVALID_QUERY",
                    "message": "Query cannot be empty",
                    "details": {},
                },
            }
        }
