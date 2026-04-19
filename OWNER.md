# KB-Search-API Ownership

## Owner
**Primary**: ajame  
**Escalation**: [TBD - assign team lead]  

## Maintenance Expectations

### Code Review Process
- All pull requests require review from the owner
- Changes to circuit breaker, caching, or database logic require additional verification
- API contract changes (endpoints, request/response schema) require design review

### Production Support
- Owner is responsible for monitoring kb-search-api health in production
- Response time SLA: 1 hour for critical issues (service down)
- Response time SLA: 4 hours for non-critical issues (degraded performance)
- On-call rotation: [TBD]

### Maintenance Schedule
- Weekly: Review error logs and performance metrics
- Monthly: Review dependency updates and security patches
- Quarterly: Capacity planning and load testing

## Escalation Path
1. First contact: ajame (primary owner)
2. Second contact: [Team lead name] (escalation)
3. Emergency: [Operations team contact]

## Related Documentation
- API Contract: `API_CONTRACT.md`
- Integration Guide: `INTEGRATION_GUIDE.md`
- Deployment Readiness: `DEPLOYMENT_READINESS.md`
- Architecture: `README.md`

## Key Metrics to Monitor
- Response time (p50, p95, p99)
- Error rate (5xx responses)
- Cache hit rate
- Circuit breaker state (open/closed/half-open)
- Database connection pool utilization

## Onboarding New Owners
1. Read `README.md` for architecture overview
2. Read `OWNER.md` (this file) for responsibilities
3. Review `API_CONTRACT.md` to understand endpoints
4. Run local tests: `pytest tests/ -v`
5. Start with code review responsibilities
6. Shadow on-call for 1 week before taking ownership

---

**Last Updated**: 2026-04-19  
**Status**: Active
