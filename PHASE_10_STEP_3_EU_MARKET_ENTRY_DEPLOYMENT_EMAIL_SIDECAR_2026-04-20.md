# Phase 10, Step 3: EU Market Entry & eu-west-1 Deployment Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: DevOps engineer + compliance engineer  
**Timeline**: October 1-31, 2026 (4 weeks)  
**Effort**: 110 hours (2.8 engineer weeks)  
**Expected Impact**: Enable EU customer base, reduce latency for European users

---

## Executive Summary

EU market entry requires:
1. **Regional Deployment** — Replicate infrastructure in eu-west-1 (Dublin, Ireland)
2. **Data Residency** — Keep EU customer data within EU borders (GDPR requirement)
3. **Compliance** — GDPR consent flows, data processing agreements, privacy policies
4. **Operations** — Deploy, monitor, and support EU infrastructure

**Expected Revenue**: +$50K/month (EU customers at 25% higher ACV)  
**Infrastructure Cost**: +$300/month baseline (scales with usage)  
**Payback Period**: 6 months (assuming 25% EU customer growth)

---

## Part 1: AWS eu-west-1 Infrastructure Setup

### 1.1 RDS PostgreSQL Setup (EU)

**Create RDS Instance** (Dublin, Ireland):

```bash
# Create RDS instance in eu-west-1
aws rds create-db-instance \
  --region eu-west-1 \
  --db-instance-identifier email-sidecar-eu \
  --db-instance-class db.t3.small \
  --engine postgres \
  --master-username admin \
  --master-user-password $(aws secretsmanager get-secret-value \
    --secret-id rds/master-password \
    --query SecretString --output text) \
  --allocated-storage 100 \
  --backup-retention-period 14 \
  --multi-az  # High availability across 2 AZs in Ireland
```

**Enable Encryption at Rest** (GDPR requirement):

```bash
# Use EU KMS key (resident in eu-west-1)
aws rds modify-db-instance \
  --region eu-west-1 \
  --db-instance-identifier email-sidecar-eu \
  --storage-encrypted \
  --kms-key-id arn:aws:kms:eu-west-1:ACCOUNT:key/KEY-ID
```

**Create Read Replica in Different AZ**:

```bash
# Replicate within eu-west-1 for HA
aws rds create-db-instance-read-replica \
  --region eu-west-1 \
  --db-instance-identifier email-sidecar-eu-replica \
  --source-db-instance-identifier email-sidecar-eu
```

### 1.2 ElastiCache Redis Setup (EU)

```bash
# Create Redis cluster in eu-west-1
aws elasticache create-replication-group \
  --region eu-west-1 \
  --replication-group-description "Email Sidecar EU Cache" \
  --engine redis \
  --cache-node-type cache.t3.micro \
  --num-cache-clusters 2 \
  --automatic-failover-enabled \
  --at-rest-encryption-enabled  # GDPR encryption
```

### 1.3 S3 Buckets (EU)

```bash
# Create S3 bucket in eu-west-1
aws s3api create-bucket \
  --bucket email-sidecar-eu-attachments \
  --region eu-west-1 \
  --create-bucket-configuration LocationConstraint=eu-west-1

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket email-sidecar-eu-attachments \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:eu-west-1:ACCOUNT:key/KEY-ID"
      }
    }]
  }'

# Enable versioning (for GDPR compliance)
aws s3api put-bucket-versioning \
  --bucket email-sidecar-eu-attachments \
  --versioning-configuration Status=Enabled
```

---

## Part 2: Application Deployment to EU

### 2.1 ECR Repository (EU)

```bash
# Create ECR repo in eu-west-1
aws ecr create-repository \
  --region eu-west-1 \
  --repository-name email-sidecar-lambda
```

### 2.2 Lambda Functions (EU)

**Deploy Lambda in eu-west-1**:

```bash
# Push Docker image to eu-west-1 ECR
aws ecr get-login-password --region eu-west-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.eu-west-1.amazonaws.com

docker tag email-sidecar-lambda:latest \
  123456789.dkr.ecr.eu-west-1.amazonaws.com/email-sidecar-lambda:latest

docker push 123456789.dkr.ecr.eu-west-1.amazonaws.com/email-sidecar-lambda:latest

# Create Lambda function
aws lambda create-function \
  --region eu-west-1 \
  --function-name email-sidecar-worker-eu \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role-eu \
  --code ImageUri=123456789.dkr.ecr.eu-west-1.amazonaws.com/email-sidecar-lambda:latest \
  --timeout 30 \
  --memory-size 512 \
  --environment "Variables={
    DB_HOST=email-sidecar-eu.XXXXX.eu-west-1.rds.amazonaws.com,
    REDIS_HOST=email-sidecar-eu-cache.XXXXX.ng.0001.euw1.cache.amazonaws.com,
    REGION=eu-west-1
  }"
```

### 2.3 SQS Queues (EU)

```bash
# Create SQS queues in eu-west-1
aws sqs create-queue \
  --region eu-west-1 \
  --queue-name email-send-queue-eu \
  --attributes VisibilityTimeout=300,MessageRetentionPeriod=1209600
```

### 2.4 API Gateway (EU)

```bash
# Create REST API in eu-west-1
aws apigateway create-rest-api \
  --region eu-west-1 \
  --name email-sidecar-api-eu \
  --description "Email Sidecar API - EU Region"
```

---

## Part 3: Data Replication Strategy

### 3.1 Cross-Region Replication (Controlled)

**Problem**: EU customers MUST have data in EU (GDPR Article 44).  
**Solution**: One-way replication: EU → US (for backup only, not active serving).

```bash
# Enable RDS cross-region read replica (EU → US, for disaster recovery ONLY)
aws rds create-db-instance-read-replica \
  --region us-east-1 \
  --db-instance-identifier email-sidecar-eu-dr \
  --source-db-instance-identifier arn:aws:rds:eu-west-1:ACCOUNT:db:email-sidecar-eu \
  --db-instance-class db.t3.small

# This is a READ REPLICA ONLY, not for serving EU customer data
```

**S3 Cross-Region Replication** (compliance backup):

```bash
# Enable replication from EU → US (for compliance backup)
aws s3api put-bucket-replication \
  --bucket email-sidecar-eu-attachments \
  --replication-configuration '{
    "Role": "arn:aws:iam::ACCOUNT:role/s3-replication",
    "Rules": [{
      "Status": "Enabled",
      "Priority": 1,
      "Destination": {
        "Bucket": "arn:aws:s3:::email-sidecar-us-backup",
        "ReplicationTime": {
          "Status": "Enabled",
          "Time": {"Minutes": 15}
        }
      }
    }]
  }'
```

### 3.2 Customer Data Routing

**Application Logic** (route by customer location):

```php
namespace App\Services;

class RegionalDataService {
  
  public function getDataStore($customerId) {
    $customer = Customer::find($customerId);
    
    // Route based on region
    return match($customer->data_region) {
      'eu' => new EuDataStore(),
      'us' => new UsDataStore(),
      'apac' => new ApacDataStore(),
      default => throw new RegionException("Unknown region")
    };
  }
  
  public function sendEmail($customerId, $emailData) {
    $dataStore = $this->getDataStore($customerId);
    
    // All operations happen in customer's region
    return $dataStore->queueEmail($emailData);
  }
}

class EuDataStore {
  private $rdsEndpoint = 'email-sidecar-eu.eu-west-1.rds.amazonaws.com';
  private $lambdaRegion = 'eu-west-1';
  
  public function queueEmail($emailData) {
    // Queue in eu-west-1 SQS only
    return SqsClient::region('eu-west-1')
      ->sendMessage([
        'QueueUrl' => 'https://sqs.eu-west-1.amazonaws.com/.../email-send-queue-eu',
        'MessageBody' => json_encode($emailData)
      ]);
  }
}
```

---

## Part 4: GDPR Compliance Implementation

### 4.1 Consent Management

**Database Schema**:

```sql
CREATE TABLE gdpr_consents (
  id UUID PRIMARY KEY,
  customer_id UUID REFERENCES customers(id),
  consent_type ENUM('email', 'sms', 'whatsapp', 'marketing'),
  status ENUM('granted', 'withdrawn'),
  consented_at TIMESTAMP,
  withdrawn_at TIMESTAMP,
  ip_address INET,  -- For proof of consent
  user_agent TEXT,  -- For proof of consent
  consent_source VARCHAR(100),  -- 'api', 'ui', 'import', etc.
  UNIQUE(customer_id, consent_type)
);
```

**Consent API Endpoints**:

```php
class GdprConsentController extends Controller {
  
  public function grantConsent(Request $request) {
    $validated = $request->validate([
      'customer_id' => 'required|uuid',
      'consent_types' => 'required|array',
      'consent_types.*' => 'in:email,sms,whatsapp,marketing'
    ]);
    
    foreach ($validated['consent_types'] as $type) {
      GdprConsent::updateOrCreate(
        ['customer_id' => $validated['customer_id'], 'consent_type' => $type],
        [
          'status' => 'granted',
          'consented_at' => now(),
          'ip_address' => $request->ip(),
          'user_agent' => $request->userAgent()
        ]
      );
    }
    
    return response()->json(['status' => 'granted']);
  }
  
  public function withdrawConsent(Request $request) {
    $validated = $request->validate([
      'customer_id' => 'required|uuid',
      'consent_types' => 'required|array'
    ]);
    
    foreach ($validated['consent_types'] as $type) {
      GdprConsent::where('customer_id', $validated['customer_id'])
        ->where('consent_type', $type)
        ->update([
          'status' => 'withdrawn',
          'withdrawn_at' => now()
        ]);
    }
    
    return response()->json(['status' => 'withdrawn']);
  }
}
```

### 4.2 Right to Be Forgotten (RTBF)

```php
class GdprRtbfController extends Controller {
  
  public function requestDeletion(Request $request, $customerId) {
    // Create RTBF request (not immediate deletion)
    $request = RtbfRequest::create([
      'customer_id' => $customerId,
      'requested_at' => now(),
      'status' => 'pending',
      'deletion_date' => now()->addDays(30)  // 30-day confirmation period
    ]);
    
    // Send confirmation email
    Notification::send(
      Customer::find($customerId),
      new RtbfConfirmationNotification($request)
    );
    
    return response()->json([
      'status' => 'deletion_requested',
      'deletion_date' => $request->deletion_date
    ]);
  }
  
  public function executeRtbf() {
    // Run daily: delete customers whose 30-day period has elapsed
    $approved = RtbfRequest::where('status', 'approved')
      ->where('deletion_date', '<=', now())
      ->get();
    
    foreach ($approved as $request) {
      // Delete all customer data in EU region
      Customer::where('id', $request->customer_id)
        ->delete();  // Cascades to emails, webhooks, etc.
      
      $request->update(['status' => 'completed', 'completed_at' => now()]);
    }
  }
}
```

### 4.3 Privacy Policy & DPA

**Privacy Policy** (update for EU):
- Data processing location (eu-west-1, Ireland)
- Data retention (90 days for email, 365 for backups)
- Subprocessors (Mailgun, Twilio, Meta in EU infrastructure)
- User rights (access, correction, deletion, portability)

**Data Processing Agreement (DPA)**:
- EU customers receive DPA reflecting GDPR obligations
- Automatic signing via API (`/api/v1/legal/dpa`)

---

## Part 5: DNS & Routing

### 5.1 Geographic Routing

**Route53 Geolocation Routing**:

```bash
# US customers → us-east-1
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456 \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "api.example.com",
        "Type": "A",
        "SetIdentifier": "API-US",
        "GeoLocation": {
          "CountryCode": "US"
        },
        "AliasTarget": {
          "HostedZoneId": "Z123",
          "DNSName": "api-us.example.com",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'

# EU customers → eu-west-1
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456 \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "api.example.com",
        "Type": "A",
        "SetIdentifier": "API-EU",
        "GeoLocation": {
          "CountryCode": "IE"
        },
        "AliasTarget": {
          "HostedZoneId": "Z456",
          "DNSName": "api-eu.example.com",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'
```

---

## Part 6: Monitoring & Operations (EU)

### 6.1 CloudWatch (eu-west-1)

```bash
# Create CloudWatch dashboard for EU infrastructure
aws cloudwatch put-dashboard \
  --region eu-west-1 \
  --dashboard-name email-sidecar-eu-ops \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["AWS/Lambda", "Duration", {"stat": "Average"}],
            ["AWS/RDS", "CPUUtilization"],
            ["AWS/ElastiCache", "EngineCPUUtilization"]
          ],
          "region": "eu-west-1"
        }
      }
    ]
  }'
```

### 6.2 Alarms (EU-specific)

```bash
# Alert if EU RDS CPU exceeds threshold
aws cloudwatch put-metric-alarm \
  --region eu-west-1 \
  --alarm-name email-sidecar-eu-rds-cpu \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 75 \
  --comparison-operator GreaterThanThreshold
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | RDS/Redis/S3 setup in eu-west-1 | 30 | Infrastructure provisioned, encrypted |
| **Week 2** | Lambda/API Gateway deployment, data routing | 35 | Functions deployed, DNS geolocation routing |
| **Week 3** | GDPR compliance (consent, RTBF, DPA) | 30 | Consent flows, RTBF processor, DPA templates |
| **Week 4** | Testing, monitoring, launch, documentation | 15 | Smoke tests passed, alerts configured, runbooks |

**Total**: 110 hours

---

## Cost Breakdown (Monthly)

| Component | us-east-1 | eu-west-1 | Combined |
|---|---|---|---|
| RDS | $130 | $140 | $270 |
| ElastiCache | $28 | $30 | $58 |
| Lambda | $115 | $40 | $155 |
| S3 + backups | $35 | $45 | $80 |
| Data transfer | — | $20 | $20 |
| **Total** | **$308** | **$275** | **$583** |

**Note**: eu-west-1 slightly higher due to multi-AZ, but efficient for 25% EU customer base.

---

## Success Criteria

| Metric | Target | Measurement |
|---|---|---|
| EU customer latency | <150ms p95 | Datadog APM by region |
| GDPR compliance | 100% | Legal audit |
| Data residency | 100% EU data in EU | AWS Config rules |
| Failover RTO | <5min | Quarterly DR drill |
| Cost per EU customer | <$5/month | Chargeback analysis |

---

## Compliance Checklist

- [ ] All EU customer data in eu-west-1
- [ ] RDS encryption at rest (KMS)
- [ ] S3 encryption at rest (KMS)
- [ ] Consent management API live
- [ ] RTBF processor scheduled (daily)
- [ ] DPA available and signed
- [ ] Privacy policy updated (GDPR language)
- [ ] Subprocessor list maintained
- [ ] Data transfer impact assessment completed
- [ ] EU-specific monitoring/alerts configured

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 10 Week 3 execution  
**Next**: Phase 10, Step 4 (Developer Marketplace & Plugins)
