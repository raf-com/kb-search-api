# Multi-Tenant Isolation & Security Audit — Email Sidecar
**Version**: 1.0  
**Date**: 2026-04-19  
**Audience**: Security team, compliance, infrastructure ops

---

## Executive Summary

Multi-tenant email infrastructure requires strict isolation boundaries to prevent:
- **Cross-tenant data leakage** (customer A accessing customer B's emails)
- **Resource exhaustion attacks** (one tenant consuming all bandwidth/quota)
- **Privilege escalation** (non-admin accessing admin endpoints)
- **Regulatory violations** (GDPR/SOC2 data isolation requirements)

This document defines isolation architecture, quarterly audit procedures, and remediation workflows.

---

## Section 1: Multi-Tenant Data Isolation Architecture

### 1.1 Database-Level Isolation

**Schema Design: Row-Level Security (RLS)**

```sql
-- Tenant isolation via RLS policy
CREATE POLICY email_isolation ON email_records
  USING (tenant_id = current_user_id()::uuid)
  WITH CHECK (tenant_id = current_user_id()::uuid);

CREATE POLICY template_isolation ON email_templates
  USING (tenant_id = current_user_id()::uuid)
  WITH CHECK (tenant_id = current_user_id()::uuid);

CREATE POLICY webhook_isolation ON webhook_subscribers
  USING (tenant_id = current_user_id()::uuid)
  WITH CHECK (tenant_id = current_user_id()::uuid);
```

**Multi-Tenant Query Guard**

Every query must include explicit tenant_id filter:

```php
// CORRECT: Explicitly filters by tenant
Email::where('tenant_id', Auth::user()->tenant_id)
  ->where('id', $emailId)
  ->first();

// INCORRECT: Missing tenant filter (raises exception)
Email::where('id', $emailId)->first();
```

Policy: Use a query middleware that audits all queries and raises AlertException if tenant_id is missing.

**Tenant ID Propagation**

1. Extract tenant_id from auth token during SQS message enqueue
2. Include tenant_id in Lambda environment context
3. Validate tenant_id matches authenticated user in all handlers
4. Log all cross-boundary access attempts (red flag)

### 1.2 API-Level Isolation

**Authentication Scope Binding**

```php
// Sanctum: Token scoped to tenant + user
$token = Auth::user()
  ->createToken('api-token', ['email:read', 'email:send'], [
    'tenant_id' => Auth::user()->tenant_id,
    'expires_at' => now()->addHours(24)
  ])
  ->plainTextToken;

// Verify scope in middleware
Middleware::create(function ($request, $next) {
  $token = auth()->guard('sanctum')->user();
  if ($token->extra_attributes['tenant_id'] !== Auth::user()->tenant_id) {
    throw UnauthorizedException::tenantMismatch();
  }
  return $next($request);
});
```

**Request-Level Tenant Binding**

```php
// Extract from request header (validated)
protected function getTenantFromRequest(Request $request): UUID {
  $tenantId = $request->header('X-Tenant-ID');
  if (!UUID::isValid($tenantId)) {
    throw ValidationException::invalidTenant();
  }
  
  // Verify against auth token
  if ($tenantId !== Auth::user()->tenant_id) {
    throw UnauthorizedException::tenantMismatch();
  }
  
  return $tenantId;
}
```

### 1.3 Cache Isolation (Redis)

**Tenant-Namespaced Keys**

```php
// Template cache pattern: tenant:uuid:cache:templates:template-id
Cache::tags(["tenant:{$tenantId}"])
  ->remember(
    "templates:{$templateId}",
    now()->addHours(1),
    fn() => Template::find($templateId)
  );

// Flush only tenant's cache on purge
Cache::tags(["tenant:{$tenantId}"])->flush();
```

**Cache Entry TTL by Tenant Tier**

| Tier      | Template TTL | Contact TTL | Webhook TTL |
|-----------|--------------|-------------|------------|
| Free      | 1 hour       | 30 min      | 15 min     |
| Pro       | 6 hours      | 1 hour      | 30 min     |
| Enterprise| 12 hours     | 2 hours     | 1 hour     |

Free tier gets shorter TTL to prevent large caches from consuming shared Redis memory.

### 1.4 SQS Queue Isolation

**Separate Queue per Tenant (Enterprise)**

For Enterprise customers with high volume, provision dedicated SQS queue:

```php
// Check tier
if ($customer->tier === 'enterprise') {
  $queueUrl = "https://sqs.{region}.amazonaws.com/{account}/{tenant-id}-email-queue";
} else {
  $queueUrl = "https://sqs.{region}.amazonaws.com/{account}/shared-email-queue";
}

// Enqueue with tenant context
SQS::sendMessage([
  'QueueUrl' => $queueUrl,
  'MessageBody' => json_encode([
    'tenant_id' => $tenantId,
    'email_id' => $emailId,
    'timestamp' => now()->toIso8601String()
  ]),
  'MessageAttributes' => [
    'TenantID' => ['DataType' => 'String', 'StringValue' => $tenantId],
  ]
]);
```

**Shared Queue Rate Limiting**

For Free/Pro customers on shared queue:

```php
// Per-tenant rate limiter in Lambda
RedisRateLimiter::check(
  key: "sqs:tenant:{$tenantId}:rate",
  limit: $customer->tier === 'pro' ? 1000 : 100,
  window: 60  // per minute
);
```

---

## Section 2: Quarterly Security Audit Procedures

### 2.1 Audit Schedule & Roles

**Q1, Q2, Q3, Q4** (90-day intervals, starting 2026-04-19)

| Quarter | Audit Window    | Lead    | Observers            |
|---------|-----------------|---------|----------------------|
| Q2 2026 | Apr 19 – May 19 | CtSO    | Eng, Infra, Legal   |
| Q3 2026 | Jul 20 – Aug 20 | CtSO    | Eng, Infra, Legal   |
| Q4 2026 | Oct 19 – Nov 19 | CtSO    | Eng, Infra, Legal   |
| Q1 2027 | Jan 19 – Feb 19 | CtSO    | Eng, Infra, Legal   |

### 2.2 Audit Checklist (12 areas)

#### A. Authentication & Authorization (8 tests)

**A1: Token Scope Validation**
- [ ] Generate token via `/auth/login` with tenant_id in scope
- [ ] Attempt cross-tenant access (different tenant_id in header)
- [ ] Verify 403 Unauthorized returned
- [ ] Log audit entry recorded

**A2: API Key Revocation**
- [ ] Create API key for customer
- [ ] Call endpoint with key (verify success)
- [ ] Admin revokes key
- [ ] Call with revoked key (verify 401 Unauthorized)
- [ ] Verify <500ms to take effect (cached invalidation)

**A3: Permission Boundary Testing**
- [ ] Free tier user attempts to access Pro-only endpoints
- [ ] Verify 403 Forbidden
- [ ] Enterprise user attempts to modify settings of different Enterprise customer
- [ ] Verify 403 Forbidden

**A4: Session Fixation Defense**
- [ ] Create session, extract session token
- [ ] Simulate attacker using stolen token from different IP
- [ ] Verify suspicious activity logged (different IP + geo)
- [ ] Verify optional Step-Up authentication can be required

**A5: CSRF Token Validation**
- [ ] POST request without CSRF token
- [ ] Verify 419 Token Mismatch
- [ ] POST with token from different user's session
- [ ] Verify 419 Token Mismatch

**A6: Multi-Factor Authentication Enforcement**
- [ ] Create user account with MFA required tier
- [ ] Verify login redirects to MFA challenge if not completed
- [ ] Bypass MFA by reusing old session cookie
- [ ] Verify MFA re-prompt on sensitive actions (delete all emails, rotate API keys)

**A7: Admin Privilege Escalation**
- [ ] Regular user attempts to access `/api/admin/users` endpoint
- [ ] Verify 403 Forbidden
- [ ] Admin user attempts to grant themselves "super_admin" role
- [ ] Verify audit log shows attempted privilege escalation
- [ ] Verify such actions require two-admin sign-off

**A8: Delegation & Impersonation**
- [ ] Admin user attempts to impersonate customer
- [ ] Verify impersonation action requires approval + audit log
- [ ] Verify impersonation session has hard 15-minute timeout
- [ ] Original admin session receives notification of impersonation end

#### B. Data Isolation (6 tests)

**B1: Cross-Tenant Query Prevention**
- [ ] Query database directly: `SELECT * FROM emails WHERE tenant_id != $currentTenant LIMIT 1`
- [ ] Verify RLS policy blocks the result
- [ ] Attempt via ORM without tenant filter
- [ ] Verify middleware exception raised

**B2: Cache Poisoning Defense**
- [ ] Tenant A caches template T1
- [ ] Retrieve template as Tenant B using Tenant A's cache key
- [ ] Verify cache miss (namespace prevents poisoning)
- [ ] Load as Tenant A, confirm cache hit

**B3: Bulk Export/Import Boundary**
- [ ] Tenant A exports 100 emails
- [ ] Tamper with export file: change tenant_id in header
- [ ] Tenant B imports tampered file
- [ ] Verify import rejected (tenant_id validation)

**B4: Webhook Subscriber Isolation**
- [ ] Tenant A subscribes webhook to tenant_id=A
- [ ] Mailgun sends event for tenant_id=B
- [ ] Verify webhook NOT triggered (explicit tenant match in handler)
- [ ] Reverse: Tenant B's webhook subscribed to A's events
- [ ] Verify webhook NOT triggered

**B5: Backup/Restore Tenant Boundary**
- [ ] Backup Customer A's data (RDS automated snapshot)
- [ ] Verify backup metadata includes tenant_id
- [ ] Restore to point-in-time using unrelated snapshot
- [ ] Verify restore restricted to same tenant (PITR filters)
- [ ] Verify backup restore requires explicit tenant_id match in CLI

**B6: Search Index Isolation (Meilisearch)**
- [ ] Index emails for Tenant A
- [ ] Query index as Tenant B with wildcard search
- [ ] Verify no Tenant A documents in results
- [ ] Verify Tenant B's documents only returned

#### C. API Input Validation (5 tests)

**C1: SQL Injection via Email Metadata**
- [ ] Send email with subject: `'; DROP TABLE emails; --`
- [ ] Verify stored safely in prepared statement
- [ ] Query email, verify subject rendered literally

**C2: XSS in Email Template**
- [ ] Create template with body: `<img src=x onerror="alert('xss')">`
- [ ] Send email using template
- [ ] Retrieve email via API
- [ ] Verify script tags escaped in JSON response
- [ ] Render in UI, verify no script execution

**C3: Path Traversal in File Upload**
- [ ] Upload attachment with name: `../../etc/passwd`
- [ ] Verify stored in tenant-scoped directory only
- [ ] Attempt to retrieve via `GET /attachments/../../etc/passwd`
- [ ] Verify 404 Not Found (path canonicalization prevents escape)

**C4: CSV Injection in Bulk Export**
- [ ] Export emails to CSV with subject: `=HYPERLINK("http://evil.com")`
- [ ] Open in Excel, verify formula not evaluated
- [ ] Verify as plain text: `=HYPERLINK(...)`

**C5: Rate Limit Bypass via Header Tampering**
- [ ] Set `X-Forwarded-For: attacker-ip` to spoof originating IP
- [ ] Verify rate limiter uses real client IP (X-Real-IP or socket origin)
- [ ] Attempt distributed rate limit bypass across 10 IPs
- [ ] Verify distributed limit enforced per API key (not per IP)

#### D. Cryptography & Secrets (4 tests)

**D1: Encryption Key Rotation**
- [ ] View active encryption key ID in system table
- [ ] Rotate key via `/api/admin/crypto/rotate-key`
- [ ] Verify old key still decrypts existing data (backward compat)
- [ ] Verify new encryptions use new key
- [ ] Run background job to re-encrypt old data
- [ ] Verify old key can be safely archived after 30-day grace

**D2: Plaintext Secret Exposure**
- [ ] Search codebase for hardcoded API keys (`grep -r "sk_live"`)
- [ ] Search Docker images for secrets in layers (`docker history <image>`)
- [ ] Search Git history for deleted secrets (`git log -p | grep "password"`)
- [ ] Verify all secrets in AWS Secrets Manager or Vault (not in .env)

**D3: TLS Certificate Validation**
- [ ] Webhook send to HTTPS endpoint with self-signed cert
- [ ] Verify SSL validation fails (cert not trusted)
- [ ] Generate proper Let's Encrypt cert
- [ ] Webhook send succeeds
- [ ] Verify cert pinning enabled for critical endpoints (Mailgun API)

**D4: Password Storage**
- [ ] Hash user passwords with bcrypt (min 10 rounds)
- [ ] Query database, verify no plaintext passwords
- [ ] Attempt rainbow table attack on password hash
- [ ] Verify hash includes salt (bcrypt format includes `$salt$`)

#### E. Audit Logging (3 tests)

**E1: Critical Action Logging**
- [ ] Admin revokes API key
- [ ] Verify audit log entry created within 1 second
- [ ] Check log includes: action, actor, target, timestamp, IP, user agent
- [ ] Verify log immutable (append-only Loki stream)

**E2: Suspicious Activity Alerting**
- [ ] Simulate 10 failed login attempts from single IP
- [ ] Verify account lockout triggered
- [ ] Verify alert sent to admin via email/Slack
- [ ] Verify alert contains: IP, timestamp, user, attempt count

**E3: Log Retention & Retention Purge**
- [ ] Verify audit logs retained for 90 days (per GDPR)
- [ ] Run log purge job on day 91
- [ ] Verify logs older than 90 days deleted
- [ ] Verify immutability: purge cannot be undone (no restore from Loki)

#### F. Infrastructure (3 tests)

**F1: Network Isolation**
- [ ] Pod A (Customer A Lambda) attempts DNS lookup: `pod-b.default.svc`
- [ ] Verify network policy blocks inter-pod communication
- [ ] Verify each tenant's Lambda runs in isolated container namespace

**F2: Database Credentials**
- [ ] Retrieve database password from AWS Secrets Manager
- [ ] Verify password only accessible via IAM role (not hardcoded)
- [ ] Verify Lambda task role has only `rds-connect` permission (no delete)
- [ ] Verify credentials rotated every 30 days

**F3: Backup Encryption**
- [ ] Verify RDS backups encrypted at rest (KMS customer key)
- [ ] Verify backup decryption requires KMS permission
- [ ] Attempt to copy backup to different AWS account
- [ ] Verify copy fails without KMS grant from source account

#### G. Dependency Vulnerabilities (2 tests)

**G1: Composer Dependency Scan**
- [ ] Run `composer audit` in CI/CD
- [ ] Verify no critical vulnerabilities in active dependencies
- [ ] If found: update package or add security patch, re-scan

**G2: Docker Image Scanning**
- [ ] Run Trivy on Lambda Docker image: `trivy image <image>`
- [ ] Verify no critical OS vulnerabilities
- [ ] If found: update base image, rebuild, re-scan

### 2.3 Quarterly Audit Report Template

**File**: `/c/_infrastructure/QUARTERLY_SECURITY_AUDIT_Q2_2026.md`

```markdown
# Quarterly Security Audit — Q2 2026

**Period**: 2026-04-19 to 2026-05-19  
**Auditor**: Chief Security Officer  
**Status**: [IN PROGRESS | COMPLETE | ISSUES FOUND]

## Test Results Summary

| Category | Tests | Passed | Failed | % Pass |
|----------|-------|--------|--------|--------|
| A: Authentication | 8 | 8 | 0 | 100% |
| B: Data Isolation | 6 | 6 | 0 | 100% |
| C: Input Validation | 5 | 5 | 0 | 100% |
| D: Cryptography | 4 | 4 | 0 | 100% |
| E: Audit Logging | 3 | 3 | 0 | 100% |
| F: Infrastructure | 3 | 3 | 0 | 100% |
| G: Dependencies | 2 | 2 | 0 | 100% |
| **TOTAL** | **31** | **31** | **0** | **100%** |

## Issues Found

### Critical (Require immediate fix)
- None

### High (Fix before next quarter)
- None

### Medium (Address in next iteration)
- None

## Remediation Tracking

| ID | Issue | Owner | Due Date | Status |
|----|-------|-------|----------|--------|
| — | — | — | — | — |

## Sign-Off

- **Auditor**: [Name], [Date]
- **Tech Lead**: [Name], [Date]
- **Compliance**: [Name], [Date]

## Next Audit

**Scheduled**: 2026-07-19 (90 days from now)
```

---

## Section 3: Incident Response for Isolation Breaches

### 3.1 Breach Detection & Severity

**Severity Levels**

| Level | Description | Response Time |
|-------|-------------|----------------|
| P1    | Cross-tenant data accessed | <15 min incident creation |
| P2    | Unauthorized API access attempt | <1 hour incident creation |
| P3    | Suspicious activity pattern | <4 hours incident creation |

### 3.2 Breach Containment Playbook

**Step 1: Immediate Containment (0-5 min)**
- Pause email processing: `PAUSE_QUEUE=true` env var
- Isolate affected tenant: revoke all API keys
- Block all webhooks for tenant (circuit breaker mode)
- Notify security team: Slack #security-incidents

**Step 2: Investigation (5-30 min)**
- Query audit logs for full scope of access
- Pull CloudWatch logs for Lambda execution
- Query database: count records accessed outside normal scope
- Determine if data was exfiltrated (check S3 access logs, CloudTrail)

**Step 3: Notification & Remediation (30 min - 2 hours)**
- Notify affected customer(s): explain what was accessed, when, by whom
- If exfiltration: provide forensic summary and remediation steps
- Force password reset for all users in affected tenant
- Revoke all active sessions
- Re-enable queue processing with monitoring

**Step 4: Post-Incident (2+ hours)**
- Root cause analysis: was it code bug, config error, or malicious insider?
- Fix identified vulnerability
- Run full security audit (#2.2 checklist) on affected code path
- Document findings in incident report
- Review with customer (option to accept liability or legal escalation)

---

## Section 4: Compliance Mapping

### 4.1 GDPR Article 32 (Security)

| Requirement | Implementation |
|-------------|-----------------|
| Access control | Row-level security + API auth scope |
| Encryption in transit | TLS 1.3 on all endpoints |
| Encryption at rest | RDS KMS + Redis encryption |
| Audit logging | Immutable Loki logs, 90-day retention |
| Integrity checks | HMAC verification on webhooks, database constraints |

### 4.2 SOC2 CC (Change Control)

All security changes require:
1. Code review by 2 people (one security-focused)
2. Automated test coverage >80%
3. Staging validation before prod
4. Audit log entry at deployment time

---

## Section 5: Privilege Escalation Prevention

### 5.1 Role-Based Access Control (RBAC)

**Four Roles**: user, admin, operator, auditor

```php
enum Role: string {
  case user = 'user';           // Can only view own emails
  case admin = 'admin';         // Can manage users, settings, webhooks
  case operator = 'operator';   // Can pause/resume queues (limited)
  case auditor = 'auditor';     // Read-only audit logs
}
```

**Privilege Matrix**

| Action | User | Admin | Operator | Auditor |
|--------|------|-------|----------|---------|
| Send email | ✓ | ✓ | — | — |
| View own emails | ✓ | ✓ | — | — |
| View all tenant emails | — | ✓ | — | — |
| Manage API keys | — | ✓ | — | — |
| Pause queue | — | — | ✓ | — |
| View audit logs | — | ✓ | ✓ | ✓ |
| Delete audit logs | — | — | — | — |

### 5.2 Two-Admin Sign-Off

**Requires 2 admins for**:
- Deleting all emails for a tenant
- Disabling MFA enforcement
- Rotating encryption keys
- Extending retention beyond 90 days

```php
TwoAdminApproval::require(
  action: 'delete_all_emails',
  target_tenant: $tenantId,
  initiator: Auth::user()
);
// Notifies second admin, requires approval within 1 hour
```

---

## Section 6: Monitoring & Alerting

### 6.1 Isolation Breach Alerts

**AlertManager Rule: CrossTenantAccessAttempt**

```yaml
- alert: CrossTenantAccessAttempted
  expr: (rate(isolation_violation_total[5m]) > 0)
  for: 1m
  annotations:
    summary: "Cross-tenant access attempt detected"
    description: "{{ $value }} isolation violations in past 5 min"
    severity: "critical"
```

**AlertManager Rule: UnauthorizedAPIAccess**

```yaml
- alert: UnauthorizedAPIAccessPattern
  expr: (rate(http_requests_total{status="403"}[5m]) > 10)
  for: 5m
  annotations:
    summary: "Elevated 403 rate — possible brute force"
    description: "{{ $value }} requests/sec returned 403"
```

### 6.2 Dashboard: Security Monitoring

**Grafana Dashboard: Isolation & Security**

Panels:
1. **Cross-Tenant Access Attempts** (last 24h)
   - Graph: violations over time
   - Alert threshold line at 0

2. **Unauthorized API Attempts** (last 24h)
   - Stacked bar: by endpoint, by tenant

3. **Audit Log Volume** (last 24h)
   - Graph: log entries/min
   - Expected baseline: 5-10 entries/min

4. **Token Revocation Lag** (SLA)
   - Histogram: time from revocation to 403 return
   - SLA: <500ms (p99)

5. **Session Duration** (anomalies)
   - Graph: session lengths by tier
   - Alert if Free tier session >24h (unusual)

---

## Section 7: Testing & Validation Framework

### 7.1 Security Test Suite (PHP/Laravel)

**File**: `tests/Security/IsolationTest.php`

```php
namespace Tests\Security;

use Tests\TestCase;

class IsolationTest extends TestCase {
  
  public function test_cross_tenant_query_blocked() {
    $tenantA = Tenant::factory()->create();
    $tenantB = Tenant::factory()->create();
    
    $this->actingAs($tenantA->admin);
    
    $email = Email::factory()->for($tenantB)->create();
    
    $response = $this->getJson("/api/emails/{$email->id}");
    $response->assertStatus(404); // Not found in tenant A's context
  }
  
  public function test_api_key_scope_enforced() {
    $tenantA = Tenant::factory()->create();
    $tenantB = Tenant::factory()->create();
    $apiKey = $tenantA->createApiKey();
    
    $response = $this->withHeader('Authorization', "Bearer {$apiKey}")
      ->getJson('/api/emails', ['X-Tenant-ID' => $tenantB->id]);
    
    $response->assertStatus(403);
  }
  
  public function test_cache_isolation() {
    $tenantA = Tenant::factory()->create();
    $tenantB = Tenant::factory()->create();
    $template = Template::factory()->for($tenantA)->create();
    
    Cache::tags(["tenant:{$tenantA->id}"])
      ->put("template:{$template->id}", $template);
    
    // Cache should NOT be accessible from tenantB
    $cached = Cache::tags(["tenant:{$tenantB->id}"])->get("template:{$template->id}");
    $this->assertNull($cached);
  }
  
  public function test_rls_policy_blocks_direct_query() {
    $tenantA = Tenant::factory()->create();
    $tenantB = Tenant::factory()->create();
    $email = Email::factory()->for($tenantB)->create();
    
    $this->actingAs($tenantA->admin);
    
    // RLS policy should prevent retrieval
    $query = Email::where('id', $email->id)->toSql();
    $result = DB::select($query);
    
    $this->assertEmpty($result);
  }
}
```

---

## Section 8: External Audit Partnership (Annual)

### 8.1 Third-Party Auditor Selection

**Criteria**:
- SOC2 Type II certification experience
- Multi-tenant SaaS background
- AWS expertise
- <2 week turnaround for final report

**Annual Schedule**:
- **Q1**: Request proposals from 3 firms
- **Q2**: Audit execution (2-3 weeks)
- **Q3**: Remediation of findings
- **Q4**: Follow-up verification

### 8.2 Audit Scope & Deliverables

**In Scope**:
- Architecture review (multi-tenant design)
- Code review (isolation-critical paths)
- Infrastructure audit (network, storage, backup)
- Penetration testing (30 days of scoping + testing)
- Compliance assessment (GDPR, SOC2)

**Deliverables**:
- Executive summary (1 page)
- Detailed findings report (severity-classified)
- Remediation roadmap (by quarter)
- Evidence of fixes (follow-up verification)
- SOC2 Type II audit report template provision

---

## Section 9: Checklist for Next Quarter

**Before Q3 Audit (July 2026)**:

- [ ] All P1 findings from Q2 remediated and re-tested
- [ ] Encryption key rotation completed at least once
- [ ] RLS policies reviewed by 2 security engineers
- [ ] Third-party code review of isolation-critical paths
- [ ] Security test coverage >85% on auth/isolation modules
- [ ] Audit log retention verified (90 days)
- [ ] External audit partnership confirmed for annual review
- [ ] Team security training completed (OAuth, JWTs, SQL injection, XSS)
- [ ] Incident response playbook reviewed and practiced
- [ ] Customer security questionnaire responses updated

---

## References

- [GDPR Article 32: Security of Processing](https://gdpr-info.eu/art-32-gdpr/)
- [SOC2 Trust Service Criteria — CC (Change Control)](https://us.aicpa.org/content/dam/aicpa/interestareas/informationsystems/resources/downloads-2/pages/cc-criteria.docx)
- [OWASP: Top 10 – A07: Identification and Authentication Failures](https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/)
- [AWS Well-Architected Framework: Multi-Tenant Architecture](https://docs.aws.amazon.com/whitepapers/latest/multi-tenant-saas-storage-isolation-strategies/)

---

**Status**: Ready for Q2 2026 audit execution  
**Next Review**: 2026-07-19 (Q3 2026)
