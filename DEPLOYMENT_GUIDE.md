# kb-search-api Deployment Guide

## Overview

kb-search-api is a production-ready Knowledge Base Search Service with:
- **Hybrid search**: Meilisearch (full-text) + Qdrant (semantic)
- **Resilience**: Circuit breaker pattern, Redis caching, fallback strategies
- **Code quality**: 5518 LOC real Python + 1148 LOC comprehensive tests
- **Status**: Promoted to managed code (git init, docker-compose ready)

---

## Quick Start (Standalone)

### 1. Clone/Update Environment

```bash
cd /c/kb-search-api

# Copy environment template
cp .env.example .env

# Edit .env with your values (API keys, credentials)
nano .env
```

### 2. Start Services

```bash
# Standalone deployment (dedicated ports to avoid conflicts)
docker-compose -f docker-compose.standalone.yml up -d

# Check status
docker-compose -f docker-compose.standalone.yml ps

# View logs
docker-compose -f docker-compose.standalone.yml logs -f search-api
```

### 3. Test Health

```bash
# Should return 200 OK
curl http://localhost:8010/api/v1/health

# Example search
curl -X POST http://localhost:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 10}'
```

---

## Port Mapping

| Service | Standalone | Main Infra | Notes |
|---------|-----------|-----------|-------|
| FastAPI | 8010 | 8000 | Standalone avoids env-var-registry conflict |
| Meilisearch | 7701 | 7700 | Separate instance (or share if pooling) |
| Qdrant | 6334 | 6333 | Separate instance (or share if pooling) |
| Redis | 6380 | 6379 | Separate instance (or share if pooling) |
| PostgreSQL | 5433 | 5432 | Separate database (recommended) |

---

## Deployment Options

### Option A: Standalone (Recommended for testing/evaluation)
- Run in isolation with dedicated services
- Fastest setup, no infrastructure changes
- Good for PoC and single-team deployment

**Command:**
```bash
docker-compose -f docker-compose.standalone.yml up -d
```

**Pros**: Simple, self-contained, no port conflicts  
**Cons**: Duplicate infrastructure (PostgreSQL, Redis, Meilisearch, Qdrant)

---

### Option B: Shared Infrastructure (Recommended for production)
- Reuse Meilisearch/Qdrant from main infra
- Separate PostgreSQL + Redis for kb-search-api
- Lower resource consumption

**Setup:**
1. Extract Meilisearch/Qdrant URLs from main infra compose
2. Modify kb-search-api docker-compose to reference external services
3. Keep PostgreSQL + Redis isolated

```yaml
# Example: Reference external Meilisearch
meilisearch:
  external: true
  name: infra-meilisearch-1  # From main infra stack
```

**Pros**: Shared resources, lower resource consumption  
**Cons**: Requires coordination with main infra team

---

### Option C: Archive to Graveyard
- Move to `/c/_graveyard_2026-04-19/kb-search-api`
- Keep for future reference
- Fully reversible

**Command:**
```bash
mv /c/kb-search-api /c/_graveyard_2026-04-19/kb-search-api
# To restore:
mv /c/_graveyard_2026-04-19/kb-search-api /c/kb-search-api
```

**Pros**: Cleanup, declutters production if not used  
**Cons**: Must restore if needed later

---

## Architecture

**Complete System Architecture**: See `/c/infra/ARCHITECTURE_2026-04-19.md` for infrastructure diagrams, network topology, and system overview.

### Services

**search-api** (FastAPI)
- REST API for hybrid search
- Health checks on `/api/v1/health`
- Search endpoint: POST `/api/v1/search`
- Implements circuit breaker + caching

**PostgreSQL** (5433/5433)
- Stores document metadata, cache stats, indexing logs
- Schema initialized from `init-scripts/kb-schema.sql`

**Meilisearch** (7701/7700)
- Full-text search index
- Fast keyword search over documents

**Qdrant** (6334/6333)
- Vector database for semantic search
- Stores document embeddings
- Reciprocal Rank Fusion combines keyword + semantic results

**Redis** (6380/6379)
- Caches search results (TTL: 1 hour)
- Caches embeddings (TTL: 30 days)
- Fallback for circuit breaker

---

## Testing

### Run Tests Locally

```bash
cd /c/kb-search-api

# Install dependencies
pip install -r requirements.txt pytest pytest-cov

# Run all tests
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Test Coverage
- **test_api.py**: 666 LOC (API endpoints, search, health)
- **test_caching.py**: 482 LOC (cache invalidation, fallback, TTL)
- **Total**: 1148 LOC of real tests

---

## Health Monitoring

### Readiness Probe
```bash
curl http://localhost:8010/api/v1/health
# Response: {"status": "ready", "dependencies": {"postgres": "ok", "redis": "ok", ...}}
```

### Docker Healthcheck
Configured for 10s interval, 5s timeout, 5 retries before marking unhealthy.

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose -f docker-compose.standalone.yml logs

# Verify ports are free
lsof -i :8010
lsof -i :6380
lsof -i :6334
```

### Search Returns No Results
1. Verify Meilisearch has indexed documents
2. Check Redis cache isn't stale
3. Verify Qdrant embeddings are loaded

### High Memory Usage
- Reduce `MEILI_MAX_INDEXING_MEMORY` in .env (currently 2GB)
- Reduce Redis `--maxmemory` setting
- Implement document pagination in queries

---

## Monitoring & Metrics

### Available Metrics
- Search latency (tracked by circuit breaker)
- Cache hit rate (Redis)
- Vector search quality (Qdrant)
- API request count (FastAPI)

### Logs
```bash
# Real-time logs
docker-compose -f docker-compose.standalone.yml logs -f search-api

# Specific container
docker-compose -f docker-compose.standalone.yml logs search-api | tail -100
```

---

## Scaling

### Horizontal Scaling
For multiple instances of kb-search-api:
1. Remove port mapping from search-api service
2. Put behind load balancer (nginx, HAProxy)
3. Scale PostgreSQL + Redis to cluster (optional)

### Vertical Scaling
- Increase `API_WORKERS` (currently 2, max 4-8 recommended)
- Increase Redis `--maxmemory`
- Increase Meilisearch `--max-indexing-memory`

---

## Production Checklist

- [ ] `.env` configured with production API keys
- [ ] Database backups scheduled
- [ ] Redis persistence enabled (`AOF` or `RDB`)
- [ ] Monitoring/alerting configured
- [ ] Logs shipped to central log aggregator
- [ ] Rate limiting enabled (`RATE_LIMIT_ENABLED=true`)
- [ ] Circuit breaker enabled (`CIRCUIT_BREAKER_ENABLED=true`)
- [ ] Load balancer configured (if scaling)
- [ ] Health checks wired to orchestrator
- [ ] Disaster recovery plan documented

---

## Maintenance

### Database Maintenance
```bash
# PostgreSQL cleanup
docker-compose -f docker-compose.standalone.yml exec postgresql \
  psql -U kb_user -d kb_db -c "VACUUM ANALYZE;"
```

### Cache Cleanup
```bash
# Clear all cache
docker-compose -f docker-compose.standalone.yml exec redis \
  redis-cli FLUSHDB
```

### Index Optimization
```bash
# Meilisearch index stats
curl http://localhost:7701/indexes/kb_documents/stats
```

---

## Support & Documentation

- **Code**: Real, production-quality Python (5518 LOC)
- **Tests**: Comprehensive coverage (1148 LOC)
- **Config**: `.env.example` with all options documented
- **Docker**: Standalone + main infra compatible compose files
- **Status**: Fully managed under git with version control

---

**Deployment Status**: ✓ Ready for deployment  
**Last Updated**: 2026-04-19  
**Maintainer**: Knowledge Base Team
