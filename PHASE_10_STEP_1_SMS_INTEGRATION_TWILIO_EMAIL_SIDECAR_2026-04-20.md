# Phase 10, Step 1: SMS Integration via Twilio Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Integration engineer + backend engineer  
**Timeline**: September 1-30, 2026 (4 weeks)  
**Effort**: 120 hours (3 engineer weeks)  
**Expected Impact**: Enable SMS delivery, expand to 15% new customer base

---

## Executive Summary

SMS integration adds SMS delivery capability via Twilio, complementing email-only platform. Enables:
- SMS notifications (order confirmations, alerts, OTPs)
- SMS campaigns (bulk SMS to customer lists)
- SMS + Email bundled offerings
- Expansion into 15% new use cases (not email-viable)

**Expected Revenue**: +$20K/month (SMS at $0.0075 per message, lower volume than email)  
**Implementation Timeline**: 4 weeks  
**Risk Level**: Low (Twilio handles compliance)

---

## Architecture Overview

**Data Flow**:
```
Customer Request (SMS)
  ↓
Lambda (sms-send function)
  ↓
Twilio API
  ↓
Carrier Network
  ↓
Recipient Phone
```

**New Components**:
- SMS queue (SQS)
- SMS Lambda function
- Twilio account + credentials
- SMS delivery tracking database
- SMS bounce/delivery webhooks

---

## Component 1: Twilio Account Setup

### 1.1 Create Twilio Account

**Step 1: Sign up**
```bash
# https://www.twilio.com/signup
# Expected cost: $0.0075 per SMS (US/Canada, varies by region)
```

**Step 2: Verify phone number** (for testing)
```bash
# Receive verification code via SMS
# Confirm code in Twilio console
```

**Step 3: Get credentials**
```
Account SID: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Auth Token: (keep secret)
Twilio Phone Number: +1XXXXXXXXXX (assigned to account)
```

### 1.2 Store Credentials Securely

**AWS Secrets Manager**:
```bash
# Create secret for Twilio credentials
aws secretsmanager create-secret \
  --name twilio/sms-service \
  --secret-string '{
    "account_sid": "ACxxxxxxxxxxxxxxxxxxxx",
    "auth_token": "xxxxxxxxxxxxxxxxxxxx",
    "phone_number": "+1XXXXXXXXXX"
  }'

# Retrieve in Lambda
TWILIO_CREDS=$(aws secretsmanager get-secret-value \
  --secret-id twilio/sms-service \
  --query SecretString --output text)
```

---

## Component 2: Database Schema

### 2.1 SMS Records Table

```sql
CREATE TABLE sms_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  recipient_phone VARCHAR(20) NOT NULL,  -- E.164 format: +1234567890
  message_body TEXT NOT NULL,
  status ENUM('queued', 'sending', 'sent', 'failed', 'bounced') DEFAULT 'queued',
  twilio_message_sid VARCHAR(100),  -- Twilio's message ID
  delivery_status VARCHAR(50),  -- 'queued', 'failed', 'sent', 'undelivered'
  delivery_timestamp TIMESTAMP,
  error_message TEXT,  -- If failed
  cost_usd DECIMAL(6,4),  -- Cost per SMS
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX idx_sms_tenant_created 
  ON sms_records(tenant_id, created_at DESC);
CREATE INDEX idx_sms_twilio_sid 
  ON sms_records(twilio_message_sid);
```

### 2.2 SMS Delivery Webhook Events Table

```sql
CREATE TABLE sms_webhook_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sms_record_id UUID REFERENCES sms_records(id),
  event_type VARCHAR(50),  -- 'delivered', 'failed', 'bounced'
  event_data JSONB,  -- Full Twilio webhook payload
  webhook_timestamp TIMESTAMP,
  received_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_sms_events_record 
  ON sms_webhook_events(sms_record_id);
```

---

## Component 3: SMS Lambda Function

### 3.1 SMS Send Handler

```php
namespace App\Http\Controllers;

use Twilio\Rest\Client as TwilioClient;
use App\Models\SmsRecord;
use Illuminate\Http\Request;

class SmsController extends Controller {
  
  private $twilio;
  
  public function __construct() {
    // Initialize Twilio client
    $creds = json_decode(
      aws_get_secret('twilio/sms-service'),
      true
    );
    
    $this->twilio = new TwilioClient(
      $creds['account_sid'],
      $creds['auth_token']
    );
  }
  
  public function send(Request $request) {
    $validated = $request->validate([
      'recipient_phone' => 'required|phone:US',
      'message_body' => 'required|string|max:1600',  // Max for SMS
      'campaign_id' => 'nullable|uuid'
    ]);
    
    // Validate tenant has SMS enabled (tier requirement)
    $tier = Auth::user()->tenant->tier;
    if (!in_array($tier, ['pro', 'enterprise'])) {
      return response()->json([
        'error' => 'SMS requires Pro or Enterprise tier'
      ], 403);
    }
    
    // Create SMS record
    $smsRecord = SmsRecord::create([
      'tenant_id' => Auth::user()->tenant_id,
      'recipient_phone' => $this->normalizePhone($validated['recipient_phone']),
      'message_body' => $validated['message_body'],
      'status' => 'queued'
    ]);
    
    // Queue for async sending (via Lambda)
    SendSmsJob::dispatch($smsRecord);
    
    return response()->json([
      'sms_id' => $smsRecord->id,
      'status' => 'queued',
      'created_at' => $smsRecord->created_at
    ], 202);
  }
  
  private function normalizePhone($phone): string {
    // Convert to E.164 format: +1234567890
    $cleaned = preg_replace('/\D/', '', $phone);
    if (strlen($cleaned) == 10) {
      $cleaned = '1' . $cleaned;  // Assume US if 10 digits
    }
    return '+' . $cleaned;
  }
}
```

### 3.2 Async SMS Sender Job

```php
namespace App\Jobs;

use App\Models\SmsRecord;
use Twilio\Rest\Client as TwilioClient;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;

class SendSmsJob implements ShouldQueue {
  use Queueable;
  
  public function __construct(private SmsRecord $smsRecord) {}
  
  public function handle() {
    $creds = json_decode(
      aws_get_secret('twilio/sms-service'),
      true
    );
    
    $twilio = new TwilioClient(
      $creds['account_sid'],
      $creds['auth_token']
    );
    
    try {
      // Split long messages into multiple SMS (160 chars per SMS)
      $messages = str_split($this->smsRecord->message_body, 160);
      
      foreach ($messages as $msgPart) {
        $response = $twilio->messages->create(
          $this->smsRecord->recipient_phone,
          [
            'from' => $creds['phone_number'],
            'body' => $msgPart
          ]
        );
        
        // Store Twilio message ID
        $this->smsRecord->update([
          'twilio_message_sid' => $response->sid,
          'status' => 'sending',
          'cost_usd' => 0.0075  // Base cost
        ]);
      }
      
    } catch (\Exception $e) {
      // Log error
      $this->smsRecord->update([
        'status' => 'failed',
        'error_message' => $e->getMessage()
      ]);
      
      // Notify user
      Notification::send(
        Auth::user(),
        new SmsFailedNotification($this->smsRecord)
      );
    }
  }
}
```

---

## Component 4: Webhook Handler (Delivery Status)

### 4.1 Twilio Webhook Receiver

```php
namespace App\Http\Controllers;

use App\Models\SmsRecord;
use App\Models\SmsWebhookEvent;
use Illuminate\Http\Request;

class TwilioWebhookController extends Controller {
  
  public function handleStatusCallback(Request $request) {
    // Verify webhook signature (security)
    $this->verifyTwilioSignature($request);
    
    $messageSid = $request->input('MessageSid');
    $messageStatus = $request->input('MessageStatus');  // 'delivered', 'failed', 'undelivered'
    
    // Find SMS record
    $smsRecord = SmsRecord::where('twilio_message_sid', $messageSid)
      ->firstOrFail();
    
    // Map Twilio status to our status
    $statusMap = [
      'queued' => 'queued',
      'sending' => 'sending',
      'sent' => 'sent',
      'failed' => 'failed',
      'undelivered' => 'bounced'
    ];
    
    // Update status
    $smsRecord->update([
      'status' => $statusMap[$messageStatus] ?? 'unknown',
      'delivery_status' => $messageStatus,
      'delivery_timestamp' => now()
    ]);
    
    // Log webhook event
    SmsWebhookEvent::create([
      'sms_record_id' => $smsRecord->id,
      'event_type' => $messageStatus,
      'event_data' => $request->all()
    ]);
    
    // Notify customer if delivery failed
    if ($messageStatus === 'failed' || $messageStatus === 'undelivered') {
      Notification::send(
        $smsRecord->tenant->owners,
        new SmsDeliveryFailedNotification($smsRecord)
      );
    }
    
    return response()->json(['status' => 'received'], 200);
  }
  
  private function verifyTwilioSignature(Request $request) {
    // Twilio signature verification
    $creds = json_decode(aws_get_secret('twilio/sms-service'), true);
    $authToken = $creds['auth_token'];
    
    $url = $request->url();
    $params = $request->all();
    
    $data = '';
    foreach ($params as $key => $value) {
      if (is_array($value)) {
        $value = implode('', $value);
      }
      $data .= $key . $value;
    }
    
    $computedHash = base64_encode(
      hash_hmac('sha1', $url . $data, $authToken, true)
    );
    
    $providedHash = $request->header('X-Twilio-Signature');
    
    if (!hash_equals($computedHash, $providedHash)) {
      abort(403, 'Invalid Twilio signature');
    }
  }
}
```

### 4.2 Configure Webhook in Twilio

```bash
# Via AWS CLI (assuming Lambda frontend)
# Set Twilio webhook URL in Twilio console:
# POST https://api.example.com/webhooks/twilio/sms-status
```

---

## Component 5: Bulk SMS Campaigns

### 5.1 Campaign Creation

```php
class SmsCampaignController extends Controller {
  
  public function create(Request $request) {
    $validated = $request->validate([
      'name' => 'required|string|max:100',
      'message' => 'required|string|max:1600',
      'recipient_list_id' => 'required|uuid',
      'schedule_time' => 'nullable|datetime'
    ]);
    
    // Get recipient list
    $recipients = ContactList::find($validated['recipient_list_id'])
      ->contacts()
      ->pluck('phone_number');
    
    if ($recipients->isEmpty()) {
      return response()->json(['error' => 'No recipients'], 422);
    }
    
    // Create campaign
    $campaign = SmsCampaign::create([
      'tenant_id' => Auth::user()->tenant_id,
      'name' => $validated['name'],
      'message' => $validated['message'],
      'recipient_count' => $recipients->count(),
      'scheduled_at' => $validated['schedule_time'],
      'status' => 'draft'
    ]);
    
    // Estimate cost
    $estimatedCost = $recipients->count() * 0.0075;
    
    return response()->json([
      'campaign_id' => $campaign->id,
      'recipients' => $recipients->count(),
      'estimated_cost_usd' => $estimatedCost,
      'status' => 'draft'
    ]);
  }
  
  public function send(Request $request, $campaignId) {
    $campaign = SmsCampaign::findOrFail($campaignId);
    
    // Verify balance
    $balance = Auth::user()->tenant->account_balance;
    if ($balance < ($campaign->recipient_count * 0.0075)) {
      return response()->json([
        'error' => 'Insufficient balance',
        'required' => $campaign->recipient_count * 0.0075,
        'available' => $balance
      ], 402);
    }
    
    // Queue bulk send
    SendBulkSmsJob::dispatch($campaign);
    
    $campaign->update(['status' => 'sending']);
    
    return response()->json([
      'campaign_id' => $campaign->id,
      'status' => 'sending'
    ]);
  }
}
```

### 5.2 Bulk Send Job

```php
namespace App\Jobs;

use App\Models\SmsCampaign;
use Illuminate\Bus\Queueable;

class SendBulkSmsJob implements ShouldQueue {
  use Queueable;
  
  public function __construct(private SmsCampaign $campaign) {}
  
  public function handle() {
    // Get all recipients
    $recipients = $this->campaign->recipients()->pluck('phone_number');
    
    // Send in batches (Twilio rate limit: 100/sec)
    $chunks = $recipients->chunk(100);
    
    foreach ($chunks as $chunk) {
      foreach ($chunk as $phone) {
        SendSmsJob::dispatch(
          SmsRecord::create([
            'tenant_id' => $this->campaign->tenant_id,
            'recipient_phone' => $phone,
            'message_body' => $this->campaign->message,
            'campaign_id' => $this->campaign->id
          ])
        );
      }
      
      // Rate limiting: wait 1 second between 100-message batches
      sleep(1);
    }
    
    $this->campaign->update(['status' => 'sent']);
  }
}
```

---

## Component 6: API Endpoints

### 6.1 SMS Send Endpoint

```
POST /api/v1/sms/send

Request:
{
  "recipient_phone": "+1-555-123-4567",
  "message_body": "Your order #12345 has been delivered!"
}

Response (HTTP 202 - Accepted):
{
  "sms_id": "sms-uuid",
  "status": "queued",
  "created_at": "2026-09-01T14:30:00Z"
}
```

### 6.2 SMS Status Endpoint

```
GET /api/v1/sms/{sms_id}

Response:
{
  "id": "sms-uuid",
  "recipient": "+15551234567",
  "message": "Your order...",
  "status": "delivered",
  "delivery_timestamp": "2026-09-01T14:35:00Z",
  "cost_usd": 0.0075
}
```

### 6.3 Bulk Campaign Endpoints

```
POST /api/v1/sms/campaigns
GET /api/v1/sms/campaigns/{id}
POST /api/v1/sms/campaigns/{id}/send
GET /api/v1/sms/campaigns/{id}/stats
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | Twilio setup, database schema, credentials | 30 | Twilio account, SMS tables, secrets stored |
| **Week 2** | Lambda SMS handler, async job, webhook | 40 | Send function, delivery tracking, webhooks |
| **Week 3** | Bulk campaigns, campaign UI, testing | 30 | Campaign manager, bulk send job, K6 tests |
| **Week 4** | Integration testing, documentation, launch | 20 | Docs, runbooks, production deployment |

**Total**: 120 hours

---

## Success Criteria

| Metric | Target | Measurement |
|---|---|---|
| SMS delivery rate | >95% | Twilio delivery status |
| API latency | <500ms | Datadog APM |
| Webhook reliability | >99% | Webhook event logs |
| Cost per SMS | $0.0075 | Twilio billing |
| Customer adoption | >5% of base | Feature flag analytics |

---

## Compliance & Security

**TCPA Compliance** (Telephone Consumer Protection Act):
- ✓ Only send to opted-in contacts
- ✓ Include unsubscribe instructions
- ✓ Respect "Do Not Call" registry
- (Twilio handles carrier compliance)

**GDPR Compliance**:
- ✓ Phone number encrypted at rest
- ✓ Audit logs for all SMS
- ✓ Right to deletion (RTBF)
- (Leverage existing infrastructure)

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 10 Week 1 execution  
**Next**: Phase 10, Step 2 (WhatsApp Integration via Meta API)
