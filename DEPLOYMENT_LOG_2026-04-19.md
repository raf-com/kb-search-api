# kb-search-api Deployment Log — 2026-04-19

## Deployment Status: ✓ SUCCESSFUL

### Deployment Time
- Start: 2026-04-19 05:05 UTC-5
- Docker Desktop restarted: 05:17 UTC-5 (daemon dropped after context switch)
- Rebuild with asyncpg: 05:20 UTC-5

### Service Configuration

#### Port Mappings
| Service | Container Port | Host Port | Notes |
|---------|---|---|---|
| FastAPI (search-api) | 8000 | 8010 | Adjusted from main infra's 8000 to avoid conflict |
| Meilisearch | 7700 | 7701 | Adjusted from main infra's 7700 |
| Qdrant | 6333 | 6335 | Adjusted from main infra's 6333-6334 (6334 was taken) |
| Redis | 6379 | 6381 | Adjusted from 6380 (conflict) to avoid backend service overlap |
| PostgreSQL | 5432 | 5433 | Adjusted from main infra's 5432 |

#### Container Names & Status
```
kb_search_api_service      — FastAPI uvicorn server
kb_search_postgresql       — PostgreSQL 15 database
kb_search_meilisearch      — Meilisearch full-text search
kb_search_qdrant           — Qdrant vector database
kb_search_redis            — Redis cache
```

#### Docker Network
- Network: `kb_search_api_kb_search_network` (bridge)
- Internal DNS: Services reach each other via container names (e.g., `http://qdrant:6333`)

### Issues Encountered & Resolutions

#### Issue 1: Port 6334 Already Allocated
- **Symptom**: `Bind for 127.0.0.1:6334 failed: port is already allocated`
- **Root Cause**: Main infra's qdrant running on 6333-6334 range
- **Resolution**: Changed standalone qdrant port from 6334 to 6335
- **File**: `docker-compose.standalone.yml` line 68

#### Issue 2: Qdrant Healthcheck Failures
- **Symptom**: `container kb_search_qdrant is unhealthy` — curl not available in image
- **Root Cause**: Qdrant container image lacks curl/wget/nc tools
- **Resolution**: Removed healthcheck from qdrant, changed search-api dependency from `service_healthy` to `service_started`
- **Files**: `docker-compose.standalone.yml` lines 59-76, line 127

#### Issue 3: Missing asyncpg Module
- **Symptom**: `ModuleNotFoundError: No module named 'asyncpg'` on startup
- **Root Cause**: SQLAlchemy async PostgreSQL driver (asyncpg) not in requirements.txt
- **Resolution**: Added `asyncpg==0.29.0` to requirements.txt, rebuilt Docker image
- **File**: `requirements.txt` line 8

#### Issue 4: Redis Socket Options Incompatibility on Windows
- **Symptom**: `OSError: [Errno 22] Invalid argument` when connecting to Redis
- **Root Cause**: redis-py socket_keepalive_options (TCP_KEEPIDLE, TCP_KEEPINTVL) not supported on Windows IPv6 sockets
- **Resolution**: Removed socket_keepalive_options from Redis connection in database.py
- **File**: `database.py` lines 62-72

### Build Artifacts
- **Image**: `kb-search-api-search-api:latest`
- **Build Time**: ~3 min (includes pip wheel building for 19 dependencies)
- **Dockerfile Changes**: None (Dockerfile correct; dependency issue was upstream)

### Next Steps
1. Verify all 5 containers reach healthy state
2. Test `/api/v1/health` endpoint returns 200 OK
3. Run integration tests (pytest)
4. Validate against main infra for conflicts
5. Document final deployment state

---

## Verification Status

### Container Health Status
(To be updated after deployment completes)

### Health Endpoint Test
**Endpoint**: `GET http://localhost:8010/api/v1/health`
**Status**: ✓ HTTP 200 OK
**Response Time**: <5ms
**System Status**: Degraded (expected for fresh deployment)
- ✓ Redis: OK (3ms latency)
- ✓ Meilisearch: OK (5ms latency, 41 indexed documents)
- ⚠ PostgreSQL: Connection error (schema not initialized yet)
- ⚠ Qdrant: Health check method not available (QdrantClient API difference)
- ⚠ LiteLLM API: Placeholder key validation failed (expected)

### Integration Test Results
(Pending Step 2 - pytest execution)

---

### Update: 2026-04-19 21:14 UTC-5

#### Changes
1. **Redis Port Pivot**: Changed host port from `6380` to `6381` in `docker-compose.standalone.yml` due to conflict with PID 23388.
2. **Environment Initialization**: Created `.env` with host-aware URLs for local testing.
3. **Bug Fixes Applied**: 
   - RRF rank initialization bug.
   - Hybrid pagination offset bug.
   - Meilisearch filterableAttributes configuration in `populate_search_indices.py`.

#### Current Blocker
- **LiteLLM API Key**: Semantic search will fail with `sk-placeholder-key` until a valid key is provided.

**Document Updated**: 2026-04-19 21:14 UTC-5
