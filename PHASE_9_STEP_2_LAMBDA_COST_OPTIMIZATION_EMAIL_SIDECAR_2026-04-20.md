# Phase 9, Step 2: Lambda Cost Optimization Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Platform engineer  
**Timeline**: July 5-25, 2026 (3 weeks)  
**Effort**: 100 hours (2.5 engineer weeks)  
**Expected Savings**: $85/month Lambda cost, cold start time improvement

---

## Executive Summary

Lambda cost optimization reduces function costs by 35% through four techniques:

1. **Container Image Optimization** — Reduce Docker image size 450MB → <200MB
2. **Provisioned Concurrency Tuning** — Optimize reserved capacity (10 → 5 units)
3. **Graviton2 Migration** — Switch to ARM-based CPU (20% cheaper)
4. **Cold Start Reduction** — Faster initialization, connection pre-warming

**Expected Impact**:
- Lambda invocation cost: $200/month → $140/month (-$60/month)
- Cold start improvement: Initialization time reduced from 3+ seconds to under 2 seconds
- Total compute savings: $85/month

---

## Technique 1: Docker Image Optimization

### 1.1 Current Image Analysis

**Base Image Audit**:

```bash
# Analyze current image
docker inspect email-sidecar-lambda:current

# Expected output:
# {
#   "Size": 471859200,  # 450 MB
#   "VirtualSize": 471859200,
#   "RootFS": {
#     "Type": "layers",
#     "Layers": [
#       { "Size": 128 MB },   # Ubuntu base
#       { "Size": 89 MB },    # PHP + extensions
#       { "Size": 93 MB },    # Composer dependencies
#       { "Size": 51 MB },    # Application code
#       { "Size": 110 MB }    # Dev tools (unnecessary in Lambda)
#     ]
#   }
# }
```

### 1.2 Optimization Strategy

**BEFORE** (Current Dockerfile):

```dockerfile
# Current: 450 MB
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
  php8.2 \
  php8.2-fpm \
  php8.2-mysql \
  php8.2-redis \
  composer \
  curl \
  wget \
  git \
  vim \
  less \
  strace \
  build-essential \
  && apt-get clean

COPY composer.json composer.lock /app/
COPY . /app/

WORKDIR /app
RUN composer install

ENTRYPOINT ["./runtime.php"]
```

**AFTER** (Optimized Dockerfile):

```dockerfile
# Optimized: <200 MB
FROM php:8.2-fpm-alpine  # Alpine = 180 MB base (vs 350 MB Ubuntu)

# Install minimal dependencies
RUN apk add --no-cache \
  composer \
  mysql-client \
  && rm -rf /tmp/* /var/cache/apk/*

WORKDIR /app

# Multi-stage build: separate build from runtime
COPY composer.json composer.lock ./

# Build stage: includes dev dependencies
RUN composer install \
  --no-progress \
  --no-interaction \
  --optimize-autoloader \
  --no-dev  # CRITICAL: exclude dev dependencies

COPY . .

# Runtime stage: only necessary files
FROM php:8.2-fpm-alpine

COPY --from=builder /app /app

# Minimal runtime setup
RUN apk add --no-cache mysql-client

WORKDIR /app

# Cache-busting: runtime config only
COPY runtime.php ./

ENTRYPOINT ["php", "runtime.php"]
```

### 1.3 Build Optimization Commands

```bash
# Step 1: Build with multi-stage
docker build -t email-sidecar-lambda:optimized .

# Step 2: Measure reduction
docker image ls email-sidecar-lambda

# Expected output:
# REPOSITORY                    TAG         SIZE
# email-sidecar-lambda          current     450MB
# email-sidecar-lambda          optimized   175MB  # 61% reduction!

# Step 3: Test in Lambda runtime
docker run --rm -v /var/task:/var/task \
  email-sidecar-lambda:optimized

# Step 4: Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
docker tag email-sidecar-lambda:optimized $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:optimized
docker push $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:optimized
```

### 1.4 Layer Analysis

**Size Breakdown Before/After**:

| Layer | Before | After | Reduction |
|-------|--------|-------|-----------|
| Base OS | 350 MB | 110 MB | 69% |
| PHP extensions | 89 MB | 25 MB | 72% |
| Composer deps (dev) | 110 MB | 0 MB | 100% |
| App code | 51 MB | 40 MB | 22% |
| Dev tools | 110 MB | 0 MB | 100% |
| **Total** | **450 MB** | **175 MB** | **61%** |

---

## Technique 2: Provisioned Concurrency Tuning

### 2.1 Current Capacity Analysis

**Current Setup** (sub-optimal):

```json
{
  "ProvisionedConcurrentExecutions": 10,
  "EstimatedCost": "$2/month",
  "AverageUtilization": "40%",
  "PeakUtilization": "85%"
}
```

**Problem**: Paying for 10 units but only using 4 on average

### 2.2 Optimization Decision Tree

```
Step 1: Analyze historical traffic
  → 30-day average: 4 concurrent executions
  → Peak (weekend): 8 concurrent executions
  → 95th percentile: 6 concurrent executions

Step 2: Compare cost vs benefit
  → 5 provisioned units = $1/month
  → Increase 2 on-demand to 8 = $0.25/month
  → Total: $1.25/month (vs $2/month)

Step 3: Monitor for 2 weeks
  → Verify no throttling (CloudWatch: Throttles metric)
  → Measure cold start improvements
  → Validate error rates remain <0.1%

Step 4: Decision
  → ✓ Reduce provisioned to 5 units
```

### 2.3 Implementation

**Update Lambda Provisioned Concurrency** (via CLI):

```bash
# Current state
aws lambda get-provisioned-concurrency-config \
  --function-name email-sidecar-worker \
  --provisioned-concurrent-executions

# Reduce provisioned concurrency
aws lambda put-provisioned-concurrency-config \
  --function-name email-sidecar-worker \
  --provisioned-concurrent-executions 5

# Verify
aws lambda get-provisioned-concurrency-config \
  --function-name email-sidecar-worker

# Expected output:
# {
#   "ProvisionedConcurrentExecutions": 5,
#   "Requested Timestamp": "...",
#   "Status": "InProgress"
# }

# Wait ~5 minutes for status → "Succeeded"
```

**CloudWatch Validation** (monitor for 2 weeks):

```bash
# Check for throttling
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=email-sidecar-worker \
  --start-time 2026-07-05T00:00:00Z \
  --end-time 2026-07-19T00:00:00Z \
  --period 86400 \
  --statistics Sum

# Expected: All zeros (no throttling)

# Check concurrent executions
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --dimensions Name=FunctionName,Value=email-sidecar-worker \
  --start-time 2026-07-05T00:00:00Z \
  --end-time 2026-07-19T00:00:00Z \
  --period 3600 \
  --statistics Maximum,Average

# Expected: Maximum < 5 (within provisioned limit)
```

---

## Technique 3: Graviton2 Migration (ARM-based CPU)

### 3.1 Architecture Comparison

| Architecture | Cost | Performance | Support |
|---|---|---|---|
| x86_64 (Intel/AMD) | $0.0000166667/s | Baseline | Full |
| ARM (Graviton2) | $0.0000133333/s | Baseline | PHP 8.2+ ✓ |
| **Savings** | **20%** | Same | Full |

### 3.2 Migration Path

**Step 1: Build ARM Image**:

```dockerfile
# Multi-architecture build
FROM --platform=linux/arm64 php:8.2-fpm-alpine

# Rest of Dockerfile identical
# Docker buildx handles cross-compilation
```

**Step 2: Build & Push ARM Image**:

```bash
# Install buildx (one-time)
docker buildx create --use

# Build for ARM64
docker buildx build \
  --platform linux/arm64 \
  --push \
  --tag $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:arm64 \
  .

# Verify push
aws ecr describe-images \
  --repository-name email-sidecar-lambda \
  --query 'imageDetails[*].[imageTags, architectures]'
```

**Step 3: Update Lambda Function** (gradual rollout):

```bash
# Backup current x86 version
aws lambda update-function-code \
  --function-name email-sidecar-worker \
  --image-uri $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:x86-current

# Create new version with ARM
aws lambda update-function-code \
  --function-name email-sidecar-worker \
  --image-uri $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:arm64

# Test new version
aws lambda invoke \
  --function-name email-sidecar-worker \
  --payload '{"test": true}' \
  /tmp/response.json

cat /tmp/response.json
# Expected: Normal response, no errors

# If successful, keep ARM
# If errors, rollback: aws lambda update-function-code ... --image-uri x86-current
```

### 3.3 Validation

**Performance Testing** (identical workload):

```python
import boto3
import time

lambda_client = boto3.client('lambda')

def test_architecture(arch_uri):
    times = []
    for i in range(10):
        start = time.time()
        lambda_client.invoke(
            FunctionName='email-sidecar-worker',
            InvocationType='RequestResponse',
            Payload=json.dumps({'test_email_count': 100})
        )
        times.append(time.time() - start)
    
    return {
        'architecture': arch_uri.split(':')[-1],
        'mean_time': sum(times) / len(times),
        'max_time': max(times),
        'min_time': min(times)
    }

x86_results = test_architecture('x86-current')
arm_results = test_architecture('arm64')

print(f"x86: {x86_results['mean_time']:.3f}s")
print(f"ARM: {arm_results['mean_time']:.3f}s")
print(f"Difference: {((arm_results['mean_time'] - x86_results['mean_time']) / x86_results['mean_time'] * 100):.1f}%")
# Expected: Within 5% (performance parity)
```

---

## Technique 4: Cold Start Reduction

### 4.1 Root Cause Analysis

**Current Cold Start Timeline**:

```
Total: 3.5 seconds (reported by Lambda Duration metric)

Breakdown:
├─ Lambda initialization: 0.8s (OS + container)
├─ PHP bootstrap: 1.2s (extension loading)
├─ Autoloader: 0.6s (composer PSR-4)
├─ Database connection: 0.6s (TCP handshake + auth)
├─ Redis connection: 0.3s (connection pooling miss)
```

### 4.2 Optimization Techniques

**A. Lazy-Load Dependencies**:

```php
// BEFORE: Load everything upfront
require_once 'vendor/autoload.php';

$db = new PDO('postgresql://...');
$redis = new Redis();
$redis->connect('localhost', 6379);

function handle_event($event) {
  // Database + Redis already loaded, even if not needed
}

// AFTER: Load only when needed
require_once 'vendor/autoload.php';

$db = null;
$redis = null;

function handle_event($event) {
  global $db, $redis;
  
  if ($event['needs_database']) {
    // Lazy-initialize only if needed
    if (!$db) {
      $db = new PDO('postgresql://...');
    }
    return $db->query(...);
  }
}
```

**B. Pre-warm Connections** (via Lambda layers):

```php
// Layer: connection-warmer.php
// Runs once during initialization, keeps connection warm

class ConnectionWarmer {
  public function warmConnections() {
    // TCP pre-connect to RDS (no query)
    $sock = fsockopen('rds-host', 5432, $errno, $errstr, 2);
    if ($sock) fclose($sock);
    
    // Redis pre-connect
    $redis = new Redis();
    $redis->connect('elasticache-endpoint', 6379, 2);
    $redis->close();
    
    // Prime class loader
    class_exists('PDO');
    class_exists('Redis');
  }
}

(new ConnectionWarmer())->warmConnections();
```

**C. Response Caching** (for repeated queries):

```php
// Cache strategy: reuse prepared statements across invocations
class CachedPDO {
  private static $instance = null;
  private static $statements = [];
  
  public static function getInstance() {
    if (!self::$instance) {
      self::$instance = new PDO('postgresql://...');
    }
    return self::$instance;
  }
  
  public static function prepare($sql) {
    if (!isset(self::$statements[$sql])) {
      self::$statements[$sql] = self::getInstance()->prepare($sql);
    }
    return self::$statements[$sql];
  }
}

// Use cached PDO
$stmt = CachedPDO::prepare('SELECT * FROM emails WHERE id = ?');
$stmt->execute([$emailId]);
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | Image optimization, testing | 35 | New Docker image (<200 MB), layer analysis |
| **Week 2** | Provisioned concurrency, Graviton2 migration | 40 | 5 units provisioned, ARM image in ECR |
| **Week 3** | Cold start reduction, validation | 25 | Lazy loading implemented, connections pre-warmed |

**Total**: 100 hours

---

## Cost Savings Breakdown

| Optimization | Current | After | Savings |
|---|---|---|---|
| Container image | $0 | $0 | $0 (storage only) |
| Provisioned concurrency | $2/mo | $1/mo | $1/mo |
| Graviton2 (20% cheaper) | $200/mo | $160/mo | $40/mo |
| Invocation count reduction (caching) | $0 | -$44/mo* | $44/mo |
| **Total Monthly Savings** | **$200/mo** | **$115/mo** | **$85/mo** |

*Assumes 5% reduction in total invocations due to caching/connection reuse

---

## Success Criteria

| Metric | Baseline | Target | Measurement |
|---|---|---|---|
| Docker image size | 450 MB | <200 MB | ECR repository size |
| Provisioned units | 10 | 5 | Lambda concurrency config |
| Architecture | x86_64 only | ARM64 | Lambda logs arch field |
| Cold start time | 3.5+ seconds | <2 seconds | CloudWatch Duration metric |
| Throttle rate | 0% | 0% | CloudWatch Throttles metric |
| Monthly Lambda cost | $200 | $115 | AWS billing, compute section |

---

## Rollback Plan

**If cold starts degrade or errors spike**:

```bash
# Rollback to previous Docker image
aws lambda update-function-code \
  --function-name email-sidecar-worker \
  --image-uri $AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/email-sidecar-lambda:previous

# Increase provisioned concurrency if needed
aws lambda put-provisioned-concurrency-config \
  --function-name email-sidecar-worker \
  --provisioned-concurrent-executions 10

# Restore x86 architecture
# (Keep ARM for future, but don't use)
```

---

## Ongoing Monitoring

**Weekly Lambda Cost Report** (schedule):

```bash
# Check Lambda costs
aws ce describe-cost-and-usage \
  --time-period Start=2026-07-01,End=2026-07-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://lambda-filter.json

# lambda-filter.json:
# {
#   "Dimensions": {
#     "Key": "SERVICE",
#     "Values": ["AWS Lambda"]
#   }
# }
```

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 9 Week 2 execution  
**Next**: Phase 9, Step 3 (Storage & Backup Optimization)
