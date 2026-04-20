# Phase 9, Step 3: Storage & Backup Optimization Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Infrastructure engineer  
**Timeline**: July 12-29, 2026 (3 weeks)  
**Effort**: 75 hours (1.9 engineer weeks)  
**Expected Savings**: $57/month storage cost

---

## Executive Summary

Storage optimization reduces S3, RDS backup, and CloudWatch log costs through three strategies:

1. **S3 Lifecycle Policies** — Archive old objects to Glacier (80% cost reduction)
2. **RDS Backup Optimization** — Reduce retention window, compress backups
3. **CloudWatch Log Retention** — Archive logs to S3, reduce CloudWatch spend

**Expected Impact**:
- S3 costs: $40/month → $20/month (-$20/month)
- RDS backup costs: $35/month → $15/month (-$20/month)
- CloudWatch costs: $25/month → $8/month (-$17/month)
- **Total**: $100/month → $43/month (-$57/month)

---

## Component 1: S3 Lifecycle Policies

### 1.1 Current S3 Usage Analysis

**Bucket Inventory**:

```bash
# Analyze bucket contents
aws s3api list-objects-v2 \
  --bucket email-sidecar-attachments \
  --output table \
  --query 'Contents[*].[Key, Size, LastModified]' | head -20

# Get storage by age
aws s3api list-objects-v2 \
  --bucket email-sidecar-attachments \
  --query 'Contents[?LastModified<`2026-01-01`].Size' \
  --output text | awk '{sum+=$1} END {print sum/(1024^3) " GB"}'

# Expected output:
# ~50 GB in old attachments (>90 days)
# ~10 GB in recent attachments (<30 days)
```

### 1.2 Storage Classes Cost Comparison

| Storage Class | Cost/GB/month | Access Time | Use Case |
|---|---|---|---|
| S3 Standard | $0.023 | Immediate | Recent data (<30 days) |
| S3 Glacier Instant | $0.004 | 1-3 hours | Archive (30-90 days) |
| S3 Glacier Flexible | $0.0036 | 3-5 hours | Long-term (>90 days) |
| S3 Deep Archive | $0.00099 | 12 hours | Compliance (>180 days) |

### 1.3 Lifecycle Policy Configuration

**CloudFormation Template**:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: S3 Lifecycle policies for email attachments

Resources:
  AttachmentsBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: email-sidecar-attachments
      VersioningConfiguration:
        Status: Enabled

  LifecyclePolicy:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: email-sidecar-attachments
      LifecycleConfiguration:
        Rules:
          # Transition to Glacier Instant after 30 days
          - Id: TransitionToGlacierInstant
            Status: Enabled
            Prefix: attachments/
            Transitions:
              - StorageClass: GLACIER_IR
                TransitionInDays: 30
            ExpirationInDays: 365  # Delete after 1 year (GDPR compliance)
            NoncurrentVersionTransitions:
              - StorageClass: GLACIER_IR
                TransitionInDays: 30
            NoncurrentVersionExpirationInDays: 30

          # Transition to Deep Archive after 90 days (for compliance backup)
          - Id: TransitionToDeepArchive
            Status: Enabled
            Prefix: backups/
            Transitions:
              - StorageClass: DEEP_ARCHIVE
                TransitionInDays: 90
            ExpirationInDays: 2555  # 7 years for regulatory compliance

          # Delete incomplete multipart uploads after 7 days
          - Id: DeleteIncompleteMultipartUploads
            Status: Enabled
            AbortIncompleteMultipartUpload:
              DaysAfterInitiation: 7

Outputs:
  BucketName:
    Value: !Ref AttachmentsBucket
    Export:
      Name: EmailSidecarAttachmentsBucket
```

**Deploy via AWS CLI**:

```bash
# Create stack
aws cloudformation create-stack \
  --stack-name email-sidecar-s3-lifecycle \
  --template-body file://s3-lifecycle.yaml

# Monitor creation
aws cloudformation wait stack-create-complete \
  --stack-name email-sidecar-s3-lifecycle

# Verify policy
aws s3api get-bucket-lifecycle-configuration \
  --bucket email-sidecar-attachments \
  --output table
```

### 1.4 Validation & Monitoring

**Test Lifecycle Policy** (staging):

```bash
# Create test file in staging bucket
aws s3 cp test-file.txt s3://email-sidecar-attachments-staging/test.txt

# Add lifecycle policy (same as above)
aws s3api put-bucket-lifecycle-configuration \
  --bucket email-sidecar-attachments-staging \
  --lifecycle-configuration file://lifecycle-config.json

# Wait 1-2 days, verify transition
aws s3api head-object \
  --bucket email-sidecar-attachments-staging \
  --key test.txt \
  --query 'StorageClass'

# Expected output: GLACIER_IR (or original STANDARD if <30 days)
```

**Monitor Lifecycle Transitions**:

```bash
# CloudWatch metric: S3 storage by class
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value=email-sidecar-attachments \
                Name=StorageType,Value=StandardStorageSize \
  --start-time 2026-07-01T00:00:00Z \
  --end-time 2026-07-31T00:00:00Z \
  --period 86400 \
  --statistics Average
```

---

## Component 2: RDS Backup Optimization

### 2.1 Current Backup Configuration

**Analyze Current Backups**:

```bash
# List RDS backups
aws rds describe-db-snapshots \
  --db-instance-identifier email-sidecar-prod \
  --output table \
  --query 'DBSnapshots[*].[DBSnapshotIdentifier, SnapshotCreateTime, AllocatedStorage]'

# Expected output:
# 35 daily snapshots × 1.5 GB = 52.5 GB total
# Cost: 52.5 GB × $0.095/GB = $5/month (plus storage)
```

### 2.2 Retention Window Optimization

**BEFORE** (Current):
```
35-day retention (35 snapshots)
Cost: $35/month (1.5 GB × 35 × $0.095)
+ Snapshot storage: Additional $10/month
= $45/month total
```

**AFTER** (Optimized):
```
14-day retention (14 snapshots) + monthly backup
- Daily: Last 14 days (= 2 weeks, covers most use cases)
- Weekly: Last 4 weeks (1 snapshot per week, = 4 snapshots)
- Monthly: Last 12 months (1 snapshot per month, = 12 snapshots)
Cost: (14 + 4 + 12) × 1.5 GB × $0.095 = $3.65/month
+ Snapshot storage: $0.50/month
= $4.15/month total

Savings: $45 → $4.15 = -$40.85/month (91% reduction!)
```

### 2.3 Implementation

**Modify Backup Retention** (AWS Console or CLI):

```bash
# Via CLI
aws rds modify-db-instance \
  --db-instance-identifier email-sidecar-prod \
  --backup-retention-period 14 \
  --preferred-backup-window "02:00-03:00" \
  --apply-immediately

# Verify
aws rds describe-db-instances \
  --db-instance-identifier email-sidecar-prod \
  --query 'DBInstances[0].BackupRetentionPeriod'
# Expected output: 14
```

**Create Monthly Backup Strategy** (Lambda function):

```python
import boto3
from datetime import datetime

rds = boto3.client('rds')

def create_monthly_backup(event, context):
    """Create monthly backup snapshot for long-term retention"""
    
    db_id = 'email-sidecar-prod'
    month = datetime.now().strftime('%Y-%m')
    snapshot_id = f"{db_id}-monthly-{month}"
    
    try:
        response = rds.create_db_snapshot(
            DBSnapshotIdentifier=snapshot_id,
            DBInstanceIdentifier=db_id,
            Tags=[
                {'Key': 'Type', 'Value': 'Monthly-Backup'},
                {'Key': 'RetentionDays', 'Value': '365'}  # Keep for 1 year
            ]
        )
        
        print(f"Created snapshot: {snapshot_id}")
        return {'statusCode': 200, 'body': f'Snapshot {snapshot_id} created'}
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': str(e)}

# Schedule via CloudWatch Events
# Rule: "Cron: 0 3 1 * ? *" (First day of every month, 3 AM UTC)
```

### 2.4 Cross-Region Backup

**Enable Automated Cross-Region Copies** (for disaster recovery):

```bash
# Modify DB instance to enable cross-region backups
aws rds modify-db-instance \
  --db-instance-identifier email-sidecar-prod \
  --copy-backups-to-region us-west-2 \
  --copy-tags-to-snapshot

# Verify
aws rds describe-db-instances \
  --db-instance-identifier email-sidecar-prod \
  --query 'DBInstances[0].CopyTagsToSnapshot'
```

---

## Component 3: CloudWatch Log Retention & Archival

### 3.1 Current Log Storage

**Analyze Log Groups**:

```bash
# List log groups and their retention
aws logs describe-log-groups \
  --output table \
  --query 'logGroups[*].[logGroupName, retentionInDays, storedBytes]'

# Expected output:
# /aws/lambda/email-sidecar-worker        - 0 (infinite) - 50 GB
# /aws/rds/email-sidecar-prod             - 0 (infinite) - 20 GB
# /aws/ecs/email-sidecar-tasks            - 0 (infinite) - 30 GB
# Total: 100 GB indefinite retention = $25/month
```

### 3.2 Retention Policy

**Apply Retention to Log Groups** (30 days):

```bash
# Set retention for Lambda logs
aws logs put-retention-policy \
  --log-group-name /aws/lambda/email-sidecar-worker \
  --retention-in-days 30

# Set retention for RDS logs
aws logs put-retention-policy \
  --log-group-name /aws/rds/email-sidecar-prod \
  --retention-in-days 30

# Set retention for ECS logs
aws logs put-retention-policy \
  --log-group-name /aws/ecs/email-sidecar-tasks \
  --retention-in-days 30

# Verify all groups now have 30-day retention
aws logs describe-log-groups \
  --query 'logGroups[?retentionInDays==`30`].[logGroupName]'
```

### 3.3 Archive to S3 Before Expiration

**Export Logs to S3** (via Lambda, weekly):

```python
import boto3
from datetime import datetime, timedelta
import json

logs = boto3.client('logs')
s3 = boto3.client('s3')

def export_logs_to_s3(event, context):
    """Export CloudWatch logs to S3 before they expire (30-day retention)"""
    
    log_groups = [
        '/aws/lambda/email-sidecar-worker',
        '/aws/rds/email-sidecar-prod',
        '/aws/ecs/email-sidecar-tasks'
    ]
    
    bucket = 'email-sidecar-log-archive'
    
    for log_group in log_groups:
        # Calculate date range: last 7 days
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
        
        # Create task to export logs
        response = logs.create_export_task(
            logGroupName=log_group,
            frm=start_time,
            to=end_time,
            destination=bucket,
            destinationPrefix=f"logs/{log_group.replace('/', '_')}/{datetime.now().strftime('%Y/%m/%d')}"
        )
        
        print(f"Exporting {log_group}: task ID {response['taskId']}")
    
    return {'statusCode': 200, 'body': 'Export tasks created'}

# Schedule via CloudWatch Events
# Rule: "Cron: 0 0 ? * 1" (Every Monday at midnight UTC)
```

**S3 Lifecycle for Archived Logs**:

```yaml
ArchiveLogsLifecycle:
  Rules:
    # Keep compressed logs in S3 Standard for 30 days
    - Id: ArchiveCompressedLogs
      Status: Enabled
      Filter:
        Prefix: logs/
      Transitions:
        - StorageClass: GLACIER_IR
          TransitionInDays: 30
      ExpirationInDays: 365  # Delete after 1 year (per GDPR)
```

### 3.4 Cost Reduction Summary

| Component | Before | After | Savings |
|---|---|---|---|
| CloudWatch Logs | $25/month (infinite) | $8/month (30-day) | $17/month |
| S3 Standard | $20/month | $5/month (moved to Glacier) | $15/month |
| RDS Backups | $35/month (35-day) | $15/month (14-day + monthly) | $20/month |
| **Total** | **$80/month** | **$28/month** | **$52/month** |

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | S3 lifecycle policies, testing | 25 | CloudFormation template, lifecycle rules deployed |
| **Week 2** | RDS backup optimization, monthly snapshots | 25 | Retention reduced to 14 days, Lambda function deployed |
| **Week 3** | CloudWatch log archival, validation | 25 | Log export Lambda, 30-day retention applied, monitoring |

**Total**: 75 hours

---

## Cost Impact (Monthly)

**Before Phase 9, Step 3**:
- S3: $40/month
- RDS backups: $35/month
- CloudWatch logs: $25/month
- **Subtotal**: $100/month

**After Phase 9, Step 3**:
- S3: $20/month (Glacier for >30 days)
- RDS backups: $15/month (14-day + monthly)
- CloudWatch logs: $8/month (30-day retention, archived to S3)
- **Subtotal**: $43/month

**Monthly Savings**: $57/month = **$684/year**

---

## Validation & Monitoring

**Week 1 Validation** (S3):

```bash
# Verify objects are transitioning to Glacier
aws s3api list-objects-v2 \
  --bucket email-sidecar-attachments \
  --query 'Contents[?StorageClass==`GLACIER_IR`].Key' \
  --output text | wc -l

# Expected: Increasing over 30 days
```

**Week 2 Validation** (RDS):

```bash
# Verify snapshot count has decreased
aws rds describe-db-snapshots \
  --db-instance-identifier email-sidecar-prod \
  --query 'DBSnapshots | length(@)'

# Expected: ~14-20 snapshots (vs previous 35)
```

**Week 3 Validation** (CloudWatch):

```bash
# Verify logs are archived
aws s3 ls s3://email-sidecar-log-archive/logs/ --recursive | wc -l

# Expected: Increasing number of log files in S3
```

---

## Disaster Recovery Impact

**RTO/RPO with New Backup Strategy**:

| Scenario | Before | After | Impact |
|---|---|---|---|
| Last 24 hours | 24 snapshots | 1 snapshot | Minimal (last 24h always available) |
| Last 7 days | 7 snapshots | 7 snapshots | None (same) |
| Last 30 days | 30 snapshots | ~5 snapshots (2 week + weekly) | Can restore to any Monday |
| Last year | 365 snapshots | 12 snapshots (monthly) | Can restore to any month |

**Risk Mitigation**: Monthly snapshots provide sufficient granularity for compliance (GDPR requires ability to restore, not necessarily to-the-minute).

---

## Rollback Plan

**If restoration from Glacier is too slow**:

```bash
# Increase RDS backup retention temporarily
aws rds modify-db-instance \
  --db-instance-identifier email-sidecar-prod \
  --backup-retention-period 35

# Store more in S3 Standard instead of Glacier
aws s3api put-bucket-lifecycle-configuration \
  --bucket email-sidecar-attachments \
  --lifecycle-configuration file://lifecycle-standard.json
```

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 9 Week 3 execution  
**Next**: Phase 9, Step 4 (Auto-Scaling Enhancements)
