# KB-Search-API — Integration Guide

**For**: kb-web-ui and other clients  
**Base URL**: `http://localhost:8002` (local) or `https://api.kb.internal/search` (production TBD)  

---

## Quick Start

### 1. Verify Service is Running

```bash
# Check container status
docker ps --filter name=kb-search-api

# Test root endpoint
curl http://localhost:8002/
```

Expected response:
```json
{
  "name": "Knowledge Base Search API",
  "version": "1.0.0",
  "status": "running"
}
```

### 2. Basic Search Example

```bash
curl -X POST http://localhost:8002/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "postgresql replication",
    "limit": 5
  }'
```

### 3. JavaScript/React Integration

```typescript
// SearchService.ts
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

export async function search(query: string, limit: number = 10) {
  const response = await fetch(`${API_URL}/api/v1/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      limit,
      semantic_weight: 0.5,
      highlight: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`);
  }

  return response.json();
}
```

---

## Environment Configuration

### Development (.env.local)

```env
# kb-web-ui/.env.local
VITE_API_URL=http://localhost:8002
VITE_API_TIMEOUT=30000
VITE_LOG_LEVEL=debug
```

### Production (TBD)

```env
# .env
VITE_API_URL=https://api.kb.internal/search
VITE_API_TIMEOUT=10000
VITE_LOG_LEVEL=warn
```

---

## Key Endpoints for Integration

### Search (Primary)
```
POST /api/v1/search
Body: { query, filters?, limit, offset, semantic_weight, highlight }
Returns: { results, total, facets }
```

### Get Document
```
GET /api/v1/docs/{doc_id}
Returns: { title, content, metadata, similar }
```

### Get Metadata
```
GET /api/v1/metadata/{doc_id}
Returns: { title, owner, classification, topics, created_at, updated_at }
```

---

## Error Handling

All errors follow standard HTTP conventions:

```typescript
async function handleSearchError(error: unknown) {
  if (error instanceof Response) {
    const errorBody = await error.json();
    console.error(`API Error: ${error.status}`, errorBody.error);
    
    switch (error.status) {
      case 400:
        // Invalid query or parameters
        showUserMessage('Invalid search query');
        break;
      case 404:
        // No results found
        showUserMessage('No documents found');
        break;
      case 500:
        // Server error
        showUserMessage('Search service unavailable, please try again');
        break;
    }
  }
}
```

---

## Performance Considerations

### Caching
- Results are cached in Redis for 1 hour
- Cache key: `search:{query_hash}:{semantic_weight}`
- Metadata is cached for 30 minutes

### Rate Limiting (TBD)
- Implement rate limiting in production
- Suggested: 100 requests/minute per client

### Timeout Handling
- Search timeout: 30 seconds
- Document retrieval: 10 seconds
- Metadata fetch: 5 seconds

---

## Testing

### Manual Testing with curl

```bash
# Test search
curl -X POST http://localhost:8002/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 5}'

# Test document retrieval  
curl http://localhost:8002/api/v1/docs/550e8400-e29b-41d4-a716-446655440000

# Test metadata
curl http://localhost:8002/api/v1/metadata/550e8400-e29b-41d4-a716-446655440000
```

### Unit Testing in React

```typescript
// SearchBox.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import SearchBox from './SearchBox';

describe('SearchBox', () => {
  it('calls API when search is submitted', async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { results: [] } }),
    });
    global.fetch = mockFetch;

    render(<SearchBox />);
    const input = screen.getByPlaceholderText('Search...');
    
    fireEvent.change(input, { target: { value: 'test' } });
    fireEvent.submit(input.form!);

    await expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8002/api/v1/search',
      expect.any(Object)
    );
  });
});
```

---

## CORS & Headers

The API accepts:
- `Content-Type: application/json`
- `Accept: application/json`

All responses include:
- `Content-Type: application/json; charset=utf-8`

---

## Links

- **Full API Documentation**: [API_CONTRACT.md](./API_CONTRACT.md)
- **Interactive Docs**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc
- **Owner & Maintenance**: [OWNER.md](./OWNER.md)

---

**Last Updated**: 2026-04-19  
**Status**: Active
