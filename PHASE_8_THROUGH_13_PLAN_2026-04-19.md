# Next 30 Steps Plan — Phases 8-13 — Updated 2026-04-19

**Current Status**: Phase 7 complete, kb-search-api running on isolated ports  
**Starting Point**: Phase 8, Step 1 (Database Population)  
**Total Scope**: 30 steps, 6 phases, 15-20 hours  
**Target Completion**: 4-5 additional sessions

---

## Phase 8: Database Population & Configuration (Steps 1-5)

**Objective**: Seed database with test documents, configure LiteLLM, enable semantic search.  
**Time**: 2-3 hours | **Blocker**: None | **Risk**: Low

### Step 1: Create PostgreSQL Seed Documents
- **Action**: Create `seed_documents.sql` with 25+ test documents
- **Content**: Mix of internal/public/confidential documents from different owners
- **Fields**: id (UUID), title, content, owner, classification, status, created_date, topics
- **Example owners**: platform-eng, security, devops, ml-infra
- **Example classifications**: public, internal, confidential
- **File location**: `/c/kb-search-api/scripts/seed_documents.sql`
- **Verification**: `psql -h localhost -p 5433 -U kb_user -d kb_db -c "SELECT COUNT(*) FROM documents;"`
- **Expected output**: 25 (or more)
- **Estimated time**: 30 minutes

### Step 2: Load Documents into PostgreSQL
- **Command**: `psql -h localhost -p 5433 -U kb_user -d kb_db < scripts/seed_documents.sql`
- **Verify**: Connect and check document count
- **Check tables**: `\dt` to list tables, `SELECT * FROM documents LIMIT 1` to view
- **Verify all fields populated**: owner, classification, created_date, topics all have values
- **Document findings**: `SEED_LOAD_VERIFICATION_2026-04-19.md`
- **Estimated time**: 15 minutes

### Step 3: Populate Meilisearch Index
- **Update**: `seed_test_data.py` to read from PostgreSQL instead of hardcoded list
- **Logic**: Query `documents` table, build index payload with id, title, content, owner, classification, created_date, topics
- **Create index**: `meilisearch.index('documents').add_documents(docs)`
- **Run migration**: `python3 scripts/seed_test_data.py`
- **Verify**: Check Meilisearch index has documents
- **Command to verify**: `curl -H "Authorization: Bearer your-key" http://localhost:7700/indexes/documents/stats`
- **Expected**: Document count > 0, indexed_documents field populated
- **Estimated time**: 45 minutes

### Step 4: Configure LiteLLM API Key
- **Get API key**: User provides OpenAI API key or equivalent
- **Update environment**: Add to docker-compose.yml or `.env`:
  ```
  LITELLM_API_KEY=sk-...
  LITELLM_MODEL=text-embedding-3-small
  ```
- **Restart container**: `docker restart kb_search_api`
- **Test embedding**: Call `POST /api/v1/embeddings/reindex` with a sample doc_id
- **Verify**: Check logs for successful embedding generation
- **Estimated time**: 30 minutes

### Step 5: Regenerate Semantic Embeddings
- **Create**: `scripts/reindex_embeddings.py` to:
  1. Query all documents from PostgreSQL
  2. Call `embedding_service.embed_text(document.content)` for each
  3. Upsert to Qdrant with metadata
  4. Update `document.embedding_generated_at` timestamp
- **Run**: `python3 scripts/reindex_embeddings.py`
- **Monitor**: Watch logs for embedding progress
- **Verify**: `curl http://localhost:6335/collections/documents/points/count` (should match doc count)
- **Estimated time**: 60 minutes (depends on document count and API rate limits)

**Phase 8 Status**: ✅ Ready to start

---

## Phase 9: Owner Assignment & CI/CD Setup (Steps 6-10)

**Objective**: Assign owners, set up GitHub Actions, enable automated builds.  
**Time**: 2-2.5 hours | **Blocker**: Owner availability | **Risk**: Low-Medium

### Step 6: Identify Owner Candidates for kb-search-api
- **Create**: `OWNER_CANDIDATES_KB_SEARCH_API_2026-04-19.md`
- **Candidates**: 
  - Option A: Platform engineer with FastAPI experience (recommended)
  - Option B: New backend specialist hire
  - Option C: Shared ownership (2-person team)
- **Decision criteria**: Experience, availability, long-term commitment
- **Document**: Responsibility matrix, on-call expectations, escalation paths
- **Estimated time**: 30 minutes

### Step 7: Identify Owner Candidates for kb-web-ui
- **Create**: `OWNER_CANDIDATES_KB_WEB_UI_2026-04-19.md`
- **Candidates**:
  - Option A: React/TypeScript specialist (recommended)
  - Option B: Full-stack engineer (shares responsibility with kb-search-api owner)
  - Option C: Frontend team ownership (3+ engineers rotating)
- **Decision criteria**: Component expertise, UI/UX understanding, availability
- **Document**: Feature development roadmap, design system alignment, testing requirements
- **Estimated time**: 30 minutes

### Step 8: Create GitHub Actions Workflow for kb-search-api
- **File**: `/c/kb-search-api/.github/workflows/ci.yml`
- **Stages**:
  1. Lint: `ruff check src/` + `mypy src/ --strict`
  2. Test: `pytest tests/ -v --cov=src/ --cov-fail-under=80`
  3. Build Docker: `docker build -t kb-search-api:${GIT_SHA} .`
  4. Push: `docker push registry.example.com/kb-search-api:${GIT_SHA}` (if main branch)
  5. Security scan: `trivy image kb-search-api:${GIT_SHA}`
- **Triggers**: Every push to main, every PR to main, manual trigger
- **Document**: `CI_CD_SETUP_KB_SEARCH_API_2026-04-19.md`
- **Estimated time**: 60 minutes

### Step 9: Create GitHub Actions Workflow for kb-web-ui
- **File**: `/c/kb-web-ui/.github/workflows/ci.yml`
- **Stages**:
  1. Install: `npm ci` (clean install)
  2. Lint: `npm run lint` (eslint)
  3. Type check: `npm run type-check` (typescript)
  4. Test: `npm run test` (vitest)
  5. Build: `npm run build` (vite)
  6. Build Docker: `docker build -t kb-web-ui:${GIT_SHA} .` (optional)
  7. Deploy staging: Push to S3 or registry (optional)
- **Triggers**: Same as kb-search-api
- **Document**: `CI_CD_SETUP_KB_WEB_UI_2026-04-19.md`
- **Estimated time**: 45 minutes

### Step 10: Test and Verify CI/CD Pipelines
- **Create test PR**: Make minor code change to kb-search-api
- **Verify workflow runs**: Check GitHub Actions tab for running workflow
- **Verify stages pass/fail**: Lint, test, build all complete successfully
- **Document results**: `CI_CD_VERIFICATION_2026-04-19.md` with screenshots/logs
- **Fix any failures**: Resolve linting errors, test failures, etc.
- **Repeat for kb-web-ui**: Same verification process
- **Estimated time**: 45 minutes

**Phase 9 Status**: ✅ Ready to start (owner candidates should be identified first)

---

## Phase 10: Frontend Integration & Feature Work (Steps 11-15)

**Objective**: Connect frontend to backend, implement core UI features, test end-to-end.  
**Time**: 3-4 hours | **Blocker**: kb-search-api fully operational | **Risk**: Medium

### Step 11: Implement API Integration in kb-web-ui
- **File**: `src/services/searchService.ts`
- **Create function**:
  ```typescript
  const performSearch = async (
    query: string,
    filters?: SearchFilters,
    limit: number = 10,
    offset: number = 0
  ) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, filters, limit, offset, semantic_weight: 0.5 })
    });
    return response.json();
  };
  ```
- **Update SearchPage.tsx**: Call `performSearch()` on form submit
- **Update .env.example**: Add `REACT_APP_API_URL=http://localhost:8000/api/v1`
- **Test**: Type search in UI → verify results populate from backend
- **Document**: `API_INTEGRATION_GUIDE_KB_WEB_UI_2026-04-19.md`
- **Estimated time**: 60 minutes

### Step 12: Create FilterPanel Component
- **File**: `src/components/FilterPanel.tsx`
- **Features**:
  - Owner dropdown (values: platform-eng, security, devops, ml-infra)
  - Classification selector (radio: public, internal, confidential)
  - Status selector (radio: active, archived, deprecated)
  - Topics tag input (multi-select with autocomplete)
  - Apply/Clear buttons
- **Props**: `onFilterChange: (filters: SearchFilters) => void`
- **Integration**: Wire to SearchPage state, trigger new search on filter change
- **Test**: Select filters → search results update to show only filtered documents
- **Estimated time**: 90 minutes

### Step 13: Create DocumentDetailPage Component
- **File**: `src/pages/DocumentDetailPage.tsx`
- **Features**:
  - Query parameter: `?doc_id=<uuid>`
  - Fetch document via `GET /api/v1/docs/{doc_id}`
  - Display: title, owner, classification, created_date, content (full text)
  - Add sidebar with metadata: source, status, topics, updated_date
  - Back link to search results
- **Route**: Add to App.tsx: `<Route path="/detail/:doc_id" element={<DocumentDetailPage />} />`
- **Integration**: From SearchResults, click result → navigate to detail page
- **Test**: Click search result → detail page loads with full content
- **Estimated time**: 75 minutes

### Step 14: Implement Pagination Controls
- **Update**: `src/components/SearchResults.tsx`
- **UI Elements**:
  - Previous/Next buttons (disabled when at edges)
  - Current page indicator (e.g., "Page 1 of 5")
  - Jump-to-page input or numbered buttons (1, 2, 3, ...)
  - Items-per-page selector (10/25/50)
- **State management**: Track `currentPage`, `itemsPerPage`
- **API integration**: Calculate `offset = (currentPage - 1) * itemsPerPage`
- **Test**: Search → navigate pages → verify results change, no data duplication
- **Estimated time**: 60 minutes

### Step 15: Run End-to-End Test Flow
- **Scenario 1**: Search → view results → click result → view detail → back to search
- **Scenario 2**: Apply filters → see filtered results → paginate through pages
- **Scenario 3**: Change search query → verify filters reset or persist (as designed)
- **Scenario 4**: Test edge cases: empty results, single result, large result sets
- **Document**: `E2E_SEARCH_FLOW_TEST_2026-04-19.md` with pass/fail criteria
- **Capture**: Screenshots or video of working flow
- **Estimated time**: 60 minutes

**Phase 10 Status**: ✅ Ready to start (after Phase 8-9 complete)

---

## Phase 11: Memory & Documentation Finalization (Steps 16-20)

**Objective**: Clean up memory, finalize documentation, prepare for next session.  
**Time**: 1.5 hours | **Blocker**: None | **Risk**: Low

### Step 16: Audit Quarantine Directory
- **Review**: `/c/Users/ajame/.claude/projects/C--/memory/_QUARANTINE_2026-04-18/`
- **Count**: Files by type (md, txt, json, etc.)
- **Assess**: Which entries are valuable vs. which can be deleted
- **Restore**: Move valuable debugging info back to active memory
- **Document**: `QUARANTINE_AUDIT_2026-04-19.md` (what's in, why, retention period)
- **Set retention**: Schedule deletion for 2026-05-18 (30-day window)
- **Estimated time**: 30 minutes

### Step 17: Update MEMORY.md with Session Entries
- **Add new section**: "Session 2026-04-19 (Continuation 2)"
- **Document**:
  - Phase 7 completion summary
  - Phase 8-10 kickoff status
  - Owners assigned (if applicable)
  - Next session priorities
  - Key decisions made
- **Update index**: Ensure all new documents are linked
- **Verify**: All session files indexed and searchable
- **Estimated time**: 30 minutes

### Step 18: Create DEPLOYMENT_COMPLETE_2026-04-19.md
- **File**: `/c/_infrastructure/DEPLOYMENT_COMPLETE_2026-04-19.md`
- **Contents**:
  - Executive summary: "kb-search-api and kb-web-ui fully operational and integrated"
  - Deployment timeline: Phase 1-10 completion dates
  - System status snapshot: All services healthy, 0 critical errors
  - Testing summary: API tests passing, E2E flow verified
  - Owner transition plan: Who owns what going forward
  - SLO performance: p95 latency, cache hit rate, success rate
  - Key documents: Links to all status files, runbooks, operational guides
- **Estimated time**: 45 minutes

### Step 19: Create NEXT_SESSION_ROADMAP_2026-04-19.md
- **File**: `/c/_infrastructure/NEXT_SESSION_ROADMAP_2026-04-19.md`
- **Contents**:
  - Session objectives: "Verify Phase 8-10 functionality, begin Phase 11-13"
  - Critical path: Phase 8 database → Phase 9 owners → Phase 10 frontend → Phase 11 docs
  - Decision points: Owners accept, CI/CD stable, search features verified
  - Risk factors: Department marketing artisan timeout (deferred), webapp_core symlinks (deferred)
  - Quick reference: Container status, health endpoints, running services
  - Escalation path: Which owner handles what issues
- **Estimated time**: 30 minutes

### Step 20: Archive Session Transcript and Prepare Summary
- **Save**: Full transcript to `/c/_infrastructure/session_transcripts/session_2026-04-19_continuation_2.jsonl`
- **Create**: `SESSION_SUMMARY_2026-04-19_CONTINUATION_2.md`
- **Document**:
  - What was accomplished: Phase 7 complete (5 steps), Phase 8-13 planned
  - What remains: Phases 8-13 execution (30 steps)
  - Key decisions: Port remapping, filter fix implementation
  - Time investment: ~2.5 hours actual work + planning
  - Confidence level: High (infrastructure resolved, code ready)
  - Context usage: ~85% (good budget remaining)
- **Estimated time**: 30 minutes

**Phase 11 Status**: ✅ Ready to start (after Phase 10 complete)

---

## Phase 12: Search Optimization Phase 2 (Steps 21-25)

**Objective**: Implement pagination offset fix, optimize Meilisearch, add advanced features.  
**Time**: 2-2.5 hours | **Blocker**: Phase 8-9 complete | **Risk**: Medium

### Step 21: Implement Pagination Offset Fix
- **File**: `search_service.py:search()` method
- **Change**: Apply offset **after** RRF combination instead of before
- **Logic**:
  1. Fetch extra results from Meilisearch/Qdrant (limit * 2)
  2. Combine with RRF
  3. Apply offset: `combined[offset:offset+limit]`
- **Test**: offset=0, 5, 10 all return correct pages
- **Verify**: No duplicate results across pages
- **Estimated time**: 45 minutes

### Step 22: Optimize Meilisearch Index Configuration
- **Review**: Current index settings
- **Optimize**:
  - Adjust `searchableAttributes`: Prioritize title over content
  - Configure `sortableAttributes`: Add owner, created_date for sorting
  - Tune `filterableAttributes`: Ensure all filter fields are indexed
  - Set ranking rules: Optimize relevance scoring
- **Benchmark**: Measure query latency before/after
- **Expected improvement**: 10-20% latency reduction
- **Document**: `MEILISEARCH_OPTIMIZATION_2026-04-19.md`
- **Estimated time**: 60 minutes

### Step 23: Add Query Expansion & Advanced Search Features
- **Feature 1**: Typo tolerance (fuzzy matching)
- **Feature 2**: Multi-field search (search across title, content, owner)
- **Feature 3**: Faceted navigation (filters displayed as counts)
- **Feature 4**: Search suggestions/autocomplete
- **Implementation**: Update Meilisearch settings + frontend UI
- **Test**: Verify fuzzy matching, multi-field, facets all work
- **Estimated time**: 75 minutes

### Step 24: Implement Cache Pre-warming for Common Queries
- **Identify**: Top 10 most common queries (from logs)
- **Script**: `scripts/warmup_cache.py` to pre-populate Redis cache
- **Run**: On service startup or scheduled task
- **Expected benefit**: Cache hit rate 70%+ for common queries
- **Measure**: Track cache hit ratio before/after
- **Estimated time**: 45 minutes

### Step 25: Create Performance Optimization Report
- **File**: `PERFORMANCE_OPTIMIZATION_PHASE_2_2026-04-19.md`
- **Contents**:
  - Pagination offset fix: Before/after metrics
  - Meilisearch optimization: Latency improvements
  - Advanced features: Implementation details, usage examples
  - Cache performance: Hit rate, warm-up effectiveness
  - Recommendations: Next optimizations (semantic search tuning, etc.)
- **Estimated time**: 30 minutes

**Phase 12 Status**: Ready to start (after Phase 8-9)

---

## Phase 13: Post-Deployment Review & Planning (Steps 26-30)

**Objective**: Review deployment, gather feedback, plan Q2 priorities.  
**Time**: 2 hours | **Blocker**: All systems operational | **Risk**: Low

### Step 26: Schedule Post-Deployment Review Meeting
- **Date/Time**: May 3, 2026, 10:00 AM (2 weeks post-Phase 1 deployment)
- **Duration**: 60 minutes
- **Attendees**: kb-search-api owner, kb-web-ui owner, infra lead, stakeholders
- **Create**: `POST_DEPLOYMENT_REVIEW_AGENDA_2026-05-03.md`
- **Agenda topics**:
  1. Lessons learned (what went well, what was hard)
  2. SLO achievement (latency, availability, cache hit rate)
  3. Operational experience (on-call, incident response)
  4. Feature feedback (missing features, user requests)
  5. Performance observations (bottlenecks, optimization opportunities)
  6. Q2 priorities (roadmap, team capacity)
  7. Infrastructure health (costs, resource utilization)
  8. Team feedback (process improvements, tool needs)
- **Send calendar invite**: To all attendees
- **Estimated time**: 45 minutes

### Step 27: Create Pre-Meeting Survey
- **File**: `POST_DEPLOYMENT_SURVEY_2026-05-03.md`
- **Questions** (8-10):
  1. Deployment experience: Smooth / Moderate / Challenging
  2. Documentation quality: Adequate / Needs improvement / Excellent
  3. Operational confidence: 1-10 scale
  4. Monitoring effectiveness: Can you spot issues proactively?
  5. Scaling concerns: Any bottlenecks observed?
  6. Incident response readiness: Tested? Confident?
  7. Top missing features: List 3 priorities
  8. Team feedback: What should we do differently?
- **Send**: 1 week before meeting
- **Analyze**: Summarize feedback for discussion
- **Estimated time**: 30 minutes

### Step 28: Create Q2 Roadmap Based on Feedback
- **File**: `Q2_2026_ROADMAP_KB_SEARCH_API_2026-05-03.md`
- **Sections**:
  - High-priority features (from feedback)
  - Performance optimizations (identified bottlenecks)
  - Operational improvements (runbooks, automation)
  - Team scaling (hiring, training needs)
  - Infrastructure upgrades (capacity planning)
- **Timeline**: Break into May (1-2 weeks post-review), June (mid-quarter)
- **Resource allocation**: Estimate team capacity needed
- **Estimated time**: 60 minutes

### Step 29: Document Operational Handoff & Training
- **File**: `OPERATIONAL_HANDOFF_2026-05-03.md`
- **Contents**:
  - Owner responsibilities checklist
  - On-call procedure & escalation paths
  - Runbooks for common tasks (restart service, clear cache, scale up)
  - Alert response procedures (what to do when alert fires)
  - Disaster recovery (restore from backup, switch regions)
  - Team training: Do team members know the systems?
- **Training sessions**: Schedule if needed (1-2 hours)
- **Estimated time**: 60 minutes

### Step 30: Final Deployment Summary & Archive
- **Create**: `DEPLOYMENT_FINAL_SUMMARY_2026-05-03.md`
- **Contents**:
  - Project completion status: 100% deployed and operational
  - Metrics summary: Performance, reliability, adoption
  - Team feedback: Key learnings, team morale
  - Financial summary: Infrastructure costs, ROI
  - Next steps: Q2 roadmap, future expansion plans
- **Archive**: Move all session documents to `/c/_infrastructure/session_archives/2026-04-19/`
- **Update**: ROOT status file with final numbers
- **Celebration**: Acknowledge team, celebrate milestone
- **Estimated time**: 45 minutes

**Phase 13 Status**: Ready to start (2 weeks after Phase 10 deployment)

---

## Summary: Phases 8-13 (30 Steps)

| Phase | Objective | Steps | Time | Dependency |
|-------|-----------|-------|------|------------|
| **8** | Database & Config | 1-5 | 2-3h | Phase 7 ✅ |
| **9** | Owners & CI/CD | 6-10 | 2-2.5h | Phase 8 |
| **10** | Frontend & Features | 11-15 | 3-4h | Phase 8-9 |
| **11** | Docs & Memory | 16-20 | 1.5h | Phase 10 |
| **12** | Optimization Ph2 | 21-25 | 2-2.5h | Phase 8-9 |
| **13** | Post-Review | 26-30 | 2h | All phases |

**Total**: ~15-20 hours over 4-5 additional sessions

---

## Execution Strategy

### Recommended Pacing
- **Session 2** (next): Phase 8 (database) + Phase 9 start (3-4 hours)
- **Session 3**: Phase 9 complete + Phase 10 start (4 hours)
- **Session 4**: Phase 10 complete + Phase 11 (3-4 hours)
- **Session 5**: Phase 12 + early Phase 13 planning (3 hours)
- **Session 6** (optional): Phase 13 execution + Q2 planning (2-3 hours)

### Parallel Work Opportunities
- Phase 9 (owners/CI) can start while Phase 8 (database) is running
- Phase 12 (optimization) can run in parallel with Phase 10 if needed
- Phase 11 (docs) is lightweight and can be done anytime after Phase 10

### Decision Gates
- **After Phase 8**: Database verified, search working
- **After Phase 9**: Owners assigned, CI/CD tested
- **After Phase 10**: Frontend fully integrated, E2E flow verified
- **Before Phase 13**: All systems stable for 1 week

---

## Success Criteria (End of Phase 13)

✅ **Deployment Complete**
- kb-search-api: Operational, SLOs met, owner assigned, CI/CD working
- kb-web-ui: Operational, integrated, owner assigned, CI/CD working
- Database: Populated, all queries working, backup automated
- Monitoring: Alerts configured, dashboards live, team trained

✅ **Code Quality**
- Tests: >80% coverage, all passing
- Linting: Clean (ruff, mypy, eslint all pass)
- Documentation: Complete (API docs, runbooks, architecture)
- Code review: All PRs reviewed by owners

✅ **Operational Excellence**
- SLOs: p95 <1000ms, 99.5%+ availability, >70% cache hit rate
- Performance: Optimized, no obvious bottlenecks
- Security: Credentials managed, no hardcoded secrets
- Scaling: Ready for 10x load, horizontal scaling plan in place

✅ **Team Readiness**
- Owners: Assigned, trained, confident
- On-call: Procedure documented, team ready
- Escalation: Clear paths for incidents, emergency contacts listed
- Q2 priorities: Defined, communicated, resource allocated

---

**Plan Created**: 2026-04-19  
**Plan Type**: Updated post-Phase-7 with lessons learned  
**Total Scope**: 30 steps, 6 phases, 15-20 hours  
**Next Checkpoint**: End of Phase 8 (database populated)  
**Final Checkpoint**: End of Phase 13 (post-review meeting, 2026-05-03)
