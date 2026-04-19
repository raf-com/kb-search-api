# kb-search-api Troubleshooting Guide

**Created**: 2026-04-19  
**Updated**: 2026-04-19  
**Audience**: Developers, DevOps, SRE

---

## Quick Diagnostics

**Is the service up?**
```bash
curl http://localhost:8010/api/v1/health
# Expected: {"status": "ready", "dependencies": {...}}
```

**Are all containers running?**
```bash
docker-compose -f docker-compose.standalone.yml ps
# Expected: All 5 services with status "Up"
```

**Are there recent errors?**
```bash
docker-compose -f docker-compose.standalone.yml logs --tail 50 search-api
```

---

## Common Issues & Solutions

### Issue 1: Service Won't Start

**Symptom**: Container exits immediately or doesn't start

**Diagnosis**:
```bash
# Check logs
docker logs kb_search_api_service --tail 100

# Check status
docker ps -a | grep kb_search

# Look for exit code
docker inspect kb_search_api_service --format='{{.State}}'
```

**Common causes & fixes**:

**A) Missing environment variables**
```
Error: ValueError: Missing environment variable DATABASE_URL
```

**Fix**: Ensure `.env` file exists and has all required variables
```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env

# Verify all required vars
grep -E "DATABASE_URL|QDRANT_URL|MEILISEARCH_URL|REDIS_URL|LITELLM_API_KEY" .env

# Restart
docker-compose -f docker-compose.standalone.yml restart search-api
```

**B) Port already in use**
```
Error: bind: address already in use
```

**Fix**: Change port mapping in docker-compose.standalone.yml
```bash
# Find what's using port 8010
lsof -i :8010

# Kill the process or change port mapping
# In docker-compose.standalone.yml:
#   ports:
#     - "8011:8000"  # Changed from 8010

# Restart
docker-compose -f docker-compose.standalone.yml up -d
```

**C) Database connection refused**
```
Error: psycopg2.OperationalError: could not connect to server
```

**Fix**: Ensure PostgreSQL is healthy
```bash
# Check PostgreSQL status
docker-compose -f docker-compose.standalone.yml ps postgresql

# Verify healthcheck passed
docker inspect kb_search_postgresql --format='{{.State.Health.Status}}'

# Check PostgreSQL logs
docker logs kb_search_postgresql | tail -20

# Restart PostgreSQL
docker-compose -f docker-compose.standalone.yml restart postgresql

# Then restart search-api
docker-compose -f docker-compose.standalone.yml restart search-api
```

**D) Memory limit exceeded (OOMKilled)**
```
Error: Container exited with code 137
Exit reason: OOMKilled
```

**Fix**: Increase memory limit (see Step 11: RESOURCE_LIMITS.md)
```bash
# Edit docker-compose.standalone.yml
# Find search-api service section, change:
#   deploy:
#     resources:
#       limits:
#         memory: 1G  # Increased from 512M

# Rebuild and restart
docker-compose -f docker-compose.standalone.yml down
docker-compose -f docker-compose.standalone.yml up -d
```

---

### Issue 2: Search Returns No Results

**Symptom**: Query executes but returns empty results or 0 matches

**Diagnosis**:
```bash
# Check Meilisearch has indexed documents
curl http://localhost:7701/indexes/kb_documents/stats | jq .numberOfDocuments

# Check Qdrant has vectors
curl http://localhost:6335/collections | jq '.result | length'

# Check Redis cache (search results TTL=1 hour)
docker exec kb_search_redis redis-cli DBSIZE
```

**Common causes & fixes**:

**A) No documents indexed in Meilisearch**
```
Symptom: numberOfDocuments = 0
```

**Fix**: Add documents to Meilisearch
```bash
# Check if documents endpoint exists
curl -X POST http://localhost:7701/indexes/kb_documents/documents \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MEILI_MASTER_KEY" \
  -d '[{"id": "1", "title": "Test", "content": "Hello world"}]'

# Verify indexing completed
curl http://localhost:7701/indexes/kb_documents/stats | jq .numberOfDocuments
```

**B) No embeddings in Qdrant**
```
Symptom: qdrant returns 0 collections or collection is empty
```

**Fix**: Generate embeddings for your documents
```bash
# The kb-search-api should auto-embed on document insert
# Check if embedding model is working:
docker logs kb_search_api_service | grep -i "embedding\|llm\|openai"

# Verify LiteLLM API key is valid
curl -X POST http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "text-embedding-3-small"}'
```

**C) Redis cache is stale**
```
Symptom: Results are old, cache not updating
```

**Fix**: Clear cache and retry
```bash
# Clear all cache
docker exec kb_search_redis redis-cli FLUSHDB

# Search again (should populate cache with fresh results)
curl -X POST http://localhost:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 10}'

# Verify cache populated
docker exec kb_search_redis redis-cli DBSIZE
```

**D) Query syntax error**
```
Error: invalid search syntax or empty query
```

**Fix**: Validate query format
```bash
# Correct format:
curl -X POST http://localhost:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "your search term",
    "limit": 10,
    "offset": 0
  }'

# Check application logs
docker logs kb_search_api_service | grep -i "error\|invalid"
```

---

### Issue 3: High Memory Usage

**Symptom**: Memory usage approaching or exceeding limit, container may OOMKill

**Diagnosis**:
```bash
# Check memory usage
docker stats --no-stream kb_search_api_service kb_search_meilisearch kb_search_qdrant

# Check memory limit
docker inspect kb_search_api_service --format='{{json .HostConfig.Memory}}' | jq . # bytes

# Check if Meilisearch indexing is consuming memory
curl http://localhost:7701/stats | jq .isIndexing
```

**Common causes & fixes**:

**A) Large search result set (Meilisearch issue)**
```
Symptom: Meilisearch using 80-90% of 1GB limit
Cause: Indexing large document batch
```

**Fix**: Monitor indexing, reduce batch size
```bash
# Check indexing status
curl http://localhost:7701/tasks | jq '.results | length'

# Reduce max indexing memory in docker-compose.standalone.yml:
# OLD: MEILI_MAX_INDEXING_MEMORY: 2gb
# NEW: MEILI_MAX_INDEXING_MEMORY: 1gb

# Reduce batch size for document inserts
# Instead of: INSERT 10,000 documents at once
# Do: INSERT 1,000 documents per batch, wait 5s between batches
```

**B) Qdrant vector database growing**
```
Symptom: Qdrant using 80-90% of 1GB limit
Cause: Many embeddings stored, collection size growing
```

**Fix**: Monitor collection size, archive old vectors
```bash
# Check collection size
curl http://localhost:6335/collections | jq '.result[] | {name, points_count}'

# Check individual collection stats
curl http://localhost:6335/collections/documents | jq '.result'

# Consider tiered storage (keep last N months, archive older)
# Or use Qdrant's snapshot/export feature to reduce size
```

**C) Search-API memory leak** (rare)
```
Symptom: Memory gradually increases even with no queries
Cause: Possible memory leak in application
```

**Fix**: Restart and monitor
```bash
# Restart search-api
docker-compose -f docker-compose.standalone.yml restart search-api

# Monitor memory over time
while true; do
  echo "$(date): $(docker stats --no-stream kb_search_api_service | tail -1 | awk '{print $7}')"
  sleep 60
done

# If memory still increases, file a GitHub issue with metrics
```

---

### Issue 4: Slow Search Queries

**Symptom**: Search takes >2-5 seconds when it should be <1 second

**Diagnosis**:
```bash
# Check query latency
curl -w "Time: %{time_total}s\n" -X POST http://localhost:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 10}'

# Check application logs for query time
docker logs kb_search_api_service | grep -i "query\|latency\|duration"

# Check Meilisearch indexing (might be slowing everything)
curl http://localhost:7701/stats | jq '{isIndexing, taskDatabaseSize}'

# Check Qdrant vector search latency
curl http://localhost:6335/health | jq .
```

**Common causes & fixes**:

**A) Meilisearch rewriting indexes**
```
Symptom: Slow queries during indexing
```

**Fix**: Index during off-peak hours
```bash
# Check if indexing in progress
curl http://localhost:7701/stats | jq .isIndexing

# Wait for indexing to complete
while curl -s http://localhost:7701/stats | jq .isIndexing | grep -q true; do
  echo "Indexing in progress..."
  sleep 5
done

# Or schedule batch indexing for 02:00-04:00 UTC when traffic is low
```

**B) Missing database indexes**
```
Symptom: PostgreSQL full table scans
```

**Fix**: Check and create indexes
```bash
# Connect to PostgreSQL
docker-compose -f docker-compose.standalone.yml exec postgresql \
  psql -U kb_user -d kb_db -c "SELECT * FROM pg_stat_user_indexes;"

# If no indexes on frequently-searched columns, create them:
# CREATE INDEX idx_document_id ON documents(document_id);
# CREATE INDEX idx_created_at ON documents(created_at);
```

**C) Large result sets (retrieval latency)**
```
Symptom: Search fast, but retrieval of results is slow
Cause: Returning too many results
```

**Fix**: Reduce result size or paginate
```bash
# Instead of:
curl -X POST http://localhost:8010/api/v1/search \
  -d '{"query": "test", "limit": 1000}'  # Returns 1000 results

# Do:
curl -X POST http://localhost:8010/api/v1/search \
  -d '{"query": "test", "limit": 10, "offset": 0}'  # First 10 results

# Then paginate:
# For next page: offset: 10
# For page N: offset: (N-1)*limit
```

**D) Redis not caching results**
```
Symptom: Every search query hits Meilisearch/Qdrant
Cause: Cache hit rate low
```

**Fix**: Verify caching is enabled
```bash
# Check cache hit rate in logs
docker logs kb_search_api_service | grep -i "cache\|hit\|miss"

# Check Redis is storing results
docker exec kb_search_redis redis-cli DBSIZE  # Should be >0

# Check cache TTL (1 hour default)
docker exec kb_search_redis redis-cli TTL search:test:10

# If issues, clear cache and verify it refills
docker exec kb_search_redis redis-cli FLUSHDB
docker logs kb_search_api_service --tail 5
```

---

### Issue 5: Circuit Breaker Open

**Symptom**: "Circuit breaker open" error in logs, search fails

**Diagnosis**:
```bash
# Check circuit breaker state
docker logs kb_search_api_service | grep -i "circuit\|breaker\|open\|closed"

# Verify Qdrant is responsive
curl -v http://localhost:6335/health

# Verify Meilisearch is responsive
curl -v http://localhost:7701/health
```

**Common causes & fixes**:

**A) Qdrant or Meilisearch briefly unavailable**
```
Symptom: Circuit breaker opened after 3-5 failed requests
```

**Fix**: Verify services healthy, restart circuit breaker
```bash
# Check service status
docker ps | grep -E "qdrant|meilisearch"

# If unavailable, restart
docker-compose -f docker-compose.standalone.yml restart qdrant meilisearch

# Wait for healthchecks to pass
sleep 30

# Circuit breaker automatically closes after cooldown period (default 60s)
# Or restart search-api to reset
docker-compose -f docker-compose.standalone.yml restart search-api

# Verify recovery
curl http://localhost:8010/api/v1/health
```

**B) Circuit breaker threshold too aggressive**
```
Symptom: Circuit breaker opens after 2-3 brief failures
Cause: Threshold set too low
```

**Fix**: Check circuit breaker configuration in application
```bash
# In kb_search_api source code, find:
# CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
# CIRCUIT_BREAKER_COOLDOWN_SECONDS = 60

# Adjust and rebuild if needed
# Then restart application
```

---

### Issue 6: Network Connectivity Issues

**Symptom**: "Connection refused", "Host unreachable", "name resolution failed"

**Diagnosis**:
```bash
# Test network connectivity
docker exec kb_search_api_service ping qdrant

# Test DNS resolution
docker exec kb_search_api_service nslookup qdrant

# Test port connectivity
docker exec kb_search_api_service curl -v http://qdrant:6333/health

# Check Docker network
docker network inspect kb_search_network | jq '.Containers'
```

**Common causes & fixes**:

**A) Service not on same Docker network**
```
Error: Name or service not known
```

**Fix**: Verify all services on kb_search_network
```bash
# Check which network each service is on
docker inspect kb_search_api_service --format='{{json .NetworkSettings.Networks}}'
docker inspect kb_search_qdrant --format='{{json .NetworkSettings.Networks}}'

# Both should show: {"kb_search_network":{...}}

# If not, restart the stack
docker-compose -f docker-compose.standalone.yml down
docker-compose -f docker-compose.standalone.yml up -d
```

**B) Docker DNS not working**
```
Error: Temporary failure in name resolution
```

**Fix**: Restart Docker daemon
```bash
# Linux
sudo systemctl restart docker

# macOS/Docker Desktop
# Quit Docker Desktop and restart

# After restart, bring up stack again
docker-compose -f docker-compose.standalone.yml up -d
```

**C) Port mapped incorrectly**
```
Error: Connection refused (port not open)
```

**Fix**: Verify port mapping in docker-compose.standalone.yml
```bash
# Expected mapping:
# qdrant: 6335:6333 (host:container)
# search-api: 8010:8000 (host:container)

# Check actual ports
docker port kb_search_api_service
docker port kb_search_qdrant

# If wrong, fix docker-compose.standalone.yml and restart
```

---

### Issue 7: API Responds 500 / 502 / 503

**Symptom**: Search endpoint returns HTTP 500 (server error), 502 (bad gateway), or 503 (unavailable)

**Diagnosis**:
```bash
# Check status code and response
curl -v -X POST http://localhost:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# Check application logs for error
docker logs kb_search_api_service | grep -i "error\|exception\|traceback"

# Check health endpoint
curl http://localhost:8010/api/v1/health
```

**Common causes & fixes**:

**A) Unhandled exception in search logic**
```
Error: 500 Internal Server Error
Logs: Traceback (most recent call last):...
```

**Fix**: Check logs, fix bug, restart
```bash
# Get full traceback
docker logs kb_search_api_service | grep -A 30 "Traceback"

# Example fix: If error is "KeyError: 'results'"
# File bug in GitHub, update code, rebuild
docker build -t kb_search_api:latest .
docker-compose -f docker-compose.standalone.yml up -d --build
```

**B) Dependency unavailable (Qdrant, Meilisearch, etc.)**
```
Error: 503 Service Unavailable
Logs: Could not connect to qdrant...
```

**Fix**: Restart dependency
```bash
# Identify which service is down
curl http://localhost:8010/api/v1/health | jq .dependencies

# Restart the unavailable service
docker-compose -f docker-compose.standalone.yml restart qdrant

# Wait for healthcheck
sleep 10

# Retry search
curl -X POST http://localhost:8010/api/v1/search \
  -d '{"query": "test"}'
```

**C) Database connection pool exhausted**
```
Error: 502 Bad Gateway (proxy error)
Logs: psycopg2.OperationalError: could not connect to server
```

**Fix**: Increase connection pool size
```bash
# Check current pool configuration
docker logs kb_search_api_service | grep -i "pool"

# In code, increase pool settings:
# pool_size = 10 (currently 5)
# max_overflow = 20 (currently 10)

# Rebuild and restart
docker build -t kb_search_api:latest .
docker-compose -f docker-compose.standalone.yml up -d --build
```

---

### Issue 8: Healthcheck Failing

**Symptom**: Container marked "Unhealthy" in docker ps

**Diagnosis**:
```bash
# Check health status
docker inspect kb_search_api_service --format='{{.State.Health.Status}}'

# Check health details
docker inspect kb_search_api_service | jq '.State.Health'

# Run healthcheck manually
curl http://localhost:8010/api/v1/health
```

**Common causes & fixes**:

**A) Service not fully started yet**
```
Symptom: Health check fails first 2-3 times, then passes
Cause: Normal startup sequence
```

**Fix**: Increase startup timeout
```bash
# In docker-compose.standalone.yml, add:
# healthcheck:
#   start_period: 30s  # Give 30s to start before checking
#   interval: 10s
#   timeout: 5s
#   retries: 5

docker-compose -f docker-compose.standalone.yml up -d
```

**B) Health endpoint returning error**
```
Symptom: Consistently unhealthy
Cause: Application error or dependency down
```

**Fix**: Debug health endpoint
```bash
# Test health endpoint directly
curl -v http://localhost:8010/api/v1/health

# Check logs
docker logs kb_search_api_service | tail -50

# Fix the issue (e.g., restart dependencies)
docker-compose -f docker-compose.standalone.yml restart
```

---

## Getting Help

### Gathering Debug Information

When reporting a bug, collect:

```bash
# 1. Docker status
docker-compose -f docker-compose.standalone.yml ps > debug_docker_status.txt

# 2. Container logs (all services)
for service in search-api postgresql meilisearch qdrant redis; do
  docker-compose -f docker-compose.standalone.yml logs --tail 50 $service >> debug_logs.txt
done

# 3. System info
docker stats --no-stream >> debug_stats.txt
df -h >> debug_disk.txt

# 4. Network info
docker network inspect kb_search_network >> debug_network.txt

# Create bug report with these files attached
```

### Common Debug Commands

```bash
# Restart all services
docker-compose -f docker-compose.standalone.yml restart

# Rebuild and restart
docker-compose -f docker-compose.standalone.yml up -d --build

# View logs in real-time
docker-compose -f docker-compose.standalone.yml logs -f search-api

# Execute command in container
docker exec kb_search_api_service curl http://postgresql:5432

# Get shell access
docker exec -it kb_search_api_service /bin/bash

# Check environment variables
docker exec kb_search_api_service env | grep -i "database\|qdrant\|meilisearch"
```

---

## Related Documentation

- [Deployment Guide](./DEPLOYMENT_GUIDE.md) — Setup and configuration
- [Health Monitoring](../MONITORING_SETUP_2026-04-19.md) — Alerting and health checks
- [Incident Response Runbook](../_infrastructure/INCIDENT_RESPONSE_RUNBOOK.md) — Major incident procedures
- [Resource Limits](../_infrastructure/RESOURCE_LIMITS.md) — Memory/CPU issues
- [Database Maintenance](../_infrastructure/DATABASE_MAINTENANCE.md) — Database issues

**Last updated**: 2026-04-19  
**Last reviewed**: 2026-04-19  
**Maintained by**: Knowledge Base Team
