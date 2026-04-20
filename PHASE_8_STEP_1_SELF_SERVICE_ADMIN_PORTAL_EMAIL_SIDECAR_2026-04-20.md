# Phase 8, Step 1: Self-Service Admin Portal Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Full-stack engineer  
**Timeline**: May 1-24, 2026 (4 weeks)  
**Effort**: 40 hours (1 engineer week × 4 weeks)

---

## Executive Summary

Self-service portal empowers customers to manage emails, webhooks, and API keys without support tickets. Current state: all operations require support intervention. Target state: >60% of customers perform self-service operations by week 4.

**Key Metrics**:
- Support ticket reduction: >25% fewer setup requests
- Feature adoption: >60% of active customers
- Success rate: >99% for all operations
- Performance: <500ms response time on all endpoints

---

## Feature 1: Email Search & Bulk Operations

### 1.1 Database Schema Design

```sql
-- Search indexes for email table
CREATE INDEX CONCURRENTLY idx_emails_tenant_created 
  ON emails(tenant_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_emails_tenant_sender 
  ON emails(tenant_id, sender) 
  INCLUDE (created_at, status);

CREATE INDEX CONCURRENTLY idx_emails_tenant_subject 
  ON emails(tenant_id, subject) 
  USING GIN (to_tsvector('english', subject));

-- Audit table for bulk operations (immutable)
CREATE TABLE email_bulk_operations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  operation_type ENUM('delete', 'export', 'tag'),
  filter_criteria JSONB NOT NULL,
  affected_count INT DEFAULT 0,
  status ENUM('pending', 'executing', 'completed', 'failed') DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT now(),
  completed_at TIMESTAMP,
  created_by UUID REFERENCES users(id),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX CONCURRENTLY idx_bulk_ops_tenant_status 
  ON email_bulk_operations(tenant_id, status, created_at DESC);
```

### 1.2 API Endpoints

**POST /api/v1/emails/search** — Advanced search with filtering

```php
// Request
{
  "query": "from:customer@example.com",
  "filters": {
    "status": "delivered",
    "date_from": "2026-04-01",
    "date_to": "2026-04-20",
    "recipient": "user@example.com"
  },
  "pagination": {
    "page": 1,
    "per_page": 50
  }
}

// Response (HTTP 200)
{
  "data": [
    {
      "id": "email-uuid",
      "sender": "customer@example.com",
      "recipient": "user@example.com",
      "subject": "Order confirmation",
      "status": "delivered",
      "created_at": "2026-04-19T14:30:00Z",
      "opened_at": "2026-04-19T14:35:00Z",
      "clicked_at": null
    }
  ],
  "pagination": {
    "total": 142,
    "page": 1,
    "per_page": 50,
    "last_page": 3
  }
}
```

**Implementation (Laravel)**:

```php
namespace App\Http\Controllers;

use App\Models\Email;
use Illuminate\Http\Request;

class EmailSearchController extends Controller {
  public function search(Request $request) {
    $validated = $request->validate([
      'query' => 'nullable|string|max:100',
      'filters.status' => 'in:delivered,bounced,complained,deferred',
      'filters.date_from' => 'date_format:Y-m-d',
      'filters.date_to' => 'date_format:Y-m-d',
      'pagination.page' => 'integer|min:1',
      'pagination.per_page' => 'integer|in:10,25,50,100'
    ]);

    $query = Email::where('tenant_id', Auth::user()->tenant_id);

    // Apply filters
    if ($validated['filters']['status'] ?? null) {
      $query->where('status', $validated['filters']['status']);
    }

    if ($validated['filters']['date_from'] ?? null) {
      $query->whereDate('created_at', '>=', $validated['filters']['date_from']);
    }

    // Full-text search on subject + body (PostgreSQL tsvector)
    if ($validated['query'] ?? null) {
      $query->whereRaw(
        "to_tsvector('english', subject || ' ' || body) @@ 
         plainto_tsquery('english', ?)",
        [$validated['query']]
      );
    }

    $emails = $query
      ->orderBy('created_at', 'desc')
      ->paginate($validated['pagination']['per_page'] ?? 50);

    return response()->json([
      'data' => $emails->items(),
      'pagination' => [
        'total' => $emails->total(),
        'page' => $emails->currentPage(),
        'per_page' => $emails->perPage(),
        'last_page' => $emails->lastPage()
      ]
    ]);
  }
}
```

**GET /api/v1/emails/bulk-delete** — Bulk delete with soft-delete grace period

```php
namespace App\Http\Controllers;

class EmailBulkDeleteController extends Controller {
  public function delete(Request $request) {
    $validated = $request->validate([
      'filter_criteria' => 'required|array',
      'filter_criteria.status' => 'in:delivered,bounced,complained',
      'confirm' => 'required|boolean' // Must explicitly confirm
    ]);

    if (!$validated['confirm']) {
      return response()->json([
        'message' => 'Deletion requires explicit confirmation',
        'estimated_count' => $this->countAffected($validated['filter_criteria'])
      ], 422);
    }

    // Create audit entry for bulk operation
    $operation = EmailBulkOperation::create([
      'tenant_id' => Auth::user()->tenant_id,
      'operation_type' => 'delete',
      'filter_criteria' => $validated['filter_criteria'],
      'status' => 'pending',
      'created_by' => Auth::id()
    ]);

    // Queue async job (soft delete, recoverable for 24 hours)
    DeleteEmailsJob::dispatch($operation)->onQueue('bulk-operations');

    return response()->json([
      'operation_id' => $operation->id,
      'status' => 'pending',
      'message' => 'Bulk delete queued. You can recover deleted emails for 24 hours.',
      'recovery_url' => "/api/v1/emails/bulk-recovery/{$operation->id}"
    ], 202); // 202 Accepted
  }
}
```

**24-Hour Soft Delete Recovery**:

```php
// In Email model
class Email extends Model {
  protected $dates = ['deleted_at', 'permanently_deleted_at'];
  
  // Soft delete: recoverable for 24 hours
  public function delete() {
    $this->deleted_at = now();
    $this->save();
    
    // Schedule permanent deletion after 24 hours
    PermanentlyDeleteEmailJob::dispatch($this)
      ->delay(now()->addHours(24));
  }

  // Restore deleted email
  public function restore() {
    if ($this->deleted_at && now()->diffInHours($this->deleted_at) <= 24) {
      $this->deleted_at = null;
      $this->save();
      return true;
    }
    return false; // Too late to recover
  }
}
```

### 1.3 Frontend UI Components (React/TypeScript)

**Email Search Component**:

```tsx
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Input, Select, DatePicker, Button, Table } from '@ui-library';

interface EmailSearchFilters {
  query: string;
  status: 'delivered' | 'bounced' | 'complained' | '';
  date_from: string;
  date_to: string;
  page: number;
  per_page: 50;
}

export const EmailSearchUI: React.FC = () => {
  const [filters, setFilters] = useState<EmailSearchFilters>({
    query: '',
    status: '',
    date_from: '',
    date_to: '',
    page: 1,
    per_page: 50
  });

  const { data, isLoading, error } = useQuery(
    ['emails', filters],
    () => api.post('/emails/search', { filters, pagination: { page: filters.page, per_page: filters.per_page } }),
    { keepPreviousData: true }
  );

  return (
    <div className="email-search">
      <div className="search-filters">
        <Input
          type="text"
          placeholder="Search subject, sender, recipient..."
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value, page: 1 })}
        />
        
        <Select
          value={filters.status}
          onChange={(val) => setFilters({ ...filters, status: val, page: 1 })}
          options={[
            { label: 'All Statuses', value: '' },
            { label: 'Delivered', value: 'delivered' },
            { label: 'Bounced', value: 'bounced' },
            { label: 'Complained', value: 'complained' }
          ]}
        />

        <DatePicker
          label="From"
          value={filters.date_from}
          onChange={(val) => setFilters({ ...filters, date_from: val, page: 1 })}
        />

        <DatePicker
          label="To"
          value={filters.date_to}
          onChange={(val) => setFilters({ ...filters, date_to: val, page: 1 })}
        />
      </div>

      {isLoading && <div>Loading...</div>}
      {error && <div className="error">Search failed: {error.message}</div>}

      <Table
        columns={[
          { key: 'sender', label: 'From', width: '20%' },
          { key: 'recipient', label: 'To', width: '20%' },
          { key: 'subject', label: 'Subject', width: '35%' },
          { key: 'status', label: 'Status', width: '15%', render: (val) => <Badge>{val}</Badge> },
          { key: 'created_at', label: 'Date', width: '10%', render: (val) => formatDate(val) }
        ]}
        rows={data?.data || []}
        pagination={{
          page: filters.page,
          per_page: filters.per_page,
          total: data?.pagination.total || 0,
          onPageChange: (page) => setFilters({ ...filters, page })
        }}
      />
    </div>
  );
};
```

**Bulk Delete Dialog**:

```tsx
export const BulkDeleteDialog: React.FC<{ selectedEmails: string[] }> = ({ selectedEmails }) => {
  const [confirmed, setConfirmed] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const mutation = useMutation(() => api.post('/emails/bulk-delete', {
    filter_criteria: { ids: selectedEmails },
    confirm: confirmed
  }));

  const handleDelete = async () => {
    if (!confirmed) {
      alert('Please check the confirmation box');
      return;
    }
    setIsDeleting(true);
    await mutation.mutateAsync();
    setIsDeleting(false);
  };

  return (
    <Dialog open={true}>
      <div className="dialog-content">
        <h3>Delete {selectedEmails.length} emails?</h3>
        <p>Deleted emails can be recovered for 24 hours from the Trash folder.</p>
        
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I confirm deletion of {selectedEmails.length} email(s)
        </label>

        <div className="actions">
          <Button onClick={handleDelete} disabled={!confirmed || isDeleting}>
            {isDeleting ? 'Deleting...' : 'Delete'}
          </Button>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </div>
    </Dialog>
  );
};
```

### 1.4 Implementation Milestones

**Week 1: Database & API Foundation**
- [ ] Create email search indexes (PostgreSQL tsvector on subject + body)
- [ ] Implement EmailSearchController with filter support
- [ ] Add EmailBulkOperation audit table
- [ ] Write API tests (10 test cases: search, filter, pagination, empty results)
- [ ] Deployment: Staging

**Week 2: Soft Delete & Recovery**
- [ ] Implement soft delete logic (deleted_at column)
- [ ] Queue permanent deletion job (24-hour delay)
- [ ] Implement recovery endpoint (POST /emails/{id}/restore)
- [ ] Write tests (5 cases: delete, recover, permanent deletion)
- [ ] Manual testing: delete email, wait 1 second, recover, verify

**Week 3: Frontend UI**
- [ ] Build EmailSearchUI component with filtering
- [ ] Build BulkDeleteDialog with confirmation
- [ ] Integrate with existing customer dashboard
- [ ] Styling & responsive design
- [ ] Accessibility audit (WCAG 2.1 AA)

**Week 4: Integration & Launch**
- [ ] End-to-end testing (search → select → delete → recover)
- [ ] Performance testing (search response time <500ms)
- [ ] Beta rollout to 5% of customers
- [ ] Monitor error rates, support tickets
- [ ] Full production rollout

### 1.5 Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Search latency (p95) | <500ms | CloudWatch metrics |
| Bulk delete success rate | >99.5% | Error logs |
| Feature adoption | >40% of active users | Analytics |
| Support ticket reduction | 20% fewer "how do I delete emails?" | Zendesk |
| UI accessibility | WCAG 2.1 AA | Automated audit + manual review |

---

## Feature 2: Webhook Management UI

### 2.1 Database Schema

```sql
CREATE TABLE webhook_subscribers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  webhook_url VARCHAR(500) NOT NULL,
  event_types TEXT[] NOT NULL, -- ['email.delivered', 'email.bounced', ...]
  is_active BOOLEAN DEFAULT true,
  retry_config JSONB DEFAULT '{"max_retries": 5, "backoff_ms": 1000}',
  created_at TIMESTAMP DEFAULT now(),
  last_tested_at TIMESTAMP,
  test_result_status INT, -- HTTP status code from last test
  execution_count INT DEFAULT 0,
  last_execution_at TIMESTAMP
);

CREATE INDEX CONCURRENTLY idx_webhooks_tenant_active 
  ON webhook_subscribers(tenant_id, is_active);

-- Webhook execution log (for debugging)
CREATE TABLE webhook_execution_log (
  id BIGSERIAL PRIMARY KEY,
  webhook_id UUID NOT NULL REFERENCES webhook_subscribers(id),
  event_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL,
  http_status INT,
  response_body TEXT,
  execution_time_ms INT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX CONCURRENTLY idx_webhook_log_webhook_created 
  ON webhook_execution_log(webhook_id, created_at DESC);
```

### 2.2 API Endpoints

**POST /api/v1/webhooks** — Create webhook

```php
class WebhookController extends Controller {
  public function store(Request $request) {
    $validated = $request->validate([
      'webhook_url' => 'required|url|max:500',
      'event_types' => 'required|array|min:1',
      'event_types.*' => 'in:email.delivered,email.bounced,email.complained,email.deferred'
    ]);

    $webhook = WebhookSubscriber::create([
      'tenant_id' => Auth::user()->tenant_id,
      'webhook_url' => $validated['webhook_url'],
      'event_types' => $validated['event_types'],
      'is_active' => true
    ]);

    // Test webhook immediately
    $this->testWebhook($webhook);

    return response()->json([
      'id' => $webhook->id,
      'webhook_url' => $webhook->webhook_url,
      'event_types' => $webhook->event_types,
      'is_active' => $webhook->is_active,
      'test_status' => $webhook->test_result_status
    ], 201);
  }

  // Test webhook with mock event
  private function testWebhook(WebhookSubscriber $webhook) {
    $mockPayload = [
      'event_type' => 'email.delivered',
      'email_id' => 'test-' . uniqid(),
      'recipient' => 'test@example.com',
      'timestamp' => now()->toIso8601String()
    ];

    try {
      $response = Http::timeout(5)->post($webhook->webhook_url, [
        'event' => $mockPayload,
        'X-Webhook-Secret' => hash_hmac('sha256', json_encode($mockPayload), config('app.webhook_secret'))
      ]);

      $webhook->update([
        'test_result_status' => $response->status(),
        'last_tested_at' => now()
      ]);

      return $response->status() === 200;
    } catch (Exception $e) {
      $webhook->update([
        'test_result_status' => 0,
        'last_tested_at' => now()
      ]);
      return false;
    }
  }
}
```

**GET /api/v1/webhooks/{id}/executions** — View webhook execution log

```php
public function getExecutions(Request $request, $webhookId) {
  $webhook = WebhookSubscriber::where('id', $webhookId)
    ->where('tenant_id', Auth::user()->tenant_id)
    ->firstOrFail();

  $executions = WebhookExecutionLog::where('webhook_id', $webhook->id)
    ->orderBy('created_at', 'desc')
    ->paginate(50);

  return response()->json([
    'webhook_id' => $webhook->id,
    'webhook_url' => $webhook->webhook_url,
    'executions' => $executions->items(),
    'pagination' => [
      'total' => $executions->total(),
      'page' => $executions->currentPage()
    ]
  ]);
}
```

### 2.3 Frontend: Webhook Manager UI (React)

```tsx
export const WebhookManagerUI: React.FC = () => {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [showAddDialog, setShowAddDialog] = useState(false);

  const { data: webhooksData } = useQuery(
    ['webhooks'],
    () => api.get('/webhooks'),
    { refetchInterval: 10000 } // Refresh every 10s
  );

  useEffect(() => {
    if (webhooksData) setWebhooks(webhooksData.data);
  }, [webhooksData]);

  return (
    <div className="webhook-manager">
      <div className="header">
        <h2>Webhooks</h2>
        <Button onClick={() => setShowAddDialog(true)}>+ Add Webhook</Button>
      </div>

      <div className="webhook-list">
        {webhooks.map((webhook) => (
          <WebhookCard key={webhook.id} webhook={webhook} onTestClick={handleTest} />
        ))}
      </div>

      {showAddDialog && <AddWebhookDialog onClose={() => setShowAddDialog(false)} />}
    </div>
  );
};

const WebhookCard: React.FC<{ webhook: Webhook; onTestClick: (id: string) => void }> = ({ webhook, onTestClick }) => {
  const [showLogs, setShowLogs] = useState(false);
  const { data: logs } = useQuery(
    ['webhook-logs', webhook.id],
    () => api.get(`/webhooks/${webhook.id}/executions`),
    { enabled: showLogs }
  );

  return (
    <div className="webhook-card">
      <div className="webhook-header">
        <span className="url">{webhook.webhook_url}</span>
        <Badge status={webhook.is_active ? 'active' : 'inactive'}>
          {webhook.test_result_status === 200 ? '✓ Healthy' : '✗ Last failed'}
        </Badge>
      </div>

      <div className="webhook-events">
        {webhook.event_types.map((evt) => (
          <span key={evt} className="event-tag">{evt}</span>
        ))}
      </div>

      <div className="webhook-actions">
        <Button size="sm" onClick={() => onTestClick(webhook.id)}>Test Now</Button>
        <Button size="sm" variant="secondary" onClick={() => setShowLogs(!showLogs)}>
          {showLogs ? 'Hide' : 'View'} Logs
        </Button>
        <Button size="sm" variant="danger">Delete</Button>
      </div>

      {showLogs && (
        <div className="execution-logs">
          <h4>Recent Executions (last 50)</h4>
          <Table
            columns={[
              { key: 'event_type', label: 'Event' },
              { key: 'http_status', label: 'Status', render: (val) => <Badge>{val}</Badge> },
              { key: 'execution_time_ms', label: 'Duration', render: (val) => `${val}ms` },
              { key: 'created_at', label: 'Time', render: (val) => formatDate(val) }
            ]}
            rows={logs?.executions || []}
          />
        </div>
      )}
    </div>
  );
};
```

### 2.4 Implementation Timeline

**Week 1**: Webhook CRUD operations + test functionality (15 hours)
**Week 2**: Execution log viewer + retry logic (10 hours)
**Week 3**: Frontend UI components (15 hours)
**Week 4**: Integration testing + launch (10 hours)

**Total**: 50 hours (1.25 engineer weeks)

---

## Feature 3: API Key Management

### 3.1 API Endpoints

**POST /api/v1/api-keys** — Generate new API key

```php
class ApiKeyController extends Controller {
  public function store(Request $request) {
    $validated = $request->validate([
      'name' => 'required|string|max:100',
      'scopes' => 'required|array|min:1',
      'scopes.*' => 'in:email.read,email.send,webhook.manage,template.read',
      'expires_at' => 'nullable|date|after:today'
    ]);

    $key = ApiKey::create([
      'tenant_id' => Auth::user()->tenant_id,
      'name' => $validated['name'],
      'key' => 'sk_live_' . bin2hex(random_bytes(32)),
      'key_hash' => hash('sha256', $validated['key']),
      'scopes' => $validated['scopes'],
      'expires_at' => $validated['expires_at'] ?? now()->addYears(1),
      'created_by' => Auth::id()
    ]);

    // Return plain key ONCE (not stored in DB)
    return response()->json([
      'key' => $key->key, // Only shown once
      'name' => $key->name,
      'created_at' => $key->created_at,
      'warning' => 'Save this key in a secure location. You will not be able to see it again.'
    ], 201);
  }

  public function index(Request $request) {
    $keys = ApiKey::where('tenant_id', Auth::user()->tenant_id)
      ->select('id', 'name', 'scopes', 'created_at', 'last_used_at', 'expires_at', 'is_active')
      ->orderBy('created_at', 'desc')
      ->paginate();

    return response()->json([
      'data' => $keys->items(),
      'pagination' => ['total' => $keys->total(), 'page' => $keys->currentPage()]
    ]);
  }

  public function revoke($keyId) {
    $key = ApiKey::where('id', $keyId)
      ->where('tenant_id', Auth::user()->tenant_id)
      ->firstOrFail();

    $key->update(['is_active' => false, 'revoked_at' => now()]);

    // Invalidate cache immediately (<500ms to take effect)
    Cache::forget("api_key:{$key->key_hash}");

    return response()->json(['message' => 'API key revoked']);
  }
}
```

### 3.2 Frontend: API Key Manager

```tsx
export const ApiKeyManagerUI: React.FC = () => {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [showAddDialog, setShowAddDialog] = useState(false);

  const { data: keysData } = useQuery(
    ['api-keys'],
    () => api.get('/api-keys')
  );

  useEffect(() => {
    if (keysData) setKeys(keysData.data);
  }, [keysData]);

  const handleRevoke = async (keyId: string) => {
    if (confirm('Revoking this key will immediately stop it from working.')) {
      await api.post(`/api-keys/${keyId}/revoke`);
      setKeys(keys.filter((k) => k.id !== keyId));
    }
  };

  return (
    <div className="api-key-manager">
      <h2>API Keys</h2>
      <Button onClick={() => setShowAddDialog(true)}>+ Generate New Key</Button>

      <Table
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'scopes', label: 'Permissions', render: (val) => val.join(', ') },
          { key: 'created_at', label: 'Created', render: (val) => formatDate(val) },
          { key: 'last_used_at', label: 'Last Used', render: (val) => val ? formatDate(val) : 'Never' },
          { key: 'expires_at', label: 'Expires', render: (val) => formatDate(val) },
          {
            label: 'Action',
            render: (_, row) => (
              <Button size="sm" variant="danger" onClick={() => handleRevoke(row.id)}>
                Revoke
              </Button>
            )
          }
        ]}
        rows={keys}
      />

      {showAddDialog && <GenerateKeyDialog onClose={() => setShowAddDialog(false)} />}
    </div>
  );
};
```

### 3.3 Implementation Timeline

**Week 1**: API endpoints + key generation (12 hours)
**Week 2**: Revocation + expiration logic (8 hours)
**Week 3**: Frontend UI (10 hours)
**Week 4**: Integration testing (5 hours)

**Total**: 35 hours (0.9 engineer weeks)

---

## Feature 1-3 Combined: Week-by-Week Breakdown

| Week | Email Search | Webhooks | API Keys | Deliverables |
|------|--------------|----------|----------|--------------|
| Week 1 | DB + API foundation | DB schema | API endpoints | 3 database migrations, 3 controller files |
| Week 2 | Soft delete + recovery | CRUD + test | Key revocation | 2 job files, 1 middleware file |
| Week 3 | Frontend search/delete | Frontend manager | Frontend manager | 4 React components |
| Week 4 | Integration testing | Integration testing | Integration testing | 30 test cases, QA report |

**Total Effort**: 40 + 50 + 35 = **125 hours** (3.1 engineer weeks)  
**Status**: Week 1 of Phase 8, on track for 2026-05-24 completion

---

## Testing Strategy

**Unit Tests**: 25 tests (API endpoints, data validation)
**Integration Tests**: 20 tests (search → select → delete flow)
**UI Tests**: 15 tests (Vitest for React components)
**Performance Tests**: K6 load test (1,000 concurrent searches)

**Total**: 60 test cases, target >95% pass rate

---

## Success Criteria Validation

By May 24, 2026:
- [ ] Search latency <500ms (p95)
- [ ] Bulk delete success rate >99.5%
- [ ] Webhook test success rate >95%
- [ ] API key generation <1 second
- [ ] 60 test cases passing
- [ ] UI accessibility WCAG 2.1 AA
- [ ] 5% customer beta adoption
- [ ] Zero data loss in delete operations

**Status**: Ready for Phase 8, Week 1 execution starting 2026-05-01

---

**Document Created**: 2026-04-20  
**Status**: Ready for implementation  
**Next**: Phase 8, Step 2 (AI-Powered Features)
