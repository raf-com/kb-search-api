# CI/CD Pipeline Verification Guide

## Overview
This document provides step-by-step instructions for testing and verifying the GitHub Actions CI/CD pipeline for kb-search-api.

## Prerequisites
- GitHub repository with Actions enabled
- `.github/workflows/01-lint-test-build.yml` deployed
- Push access to create test branches

## Testing Strategy

### Phase 1: Local Pre-Testing (Before Push)
Before pushing to trigger the workflow, validate locally:

```bash
# Run linting
python -m pip install ruff black flake8 mypy
ruff check --select=E,W,F .
black --check .

# Run tests (requires test database)
python -m pip install pytest pytest-cov pytest-asyncio
pytest --cov=. --cov-report=term-missing -v

# Check type safety
mypy . --ignore-missing-imports
```

### Phase 2: GitHub Actions Trigger

#### Test Case 1: Pull Request on `develop` Branch
1. Create a test feature branch: `git checkout -b test/ci-verify`
2. Make a minor code change (e.g., update README)
3. Commit and push: `git push origin test/ci-verify`
4. Create a pull request against `develop`
5. **Expectations**:
   - ✅ Lint job starts
   - ✅ Test job starts  
   - ✅ Security scan starts
   - ✅ Build job should NOT run (PR only)
   - ✅ PR comment with results

**Verification**:
```
Navigate to: GitHub > kb-search-api > Actions
Look for workflow run "Lint, Test & Build"
Check: All 4 jobs (lint, test, security, build) show green checkmarks
```

#### Test Case 2: Push to `main` Branch
1. Merge the test PR into `develop`
2. Create PR from `develop` → `main`
3. Merge to main
4. **Expectations**:
   - ✅ Lint, Test, Security jobs run
   - ✅ Build job runs (pushed to main)
   - ✅ Docker image built and pushed
   - ✅ Image tagged with commit SHA

**Verification**:
```
Navigate to: GitHub > kb-search-api > Actions > Latest Run
Confirm: All 5 jobs completed successfully
Navigate to: GitHub > kb-search-api > Packages
Confirm: New image appears with tag matching latest commit
```

#### Test Case 3: Linting Failure
1. Create branch: `git checkout -b test/lint-failure`
2. Intentionally introduce linting error (e.g., unused import):
   ```python
   import os  # Unused
   ```
3. Commit and push
4. Create PR
5. **Expectations**:
   - ❌ Lint job fails
   - ✅ Lint job shows clear error message in logs
   - ✅ PR comment shows lint failure
   - ❌ Test job still runs (for visibility)
   - ❌ Build job doesn't run

**Verification**:
```
Navigate to: GitHub > Checks tab on PR
Look for: Lint job with ❌ status
Click: View logs to see error message
Expected: "unused import" or similar clear error
```

#### Test Case 4: Test Failure
1. Create branch: `git checkout -b test/test-failure`
2. Modify a test to fail temporarily:
   ```python
   def test_example():
       assert False, "Intentional test failure"
   ```
3. Commit and push
4. Create PR
5. **Expectations**:
   - ✅ Lint passes
   - ❌ Test job fails
   - ✅ Failure is clearly shown
   - ❌ Build job doesn't run

**Verification**:
```
Navigate to: Test job logs
Look for: test_example failure
Expected: Clear error message showing assertion failed
```

### Phase 3: Coverage Verification

1. Check test coverage upload:
```
Navigate to: Actions > Test job > "Upload coverage reports" step
Look for: Successful upload to codecov
```

2. Verify coverage report:
```
Navigate to: GitHub > kb-search-api > Code Coverage badge
Should show: Coverage percentage (e.g., "Coverage: 85%")
```

### Phase 4: Docker Build Verification

1. Verify image push:
```bash
# Check image registry
docker pull ghcr.io/<github-username>/kb-search-api:latest
docker run --rm ghcr.io/<github-username>/kb-search-api:latest --version
```

2. Check image tags:
```
Navigate to: GitHub > Packages > kb-search-api
Look for: Multiple tags (main, commit SHA, latest)
```

## Success Criteria Checklist

### For PR to `develop`:
- [ ] Lint job passes
- [ ] Test job passes
- [ ] Security scan completes
- [ ] PR comment shows all checks ✅
- [ ] Build job does NOT run (expected)

### For merge to `main`:
- [ ] All PR checks pass
- [ ] Build job runs and completes
- [ ] Docker image successfully built
- [ ] Image pushed to registry
- [ ] Image has correct tags (latest, commit SHA)
- [ ] Can pull and run image locally

### For failure scenarios:
- [ ] Lint failures clearly visible
- [ ] Test failures show root cause
- [ ] Build doesn't run on failures
- [ ] PR comments reflect actual status
- [ ] Easy to identify and fix issues

## Troubleshooting

### Workflow doesn't trigger
- Verify: GitHub Actions enabled in Settings > Actions
- Check: `.github/workflows/` directory exists
- Confirm: YAML syntax is valid (run `yamllint`)
- Look for: Workflow file has `on:` section

### Tests fail locally but pass in CI
- Check: Python version mismatch (use 3.11)
- Verify: All services running (postgres, redis, meilisearch, qdrant)
- Ensure: Database initialized with schema
- Compare: Environment variables match

### Docker build fails
- Check: Dockerfile syntax
- Verify: All source files included
- Check: Base image available
- Look for: Permission issues in Dockerfile

### Coverage not uploading
- Verify: CODECOV_TOKEN secret set (if private repo)
- Check: Coverage file generated (`coverage.xml`)
- Ensure: pytest-cov installed
- Look for: Upload step in logs

## Performance Targets

| Job | Target Time | Acceptable |
|-----|------------|-----------|
| Lint | < 1 min | < 2 min |
| Test | < 3 min | < 5 min |
| Security | < 2 min | < 5 min |
| Build | < 5 min | < 10 min |
| **Total** | **< 10 min** | **< 20 min** |

## Next Steps

After verification is complete:

1. **Monitor**: Watch for failed runs and fix issues promptly
2. **Optimize**: Reduce job times if they exceed targets
3. **Extend**: Add more test jobs as coverage grows
4. **Document**: Update runbooks with CI/CD procedures
5. **Train**: Ensure team understands workflow and debugging

## Support Resources

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Docker Build Action](https://github.com/docker/build-push-action)
- [Setup Python Action](https://github.com/actions/setup-python)
- [Codecov Integration](https://codecov.io/)

---

**Owner**: kb-search-api owner  
**Last Updated**: 2026-04-19  
**Status**: Ready for verification
