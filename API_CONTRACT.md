# KB-Search-API — API Contract

**Base URL**: `http://localhost:8002`  
**API Version**: `/api/v1`  
**Authentication**: [TBD - add if needed]  

---

## Endpoints

### 1. Root Information
**Endpoint**: `GET /`  
**Description**: Get API information and available resources  
**Status Code**: 200 OK  

**Response**:
```json
{
  "name": "Knowledge Base Search API",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs",
  "health": "/api/v1/health"
}
```

---

### 2. Hybrid Search
**Endpoint**: `POST /api/v1/search`  
**Description**: Perform hybrid keyword + semantic search across knowledge base  
**Status Code**: 200 OK  

**Request Body**:
```json
{
  "query": "postgresql replication",
  "filters": {
    "owner": "platform-eng",
    "classification": "internal"
  },
  "limit": 10,
  "offset": 0,
  "semantic_weight": 0.5,
  "highlight": true
}
```

**Parameters**:
- `query` (string, required): Search query
- `filters` (object, optional): Metadata filters for narrowing results
- `limit` (integer, default 10, max 100): Maximum number of results
- `offset` (integer, default 0): Pagination offset
- `semantic_weight` (float, default 0.5, range 0-1): Balance between keyword (0) and semantic (1) search
- `highlight` (boolean, default true): Include highlighted excerpts in results

**Response**:
```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "doc_id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "PostgreSQL Replication Guide",
        "excerpt": "...PostgreSQL replication ensures high availability...",
        "score": 0.95,
        "relevance": "high",
        "owner": "platform-eng"
      }
    ],
    "total": 42,
    "limit": 10,
    "offset": 0,
    "facets": {
      "owner": ["platform-eng", "data-science"],
      "classification": ["internal", "public"]
    }
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid query or parameters
- `500 Internal Server Error`: Search operation failed

---

### 3. Get Document
**Endpoint**: `GET /api/v1/docs/{doc_id}`  
**Description**: Retrieve full document with content and metadata  
**Status Code**: 200 OK  

**Path Parameters**:
- `doc_id` (string, UUID format): Document identifier

**Response**:
```json
{
  "status": "success",
  "data": {
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "PostgreSQL Replication Guide",
    "content": "# PostgreSQL Replication\n\nPostgreSQL replication ensures...",
    "metadata": {
      "owner": "platform-eng",
      "classification": "internal",
      "topics": ["postgresql", "replication", "ha"],
      "updated_at": "2026-04-19T10:00:00Z"
    },
    "similar": [
      {
        "doc_id": "660e8400-e29b-41d4-a716-446655440001",
        "title": "MySQL Replication Comparison",
        "similarity": 0.82
      }
    ]
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid doc_id format (not valid UUID)
- `404 Not Found`: Document not found
- `500 Internal Server Error`: Retrieval failed

---

### 4. Get Metadata
**Endpoint**: `GET /api/v1/metadata/{doc_id}`  
**Description**: Retrieve document metadata only (faster than full document retrieval)  
**Status Code**: 200 OK  

**Path Parameters**:
- `doc_id` (string, UUID format): Document identifier

**Response**:
```json
{
  "status": "success",
  "data": {
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "PostgreSQL Replication Guide",
    "owner": "platform-eng",
    "classification": "internal",
    "topics": ["postgresql", "replication", "ha"],
    "created_at": "2026-01-15T08:30:00Z",
    "updated_at": "2026-04-19T10:00:00Z",
    "version": 3,
    "size_bytes": 45230
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid doc_id format
- `404 Not Found`: Document not found
- `500 Internal Server Error`: Retrieval failed

---

### 5. Bulk Update Metadata
**Endpoint**: `POST /api/v1/metadata/bulk-update`  
**Description**: Update metadata for multiple documents in one request  
**Status Code**: 200 OK  

**Request Body**:
```json
{
  "updates": [
    {
      "doc_id": "550e8400-e29b-41d4-a716-446655440000",
      "changes": {
        "topics": ["postgresql", "replication"],
        "owner": "platform-eng",
        "classification": "internal"
      }
    },
    {
      "doc_id": "660e8400-e29b-41d4-a716-446655440001",
      "changes": {
        "classification": "public"
      }
    }
  ]
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "total": 2,
    "updated": 2,
    "failed": 0,
    "results": [
      {
        "doc_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "success",
        "message": "Updated 3 fields"
      },
      {
        "doc_id": "660e8400-e29b-41d4-a716-446655440001",
        "status": "success",
        "message": "Updated 1 field"
      }
    ]
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request format
- `500 Internal Server Error`: Bulk update operation failed

---

### 6. Reindex Embeddings
**Endpoint**: `POST /api/v1/embeddings/reindex`  
**Description**: Trigger async reindexing of embeddings for specified documents  
**Status Code**: 202 Accepted (async operation)  

**Request Body**:
```json
{
  "doc_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440001"
  ],
  "force": false,
  "priority": "normal"
}
```

**Parameters**:
- `doc_ids` (array of strings, required): UUIDs to reindex
- `force` (boolean, default false): Force reindex even if already indexed
- `priority` (string, enum: low|normal|high, default normal): Job priority

**Response**:
```json
{
  "status": "success",
  "data": {
    "job_id": "job-12345678-abcd-ef00-0000-000000000000",
    "status": "queued",
    "queued_count": 2,
    "estimated_duration_seconds": 45,
    "status_url": "/api/v1/embeddings/reindex/job-12345678-abcd-ef00-0000-000000000000"
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request or doc_ids format
- `500 Internal Server Error`: Reindex operation failed

---

## Error Handling

All error responses follow this format:

```json
{
  "status": "error",
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "Search operation failed",
    "timestamp": "2026-04-19T10:00:00Z"
  }
}
```

**Common Error Codes**:
- `BAD_REQUEST`: Invalid request parameters (400)
- `UNAUTHORIZED`: Missing or invalid authentication (401)
- `NOT_FOUND`: Resource not found (404)
- `INTERNAL_SERVER_ERROR`: Server error (500)
- `SERVICE_UNAVAILABLE`: Service temporarily unavailable (503)

---

## Authentication & Rate Limiting

**Authentication**: [TBD - Add API key, OAuth, JWT, etc.]  
**Rate Limit**: [TBD - Add rate limiting policy]  

---

## CORS & Compatibility

**CORS**: All origins allowed (*)  
**Content-Type**: `application/json`  
**Charset**: `utf-8`  

---

## Links

- **Interactive API Docs**: `/docs` (Swagger UI)
- **Alternative Docs**: `/redoc` (ReDoc)
- **OpenAPI Schema**: `/openapi.json`

---

**Last Updated**: 2026-04-19  
**Status**: Active
