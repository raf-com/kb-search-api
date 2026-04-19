# Phases 8-13 Execution Guide — Quick Reference

## At a Glance

**30 steps organized as 6 phases × 5 steps each**. Total effort: 15-20 hours over 4-5 sessions.

```
Phase 8 (Steps 1-5)         Phase 9 (Steps 6-10)        Phase 10 (Steps 11-15)
Database & Configuration    Owners & CI/CD              Frontend Integration
┌─────────────────┐        ┌──────────────────┐        ┌────────────────────┐
│ Seed Postgres   │        │ Owner Candidates │        │ API Integration    │
│ Load Data       │        │ CI/CD kb-search  │        │ Filter Panel       │
│ Populate Index  │        │ CI/CD kb-web-ui  │        │ Detail Page        │
│ LiteLLM Config  │        │ Test Workflows   │        │ Pagination         │
│ Regenerate Emb  │        │ Verify Pipelines │        │ E2E Testing        │
└─────────────────┘        └──────────────────┘        └────────────────────┘
        │                           │                         │
        └───────────────────────────┴─────────────────────────┘
                          Prerequisite for Phase 12

    Phase 11 (Steps 16-20)     Phase 12 (Steps 21-25)    Phase 13 (Steps 26-30)
    Memory & Documentation     Optimization Phase 2      Post-Review Planning
    ┌─────────────────────┐   ┌─────────────────────┐   ┌────────────────────┐
    │ Audit Quarantine    │   │ Pagination Fix      │   │ Schedule Review    │
    │ Update MEMORY.md    │   │ Meilisearch Tuning  │   │ Pre-Meeting Survey │
    │ DEPLOYMENT_COMPLETE │   │ Advanced Features   │   │ Q2 Roadmap         │
    │ NEXT_SESSION_ROADMAP│   │ Cache Pre-warming   │   │ Handoff & Training │
    │ Archive Transcript  │   │ Optimization Report │   │ Final Summary      │
    └─────────────────────┘   └─────────────────────┘   └────────────────────┘
```

## Which Chunk to Execute First?

**Recommended: Phase 8 (Database Population)** ← Start here

- **Why**: Unblocks Phase 9-10, enables testing of filter fix, quick win
- **Time**: 2-3 hours
- **Dependencies**: None (kb-search-api already running)
- **Risk**: Low

### Execution Path (Sequential)

**Session 2** (3-4 hours):
- Phase 8: Steps 1-5 (database & config) ✅
- Phase 9: Step 6-7 (start owner assignment) — 30 min

**Session 3** (4 hours):
- Phase 9: Steps 8-10 (CI/CD setup, test) ✅
- Phase 10: Steps 11-12 (API integration, filters) — start

**Session 4** (3-4 hours):
- Phase 10: Steps 13-15 (detail page, pagination, E2E) ✅
- Phase 11: Steps 16-17 (quarantine, memory) — start

**Session 5** (3 hours):
- Phase 11: Steps 18-20 (deployment summary, roadmap) ✅
- Phase 12: Steps 21-22 (pagination fix, optimization) — start

**Session 6** (2-3 hours, optional):
- Phase 12: Steps 23-25 (advanced features, reporting) ✅
- Phase 13: Steps 26-30 (post-review planning) — 1-2 weeks later

---

## Chunk Sizes & Time Estimates

| Phase | Steps | Est. Time | Complexity | Blockers |
|-------|-------|-----------|------------|----------|
| **8** | 1-5 | 2-3h | Low | None |
| **9** | 6-10 | 2-2.5h | Medium | Owner availability |
| **10** | 11-15 | 3-4h | High | Phases 8-9 complete |
| **11** | 16-20 | 1.5h | Low | Phase 10 complete |
| **12** | 21-25 | 2-2.5h | Medium | Phases 8-9 complete |
| **13** | 26-30 | 2h | Low | All systems stable |

---

## Critical Path vs. Optional Work

### Critical Path (Must Do)
- Phase 8: Database seeding + Meilisearch population ← **Unblocks everything**
- Phase 9: Owner assignment + CI/CD (enables team handoff)
- Phase 10: Frontend integration (validates system end-to-end)
- Phase 11: Documentation + memory (keeps next session efficient)

### High-Value (Should Do)
- Phase 12: Pagination fix (enables pagination to work)
- Phase 12: Meilisearch optimization (improves performance)

### Nice-to-Have (Can Defer)
- Phase 12: Advanced features (typo tolerance, query expansion)
- Phase 12: Cache pre-warming (optimization, not critical)
- Phase 13: Post-review meeting (important but can be rescheduled)

---

## Key Decisions & Gates

### Before Phase 8 Starts
- ✅ kb-search-api running? Check: `curl http://localhost:8000/api/v1/health`
- ✅ PostgreSQL accessible? Check: `psql -h localhost -p 5433 -U kb_user -d kb_db -c "\dt"`

### After Phase 8 Complete (Gate 1)
- ✅ Documents in PostgreSQL? `SELECT COUNT(*) FROM documents;` → should be 25+
- ✅ Meilisearch populated? `curl -H "Authorization: Bearer ..." http://localhost:7700/indexes/documents/stats` → document_count > 0
- ✅ LiteLLM configured? Test embedding generation
- ✅ Qdrant populated? `curl http://localhost:6335/collections/documents` → point_count > 0
- **Decision**: Proceed to Phase 9 if all checks pass, else debug

### After Phase 9 Complete (Gate 2)
- ✅ CI/CD workflows running? GitHub Actions status shows green checkmarks
- ✅ Owners assigned? Document them in MEMORY.md
- **Decision**: Proceed to Phase 10

### After Phase 10 Complete (Gate 3)
- ✅ Frontend loads? `http://localhost:3000` → Search UI renders
- ✅ E2E flow works? Search → results → detail page → back
- ✅ No console errors? Browser DevTools shows clean console
- **Decision**: Phase 10 validated, ready for production

### Before Phase 13 (Gate 4)
- ✅ All systems stable for 7 days? No critical incidents
- ✅ SLOs met? Review metrics in Grafana
- ✅ Team trained? Owners confident in operations
- **Decision**: Schedule post-deployment review meeting

---

## Success Criteria (By Phase)

### Phase 8 Success ✅
- PostgreSQL: 25+ documents loaded, all fields populated
- Meilisearch: Index created, documents indexed, queries returning results
- LiteLLM: API key configured, embedding generation working
- Qdrant: Embeddings stored, collection queryable

### Phase 9 Success ✅
- Owners: Named for both projects, responsibilities clear
- CI/CD: Both projects have automated test/build/deploy pipelines
- Workflows: GitHub Actions green for test PR on both projects

### Phase 10 Success ✅
- API Integration: Frontend can search and display results
- UI Features: Filters, detail page, pagination all working
- E2E Flow: Complete user journey working without errors
- No Regressions: Existing functionality still works

### Phase 11 Success ✅
- Memory: Updated with current session info, all files indexed
- Documentation: DEPLOYMENT_COMPLETE and NEXT_SESSION_ROADMAP created
- Archive: Session transcript saved, previous quarantine audited

### Phase 12 Success ✅
- Pagination: Offset parameter works for all page numbers
- Performance: Meilisearch optimized, measurable latency improvement
- Features: Query expansion, typo tolerance, facets implemented

### Phase 13 Success ✅
- Review: Meeting scheduled, agenda finalized, pre-survey sent
- Feedback: Team input gathered, Q2 priorities defined
- Handoff: Operations runbook complete, team trained and confident

---

## Command Reference

### Database Operations
```bash
# Connect to PostgreSQL
psql -h localhost -p 5433 -U kb_user -d kb_db

# Check document count
psql -h localhost -p 5433 -U kb_user -d kb_db -c "SELECT COUNT(*) FROM documents;"

# Load seed data
psql -h localhost -p 5433 -U kb_user -d kb_db < scripts/seed_documents.sql
```

### Meilisearch Operations
```bash
# Get master key from docker-compose
grep MEILI_MASTER_KEY docker-compose.yml

# Check indexes
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:7700/indexes

# Check index stats
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:7700/indexes/documents/stats
```

### Search API Testing
```bash
# Health check
curl http://localhost:8000/api/v1/health

# Search without filters
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "database", "limit": 10}'

# Search with filters (tests filter fix)
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "database", "filters": {"owner": "platform-eng"}}'

# Test pagination
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "database", "limit": 5, "offset": 5}'
```

### Docker Operations
```bash
# Check container status
docker ps | grep kb_

# View logs
docker logs kb_search_api -f
docker logs kb_meilisearch -f
docker logs kb_postgresql -f

# Restart service
docker restart kb_search_api
```

---

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| PostgreSQL connection error | Check connection string uses port 5433 |
| Meilisearch "no auth header" | Add `-H "Authorization: Bearer YOUR_KEY"` to curl |
| Qdrant unhealthy | Health check timeout, service still functional |
| Frontend can't reach API | Check `REACT_APP_API_URL` in .env, CORS headers |
| Search returns 0 results | Check Meilisearch index populated, documents have fields |
| Pagination offset broken | Implement fix in Step 21 (Phase 12) |
| CI/CD workflow fails | Check linting errors: `ruff check src/` or `npm run lint` |

---

## Resource Requirements

### Disk Space
- PostgreSQL: ~100MB (for 25-50 documents)
- Meilisearch: ~50MB (index data)
- Qdrant: ~100MB (embeddings)
- Docker images: ~1GB (already built)
- Total: ~1.5GB

### CPU/Memory
- kb_search_api: 1 CPU, 512MB RAM (comfortable)
- PostgreSQL: 1 CPU, 256MB RAM
- Meilisearch: 0.5 CPU, 256MB RAM
- Qdrant: 0.5 CPU, 256MB RAM
- Total: 3 CPU, ~1.5GB RAM (all running simultaneously)

### Network
- All services on local Docker bridge (internal)
- External APIs: OpenAI (for embeddings, if LiteLLM enabled)
- GitHub Actions: Minimal (just CI/CD logs)

---

## Session Planning Template

Use this for each session:

```
# Session N: Phase X [START DATE-TIME]

## Objectives
- [ ] Step 1: [Description]
- [ ] Step 2: [Description]
- [ ] Step 3: [Description]

## Prerequisites Met
- [ ] kb-search-api running
- [ ] Previous phase complete
- [ ] Required credentials available

## Success Criteria
- [ ] All steps executed
- [ ] All tests passing
- [ ] Documentation updated

## Time Tracking
- Started: [TIME]
- Completed: [TIME]
- Total: [DURATION]

## Blockers Encountered
- [None / List any]

## Next Session Priorities
- [Step X]
- [Step Y]
```

---

**Plan Created**: 2026-04-19  
**Total Scope**: 30 steps, 6 phases, 15-20 hours  
**Recommended Pace**: 1 phase per session (5-7 steps per session)  
**Expected Completion**: 4-5 additional sessions after this one  
**Next Checkpoint**: After Phase 8 (database populated)  
**Final Checkpoint**: 2026-05-03 (post-deployment review meeting)
