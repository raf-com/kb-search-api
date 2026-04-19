# kb-search-api Performance SLOs & Baselines

**Created**: 2026-04-19  
**Updated**: 2026-04-19

---

## Service Level Objectives (SLOs)

### Availability SLO

**Target**: 99.5% uptime  
**Error budget**: 21.6 minutes/month or 3.65 hours/year  
**Measurement**: `(time_service_up / total_time) * 100`

**Acceptable downtime**:
- Per day: 43 seconds
- Per week: 5 minutes
- Per month: 21.6 minutes
- Per quarter: 65 minutes

### Latency SLO

**Target (Search queries)**:
- p50 (median): <300ms
- p95: <1000ms (1 second)
- p99: <2000ms (2 seconds)

**Measurement**: HTTP request duration histogram from Prometheus

### Success Rate SLO

**Target**: ≥99% of search requests return results successfully  
**Definition**: HTTP 200 response with non-empty result set  
**Measurement**: `(successful_searches / total_searches) * 100`

### Cache Hit Rate

**Target**: ≥70% of repeated searches served from cache  
**Measurement**: Redis cache hits / (hits + misses)

---

## Performance Baselines (2026-04-19)

### Under No Load (Idle)

| Metric | Value | Status |
|--------|-------|--------|
| API Response | 200 OK | ✓ Healthy |
| p50 Latency | <100ms | ✓ Excellent |
| p95 Latency | <200ms | ✓ Excellent |
| Memory | 150-180 MB | ✓ Normal |
| CPU | 2-5% | ✓ Idle |
| Cache Hit Rate | N/A | - |

### Under Moderate Load (10 req/sec)

[To be populated after load testing - Step 20]

| Metric | Value | Status |
|--------|-------|--------|
| API Response | 200 OK | TBD |
| p50 Latency | TBD | TBD |
| p95 Latency | TBD | TBD |
| Memory | TBD | TBD |
| CPU | TBD | TBD |
| Cache Hit Rate | TBD | TBD |

### Under Heavy Load (100 req/sec)

[To be populated after load testing - Step 20]

---

## Tracking SLO Compliance

### Monthly Review

1. Calculate availability: `uptime_minutes / (30 * 24 * 60) * 100`
2. Check latency percentiles: p50, p95, p99
3. Calculate success rate: `successful_requests / total_requests * 100`
4. Review error budget spent

### If SLO Breached

1. **Immediate**: Document incident (severity, duration, root cause)
2. **Within 24h**: Post-mortem meeting
3. **Within 1 week**: Implement fixes
4. **Quarterly**: Review SLO targets (may need adjustment)

### SLO Dashboard (Future)

Create Grafana dashboard showing:
- Cumulative uptime % (rolling 30 days)
- Availability error budget remaining
- Latency trend (p50/p95/p99)
- Success rate %
- Incidents affecting SLO compliance

---

## Scaling Targets

### Tier 1: Single Instance (Current)
- Concurrent users: 10-20
- Requests/sec: <10
- Resource limits: 1 CPU, 512 MB RAM

### Tier 2: Horizontal Scaling (100 users)
- Concurrent users: 50-100
- Requests/sec: 50-100
- Resource limits: 2 CPUs, 1 GB RAM per instance
- Number of instances: 2-3 behind load balancer

### Tier 3: Multi-Region (1000 users)
- Concurrent users: 500-1000
- Requests/sec: 500-1000
- Resource limits: 4 CPUs, 2 GB RAM per instance
- Number of instances: 5-10 per region
- Database: Sharded PostgreSQL, distributed cache

---

## References

- [SLO Engineering Guide](https://sre.google/sre-book/service-level-objectives/)
- [Prometheus Uptime Calculation](https://prometheus.io/docs/practices/alerting/)

**Last updated**: 2026-04-19  
**Next review**: 2026-05-19 (after load testing completes)
