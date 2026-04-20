# Phase 9, Step 1: Database Query Optimization Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Database engineer  
**Timeline**: July 1-18, 2026 (3 weeks)  
**Effort**: 80 hours (2 engineer weeks)  
**Expected Savings**: $15/month RDS cost, query latency improvement to sub-100ms range

---

## Executive Summary

Database optimization reduces RDS CPU utilization from 45% average to <30%, improving performance and reducing costs. Three focus areas:

1. **Slow Query Analysis** — Identify queries exceeding 500ms, root cause analysis
2. **Index Optimization** — Add composite indexes, remove unused ones
3. **Query Refactoring** — Eliminate N+1 queries, batch operations, connection pooling

**Expected Impact**:
- RDS CPU: 45% → <30% (20% reduction)
- Query latency: Sustained improvement to under 100ms for 95th percentile
- Monthly RDS cost: $150 → $135 (-$15/month)

---

## Phase 1: Slow Query Analysis

### 1.1 Enable Slow Query Logging

**RDS Parameter Group Configuration**:

```sql
-- SSH into RDS or use AWS RDS Console
-- Modify Parameter Group

-- Enable slow query log
slow_query_log = 1
long_query_time = 0.5  -- Log queries exceeding half-second
log_queries_not_using_indexes = 1  -- Flag full table scans
log_output = TABLE  -- Or FILE to S3
```

**Verify Configuration**:
```sql
SHOW VARIABLES LIKE 'slow_query_log%';
SHOW VARIABLES LIKE 'long_query_time';
```

### 1.2 Query Analysis Script (Python)

**File**: `analyze_slow_queries.py`

```python
#!/usr/bin/env python3
import psycopg2
import sys
from datetime import datetime, timedelta
from statistics import mean, median, stdev

class SlowQueryAnalyzer:
    def __init__(self, connection_string):
        self.conn = psycopg2.connect(connection_string)
        self.cursor = self.conn.cursor()
    
    def get_slow_queries(self, threshold_ms=500, hours=24):
        """Fetch queries slower than threshold from pg_stat_statements"""
        
        query = """
        SELECT 
            query,
            calls,
            total_time,
            mean_time,
            max_time,
            stddev_time,
            rows
        FROM pg_stat_statements
        WHERE mean_time > %s
            AND query_timestamp > NOW() - INTERVAL '%s hours'
        ORDER BY mean_time DESC
        LIMIT 50;
        """
        
        self.cursor.execute(query, (threshold_ms, hours))
        return self.cursor.fetchall()
    
    def analyze_query_plan(self, query):
        """EXPLAIN ANALYZE to identify bottlenecks"""
        
        self.cursor.execute(f"EXPLAIN ANALYZE {query}")
        plan = self.cursor.fetchall()
        return plan
    
    def generate_report(self):
        """Generate optimization recommendations"""
        
        slow_queries = self.get_slow_queries(threshold_ms=500)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'slow_queries_found': len(slow_queries),
            'queries': []
        }
        
        for query, calls, total_time, mean_time, max_time, stddev, rows in slow_queries:
            # Clean query (remove excess whitespace)
            clean_query = ' '.join(query.split())[:200]  # First 200 chars
            
            # Analyze plan
            plan = self.analyze_query_plan(query)
            
            # Identify issue
            issue = self._identify_issue(plan, query)
            
            report['queries'].append({
                'query': clean_query,
                'calls': calls,
                'mean_time_milliseconds': round(mean_time, 2),
                'max_time_milliseconds': round(max_time, 2),
                'total_time_milliseconds': round(total_time, 2),
                'rows_returned': rows,
                'identified_issue': issue['type'],
                'recommendation': issue['recommendation'],
                'estimated_improvement_percent': issue['improvement_percent']
            })
        
        return report
    
    def _identify_issue(self, plan, query):
        """Identify bottleneck from execution plan"""
        
        plan_str = str(plan).lower()
        
        if 'seq scan' in plan_str and 'limit' not in query.lower():
            return {
                'type': 'Full table scan without index',
                'recommendation': 'Create composite index on filtered/sorted columns',
                'improvement_percent': 70
            }
        elif 'n+1 query pattern' in query.lower() or query.count('SELECT') > 1:
            return {
                'type': 'N+1 query pattern',
                'recommendation': 'Use JOIN instead of separate queries',
                'improvement_percent': 80
            }
        elif 'sort' in plan_str:
            return {
                'type': 'In-memory sorting',
                'recommendation': 'Create index on sort key',
                'improvement_percent': 60
            }
        else:
            return {
                'type': 'Complex query',
                'recommendation': 'Review with DBA',
                'improvement_percent': 30
            }

# Usage
if __name__ == '__main__':
    analyzer = SlowQueryAnalyzer(
        "postgresql://user:pass@rds-host:5432/email_sidecar"
    )
    report = analyzer.generate_report()
    
    print(f"Found {report['slow_queries_found']} slow queries")
    for q in report['queries']:
        print(f"\n{q['query'][:100]}...")
        print(f"  Mean time: {q['mean_time_milliseconds']}ms")
        print(f"  Issue: {q['identified_issue']}")
        print(f"  Fix: {q['recommendation']}")
        print(f"  Expected improvement: {q['estimated_improvement_percent']}%")
```

### 1.3 Weekly Analysis Schedule

```php
// app/Console/Commands/AnalyzeSlowQueries.php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Symfony\Component\Process\Process;

class AnalyzeSlowQueries extends Command {
    protected $signature = 'db:analyze-slow-queries';
    protected $description = 'Analyze slow queries and generate report';

    public function handle() {
        // Run Python analyzer
        $process = new Process([
            'python3',
            base_path('scripts/analyze_slow_queries.py')
        ]);

        $process->run();

        if (!$process->isSuccessful()) {
            $this->error('Analysis failed: ' . $process->getErrorOutput());
            return 1;
        }

        $report = json_decode($process->getOutput(), true);

        // Store report in database
        QueryOptimizationReport::create([
            'report_data' => $report,
            'slow_query_count' => $report['slow_queries_found'],
            'generated_at' => now()
        ]);

        // Notify team if critical issues found
        if ($report['slow_queries_found'] > 5) {
            Notification::send(
                User::whereRole('dba')->get(),
                new SlowQueriesDetectedNotification($report)
            );
        }

        $this->info("Analysis complete. Found {$report['slow_queries_found']} slow queries.");
        return 0;
    }
}

// Schedule in Kernel.php
$schedule->command('db:analyze-slow-queries')
    ->weeklyOn(2, '02:00');  // Every Tuesday at 2 AM
```

---

## Phase 2: Index Optimization

### 2.1 Composite Index Strategy

**Current Problem**: Individual column indexes are inefficient for multi-column queries

```sql
-- BEFORE (2 indexes)
CREATE INDEX idx_emails_tenant ON emails(tenant_id);
CREATE INDEX idx_emails_created ON emails(created_at DESC);

-- Query uses only first index, then filters in memory
SELECT * FROM emails 
WHERE tenant_id = 'xyz' AND created_at > '2026-01-01'
ORDER BY created_at DESC;
```

**Optimization**: Single composite index covering all filter/sort columns

```sql
-- AFTER (1 composite index)
CREATE INDEX CONCURRENTLY idx_emails_tenant_created 
  ON emails(tenant_id, created_at DESC)
  INCLUDE (status, recipient);  -- INCLUDE columns for index-only scans

-- Same query now uses composite index, no memory sort needed
```

### 2.2 Index Creation Plan

**Week 1 Analysis Output** (sample):

```
Top 5 Missing Indexes:

1. emails table (email_search queries)
   Current: Exceeds 400ms, full table scan
   Recommendation: CREATE INDEX idx_emails_tenant_created
   Impact: Reduces to under 100ms (significant improvement)

2. webhook_execution_log table (logging)
   Current: Exceeds 200ms for recent logs query
   Recommendation: CREATE INDEX idx_webhook_tenant_created
   Impact: Reduces to under 50ms (75% improvement)

3. email_templates table (template lookups)
   Current: Exceeds 150ms for template searches
   Recommendation: CREATE INDEX idx_templates_tenant_name
   Impact: Reduces to under 30ms (80% improvement)

4. api_keys table (auth lookups)
   Current: Exceeds 100ms per API request
   Recommendation: CREATE INDEX idx_keys_hash
   Impact: Reduces to under 10ms (90% improvement)

5. audit_log table (compliance queries)
   Current: Exceeds 300ms for monthly reports
   Recommendation: CREATE INDEX idx_audit_tenant_date
   Impact: Reduces to under 60ms (80% improvement)
```

### 2.3 Safe Index Creation (Production)

**Using CONCURRENTLY (non-blocking)**:

```sql
-- Creates index without locking table (takes longer, but no downtime)
CREATE INDEX CONCURRENTLY idx_emails_tenant_created
  ON emails(tenant_id, created_at DESC);

-- Monitor progress (in separate connection)
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE indexname = 'idx_emails_tenant_created';
```

**Creation Timeline** (production RDS):
- Index 1 (emails): ~15 minutes (2M rows)
- Index 2 (webhook_log): ~8 minutes (500K rows)
- Index 3 (templates): ~2 minutes (50K rows)
- Index 4 (api_keys): ~1 minute (10K rows)
- Index 5 (audit_log): ~20 minutes (3M rows)
- **Total**: ~45 minutes spread over 3 days (1-2 indexes per night)

### 2.4 Unused Index Cleanup

**Find unused indexes**:

```sql
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0  -- Never used
  AND indexname NOT LIKE 'pk_%'  -- Exclude primary keys
ORDER BY tablename;
```

**Safe Removal** (after verification):

```sql
-- Check if index is truly unused (wait 1 week)
-- Then drop with CONCURRENTLY to avoid locking

DROP INDEX CONCURRENTLY idx_old_unused_index;

-- Freed space: ~500MB (reclaimed for other indexes)
```

---

## Phase 3: Query Refactoring

### 3.1 Eliminate N+1 Query Pattern

**BEFORE (N+1 Pattern)**:

```php
// Query 1: Fetch all emails
$emails = Email::where('tenant_id', $tenantId)
  ->where('status', 'delivered')
  ->limit(50)
  ->get();

// Query 2-51: Loop fetches template for each email (50 separate queries!)
foreach ($emails as $email) {
  $template = EmailTemplate::find($email->template_id);  // N queries!
  echo $template->name;
}

// Total queries: 51 (1 + 50)
// Total time: Multiple seconds of cumulative database work
```

**AFTER (Eager Loading with JOIN)**:

```php
// Single query with JOIN
$emails = Email::where('tenant_id', $tenantId)
  ->where('status', 'delivered')
  ->with('template')  // Eager load via JOIN
  ->limit(50)
  ->get();

// No loop queries needed, template already loaded
foreach ($emails as $email) {
  echo $email->template->name;  // In-memory, no query
}

// Total queries: 1 (or 2 if using separate query optimization)
// Total time: Single database round trip
// Improvement: Dramatic reduction (90%+ faster)
```

**Code Changes Required** (Laravel):

```php
// Model relationships
class Email extends Model {
  public function template() {
    return $this->belongsTo(EmailTemplate::class);
  }
}

// Use eager loading
$emails = Email::with('template')  // Add this
  ->where('tenant_id', $tenantId)
  ->where('status', 'delivered')
  ->limit(50)
  ->get();
```

### 3.2 Batch Operations Instead of Loop

**BEFORE (Loop - Slow)**:

```php
// Delete 1000 emails one at a time
$emails = Email::where('tenant_id', $tenantId)
  ->where('deleted_at', '<', now()->subDays(90))
  ->limit(1000)
  ->get();

foreach ($emails as $email) {
  $email->delete();  // 1000 individual DELETE queries
}

// Time: Several seconds of processing
// RDS CPU spike: Significant elevation
```

**AFTER (Batch - Fast)**:

```php
// Delete 1000 emails in single batch
Email::where('tenant_id', $tenantId)
  ->where('deleted_at', '<', now()->subDays(90))
  ->limit(1000)
  ->delete();  // Single DELETE with WHERE clause

// Time: Completes quickly
// RDS CPU: Minimal impact
// Improvement: Orders of magnitude faster
```

### 3.3 Connection Pooling Tuning

**Current Config**:
```ini
max_connections = 100
shared_buffers = 4GB
work_mem = 16MB
maintenance_work_mem = 512MB
```

**Optimized Config**:
```ini
max_connections = 150  # Increase for higher concurrency
shared_buffers = 8GB  # Allocate more to buffer pool
work_mem = 32MB  # Allow bigger sorts/hash joins
maintenance_work_mem = 1GB  # Faster index creation

# Connection pooling via RDS Proxy
# Min: 1, Max: 100 per client
# Connection timeout: 300 seconds
```

**RDS Proxy Configuration** (via AWS Console):

```
Engine Family: PostgreSQL
Min Pool Size: 5
Max Pool Size: 100
Connection Timeout: 300 seconds
Idle Timeout: 900 seconds
Init Query: SET session_replication_role = replica;
```

---

## Implementation Timeline

| Week | Task | Hours | Deliverables |
|------|------|-------|--------------|
| **Week 1** | Slow query analysis, reporting | 30 | Analysis report, 10 slow queries identified |
| **Week 2** | Index creation, safety testing | 30 | 5 indexes created, 0 table locks |
| **Week 3** | Query refactoring, pool tuning | 20 | 15 N+1 patterns eliminated, connection pool optimized |

**Total**: 80 hours

---

## Success Criteria

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| RDS CPU (avg) | 45% | <30% | CloudWatch metrics, 30-day average |
| Query latency (95th percentile) | Exceeds 150ms | Under 100ms | Datadog APM, sample 10K queries |
| Slow query count | 50/day | <5/day | CloudWatch slow query logs |
| RDS cost | $150/mo | $135/mo | AWS billing, month-end |

---

## Validation & Testing

**Week 1 Testing** (staging environment):
1. Create indexes on test database (copy from production)
2. Run query benchmark suite (compare before/after)
3. Validate no regressions in application tests
4. Load test with 2x normal traffic

**Week 2-3 Testing** (production, canary rollout):
1. Create indexes during off-peak hours (2 AM UTC)
2. Monitor RDS CPU/memory for 30 minutes after each
3. Validate query performance with DataDog
4. Rollback plan: Document DROP INDEX commands

**Rollback Plan** (if issues found):
```sql
-- Quick rollback if needed
DROP INDEX CONCURRENTLY idx_emails_tenant_created;
DROP INDEX CONCURRENTLY idx_webhook_tenant_created;
-- etc.

-- Restore normal performance within 30 minutes
```

---

## Ongoing Maintenance

**Monthly Optimization Cycle**:
```
Week 1: Run slow query analysis (Tuesday)
Week 2: Review report, plan index changes
Week 3: Create new indexes, drop unused ones
Week 4: Validate performance improvements
```

**Tool**: Automated analysis script (cron job, Monday 2 AM)

---

## Cost & Resource Summary

**One-Time Cost**: 80 hours @ $150/hr = $12,000  
**Ongoing Savings**: $15/month = $180/year  
**Payback Period**: 67 months (long-term infrastructure improvement)  
**Primary Benefit**: Query performance improvement (operational excellence, not cost)

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 9 Week 1 execution  
**Next**: Phase 9, Step 2 (Lambda Cost Optimization)
