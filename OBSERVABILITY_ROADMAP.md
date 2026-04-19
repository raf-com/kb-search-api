# kb-search-api Observability Roadmap

**Created**: 2026-04-19  
**Status**: Phase 1 Complete (Metrics & Logs), Phase 2-3 Planned

---

## Current Implementation (2026-04-19)

### ✓ Metrics (Prometheus)
- Container metrics: CPU, memory, network I/O
- Application metrics: Request rate, latency, error rate (via health checks)
- Logs: Streaming to Loki via Promtail

### ✓ Logs (Loki)
- Container logs: STDOUT/STDERR captured automatically
- Log retention: 7 days
- Searchable via Grafana

### ✓ Dashboards (Grafana)
- Real-time monitoring: 9 panels covering health, latency, errors, resource usage
- Alert thresholds configured for critical metrics

---

## Phase 2: Distributed Tracing (Step 19)

### Planned: OpenTelemetry Integration

**Objective**: Trace request flow across multiple services  
**Timeline**: 2026-05-19 (after load testing)

**Components**:
- FastAPI instrumentation (auto-trace HTTP requests)
- PostgreSQL trace (query latency)
- Redis trace (cache operations)
- Meilisearch trace (search operations)
- Qdrant trace (vector DB operations)

**Implementation**:
1. Add OpenTelemetry dependencies to requirements.txt
2. Instrument FastAPI app with `OpenTelemetry FastAPI instrumentor`
3. Send traces to Jaeger (if available) or OTEL Collector
4. Create Jaeger dashboard for request tracing

**Example trace**:
```
Search Request (200ms total)
├── Validate request (10ms)
├── Query cache (5ms) - MISS
├── Search Meilisearch (80ms)
├── Search Qdrant (70ms)
├── Combine results (20ms)
├── Store in cache (5ms)
└── Return response (10ms)
```

---

## Phase 3: Custom Metrics (Future)

**Planned metrics** (align with application domain):
- `kb_search_total` - Total searches performed
- `kb_search_cache_bypass` - Searches that bypassed cache
- `kb_search_result_count` - Distribution of result sizes
- `kb_indexing_duration_seconds` - Time to index documents
- `kb_circuit_breaker_state` - State of circuit breaker (0=closed, 1=open, 2=half-open)
- `kb_embedding_latency_seconds` - Time to generate embeddings

**Implementation**: Add Prometheus client library to kb-search-api and expose `/metrics` endpoint

---

## Performance Testing Roadmap (Step 20)

### Load Testing Plan

**Tool**: k6 or Locust  
**Scenarios**:
1. Ramp-up: 0→100 concurrent users over 5min
2. Sustained: 100 concurrent users for 15min
3. Spike: Sudden jump to 200 concurrent users
4. Realistic: Mixed workload (search + document insert)

**Metrics to measure**:
- Latency (p50, p95, p99)
- Throughput (requests/sec)
- Error rate
- Resource usage (memory, CPU)
- Cache hit rate under load

**Success criteria**:
- p95 latency < 1000ms under 100 concurrent users
- Error rate < 1%
- Memory stays under 400 MB
- CPU peaks < 90%

---

## Monitoring Stack Architecture

```
Application (kb-search-api)
    ├── Metrics → Prometheus (:9090)
    ├── Logs → Promtail → Loki (:3100)
    └── Traces → OpenTelemetry Collector → Jaeger (:16686)

Visualization:
    └── Grafana (:3000)
         ├── Prometheus datasource
         ├── Loki datasource
         └── Jaeger datasource

Alerting:
    └── Alertmanager (:9093)
         ├── Slack notifications
         ├── PagerDuty escalation
         └── Custom webhooks
```

---

## Observability Checklist

- [x] Metrics collection (Prometheus)
- [x] Log aggregation (Loki)
- [x] Dashboard creation (Grafana)
- [x] Alert rules configured (Alertmanager)
- [ ] Distributed tracing (OpenTelemetry) — Phase 2
- [ ] Custom metrics (app-specific) — Phase 3
- [ ] Load testing (performance baseline) — Phase 4
- [ ] SLO tracking dashboard — Phase 4
- [ ] Automated runbooks — Phase 4

---

## References

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Prometheus Instrumentation Guide](https://prometheus.io/docs/guides/python-prometheus/)
- [k6 Load Testing Guide](https://k6.io/docs/)

**Last updated**: 2026-04-19  
**Target completion**: Phases 2-3 by 2026-06-19
