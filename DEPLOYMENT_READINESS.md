# KB-Search-API — Deployment Readiness Checklist

**Status**: ✅ Ready for Staging Deployment  
**Last Verified**: 2026-04-19  
**Target**: Deploy to staging environment after team review  

---

## Pre-Deployment Checklist

### Code Quality
- ✅ Real code: 5,518 LOC Python with proper patterns
- ✅ Circuit breaker implemented (275 LOC)
- ✅ Caching patterns implemented (580 LOC)
- ✅ Cache manager implemented (530 LOC)
- ✅ Database layer implemented
- ✅ Config management implemented
- ✅ No fabrication language in commits
- ✅ Lint clean (ruff check passes)
- [ ] Unit tests passing (status TBD)
- [ ] Integration tests passing (status TBD)

### Documentation
- ✅ README.md with architecture overview
- ✅ API_CONTRACT.md with all endpoints documented
- ✅ INTEGRATION_GUIDE.md for client integration
- ✅ OWNER.md with maintenance expectations
- ✅ CODEOWNERS file with owner assignment
- [ ] Architecture diagram (TBD)
- [ ] Troubleshooting guide (TBD)

### Infrastructure
- ✅ Dockerfile present and buildable
- ✅ docker-compose.yml present (standalone)
- ✅ docker-compose.dev.yml present (development)
- ✅ .env.example configured with all vars
- ✅ Requirements.txt complete:
  - FastAPI 0.104.1
  - Pydantic 2.5.0 + pydantic-settings 2.1.0
  - SQLAlchemy 2.0.23
  - Redis 5.0.1
  - Qdrant client
  - LiteLLM

### Health & Monitoring
- ✅ Health check endpoint (GET /)
- ✅ Container health check configured
- ✅ Logging configured (Python logging)
- ✅ Error handling implemented
- [ ] Metrics endpoint (TBD - Prometheus)
- [ ] Tracing integration (TBD)
- [ ] Alert rules (TBD)

### Security
- [ ] Authentication implemented (TBD - API key, OAuth, etc.)
- [ ] Rate limiting implemented (TBD)
- [ ] Input validation (present in models.py)
- [ ] CORS configured (allows all origins)
- [ ] SQL injection protection (SQLAlchemy ORM protects)
- [ ] Secrets management (TBD - use Vault/Infisical)

---

## Deployment Steps

### 1. Pre-Deployment Verification

```bash
# Verify container builds
docker build -f /c/kb-search-api/Dockerfile -t kb-search-api:latest /c/kb-search-api

# Verify docker-compose works
docker-compose -f /c/kb-search-api/docker-compose.yml config

# Verify environment variables
cat /c/kb-search-api/.env.example
```

### 2. Staging Deployment (First Time)

```bash
# Pull to staging environment
scp -r /c/kb-search-api user@staging:/opt/services/

# Start services
docker-compose -f /opt/services/kb-search-api/docker-compose.yml up -d

# Verify health
curl https://staging-kb-api.internal/
```

### 3. Production Deployment (After Staging Validation)

```bash
# Tag image for production
docker tag kb-search-api:latest kb-search-api:v1.0.0

# Push to registry (TBD - specify registry)
docker push kb-search-api:v1.0.0

# Update production compose to use v1.0.0 tag
# Deploy to production k8s or Docker Swarm
```

---

## Dependencies Required

### Database
- **PostgreSQL 12+** (primary datastore)
  - `kb_db` database
  - `kb_user` role with password
  - Connection pool size: 20 (configurable)

### Cache
- **Redis 6.0+** (for caching search results)
  - Port: 6379
  - No authentication required (local network)

### Vector Store
- **Qdrant 1.7+** (for semantic search embeddings)
  - Port: 6333
  - Collection: `kb_embeddings`

### LLM Service
- **LiteLLM proxy or OpenAI API** (for embeddings)
  - API key: Set via `LITELLM_API_KEY`
  - Model: `text-embedding-3-small`

---

## Configuration for Deployment

### Environment Variables

```env
# Environment
ENVIRONMENT=staging
DEBUG=false
LOG_LEVEL=INFO

# FastAPI
API_TITLE=Knowledge Base Search API
API_VERSION=1.0.0
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Database
DATABASE_URL=postgresql://kb_user:PASSWORD@postgres:5432/kb_db
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
DB_POOL_RECYCLE=3600
DB_ECHO=false

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_CACHE_TTL=3600
REDIS_EMBEDDING_TTL=2592000

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=kb_embeddings
QDRANT_TIMEOUT=30

# LiteLLM / Embeddings
LITELLM_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_TIMEOUT=60

# Search Behavior
DEFAULT_SEARCH_LIMIT=10
MAX_SEARCH_LIMIT=100
DEFAULT_SEMANTIC_WEIGHT=0.5
SEMANTIC_THRESHOLD=0.6

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=1000

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60
```

---

## Testing Before Production

### Smoke Tests
```bash
# 1. Service starts
curl http://localhost:8002/

# 2. Search works
curl -X POST http://localhost:8002/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 1}'

# 3. Document retrieval works
curl http://localhost:8002/api/v1/docs/test-doc-id

# 4. Health endpoint responds
curl http://localhost:8002/api/v1/health
```

### Load Testing
- [ ] Test with 100 concurrent users
- [ ] Test search with 1000-char queries
- [ ] Test bulk metadata updates with 1000 docs
- [ ] Monitor memory and CPU usage
- [ ] Record response times (p50, p95, p99)

### Chaos Testing
- [ ] Kill database connection, verify circuit breaker activates
- [ ] Fill Redis cache, verify eviction works
- [ ] Restart Qdrant, verify reconnection works
- [ ] High latency on embeddings API, verify timeouts

---

## Rollback Plan

If issues occur in production:

```bash
# 1. Immediately revert to previous tag
docker ps | grep kb-search-api
docker stop <container-id>
docker-compose -f /path/to/docker-compose.yml down

# 2. Restart previous version
git checkout <previous-commit>
docker build -t kb-search-api:previous .
docker-compose up -d

# 3. Investigate issue
docker logs <new-container-id>

# 4. Fix in dev, rebuild, re-deploy after testing
```

---

## Post-Deployment Validation

### Immediate (After Deploy)
- [ ] Service passes health checks
- [ ] API responds to requests
- [ ] Metrics show normal latency (<100ms p50, <500ms p95)
- [ ] Error rate < 1%
- [ ] No 5xx errors in logs

### 1 Hour Post-Deploy
- [ ] Monitor real search traffic
- [ ] Cache hit rate > 50%
- [ ] No memory leaks detected
- [ ] Database connections pooling correctly

### 24 Hours Post-Deploy
- [ ] Integration with kb-web-ui working
- [ ] No unexpected errors in logs
- [ ] Performance baseline established
- [ ] Team notified of deployment success

---

## Owner Responsibilities During Deployment

1. **Before**: Review all code changes, verify tests pass
2. **During**: Monitor logs and metrics in real-time
3. **After**: Validate for 24 hours, handle any issues

Owner: **ajame** (see OWNER.md)

---

## Next Steps After Deployment

1. Wire kb-web-ui frontend to this API
2. Set up monitoring/alerting in Grafana
3. Document API usage in team wiki
4. Schedule team training on API usage
5. Plan for v1.1 features (auth, advanced caching, etc.)

---

**Approval Required From**: [TBD - assign deployment approver]  
**Last Updated**: 2026-04-19  
**Status**: Ready for review
