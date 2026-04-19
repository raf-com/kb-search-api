# Next 30 Steps Plan — Phases 6-11 — 2026-04-19

**Scope**: Continuation of kb-search-api and kb-web-ui deployment and integration. Divided into 6 manageable phases (5 steps each), designed for sequential execution with natural breakpoints.

---

## Phase 6: Department Marketing Investigation (Steps 1-5)

**Objective**: Diagnose and document PHP 8.2 environment issues; identify blocker severity for Laravel ecosystem work.

### Step 1: Verify PHP Environment
- Check PHP version: `php --version` (expect 8.2.30)
- List enabled extensions: `php -m | grep -E "(curl|json|pdo|pdo_mysql|mbstring)"`
- Check php.ini settings: `php -i | grep -E "(memory_limit|max_execution_time|error_reporting)"`
- Document findings in `DEPT_MARKETING_PHP_ENV_2026-04-19.md`

**Expected outcome**: Baseline PHP environment inventory; any missing extensions identified.

### Step 2: Diagnose Artisan Bootstrap Timeout
- Measure artisan load time with timeout: `timeout 60 php artisan --version`
- Enable verbose timing: `time php artisan --version 2>&1 | head -50`
- Check for hanging file/module loads: `strace -e openat php artisan --version 2>&1 | tail -30`
- Document timeout behavior: command name, phase where timeout occurs, wall-clock duration

**Expected outcome**: Pinpoint whether timeout is in command discovery, Composer autoloading, or service provider initialization.

### Step 3: Analyze Bootstrap Logs
- Run artisan with debug output: `php artisan tinker --version 2>&1`
- Check service provider order: `php artisan tinker` then `Artisan::command('list')` to list providers
- Look for slow/problematic providers in `config/app.php`
- Document provider startup times and any deprecation notices

**Expected outcome**: Identify which service providers (if any) are causing delays.

### Step 4: Test Laravel Bootability
- Attempt to access Laravel routes directly via PHP: Create a test script that boots Laravel and queries routes
- Run database migrations (if safe): `php artisan migrate --dry-run` (observe behavior without committing)
- Check Laravel version and compatibility: `php artisan --version` vs package.json Laravel requirement
- Document any PHP 8.2 parse errors encountered (should be resolved per CLAUDE.md)

**Expected outcome**: Confirmed whether artisan bootstrap is solvable or OS-level blocker.

### Step 5: Summarize Phase 6 Findings
- Create `DEPT_MARKETING_INVESTIGATION_SUMMARY_2026-04-19.md` documenting:
  - PHP environment inventory (extensions, config, version)
  - Artisan bootstrap timeout root cause (if found)
  - Paths forward: (A) Skip artisan-dependent tasks for now, (B) Work around via direct PHP, (C) Defer to owner
  - Recommendations for department_marketing project owner
  - Next steps for GROUP 5 (Mailgun verification) if artisan is unblocked

**Expected outcome**: Complete diagnosis with clear recommendation for proceeding or deferring.

---

## Phase 7: Search Optimization & Fixes (Steps 6-10)

**Objective**: Investigate and resolve known search issues (filter syntax, pagination, performance); document optimization opportunities.

### Step 6: Debug Filter Syntax Issue
- **Test case**: Search with owner filter should return results, currently returns 0
  - Syntax: `curl -X POST http://localhost:8000/api/v1/search -d '{"query": "database", "filters": {"owner": "platform-eng"}}'`
- Check Meilisearch filter expression generated: Add debug logging to `_build_meilisearch_filter()`
- Verify Meilisearch index has `owner` field: `curl http://localhost:6700/indexes/documents/settings`
- Test filter directly in Meilisearch CLI: `meilisearch-http GET /indexes/documents/search?q=database&filter=owner%3Dplatform-eng`
- Root cause options: (A) field missing in index, (B) filter syntax wrong, (C) no documents in index match filter, (D) RRF logic wrong

**Expected outcome**: Identified root cause of filter returning empty results.

### Step 7: Fix Filter Implementation (if needed)
- If root cause is syntax: Update `_build_meilisearch_filter()` with correct Meilisearch filter DSL
- If root cause is missing field: Verify seed_test_data.py includes owner field and re-seed
- If root cause is RRF logic: Review `_reciprocal_rank_fusion()` to ensure filters don't cause deduplication loss
- Test fixed implementation: `curl` command with owner/classification/status filters
- Verify search with multiple filters: `{"owner": "platform-eng", "classification": "internal"}`

**Expected outcome**: Filter syntax working; search with filters returns expected results.

### Step 8: Fix Pagination Offset Issue
- **Test case**: `offset=0` works, `offset=5` returns 0 results
  - Root cause analysis: Check if offset is applied before or after RRF deduplication
  - Current code path: `search_service.py:87-110` — offset applied at Meilisearch/Qdrant level, not RRF output
  - Hypothesis: Offset applied too early, RRF deduplication causes fewer results than limit
- Fix strategy: Apply offset to **final RRF-combined results** rather than individual search sources
- Test: `curl -X POST http://localhost:8000/api/v1/search -d '{"query": "database", "limit": 5, "offset": 0}'` (works) vs `offset=5` (should work after fix)

**Expected outcome**: Pagination with offset working; all result page numbers accessible.

### Step 9: Profile Search Execution Time
- Enable timing logs: Add `time_start = time.time()` around each search phase
- Measure: (A) Cache lookup (should be <1ms), (B) Meilisearch call (<100ms typical), (C) Qdrant call (<200ms typical), (D) RRF computation (<10ms typical)
- Identify bottleneck: Which component adds the most latency?
- Run 10 searches with same query and measure variance
- Document results: `SEARCH_PERFORMANCE_BASELINE_2026-04-19.md`

**Expected outcome**: Identified which component is slowest; performance baseline established.

### Step 10: Create Search Optimization Report
- Write `SEARCH_OPTIMIZATION_REPORT_2026-04-19.md` documenting:
  - Filter syntax fix (if applied) with before/after examples
  - Pagination offset fix (if applied) with test results
  - Search performance baseline (time breakdown by component)
  - Optimization opportunities identified (caching hits, index configuration, etc.)
  - Recommendations for future work (semantic search tuning, query expansion, etc.)

**Expected outcome**: Comprehensive optimization analysis; clear status on known issues.

---

## Phase 8: Database Population & Configuration (Steps 11-15)

**Objective**: Populate PostgreSQL database; configure LiteLLM for semantic search; verify end-to-end data flow.

### Step 11: Create PostgreSQL Seed Data
- Create `seed_documents.sql` with INSERT statements for 20+ test documents
- Fields required: id (UUID), title, source, owner, classification, status, created_date, updated_date, content, topics
- Use realistic test data: Mix of internal, public, and confidential documents; various owners (platform-eng, security, devops)
- Load data: `psql -h localhost -U kb_search_api -d kb_search_api < seed_documents.sql`
- Verify insertion: `SELECT COUNT(*) FROM documents;` (expect 20+)

**Expected outcome**: PostgreSQL documents table populated with test data.

### Step 12: Populate Meilisearch and Qdrant Indices
- Update `seed_test_data.py` to read from PostgreSQL instead of hardcoded list
- Add documents to Meilisearch: Iterate over `documents` table and call `meilisearch.index().add_documents()`
- Create Qdrant points (placeholder embeddings): `client.upsert(collection_name="documents", points=[...])` with dummy vectors
- Verify indices: 
  - Meilisearch: `curl http://localhost:6700/indexes/documents` (check doc count)
  - Qdrant: `curl http://localhost:6333/collections/documents` (check point count)
- Run migration script: `python3 seed_test_data.py` (or update to `python3 migrate_data.py`)

**Expected outcome**: Both search indices populated from PostgreSQL; search queries return results from all documents.

### Step 13: Configure LiteLLM API Key
- Create `.env.litellm` with:
  ```
  LITELLM_API_KEY=<user-provided-key>
  LITELLM_MODEL=text-embedding-3-small
  LITELLM_API_BASE=https://api.openai.com/v1
  ```
- Update `docker-compose.yml` to mount `.env.litellm` or pass as env variable to kb-search-api container
- Restart kb-search-api: `docker restart kb-search-api`
- Test embedding generation: 
  ```python
  from embedding_service import EmbeddingService
  es = EmbeddingService(redis_client)
  embedding = await es.embed_text("test query")
  print(f"Embedding dimension: {len(embedding)}")  # expect 1536 for text-embedding-3-small
  ```

**Expected outcome**: LiteLLM configured; embeddings generated successfully.

### Step 14: Regenerate Semantic Embeddings
- Create script `reindex_embeddings.py` to:
  - Query all documents from PostgreSQL
  - Call `embedding_service.embed_text(document.content)` for each
  - Upsert to Qdrant with document metadata
  - Update `document.embedding_generated_at` timestamp
- Run migration: `python3 reindex_embeddings.py` (may take 1-2 minutes for 20 docs)
- Verify completion: `curl http://localhost:6333/collections/documents/points` (check point count matches doc count)
- Test semantic search: `curl -X POST http://localhost:8000/api/v1/search -d '{"query": "database", "semantic_weight": 1.0}'` (should now return semantic matches)

**Expected outcome**: All documents have embeddings; semantic search working.

### Step 15: Verify End-to-End Data Flow
- Test document retrieval: `curl http://localhost:8000/api/v1/docs/<uuid>` (should return full document)
- Test metadata retrieval: `curl http://localhost:8000/api/v1/metadata/<uuid>` (should return metadata)
- Test search with all parameters: `{"query": "...", "filters": {"owner": "...", "classification": "..."}, "semantic_weight": 0.5}`
- Verify Grafana dashboard shows data flow: Check kb-search-api latency, cache hit rate, Qdrant query volume
- Document results: Update `STATUS.md` with "Database populated" and "Semantic search enabled" checkmarks

**Expected outcome**: Complete data pipeline verified; all API endpoints returning real data.

---

## Phase 9: Owner Assignment & CI/CD Setup (Steps 16-20)

**Objective**: Assign owners to kb-search-api and kb-web-ui; establish automated build and deployment pipelines.

### Step 16: Owner Assignment for kb-search-api
- Create `OWNER_ASSIGNMENT_PLAN_2026-04-19.md` with candidates:
  - Option A: Existing platform engineer (has FastAPI experience, owns search infrastructure)
  - Option B: New dedicated owner (search/backend specialist, full-time commitment)
  - Option C: Shared ownership (2-person team, backup coverage)
- Document owner responsibilities: Maintenance, feature work, incident response, code review
- Document handoff items: API documentation, runbooks, monitoring dashboard, alert escalation
- Recommendation: Option A (existing platform engineer) — lowest onboarding cost, existing context

**Expected outcome**: Owner candidate identified with justification.

### Step 17: Owner Assignment for kb-web-ui
- Similar process as Step 16, but for frontend specialist
- Create `OWNER_ASSIGNMENT_PLAN_KB_WEB_UI_2026-04-19.md` with candidates:
  - Option A: React/TypeScript specialist (owns frontend, integrates with kb-search-api)
  - Option B: Shared with kb-search-api owner (full-stack owner)
  - Option C: Team ownership (2-3 frontend engineers, rotating responsibility)
- Document handoff items: Component patterns, Vite build config, CORS setup, API integration
- Recommendation: Option A (dedicated frontend specialist) — clear ownership boundary

**Expected outcome**: Frontend owner candidate identified with justification.

### Step 18: Create GitHub Actions Workflow for kb-search-api
- File: `/c/kb-search-api/.github/workflows/ci.yml`
- Stages:
  1. **Lint** (ruff + mypy): `ruff check src/` + `mypy src/ --strict`
  2. **Test** (pytest): `pytest tests/ -v --cov=src/ --cov-fail-under=80`
  3. **Build Docker**: `docker build -t kb-search-api:${GIT_SHA} .`
  4. **Push to Registry** (if main branch): `docker push registry.example.com/kb-search-api:${GIT_SHA}`
  5. **Security Scan** (trivy): `trivy image kb-search-api:${GIT_SHA}`
- Triggers: On every push to main, every PR to main, manual trigger
- Document workflow: `CI_CD_SETUP_KB_SEARCH_API_2026-04-19.md`

**Expected outcome**: Automated CI/CD pipeline for kb-search-api operational.

### Step 19: Create GitHub Actions Workflow for kb-web-ui
- File: `/c/kb-web-ui/.github/workflows/ci.yml`
- Stages:
  1. **Install Dependencies**: `npm install` (or `npm ci`)
  2. **Lint** (eslint): `npm run lint`
  3. **Type Check** (typescript): `npm run type-check`
  4. **Test** (vitest): `npm run test` (expect tests/SearchBox.test.tsx to pass)
  5. **Build** (vite): `npm run build` (produces dist/ directory)
  6. **Build Docker** (optional): `docker build -t kb-web-ui:${GIT_SHA} .`
  7. **Deploy to Staging** (if main branch, optional): Push built assets to staging S3 or registry
- Triggers: Same as kb-search-api (PR/push/manual)
- Document workflow: `CI_CD_SETUP_KB_WEB_UI_2026-04-19.md`

**Expected outcome**: Automated CI/CD pipeline for kb-web-ui operational.

### Step 20: Verify CI/CD Pipelines
- Create test PR to kb-search-api (minor code change) and verify:
  - GitHub Actions workflow runs (check status on PR)
  - Lint + test + build stages pass or fail with clear feedback
  - Docker build succeeds
- Create test PR to kb-web-ui with same verification
- Document pipeline status: Which steps pass, which need fixing
- Create `CI_CD_VERIFICATION_2026-04-19.md` with pipeline screenshots and status

**Expected outcome**: Both projects have working, verified CI/CD pipelines.

---

## Phase 10: Integration & Frontend Work (Steps 21-25)

**Objective**: Connect kb-web-ui frontend to kb-search-api backend; implement core search UI features.

### Step 21: Implement API Integration in kb-web-ui
- Update `src/services/searchService.ts` to connect to kb-search-api:
  ```typescript
  const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';
  
  export const performSearch = async (query: string, filters?: SearchFilters) => {
    const response = await fetch(`${BASE_URL}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, filters, limit: 10, offset: 0 })
    });
    return response.json();
  };
  ```
- Update `SearchPage.tsx` to call `performSearch()` on form submit
- Update `.env.example` to include `REACT_APP_API_URL=http://localhost:8000/api/v1`
- Test integration: Type search query in UI → verify results populate from backend
- Document integration: `API_INTEGRATION_GUIDE_KB_WEB_UI_2026-04-19.md`

**Expected outcome**: Frontend successfully queries backend; search results displayed in UI.

### Step 22: Add Search Result Filtering UI
- Create `FilterPanel.tsx` component with:
  - Owner dropdown (values from fixtures: "platform-eng", "security", "devops")
  - Classification selector (radio: "public", "internal", "confidential")
  - Status selector (radio: "active", "archived", "deprecated")
  - Topics tag input (multi-select)
  - Apply Filters button
- Wire to SearchPage: Pass filters to `performSearch()`
- Test: Select filter → perform search → verify results filtered
- Document component: Add JSDoc comments to FilterPanel.tsx

**Expected outcome**: Filter UI functional; searches with filters return filtered results.

### Step 23: Add Document Detail View Page
- Create `DocumentDetailPage.tsx` component:
  - Query parameter: `?doc_id=<uuid>`
  - Fetch document via GET `/docs/{doc_id}` (once PostgreSQL populated)
  - Display: title, source, owner, classification, created_date, full content
  - Add back link to search results
- Add route: `<Route path="/detail/:doc_id" element={<DocumentDetailPage />} />`
- Wire from search results: Click result → navigate to `/detail/{doc_id}`
- Test: Click search result → detail page loads with full document content

**Expected outcome**: Document detail view working; navigation from search to detail functional.

### Step 24: Implement Pagination Controls
- Update `SearchResults.tsx` to display pagination:
  - Previous/Next buttons
  - Current page indicator (e.g., "Page 1 of 5")
  - Jump-to-page input or page number buttons
  - Items per page selector (10/25/50)
- Wire to `performSearch()`: Pass `limit` and `offset` parameters based on pagination state
- Test: Search → navigate through pages → verify results change correctly

**Expected outcome**: Pagination UI working; all result pages accessible.

### Step 25: Test End-to-End Search Flow
- **Scenario 1**: User types query → sees results → clicks result → views detail → back to search
- **Scenario 2**: User applies filters → sees filtered results → pagination works → can clear filters
- **Scenario 3**: User adjusts semantic_weight (advanced option) → sees different results
- Document test results: `E2E_SEARCH_TEST_RESULTS_2026-04-19.md`
- Capture screenshots or video of working flow
- Final verification: All core functionality working without errors

**Expected outcome**: Complete, working search interface from frontend to backend.

---

## Phase 11: Memory & Documentation Finalization (Steps 26-30)

**Objective**: Clean up session memory; finalize documentation; prepare for next session.

### Step 26: Audit Quarantine Directory
- Review `/c/Users/ajame/.claude/projects/C--/memory/_QUARANTINE_2026-04-18/` contents:
  - Count files by type (md, txt, json, etc.)
  - Identify any files that should be restored vs deleted
  - Look for valuable debugging info or historical context worth preserving
- Move valuable entries back to active memory: Any legitimate findings from prior sessions
- Document decision: `QUARANTINE_AUDIT_2026-04-19.md` (what's in quarantine, why, what's being kept)
- Set retention policy: Delete quarantine contents on 2026-05-18 (30-day window)

**Expected outcome**: Quarantine audited; valuable content identified; deletion date scheduled.

### Step 27: Update MEMORY.md
- Add new entries to `/c/Users/ajame/.claude/projects/C--/memory/MEMORY.md`:
  - Sessions: "Session 2026-04-19 continuation" (link to transcript)
  - Projects: Update kb-search-api, kb-web-ui status (from "KEEP pending" to "KEEP assigned" once owners named)
  - Infrastructure: "20 containers running, 0 issues post-Phase 5 cleanup"
  - Pending: Document remaining Phase 10-11 work if not completed
  - Next session: "Execute Phase 10-11 if not complete; await owner assignments to proceed with CI/CD"
- Verify index is current and all session files linked

**Expected outcome**: Memory consolidated; next session can resume without re-discovery.

### Step 28: Create DEPLOYMENT_COMPLETE_2026-04-19.md
- File: `/c/_infrastructure/DEPLOYMENT_COMPLETE_2026-04-19.md`
- Contents:
  - Executive summary: "kb-search-api and kb-web-ui deployed, tested, documented, ready for owner takeover"
  - Deployment timeline: "2026-04-18 Phase 1 deployment → 2026-04-19 Phase 5 API testing complete"
  - System status snapshot: "20 containers running, 0 failures, all services healthy"
  - Testing summary: "15 API tests passing, 3 blocked by database (expected), all error paths verified"
  - Owner transition plan: "Owners assigned → CI/CD setup → feature development → production readiness"
  - Key documents: Links to STATUS.md, API_TESTING_REPORT, operational guides, etc.
  - Blockers resolved: PostgreSQL seeding, LiteLLM configuration, search filter fixes (if completed)
  - Known limitations: artisan bootstrap (deferred), Windows symlinks (deferred)

**Expected outcome**: Comprehensive deployment summary for stakeholders.

### Step 29: Create NEXT_SESSION_ROADMAP_2026-04-19.md
- File: `/c/_infrastructure/NEXT_SESSION_ROADMAP_2026-04-19.md`
- Contents:
  - Session objectives: "Complete Phase 10-11; assign owners; transition to operational support"
  - Critical path: Phase 10 integration → Phase 11 memory cleanup → Owner handoff
  - Decision points: (A) Owners accept assignments, (B) CI/CD pipelines stable, (C) Search issues resolved
  - Risk factors: "Artisan bootstrap may require owner deep-dive; Windows symlinks may block webapp_core Phase 4"
  - Quick reference: Current container status, running services, health check endpoints
  - Escalation path: Which issues go to which owner (platform-eng: kb-search-api, frontend-lead: kb-web-ui)

**Expected outcome**: Clear roadmap for next session; decision points documented.

### Step 30: Archive Session Transcript & Prepare Summary
- Save full transcript: Copy `/c/Users/ajame/.claude/projects/C--/5a8fd0d4-8ca4-4afd-84c3-c064a9ff817c.jsonl` to `/c/_infrastructure/session_transcripts/session_2026-04-19_continuation.jsonl`
- Create session summary: `SESSION_SUMMARY_2026-04-19.md` documenting:
  - What was accomplished: Phases 6-11 planned; Phase 6-7 (if executed) findings captured
  - What remains: Phase 10-11 execution, owner assignments, CI/CD deployment
  - Key decisions made: Paper-project dispositions (kb-search-api/kb-web-ui KEEP), investigation paths (artisan deferred)
  - Artifacts created: 6+ new STATUS/REPORT files
  - Time investment: Total session duration, context windows used, decisions per hour

**Expected outcome**: Session properly archived; next session can resume with full context via MEMORY.md.

---

## Summary: Phases 6-11 (30 Steps)

| Phase | Objective | Steps | Key Deliverables |
|-------|-----------|-------|------------------|
| 6 | Department Marketing Investigation | 1-5 | DEPT_MARKETING_INVESTIGATION_SUMMARY |
| 7 | Search Optimization & Fixes | 6-10 | SEARCH_OPTIMIZATION_REPORT, filter/pagination fixes |
| 8 | Database & LiteLLM Configuration | 11-15 | PostgreSQL seeded, embeddings generated, endpoints verified |
| 9 | Owner Assignment & CI/CD | 16-20 | Owner assignments, GitHub Actions pipelines, verified |
| 10 | Frontend Integration | 21-25 | kb-web-ui fully integrated, UI features complete, E2E tested |
| 11 | Memory & Documentation | 26-30 | DEPLOYMENT_COMPLETE, NEXT_SESSION_ROADMAP, archived |

---

## Execution Strategy

- **Parallel work**: Phase 6 (Laravel) can run in parallel with Phase 7 (search fixes) if needed
- **Blockers**: Phase 8 depends on Phase 6 finding a solution (if DB seeding needed); Phase 9 depends on Phase 8 (need working endpoints for owner handoff)
- **Natural breaks**:
  - After Phase 6: Can defer Phase 7 if artisan issues are insurmountable
  - After Phase 8: Can pause before Phase 9 if waiting for owner availability
  - After Phase 10: Frontend work can be incremental; Phase 11 finalizes regardless
- **Resource assumption**: Single developer (you); ~2-3 hours per phase; ~1 context window per phase

---

**Plan created**: 2026-04-19  
**Expected completion**: Within 2-3 additional sessions (assuming 1.5 phases per session)  
**Assumptions**: PostgreSQL data population is feasible; owners available for assignment; no major infrastructure failures during Phase 9-10
