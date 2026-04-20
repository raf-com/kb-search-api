# Phase 8, Step 3: Marketplace Integration Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Integration engineer  
**Timeline**: May 1-24, 2026 (4 weeks, parallel with Steps 1-2)  
**Effort**: 75 hours (1.9 engineer weeks)  
**Scope**: Zapier + Make.com only (defer custom framework to Phase 9)

---

## Executive Summary

Marketplace integrations expand reach by plugging into workflow platforms. Two initial targets:

1. **Zapier** — 6M+ users, mature marketplace ecosystem, highest ROI
2. **Make.com** — 7M+ users, European strength, visual module builder

Expected impact: +250 new customers via marketplace discovery, freemium-to-paid conversion via integration workflows.

**Success Criterion**: >500 active Zapier users and >300 Make users by 2026-07-01

---

## Architecture: OAuth Flow for Integrations

**Sequence Diagram**:
```
Zapier → [1. Authorization Request] → Our OAuth Server
        ← [2. Auth Code] ←
[3. Exchange Code for Access Token]
← [4. Access Token (Scoped to Tenant)] ←
[5. Use Token for API calls (Tenant isolation via token scopes)]
```

### OAuth Token Scoping

```php
// When Zapier requests authorization
class OAuthController {
  public function authorize(Request $request) {
    return view('oauth.authorize', [
      'client_id' => $request->client_id,
      'scopes' => ['email:read', 'email:send', 'webhook:manage'],
      'redirect_uri' => $request->redirect_uri
    ]);
  }

  public function token(Request $request) {
    $validated = $request->validate([
      'code' => 'required',
      'client_id' => 'required',
      'client_secret' => 'required'
    ]);

    // Verify code + create scoped token
    $user = User::findByOAuthCode($validated['code']);
    
    $token = $user->createToken('zapier-integration', [
      'email:read',
      'email:send',
      'webhook:manage'
    ])->plainTextToken;

    return response()->json([
      'access_token' => $token,
      'token_type' => 'Bearer',
      'expires_in' => 31536000 // 1 year
    ]);
  }
}
```

---

## Integration 1: Zapier App

### 1.1 Zapier CLI Setup

**Install & Initialize**:
```bash
npm install -g zapier-platform-cli
zapier init email-sidecar
cd email-sidecar/
```

**Directory Structure**:
```
email-sidecar/
├── src/
│   ├── triggers/
│   │   ├── email_delivered.js
│   │   ├── email_bounced.js
│   │   └── email_complained.js
│   ├── actions/
│   │   ├── send_email.js
│   │   ├── create_template.js
│   │   └── update_webhook.js
│   ├── authentication.js
│   └── index.js
├── package.json
└── .zapierapprc
```

### 1.2 Authentication (OAuth 2.0)

**authentication.js**:
```javascript
const authentication = {
  type: 'oauth2',
  test: {
    url: 'https://api.example.com/v1/user',
    method: 'GET'
  },
  oauth2Config: {
    authorizeUrl: {
      url: 'https://api.example.com/oauth/authorize',
      params: {
        client_id: '{{process.env.CLIENT_ID}}',
        redirect_uri: '{{bundle.inputData.redirect_uri}}',
        response_type: 'code',
        scope: 'email:read email:send webhook:manage'
      }
    },
    getAccessToken: {
      url: 'https://api.example.com/oauth/token',
      method: 'POST',
      body: {
        code: '{{bundle.inputData.code}}',
        client_id: '{{process.env.CLIENT_ID}}',
        client_secret: '{{process.env.CLIENT_SECRET}}',
        redirect_uri: '{{bundle.inputData.redirect_uri}}',
        grant_type: 'authorization_code'
      },
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    },
    refreshAccessToken: {
      url: 'https://api.example.com/oauth/token',
      method: 'POST',
      body: {
        refresh_token: '{{bundle.authData.refresh_token}}',
        client_id: '{{process.env.CLIENT_ID}}',
        client_secret: '{{process.env.CLIENT_SECRET}}',
        grant_type: 'refresh_token'
      }
    },
    scope: 'email:read email:send webhook:manage'
  }
};

module.exports = { authentication };
```

### 1.3 Trigger: Email Delivered

**src/triggers/email_delivered.js**:
```javascript
const emailDeliveredTrigger = {
  key: 'email_delivered',
  noun: 'Email',
  display: {
    label: 'Email Delivered',
    description: 'Triggers when an email is successfully delivered.'
  },
  operation: {
    type: 'hook',
    inputFields: [
      {
        key: 'recipient_domain',
        label: 'Recipient Domain (optional)',
        helpText: 'Filter by recipient email domain (e.g., gmail.com)',
        required: false
      }
    ],
    perform: {
      url: 'https://api.example.com/v1/webhooks',
      method: 'POST',
      body: {
        event_types: ['email.delivered'],
        webhook_url: '{{bundle.targetUrl}}',
        custom_data: {
          filter_domain: '{{bundle.inputData.recipient_domain}}'
        }
      }
    },
    performList: {
      url: 'https://api.example.com/v1/emails?status=delivered&limit=10',
      method: 'GET'
    },
    sample: {
      id: 'email-uuid',
      event_type: 'email.delivered',
      recipient: 'user@example.com',
      subject: 'Welcome to our service',
      delivered_at: '2026-04-20T14:30:00Z'
    }
  }
};

module.exports = { emailDeliveredTrigger };
```

### 1.4 Action: Send Email

**src/actions/send_email.js**:
```javascript
const sendEmailAction = {
  key: 'send_email',
  noun: 'Email',
  display: {
    label: 'Send Email',
    description: 'Sends an email through your account.'
  },
  operation: {
    inputFields: [
      { key: 'recipient', label: 'Recipient Email', required: true },
      { key: 'subject', label: 'Subject', required: true },
      { key: 'body', label: 'Body (HTML)', required: true },
      { 
        key: 'template_id', 
        label: 'Or use Template',
        helpText: 'Leave blank to use custom body'
      }
    ],
    perform: {
      url: 'https://api.example.com/v1/emails/send',
      method: 'POST',
      body: {
        recipient: '{{bundle.inputData.recipient}}',
        subject: '{{bundle.inputData.subject}}',
        body: '{{bundle.inputData.body}}',
        template_id: '{{bundle.inputData.template_id}}'
      }
    },
    sample: {
      id: 'email-uuid',
      status: 'queued',
      recipient: '{{bundle.inputData.recipient}}',
      created_at: '2026-04-20T14:30:00Z'
    }
  }
};

module.exports = { sendEmailAction };
```

### 1.5 Deployment to Zapier

```bash
# Prepare for submission
zapier push

# Verify API endpoints are working
zapier test

# Submit to Zapier app review
# (Zapier team reviews for 2-3 days)

# Once approved, appears in Zapier App Directory
# Expected: 50+ active users within 1 week
```

### 1.6 Timeline for Zapier

**Week 1**: OAuth setup, authentication testing (15 hours)
**Week 2**: Trigger/action implementation, sample data (15 hours)
**Week 3**: CLI validation, error handling (10 hours)
**Week 4**: Submit to Zapier, monitor approvals, iterate on feedback (10 hours)

**Total**: 50 hours

---

## Integration 2: Make.com Module

### 2.1 Make.com Module Structure

**Directory Structure**:
```
email-sidecar-make/
├── modules/
│   ├── SendEmail.json
│   ├── SearchEmails.json
│   ├── CreateWebhook.json
│   └── GetEmails.json
├── manifest.json
└── README.md
```

### 2.2 Module Definition: Send Email

**modules/SendEmail.json**:
```json
{
  "name": "Send Email",
  "description": "Sends an email through Email Sidecar.",
  "version": "1.0.0",
  "base_url": "https://api.example.com",
  "auth": {
    "type": "oauth2",
    "authorize_url": "/oauth/authorize",
    "access_token_url": "/oauth/token",
    "scope": "email:send"
  },
  "interface": [
    {
      "name": "recipient",
      "label": "Recipient Email",
      "type": "email",
      "required": true,
      "help": "Email address to send to"
    },
    {
      "name": "subject",
      "label": "Subject",
      "type": "text",
      "required": true
    },
    {
      "name": "body",
      "label": "Body",
      "type": "textarea",
      "required": true
    },
    {
      "name": "template_id",
      "label": "Template (optional)",
      "type": "select",
      "collection": "templates"
    }
  ],
  "request": {
    "url": "/v1/emails/send",
    "method": "POST",
    "body": {
      "recipient": "{{recipient}}",
      "subject": "{{subject}}",
      "body": "{{body}}",
      "template_id": "{{template_id}}"
    }
  },
  "response": {
    "sample": {
      "id": "email-uuid",
      "status": "queued",
      "created_at": "2026-04-20T14:30:00Z"
    }
  }
}
```

### 2.3 Module Definition: Search Emails

**modules/SearchEmails.json**:
```json
{
  "name": "Search Emails",
  "description": "Searches emails with filters.",
  "interface": [
    {
      "name": "status",
      "label": "Status",
      "type": "select",
      "options": ["delivered", "bounced", "complained", "deferred"]
    },
    {
      "name": "date_from",
      "label": "From Date",
      "type": "date"
    },
    {
      "name": "date_to",
      "label": "To Date",
      "type": "date"
    }
  ],
  "request": {
    "url": "/v1/emails/search",
    "method": "POST",
    "body": {
      "filters": {
        "status": "{{status}}",
        "date_from": "{{date_from}}",
        "date_to": "{{date_to}}"
      },
      "pagination": {
        "page": 1,
        "per_page": 50
      }
    }
  },
  "response": {
    "sample": [
      {
        "id": "email-uuid",
        "recipient": "user@example.com",
        "subject": "Welcome",
        "status": "delivered",
        "created_at": "2026-04-20T14:30:00Z"
      }
    ]
  }
}
```

### 2.4 Manifest

**manifest.json**:
```json
{
  "name": "Email Sidecar",
  "description": "Professional email delivery and analytics.",
  "version": "1.0.0",
  "author": "Email Sidecar Team",
  "homepage": "https://example.com",
  "logo": "https://example.com/logo.png",
  "modules": [
    { "name": "SendEmail", "path": "modules/SendEmail.json" },
    { "name": "SearchEmails", "path": "modules/SearchEmails.json" },
    { "name": "CreateWebhook", "path": "modules/CreateWebhook.json" },
    { "name": "GetEmails", "path": "modules/GetEmails.json" }
  ],
  "auth": {
    "type": "oauth2",
    "authorize_url": "https://api.example.com/oauth/authorize",
    "access_token_url": "https://api.example.com/oauth/token"
  }
}
```

### 2.5 Submission to Make

```bash
# Package modules
zip -r email-sidecar-make.zip modules/ manifest.json

# Submit to Make App Store
# 1. Log in to Make Developer Dashboard
# 2. Create new integration
# 3. Upload manifest + modules
# 4. Configure OAuth endpoints
# 5. Submit for review (1-2 days)

# Expected outcome: Listed in Make App Store
# Expected users: 50-100 within first month
```

### 2.6 Timeline for Make

**Week 1**: Module structure, JSON schema definitions (12 hours)
**Week 2**: Complete module implementations (15 hours)
**Week 3**: OAuth testing, error handling (8 hours)
**Week 4**: Submit, iterate on feedback (10 hours)

**Total**: 45 hours

---

## Integration 3: Custom Marketplace UI

### 3.1 One-Click Integration Templates

**File**: `/c/kb-search-api/MARKETPLACE_TEMPLATES.json`

```json
{
  "templates": [
    {
      "id": "slack-delivery-alerts",
      "name": "Slack: Email Delivery Alerts",
      "description": "Send Slack message when emails are delivered.",
      "platforms": ["Zapier", "Make"],
      "steps": [
        {
          "platform": "zapier",
          "action": "trigger_email_delivered",
          "parameters": {}
        },
        {
          "platform": "zapier",
          "action": "send_slack_message",
          "parameters": {
            "channel": "#email-alerts",
            "message": "New email delivered: {{subject}} to {{recipient}}"
          }
        }
      ],
      "installation_time_minutes": 2,
      "users": 0
    },
    {
      "id": "discord-bounce-notifications",
      "name": "Discord: Bounce Notifications",
      "description": "Get Discord alerts when emails bounce.",
      "platforms": ["Zapier", "Make"],
      "steps": [
        {
          "platform": "zapier",
          "action": "trigger_email_bounced",
          "parameters": {}
        },
        {
          "platform": "zapier",
          "action": "send_discord_message",
          "parameters": {
            "webhook_url": "user_input",
            "message": "⚠️ Email bounced: {{recipient}}"
          }
        }
      ],
      "installation_time_minutes": 2,
      "users": 0
    },
    {
      "id": "pagerduty-critical-alerts",
      "name": "PagerDuty: Critical Alerts",
      "description": "Create PagerDuty incidents for critical delivery issues.",
      "platforms": ["Zapier", "Make"],
      "steps": [],
      "installation_time_minutes": 5,
      "users": 0
    }
  ]
}
```

### 3.2 Marketplace UI Component (React)

```tsx
export const MarketplaceUI: React.FC = () => {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);

  const { data: templatesData } = useQuery(
    ['marketplace-templates'],
    () => api.get('/marketplace/templates')
  );

  useEffect(() => {
    if (templatesData) setTemplates(templatesData.templates);
  }, [templatesData]);

  const handleInstall = async (template: Template) => {
    // Redirect to Zapier or Make auth flow
    if (template.platforms.includes('Zapier')) {
      window.open(`https://zapier.com/apps/email-sidecar/integrations/${template.id}`);
    }
  };

  return (
    <div className="marketplace">
      <h1>Integration Marketplace</h1>

      <div className="templates-grid">
        {templates.map((template) => (
          <div key={template.id} className="template-card">
            <h3>{template.name}</h3>
            <p>{template.description}</p>

            <div className="platforms">
              {template.platforms.map((platform) => (
                <Badge key={platform}>{platform}</Badge>
              ))}
            </div>

            <div className="meta">
              <span>⏱️ {template.installation_time_minutes} min setup</span>
              <span>👥 {template.users} users</span>
            </div>

            <Button onClick={() => handleInstall(template)}>
              Install Integration
            </Button>
          </div>
        ))}
      </div>

      {selectedTemplate && (
        <TemplateDetailsModal template={selectedTemplate} />
      )}
    </div>
  );
};
```

### 3.3 Timeline for Custom Marketplace

**Week 1**: Marketplace UI design, component structure (10 hours)
**Week 2**: Template definitions, API endpoints (12 hours)
**Week 3**: Integration with Zapier/Make links (8 hours)
**Week 4**: Testing, launch (5 hours)

**Total**: 35 hours

---

## Phase 8, Step 3 Summary

| Integration | Effort (hrs) | Status | Timeline |
|------------|-------------|--------|----------|
| Zapier App | 50 | Schema → Submission | Weeks 1-4 |
| Make.com Module | 45 | Module builder | Weeks 1-4 |
| Custom Marketplace | 35 | UI + Templates | Weeks 1-4 |
| **TOTAL** | **130** | — | **4 weeks** |

**Actual Allocation**: 1 integration engineer, 4 weeks parallelized

---

## Success Criteria

| Metric | Target | Timeline |
|--------|--------|----------|
| Zapier active users | >500 | 2026-07-01 |
| Make.com active users | >300 | 2026-07-01 |
| Custom marketplace templates | >50 | 2026-06-30 |
| Customer acquisition via marketplace | >250 users | 2026-08-01 |
| Freemium → Paid conversion (via integrations) | >20% | 2026-09-01 |

---

## Risk & Mitigation

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Zapier/Make review rejection | Low | Follow schema docs, test thoroughly |
| OAuth token expiration issues | Medium | Implement refresh token logic, test in staging |
| Integration volume unexpectedly low | Medium | Marketing push via email, blog content, partnerships |

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 8 Week 1 execution  
**Next**: Phase 8, Step 4 (Usage Analytics Dashboard)
