# Phase 10, Step 4: Developer Marketplace & Plugins Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Platform architect + developer relations  
**Timeline**: October 15 - November 15, 2026 (4 weeks, parallel with EU deployment)  
**Effort**: 130 hours (3.3 engineer weeks)  
**Expected Impact**: Enable third-party developers, unlock custom use cases, increase stickiness

---

## Executive Summary

Developer marketplace allows third-party developers to build plugins/extensions for email sidecar platform. Creates ecosystem around core product:

**Benefits**:
- Custom integrations without core team effort
- Increased platform stickiness (switching cost)
- Revenue via revenue share (80/20 split)
- Community-driven innovation

**Use Cases**:
- Custom email validators
- Integration with proprietary systems (CRM, ERP, etc.)
- Specialized webhooks/transformations
- Industry-specific templates and workflows

**Expected Impact**: +$15K/month revenue (10% of plugins monetized), +50 ecosystem developers

---

## Part 1: Plugin Architecture

### 1.1 Plugin Types

**Type A: Webhook Transformers**
- Input: Email webhook event
- Output: Transformed data (filter, enrich, route)
- Example: "If bounce rate >5%, send Slack alert"

**Type B: Template Processors**
- Input: Template variables
- Output: Processed/enriched template body
- Example: "Pull customer data from Salesforce, insert into template"

**Type C: Delivery Handlers**
- Input: Email to send
- Output: Forwarded to alternate provider (alternative to Mailgun)
- Example: "Route marketing emails to SendGrid, transactional to Amazon SES"

**Type D: Analytics Plugins**
- Input: Metrics/events
- Output: Custom calculations/visualizations
- Example: "Calculate engagement score per recipient"

### 1.2 Plugin Manifest

**Standard Format** (`plugin.json`):

```json
{
  "name": "slack-bounce-alerts",
  "version": "1.0.0",
  "author": "john-doe",
  "description": "Send Slack notifications for high bounce rates",
  "type": "webhook_transformer",
  "permissions": [
    "webhooks:read",
    "webhooks:write",
    "alerts:create"
  ],
  "entrypoint": "index.js",
  "config": {
    "slack_webhook_url": {
      "type": "string",
      "required": true,
      "description": "Slack webhook URL for notifications"
    },
    "bounce_threshold": {
      "type": "number",
      "required": false,
      "default": 0.05,
      "description": "Bounce rate threshold (0.05 = 5%)"
    }
  },
  "triggers": {
    "on_webhook_event": {
      "event_type": "email.bounced",
      "handler": "handleBounce"
    }
  }
}
```

---

## Part 2: Plugin SDK & Runtime

### 2.1 JavaScript/Node.js SDK

**Installation**:

```bash
npm install @email-sidecar/plugin-sdk
```

**Example Plugin** (webhook transformer):

```javascript
// plugins/slack-bounce-alerts/index.js
const { Plugin, WebhookTransformer } = require('@email-sidecar/plugin-sdk');

class SlackBounceAlerts extends WebhookTransformer {
  constructor(config) {
    super(config);
    this.slackWebhookUrl = config.slack_webhook_url;
    this.bounceThreshold = config.bounce_threshold || 0.05;
    this.bounceCount = 0;
    this.totalCount = 0;
  }

  async handle(event) {
    // Track bounce rate
    this.totalCount++;
    
    if (event.type === 'email.bounced') {
      this.bounceCount++;
    }

    const bounceRate = this.bounceCount / this.totalCount;

    // Send alert if threshold exceeded
    if (bounceRate > this.bounceThreshold) {
      await this.sendSlackAlert({
        text: `⚠️ High bounce rate detected: ${(bounceRate * 100).toFixed(2)}%`,
        details: {
          bounces: this.bounceCount,
          total: this.totalCount,
          rate: bounceRate
        }
      });
    }

    // Pass through unmodified (transformer doesn't modify event)
    return event;
  }

  async sendSlackAlert(message) {
    const response = await fetch(this.slackWebhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: message.text,
        blocks: [
          {
            type: 'section',
            text: { type: 'mrkdwn', text: message.text }
          },
          {
            type: 'divider'
          },
          {
            type: 'section',
            fields: [
              {
                type: 'mrkdwn',
                text: `*Bounces*\n${message.details.bounces}`
              },
              {
                type: 'mrkdwn',
                text: `*Total*\n${message.details.total}`
              }
            ]
          }
        ]
      })
    });

    return response.ok;
  }
}

module.exports = new SlackBounceAlerts();
```

### 2.2 SDK Features

**Plugin Base Class**:

```javascript
class Plugin {
  // Lifecycle hooks
  async onCreate() {}      // Called when plugin installed
  async onUpdate() {}      // Called when plugin updated
  async onDelete() {}      // Called when plugin uninstalled
  async onEnable() {}      // Called when activated
  async onDisable() {}     // Called when deactivated

  // Configuration
  async getConfig() {}     // Retrieve current config
  async setConfig(obj) {}  // Update config

  // Logging
  log(message) {}          // Standard log
  warn(message) {}         // Warning
  error(message) {}        // Error

  // API Access (scoped to permissions)
  async api(path, options) {}  // Make authenticated API calls
}
```

**Helper Methods** (SDK provides):

```javascript
const { delay, retry, cache, hash } = require('@email-sidecar/plugin-sdk/utils');

// Retry with backoff
const result = await retry(
  () => externalApiCall(),
  { maxAttempts: 3, backoff: 'exponential' }
);

// Cache results
const cached = await cache(
  'my-key',
  () => expensiveOperation(),
  { ttl: 3600 }
);
```

---

## Part 3: Plugin Registry & Discovery

### 3.1 Marketplace Database Schema

```sql
CREATE TABLE plugins (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug VARCHAR(100) UNIQUE NOT NULL,  -- slack-bounce-alerts
  name VARCHAR(200) NOT NULL,
  description TEXT,
  author_id UUID REFERENCES users(id),
  type ENUM('webhook_transformer', 'template_processor', 'delivery_handler', 'analytics'),
  version VARCHAR(20),  -- semver: 1.0.0
  repository_url VARCHAR(500),  -- GitHub/GitLab link
  npm_package_name VARCHAR(200),  -- For Node.js plugins
  homepage_url VARCHAR(500),
  documentation_url VARCHAR(500),
  icon_url VARCHAR(500),
  
  -- Metadata
  downloads INT DEFAULT 0,
  rating DECIMAL(3,2),  -- 1.0-5.0
  review_count INT DEFAULT 0,
  last_updated TIMESTAMP,
  
  -- Status
  status ENUM('draft', 'submitted', 'approved', 'published', 'suspended') DEFAULT 'draft',
  published_at TIMESTAMP,
  
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE plugin_ratings (
  id UUID PRIMARY KEY,
  plugin_id UUID REFERENCES plugins(id),
  user_id UUID REFERENCES users(id),
  rating INT CHECK (rating >= 1 AND rating <= 5),
  review TEXT,
  created_at TIMESTAMP,
  UNIQUE(plugin_id, user_id)
);

CREATE TABLE plugin_installations (
  id UUID PRIMARY KEY,
  plugin_id UUID REFERENCES plugins(id),
  tenant_id UUID REFERENCES tenants(id),
  config JSONB,
  enabled BOOLEAN DEFAULT true,
  installed_at TIMESTAMP,
  UNIQUE(plugin_id, tenant_id)
);
```

### 3.2 Marketplace UI (React)

```tsx
export const PluginMarketplace: React.FC = () => {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [filters, setFilters] = useState({ type: '', search: '' });

  const { data: pluginsData } = useQuery(
    ['plugins', filters],
    () => api.get('/marketplace/plugins', { params: filters })
  );

  useEffect(() => {
    if (pluginsData) setPlugins(pluginsData.data);
  }, [pluginsData]);

  return (
    <div className="marketplace">
      <div className="header">
        <h1>Plugin Marketplace</h1>
        <p>{plugins.length} plugins available</p>
      </div>

      <div className="filters">
        <Input
          placeholder="Search plugins..."
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        
        <Select
          value={filters.type}
          onChange={(val) => setFilters({ ...filters, type: val })}
          options={[
            { label: 'All Types', value: '' },
            { label: 'Webhook Transformers', value: 'webhook_transformer' },
            { label: 'Template Processors', value: 'template_processor' },
            { label: 'Delivery Handlers', value: 'delivery_handler' },
            { label: 'Analytics', value: 'analytics' }
          ]}
        />
      </div>

      <div className="plugins-grid">
        {plugins.map((plugin) => (
          <PluginCard key={plugin.id} plugin={plugin} />
        ))}
      </div>
    </div>
  );
};

const PluginCard: React.FC<{ plugin: Plugin }> = ({ plugin }) => {
  const [installing, setInstalling] = useState(false);

  const handleInstall = async () => {
    setInstalling(true);
    try {
      await api.post(`/marketplace/plugins/${plugin.id}/install`);
      toast.success('Plugin installed');
    } catch (err) {
      toast.error('Installation failed');
    } finally {
      setInstalling(false);
    }
  };

  return (
    <div className="plugin-card">
      {plugin.icon_url && <img src={plugin.icon_url} alt={plugin.name} />}
      
      <h3>{plugin.name}</h3>
      <p className="author">by {plugin.author.name}</p>
      <p className="description">{plugin.description}</p>

      <div className="meta">
        <Badge>{plugin.type}</Badge>
        <span className="rating">
          ⭐ {plugin.rating?.toFixed(1) || 'N/A'} ({plugin.review_count} reviews)
        </span>
        <span className="downloads">{plugin.downloads} installs</span>
      </div>

      <Button
        onClick={handleInstall}
        loading={installing}
      >
        Install
      </Button>
    </div>
  );
};
```

---

## Part 4: Plugin Developer Console

### 4.1 Developer Dashboard

**Route**: `/developers/console`

**Features**:
- Plugin creation form (manifest generator)
- Code editor (test locally before publishing)
- Version management (publish new versions)
- Analytics (downloads, ratings, reviews)
- Earnings dashboard (revenue share tracking)

### 4.2 Plugin Submission Process

```
Step 1: Developer submits plugin manifest + code
         ↓
Step 2: Automated validation
        - Check manifest schema
        - Lint JavaScript/TypeScript
        - Security scan (no eval(), no process calls, etc.)
         ↓
Step 3: Manual review (Email Sidecar team)
        - Code review (security, performance)
        - Documentation review
        - Test installation in sandbox
         ↓
Step 4: Approved/Rejected
        - If approved: Published to marketplace
        - If rejected: Developer receives feedback
```

### 4.3 Submission API

```php
class PluginSubmissionController extends Controller {
  
  public function submit(Request $request) {
    $validated = $request->validate([
      'plugin_manifest' => 'required|json',
      'code_zip' => 'required|file|max:10240'  // 10 MB max
    ]);

    $manifest = json_decode($validated['plugin_manifest']);
    
    // Validate manifest schema
    $this->validateManifest($manifest);
    
    // Scan code for security issues
    $securityIssues = $this->scanCode($validated['code_zip']);
    if (!empty($securityIssues)) {
      return response()->json([
        'error' => 'Security issues found',
        'issues' => $securityIssues
      ], 422);
    }

    // Create plugin submission
    $plugin = Plugin::create([
      'author_id' => Auth::id(),
      'slug' => Str::slug($manifest->name),
      'name' => $manifest->name,
      'description' => $manifest->description,
      'type' => $manifest->type,
      'status' => 'submitted',
      'manifest' => $manifest
    ]);

    // Queue for review
    ReviewPluginSubmissionJob::dispatch($plugin);

    return response()->json([
      'plugin_id' => $plugin->id,
      'status' => 'submitted',
      'message' => 'Plugin submitted for review. You will receive an update within 48 hours.'
    ], 202);
  }

  private function validateManifest($manifest) {
    $schema = [
      'name' => 'required|string',
      'version' => 'required|regex:/^\d+\.\d+\.\d+$/',  // semver
      'type' => 'required|in:webhook_transformer,template_processor,delivery_handler,analytics',
      'description' => 'required|string|max:500',
      'entrypoint' => 'required|string',
      'permissions' => 'required|array',
      'config' => 'nullable|array'
    ];

    // Validate against schema
    foreach ($schema as $key => $rules) {
      // Validation logic
    }
  }

  private function scanCode($zipFile) {
    $issues = [];
    
    // Check for dangerous patterns
    $dangerousPatterns = [
      'eval(' => 'eval() is not allowed',
      'exec(' => 'exec() is not allowed',
      'process.exit' => 'process.exit() not allowed',
      'require("child_process")' => 'Child process access not allowed'
    ];

    // Extract and scan
    $contents = file_get_contents($zipFile);
    foreach ($dangerousPatterns as $pattern => $message) {
      if (strpos($contents, $pattern) !== false) {
        $issues[] = $message;
      }
    }

    return $issues;
  }
}
```

---

## Part 5: Plugin Execution & Sandboxing

### 5.1 Isolated Execution Environment

**Use AWS Lambda for Plugin Execution**:

```python
# Lambda function: execute_plugin
def lambda_handler(event, context):
    plugin_id = event['plugin_id']
    tenant_id = event['tenant_id']
    trigger = event['trigger']
    data = event['data']

    # Load plugin code (from S3)
    plugin_code = s3.get_object(
        Bucket='plugin-repository',
        Key=f'{plugin_id}/index.js'
    )['Body'].read()

    # Load plugin config (tenant-specific)
    config = dynamodb.get_item(
        TableName='PluginConfigs',
        Key={'plugin_id': plugin_id, 'tenant_id': tenant_id}
    )

    # Execute in isolated Node.js runtime
    result = execute_nodejs(
        code=plugin_code,
        config=config,
        trigger=trigger,
        data=data,
        timeout=30  # 30 second timeout per plugin
    )

    return result
```

### 5.2 Resource Limits

**Per Plugin Execution**:
- CPU: 256 MB (shared)
- Memory: 128 MB
- Timeout: 30 seconds
- API calls: 100 per execution
- Storage: 512 MB temp space (ephemeral)

**Rate Limits**:
- Per tenant per hour: 10,000 plugin executions
- Per webhook event: 5 concurrent plugins

---

## Part 6: Revenue Share & Monetization

### 6.1 Revenue Tracking

```sql
CREATE TABLE plugin_revenue (
  id UUID PRIMARY KEY,
  plugin_id UUID REFERENCES plugins(id),
  period DATE,  -- Monthly billing period
  subscriptions INT,  -- Paying customers using this plugin
  gross_revenue DECIMAL(10,2),
  platform_fee DECIMAL(10,2),  -- 20%
  developer_payout DECIMAL(10,2),  -- 80%
  status ENUM('pending', 'processed', 'paid'),
  paid_at TIMESTAMP
);
```

### 6.2 Monetization Model

**Option A: Free (Default)**
- No revenue split
- Used by developers building for community

**Option B: Paid (Premium Plugins)**
- Developer sets price ($0.01 - $100/month per tenant)
- Platform takes 20%, developer gets 80%
- Billing integrated into customer invoice

**Option C: Revenue Share (High-Value Plugins)**
- Developer revenue tied to customer success
- Example: "1% of customer's SMS volume"
- Negotiated on case-by-case basis

---

## Part 7: Plugin Lifecycle

### 7.1 Installation Workflow

```
Customer selects "Install" on plugin
  ↓
System shows config form (from plugin.json)
  ↓
Customer provides config (Slack webhook URL, etc.)
  ↓
System calls plugin.onCreate()
  ↓
Plugin installed, enabled by default
  ↓
System tests plugin (mock webhook event)
  ↓
Success notification to customer
```

### 7.2 Update Workflow

```
Developer publishes new version
  ↓
Approval process (same as initial submission)
  ↓
Approved plugins marked "Update Available"
  ↓
Customer sees update notification
  ↓
Customer clicks "Update"
  ↓
System runs plugin.onUpdate()
  ↓
New version takes effect
```

### 7.3 Uninstall Workflow

```
Customer clicks "Uninstall"
  ↓
Confirmation dialog (warn about data loss)
  ↓
System calls plugin.onDelete()
  ↓
Plugin disabled, config removed
  ↓
Uninstall notification to developer (analytics)
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | SDK design, manifest schema, runtime | 35 | SDK npm package, sandbox Lambda |
| **Week 2** | Marketplace UI, developer console, submission | 40 | Marketplace live, developer signup |
| **Week 3** | Security scanning, revenue tracking | 35 | Plugin review process, payout system |
| **Week 4** | Testing, documentation, launch | 20 | Docs, sample plugins, launch |

**Total**: 130 hours

---

## Success Criteria

| Metric | Target | Measurement | Timeline |
|---|---|---|---|
| Developer signups | >50 | Developer console analytics | 3 months |
| Published plugins | >30 | Plugin registry count | 3 months |
| Plugin installations | >500 | Installation tracking | 3 months |
| Revenue share | >$5K/month | Payout processing | 6 months |
| Average rating | >4.0 stars | User reviews | 6 months |

---

## Security & Compliance

**Plugin Sandboxing**:
- ✓ No access to host filesystem
- ✓ No access to other plugins' data
- ✓ No uncontrolled network access
- ✓ 30-second timeout (prevent infinite loops)
- ✓ Memory limit (prevent OOM attacks)

**Code Review**:
- ✓ All plugins code-reviewed before publication
- ✓ Automated security scanning (SAST)
- ✓ Manual testing in sandbox environment
- ✓ Suspend plugins if security issues discovered

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 10 Week 4 execution  
**Next**: Phase 10, Step 5 (HIPAA Compliance Framework)
