# Phase 10, Step 2: WhatsApp Integration via Meta API Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Integration engineer + compliance engineer  
**Timeline**: September 15 - October 15, 2026 (4 weeks, parallel with SMS)  
**Effort**: 140 hours (3.5 engineer weeks)  
**Expected Impact**: Enable WhatsApp messaging, expand to 10% new use cases

---

## Executive Summary

WhatsApp integration adds WhatsApp Business API capability for customer messaging. WhatsApp has 2B+ users globally, making it valuable for customer notifications, support, and campaigns.

**Use Cases**:
- Order status updates
- Customer support conversations
- Two-factor authentication (OTP)
- Customer surveys and feedback
- Marketing campaigns (limited, opt-in only)

**Cost Structure**: $0.0045 per message (vs email $0.00035, SMS $0.0075)  
**Expected Revenue**: +$10K/month (lower volume than SMS)  
**Regulatory**: Requires Meta Business Account + WhatsApp Business API approval

---

## Component 1: Meta Business Account Setup

### 1.1 Prerequisites

**Required**:
- Meta Business Account (create at business.facebook.com)
- Phone number for verification
- WhatsApp Business Account
- Company verification (tax ID, business registration)

### 1.2 WhatsApp Business API Access

```bash
# Step 1: Create Business Account (5 minutes)
# https://business.facebook.com

# Step 2: Add WhatsApp Business Account (15 minutes)
# Phone: Dedicated number for business use
# Category: Technology/Software

# Step 3: Apply for API access
# Expected wait: 3-5 business days for approval

# Step 4: Create System User (for API access)
# Permissions: whatsapp_business_messaging
```

### 1.3 API Credentials

```bash
# After approval, receive:
Phone Number ID: (phone number in WhatsApp Business Account)
Business Account ID: (identifier)
Access Token: (long-lived, never expose)
API Endpoint Base: https://graph.instagram.com/v18.0/
```

---

## Component 2: Message Templates

### 2.1 Template Management

**WhatsApp Template Requirements**:
- Pre-approved content only (no free-form sending)
- Templates must be submitted for review
- Different categories: Transactional, Marketing, OTP

### 2.2 Template Submission

```php
namespace App\Services;

use Illuminate\Support\Facades\Http;

class WhatsAppTemplateService {
  
  private $apiToken;
  private $businessAccountId;
  
  public function __construct() {
    $creds = json_decode(
      aws_get_secret('meta/whatsapp-business'),
      true
    );
    
    $this->apiToken = $creds['access_token'];
    $this->businessAccountId = $creds['business_account_id'];
  }
  
  public function submitTemplate(array $template) {
    // Template structure:
    // {
    //   "name": "order_confirmation",
    //   "language": "en_US",
    //   "category": "TRANSACTIONAL",  // or MARKETING, OTP
    //   "components": [
    //     {
    //       "type": "HEADER",
    //       "format": "TEXT"
    //     },
    //     {
    //       "type": "BODY",
    //       "text": "Your order {{1}} has been confirmed. Total: {{2}}. Track here: {{3}}"
    //     },
    //     {
    //       "type": "FOOTER",
    //       "text": "Thank you for your purchase"
    //     },
    //     {
    //       "type": "BUTTONS",
    //       "buttons": [
    //         {
    //           "type": "URL",
    //           "text": "Track Order",
    //           "url": "https://example.com/track?order={{1}}"
    //         }
    //       ]
    //     }
    //   ]
    // }
    
    $response = Http::withToken($this->apiToken)
      ->post(
        "https://graph.instagram.com/v18.0/{$this->businessAccountId}/message_templates",
        $template
      );
    
    if (!$response->successful()) {
      throw new \Exception("Template submission failed: {$response->body()}");
    }
    
    // Meta reviews templates, approval takes 30 mins - 2 days
    return $response->json();
  }
  
  public function getTemplates() {
    // Retrieve approved templates
    $response = Http::withToken($this->apiToken)
      ->get("https://graph.instagram.com/v18.0/{$this->businessAccountId}/message_templates");
    
    return $response->json()['data'];
  }
}
```

---

## Component 3: Message Sending

### 3.1 Database Schema

```sql
CREATE TABLE whatsapp_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  recipient_phone VARCHAR(20) NOT NULL,  -- E.164 format
  template_name VARCHAR(100),  -- Template ID in WhatsApp
  template_variables JSONB,  -- Variables to substitute in template
  message_type ENUM('template', 'text') DEFAULT 'template',
  message_text TEXT,  -- For text messages (limited use)
  status ENUM('queued', 'sent', 'delivered', 'read', 'failed') DEFAULT 'queued',
  meta_message_id VARCHAR(100),  -- Meta's message ID
  delivery_timestamp TIMESTAMP,
  error_message TEXT,
  cost_usd DECIMAL(6,4),  -- $0.0045 per message
  created_at TIMESTAMP DEFAULT now(),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX idx_whatsapp_tenant_created 
  ON whatsapp_messages(tenant_id, created_at DESC);
```

### 3.2 Message Sending Handler

```php
namespace App\Http\Controllers;

use App\Models\WhatsAppMessage;
use Illuminate\Http\Request;

class WhatsAppController extends Controller {
  
  public function send(Request $request) {
    $validated = $request->validate([
      'recipient_phone' => 'required|phone:INTERNATIONAL',
      'template_name' => 'required|string',
      'variables' => 'nullable|array'
    ]);
    
    // Only Pro/Enterprise tiers
    if (!in_array(Auth::user()->tenant->tier, ['pro', 'enterprise'])) {
      return response()->json([
        'error' => 'WhatsApp requires Pro or Enterprise tier'
      ], 403);
    }
    
    // Create message record
    $message = WhatsAppMessage::create([
      'tenant_id' => Auth::user()->tenant_id,
      'recipient_phone' => $this->normalizePhone($validated['recipient_phone']),
      'template_name' => $validated['template_name'],
      'template_variables' => $validated['variables'] ?? [],
      'status' => 'queued',
      'cost_usd' => 0.0045
    ]);
    
    // Queue for async sending
    SendWhatsAppMessageJob::dispatch($message);
    
    return response()->json([
      'message_id' => $message->id,
      'status' => 'queued'
    ], 202);
  }
  
  private function normalizePhone($phone): string {
    $cleaned = preg_replace('/\D/', '', $phone);
    if (strlen($cleaned) == 10) {
      $cleaned = '1' . $cleaned;  // Assume US
    }
    return '+' . $cleaned;
  }
}
```

### 3.3 Async Sender Job

```php
namespace App\Jobs;

use App\Models\WhatsAppMessage;
use Illuminate\Support\Facades\Http;
use Illuminate\Bus\Queueable;

class SendWhatsAppMessageJob implements ShouldQueue {
  use Queueable;
  
  public function __construct(private WhatsAppMessage $message) {}
  
  public function handle() {
    $creds = json_decode(
      aws_get_secret('meta/whatsapp-business'),
      true
    );
    
    try {
      $response = Http::withToken($creds['access_token'])
        ->post(
          "https://graph.instagram.com/v18.0/{$creds['phone_number_id']}/messages",
          [
            'messaging_product' => 'whatsapp',
            'to' => str_replace('+', '', $this->message->recipient_phone),  // Remove +
            'type' => 'template',
            'template' => [
              'name' => $this->message->template_name,
              'language' => [
                'code' => 'en_US'
              ],
              'components' => [
                [
                  'type' => 'body',
                  'parameters' => array_map(
                    fn($var) => ['type' => 'text', 'text' => $var],
                    $this->message->template_variables
                  )
                ]
              ]
            ]
          ]
        );
      
      if ($response->successful()) {
        $data = $response->json();
        $this->message->update([
          'status' => 'sent',
          'meta_message_id' => $data['messages'][0]['id'] ?? null,
          'delivery_timestamp' => now()
        ]);
      } else {
        $this->message->update([
          'status' => 'failed',
          'error_message' => $response->body()
        ]);
      }
      
    } catch (\Exception $e) {
      $this->message->update([
        'status' => 'failed',
        'error_message' => $e->getMessage()
      ]);
    }
  }
}
```

---

## Component 4: Webhook Handler

### 4.1 Message Status Updates

```php
namespace App\Http\Controllers;

use App\Models\WhatsAppMessage;
use Illuminate\Http\Request;

class WhatsAppWebhookController extends Controller {
  
  public function handleStatusUpdate(Request $request) {
    // Verify webhook token
    if ($request->input('hub.mode') === 'subscribe') {
      return $request->input('hub.challenge');  // Verification handshake
    }
    
    $entry = $request->input('entry.0.changes.0');
    
    if ($entry['field'] === 'messages') {
      // Incoming message (customer reply)
      $this->handleIncomingMessage($entry['value']);
    } elseif ($entry['field'] === 'message_status') {
      // Message status update
      $this->handleStatusChange($entry['value']);
    }
    
    return response()->json(['status' => 'ok']);
  }
  
  private function handleIncomingMessage($data) {
    // Customer sent a message to your WhatsApp number
    // Queue for customer support team
    
    $messageData = [
      'from' => $data['contacts'][0]['wa_id'] ?? null,
      'text' => $data['messages'][0]['text']['body'] ?? null,
      'timestamp' => $data['messages'][0]['timestamp'] ?? now()
    ];
    
    // Create support ticket or queue for agent
    IncomingWhatsAppMessageJob::dispatch($messageData);
  }
  
  private function handleStatusChange($data) {
    // Message status: sent, delivered, read, failed
    
    foreach ($data['statuses'] as $status) {
      $message = WhatsAppMessage::where('meta_message_id', $status['id'])
        ->first();
      
      if ($message) {
        $statusMap = [
          'sent' => 'sent',
          'delivered' => 'delivered',
          'read' => 'read',
          'failed' => 'failed'
        ];
        
        $message->update([
          'status' => $statusMap[$status['status']] ?? 'unknown',
          'delivery_timestamp' => now()
        ]);
      }
    }
  }
}
```

---

## Component 5: Two-Factor Authentication (OTP)

### 5.1 OTP Template

```php
class WhatsAppOtpService {
  
  public function sendOtp($phone, $otp) {
    // Pre-approved OTP template
    // "Your verification code is: {{1}}. Don't share this code."
    
    WhatsAppMessage::create([
      'tenant_id' => Auth::user()->tenant_id,
      'recipient_phone' => $phone,
      'template_name' => 'otp_verification',
      'template_variables' => [$otp],  // Will be substituted into {{1}}
      'message_type' => 'template',
      'status' => 'queued'
    ])->dispatchJob();
    
    return ['status' => 'queued'];
  }
  
  public function verifyOtp($phone, $submittedOtp) {
    // Validate OTP (implement your OTP validation logic)
    return $this->isValidOtp($phone, $submittedOtp);
  }
}
```

---

## Component 6: Opt-In / Opt-Out Management

### 6.1 Compliance

**Required**:
- ✓ Only send to users who have opted in explicitly
- ✓ Provide easy opt-out (click link in messages)
- ✓ Honor opt-out within 24 hours
- ✓ Track consent records (GDPR)

### 6.2 Database

```sql
CREATE TABLE whatsapp_contacts (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  phone_number VARCHAR(20) NOT NULL,
  opted_in BOOLEAN DEFAULT false,
  opt_in_timestamp TIMESTAMP,
  opt_out_timestamp TIMESTAMP,
  consent_source VARCHAR(100),  -- "app", "website", "sms", etc.
  UNIQUE(tenant_id, phone_number)
);
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | Meta setup, template creation, approval | 35 | Business account, 3-5 templates approved |
| **Week 2** | Message sending, webhook handler | 50 | Send function, delivery tracking, webhooks |
| **Week 3** | OTP service, opt-in/out management | 35 | OTP flow, consent tracking |
| **Week 4** | Testing, documentation, launch | 20 | Docs, runbooks, compliance checklist |

**Total**: 140 hours

---

## Success Criteria

| Metric | Target | Measurement |
|---|---|---|
| Template approval rate | >80% | Meta approval tracking |
| Message delivery rate | >92% | Meta delivery status |
| Opt-in rate | >15% of base | Tracking table |
| Cost per message | $0.0045 | Meta billing |
| API latency | <1s | Datadog APM |

---

## Compliance Checklist

- [ ] Meta Business Account verified
- [ ] All templates use approved language (no direct marketing)
- [ ] Opt-in consent recorded for all recipients
- [ ] Opt-out mechanism implemented
- [ ] Privacy policy updated (WhatsApp data handling)
- [ ] Customer notifications about WhatsApp contact
- [ ] Audit log for all messages (GDPR)

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 10 Week 2 execution (parallel with SMS)  
**Next**: Phase 10, Step 3 (EU Market Entry via eu-west-1 Deployment)
