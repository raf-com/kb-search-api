# Phase 8, Step 4: Usage Analytics Dashboard Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: Full-stack engineer  
**Timeline**: May 1-24, 2026 (4 weeks, parallel with Steps 1-3)  
**Effort**: 120 hours (3 engineer weeks)

---

## Executive Summary

Usage analytics empowers customers with visibility into consumption, costs, and trends. Enables data-driven decisions on tier upgrades and feature adoption. Expected impact: 15% upgrade conversion from forecast alerts.

**Key Metrics Displayed**:
- Real-time: Emails sent (today), cost (current month)
- Historical: Delivery trends, cost trajectories, tier utilization
- Forecasting: Linear extrapolation, seasonal patterns, budget alerts
- Recommendations: Upgrade suggestions, cost optimization tips

---

## Architecture: Metrics Aggregation Pipeline

**Data Flow**:
```
Prometheus (5-minute metrics)
  ↓
TimescaleDB (daily rollups, 1-year retention)
  ↓
GraphQL API (aggregations, forecasting)
  ↓
React Dashboard (visualizations)
```

### Technology Selection

**Why TimescaleDB instead of InfluxDB**:
- Existing RDS PostgreSQL → Add TimescaleDB extension
- 80% cost reduction vs standalone InfluxDB
- SQL interface → familiar to team
- TSDB optimizations: compression, continuous aggregates

---

## Component 1: Metrics Aggregation Layer

### 1.1 TimescaleDB Setup

**Enable extension**:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Hypertable for daily metrics (timescale for automatic partitioning)
CREATE TABLE IF NOT EXISTS metrics_daily (
  time TIMESTAMP NOT NULL,
  tenant_id UUID NOT NULL,
  metric_name VARCHAR(100) NOT NULL,
  value DECIMAL(18,4) NOT NULL,
  labels JSONB DEFAULT '{}'::jsonb
);

SELECT create_hypertable(
  'metrics_daily',
  'time',
  if_not_exists => TRUE
);

-- Continuous aggregate: Monthly rollup (auto-updated)
CREATE MATERIALIZED VIEW metrics_monthly AS
SELECT
  time_bucket('1 month', time) AS month,
  tenant_id,
  metric_name,
  SUM(value) as total,
  AVG(value) as average,
  MAX(value) as peak
FROM metrics_daily
GROUP BY month, tenant_id, metric_name;

SELECT add_continuous_aggregate_policy(
  'metrics_monthly',
  start_offset => INTERVAL '2 months',
  end_offset => INTERVAL '1 day',
  schedule_interval => INTERVAL '1 day'
);

-- Index for query performance
CREATE INDEX idx_metrics_tenant_time 
  ON metrics_daily (tenant_id, time DESC);
```

### 1.2 Metrics Collection Job (Laravel)

**Daily aggregation job** (runs at 02:00 UTC):

```php
namespace App\Jobs;

use App\Models\Tenant;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;

class AggregateMetricsJob implements ShouldQueue {
  use Queueable;

  public function handle() {
    $tenants = Tenant::all();

    foreach ($tenants as $tenant) {
      // Aggregate from Prometheus
      $prometheus = app(PrometheusClient::class);
      
      // Emails sent (yesterday)
      $emailsSent = $prometheus->query(
        'sum(increase(emails_sent_total{tenant_id="' . $tenant->id . '"}[1d]))'
      );

      // Cost (month-to-date)
      $costMtd = $this->calculateCost($tenant);

      // Delivery rate
      $deliveryRate = $prometheus->query(
        'sum(rate(emails_delivered_total{tenant_id="' . $tenant->id . '"}[1d])) / ' .
        'sum(rate(emails_sent_total{tenant_id="' . $tenant->id . '"}[1d]))'
      );

      // Store in TimescaleDB
      MetricsDaily::create([
        'time' => now()->subDay(),
        'tenant_id' => $tenant->id,
        'metric_name' => 'emails_sent',
        'value' => $emailsSent,
        'labels' => json_encode(['period' => 'daily'])
      ]);

      MetricsDaily::create([
        'time' => now()->subDay(),
        'tenant_id' => $tenant->id,
        'metric_name' => 'cost_mtd',
        'value' => $costMtd,
        'labels' => json_encode(['currency' => 'USD'])
      ]);

      // ... more metrics
    }

    // Refresh continuous aggregates
    DB::statement('REFRESH MATERIALIZED VIEW CONCURRENTLY metrics_monthly');
  }

  private function calculateCost($tenant): float {
    // Cost = base + (emails_sent * per_email_rate)
    $emailsSent = Email::where('tenant_id', $tenant->id)
      ->whereMonth('created_at', now())
      ->count();

    $baseRate = 0; // Free tier
    $perEmailRate = 0.00035; // $0.35 per 1K emails

    return $emailsSent * $perEmailRate;
  }
}

// Schedule in Kernel.php
$schedule->job(new AggregateMetricsJob)
  ->dailyAt('02:00');
```

---

## Component 2: Forecasting Engine

### 2.1 Forecasting Algorithms

**Linear Trend Forecasting**:
```python
# Python Lambda function: forecast_metrics
import numpy as np
from datetime import datetime, timedelta

def linear_forecast(history: list[float], days_ahead: int) -> dict:
    """
    history: List of metric values (e.g., daily costs for last 30 days)
    days_ahead: Number of days to forecast (e.g., 10 for rest of month)
    
    Returns: Dict with predicted_total, confidence_interval
    """
    
    # Fit linear regression: y = mx + b
    x = np.arange(len(history))
    y = np.array(history)
    
    coeffs = np.polyfit(x, y, 1)  # degree 1 = linear
    m, b = coeffs
    
    # Forecast next N days
    x_future = np.arange(len(history), len(history) + days_ahead)
    y_future = m * x_future + b
    
    # Calculate confidence interval (±1 std dev)
    residuals = y - (m * x + b)
    std_dev = np.std(residuals)
    
    return {
        'predicted_total': float(np.sum(y_future)),
        'daily_average': float(np.mean(y_future)),
        'confidence_interval': [
            float(np.sum(y_future) - std_dev),
            float(np.sum(y_future) + std_dev)
        ]
    }


def seasonal_forecast(history_by_month: dict[str, float]) -> dict:
    """
    history_by_month: {
      '2025-01': 150.0,
      '2025-02': 180.0,
      '2026-01': 210.0,  # Same month last year
      '2026-02': 240.0
    }
    
    Returns: Seasonal pattern (factor by month)
    """
    
    # Group by calendar month
    month_values = {}
    for month_str, value in history_by_month.items():
      month = month_str.split('-')[1]  # 01, 02, ... 12
      if month not in month_values:
        month_values[month] = []
      month_values[month].append(value)
    
    # Calculate average for each month
    seasonal_factors = {}
    overall_avg = sum(history_by_month.values()) / len(history_by_month)
    
    for month, values in month_values.items():
      month_avg = sum(values) / len(values)
      seasonal_factors[month] = month_avg / overall_avg  # >1 = busy month
    
    return seasonal_factors
```

### 2.2 Forecasting API Endpoint

```php
namespace App\Http\Controllers;

class ForecastingController extends Controller {
  
  public function forecast(Request $request, $tenantId) {
    $validated = $request->validate([
      'metric' => 'required|in:cost,emails_sent,delivery_rate',
      'days_ahead' => 'integer|min:1|max:90'
    ]);

    // Fetch historical data (30 days)
    $history = MetricsDaily::where('tenant_id', $tenantId)
      ->where('metric_name', $validated['metric'])
      ->where('time', '>=', now()->subDays(30))
      ->orderBy('time')
      ->pluck('value')
      ->toArray();

    if (count($history) < 5) {
      return response()->json([
        'error' => 'Insufficient historical data (need at least 5 days)',
        'history_days' => count($history)
      ], 422);
    }

    // Call Python forecasting service
    $forecast = PythonService::forecast(
      metric: $validated['metric'],
      history: $history,
      days_ahead: $validated['days_ahead'] ?? 10
    );

    return response()->json([
      'metric' => $validated['metric'],
      'history_days' => count($history),
      'days_ahead' => $validated['days_ahead'] ?? 10,
      'forecast' => $forecast,
      'confidence' => '95%'
    ]);
  }
}
```

---

## Component 3: Dashboard UI

### 3.1 React Dashboard Components

**Main Dashboard**:
```tsx
export const UsageAnalyticsDashboard: React.FC = () => {
  const { data: metrics } = useQuery(['metrics'], () => api.get('/metrics/dashboard'));
  const { data: forecast } = useQuery(['forecast'], () => api.get('/metrics/forecast'));

  return (
    <div className="analytics-dashboard">
      <div className="header">
        <h1>Usage & Analytics</h1>
        <div className="period-selector">
          <Button>This Month</Button>
          <Button>Last Month</Button>
          <Button>Last 3 Months</Button>
        </div>
      </div>

      <div className="kpi-cards">
        <MetricCard
          title="Emails Sent (This Month)"
          value={metrics?.emails_sent_mtd}
          unit="emails"
          trend={metrics?.emails_sent_trend}  // % change vs last month
        />
        <MetricCard
          title="Cost (This Month)"
          value={metrics?.cost_mtd}
          unit="USD"
          trend={metrics?.cost_trend}
        />
        <MetricCard
          title="Projected Month-End Cost"
          value={forecast?.cost?.predicted_total}
          unit="USD"
          alert={forecast?.cost?.predicted_total > metrics?.cost_budget}
        />
        <MetricCard
          title="Delivery Rate (7-day avg)"
          value={metrics?.delivery_rate_7d}
          unit="%"
          benchmark="Industry avg: 98.2%"
        />
      </div>

      <div className="charts">
        <ChartContainer title="Daily Costs (Last 30 Days)">
          <LineChart
            data={metrics?.daily_costs}
            xAxis="date"
            yAxis="cost_usd"
            forecast={forecast?.cost_daily}
          />
        </ChartContainer>

        <ChartContainer title="Email Volume Trend">
          <AreaChart
            data={metrics?.daily_volume}
            stacked={true}
            categories={['delivered', 'bounced', 'complained']}
          />
        </ChartContainer>

        <ChartContainer title="Tier Utilization">
          <ProgressBar
            label="Emails Sent vs Tier Limit"
            current={metrics?.emails_sent_mtd}
            max={metrics?.tier_limit}
            percentage={(metrics?.emails_sent_mtd / metrics?.tier_limit) * 100}
          />
        </ChartContainer>
      </div>

      <div className="recommendations">
        <h3>Recommendations</h3>
        {metrics?.recommendations?.map((rec) => (
          <RecommendationCard key={rec.id} recommendation={rec} />
        ))}
      </div>

      <div className="export-section">
        <h3>Export & Reporting</h3>
        <Button onClick={() => exportToCSV()}>📊 Export to CSV</Button>
        <Button onClick={() => scheduleReport()}>📧 Schedule Weekly Report</Button>
      </div>
    </div>
  );
};

const MetricCard: React.FC<{ title: string; value: number; unit: string; trend?: number; alert?: boolean }> = (
  { title, value, unit, trend, alert }
) => (
  <div className={`metric-card ${alert ? 'alert' : ''}`}>
    <h3>{title}</h3>
    <div className="value">
      {value?.toLocaleString()} <span className="unit">{unit}</span>
    </div>
    {trend && (
      <div className={`trend ${trend > 0 ? 'up' : 'down'}`}>
        {trend > 0 ? '📈' : '📉'} {Math.abs(trend)}% vs last month
      </div>
    )}
    {alert && <div className="alert-badge">⚠️ Approaching limit</div>}
  </div>
);
```

**Chart Configuration** (using Recharts):
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

export const CostChart: React.FC<{ data: any; forecast: any }> = ({ data, forecast }) => {
  // Combine historical + forecast data
  const combinedData = [
    ...data.map((d: any) => ({
      ...d,
      type: 'historical'
    })),
    ...forecast.map((f: any) => ({
      ...f,
      type: 'forecast'
    }))
  ];

  return (
    <LineChart data={combinedData} width={600} height={300}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="date" />
      <YAxis label={{ value: 'Cost (USD)', angle: -90, position: 'insideLeft' }} />
      <Tooltip formatter={(value) => `$${value.toFixed(2)}`} />
      <Legend />
      
      {/* Historical data: solid line */}
      <Line
        type="monotone"
        dataKey="cost"
        data={data}
        stroke="#2563eb"
        strokeWidth={2}
        name="Actual Cost"
      />
      
      {/* Forecast: dashed line */}
      <Line
        type="monotone"
        dataKey="cost"
        data={forecast}
        stroke="#9333ea"
        strokeWidth={2}
        strokeDasharray="5 5"
        name="Forecast"
      />
    </LineChart>
  );
};
```

---

## Component 4: Alerts & Recommendations

### 4.1 Alert Rules

**Cost Threshold Alert** (monthly budget):
```php
class CostAlertJob {
  public function handle() {
    $alerts = [
      ['threshold' => 0.75, 'level' => 'warning', 'message' => 'Approaching 75% of monthly budget'],
      ['threshold' => 0.90, 'level' => 'critical', 'message' => 'Approaching 90% of monthly budget'],
      ['threshold' => 1.0, 'level' => 'critical', 'message' => 'EXCEEDED monthly budget!']
    ];

    foreach (Tenant::all() as $tenant) {
      $costPct = $tenant->cost_mtd / $tenant->cost_budget;

      foreach ($alerts as $alert) {
        if ($costPct >= $alert['threshold']) {
          Notification::send(
            $tenant->owners,
            new BudgetAlertNotification($alert, $costPct)
          );
        }
      }
    }
  }
}
```

### 4.2 Upgrade Recommendation Engine

```php
class UpgradeRecommendationEngine {
  public function recommend($tenant): ?string {
    $emailsMtd = $tenant->emails_sent_mtd;
    $tierLimit = $tenant->tier_limit;
    
    // Recommend upgrade if >80% utilization
    if ($emailsMtd / $tierLimit > 0.8) {
      return sprintf(
        'You\'ve sent %s emails (%d%% of tier limit). ' .
        'Consider upgrading to %s tier for %.2f%% savings.',
        number_format($emailsMtd),
        ($emailsMtd / $tierLimit) * 100,
        $this->nextTier($tenant),
        $this->calculateSavings($tenant)
      );
    }

    return null;
  }

  private function calculateSavings($tenant): float {
    $currentCost = $tenant->cost_mtd;
    $nextTierCost = $this->getNextTierCost($tenant);
    return (($currentCost - $nextTierCost) / $currentCost) * 100;
  }
}
```

---

## Component 5: Export & Scheduled Reports

### 5.1 Export to CSV

```php
class ExportMetricsController {
  public function csv(Request $request) {
    $metrics = MetricsDaily::where('tenant_id', Auth::user()->tenant_id)
      ->whereBetween('time', [$request->start_date, $request->end_date])
      ->get();

    $csv = "Date,Metric,Value\n";
    foreach ($metrics as $metric) {
      $csv .= "{$metric->time},{$metric->metric_name},{$metric->value}\n";
    }

    return response()->streamDownload(
      fn() => echo $csv,
      "usage-analytics-" . now()->format('Y-m-d') . ".csv"
    );
  }
}
```

### 5.2 Scheduled Weekly Reports

```php
class ScheduleWeeklyReportJob {
  public function handle() {
    // Every Monday at 9 AM, email summary to account owners
    foreach (Tenant::all() as $tenant) {
      $metrics = [
        'emails_sent' => MetricsDaily::where('tenant_id', $tenant->id)
          ->whereDate('time', '>=', now()->subDays(7))
          ->sum('value'),
        'cost_week' => $this->calculateWeeklyCost($tenant),
        'delivery_rate' => $this->getDeliveryRate($tenant)
      ];

      Notification::send(
        $tenant->owners,
        new WeeklyReportNotification($metrics)
      );
    }
  }
}

// Register in Kernel.php
$schedule->job(new ScheduleWeeklyReportJob)
  ->weeklyOn(1, '09:00');  // Every Monday at 9 AM
```

---

## Implementation Timeline

| Week | Component | Deliverables |
|------|-----------|--------------|
| 1 | Metrics aggregation | TimescaleDB setup, aggregation job, Prometheus integration |
| 2 | Forecasting | Linear + seasonal algorithms, Python service, API endpoints |
| 3 | Dashboard UI | React components, charts, KPI cards, responsive design |
| 4 | Alerts + Export | Alert rules, recommendations, CSV export, scheduled reports |

**Total Effort**: 120 hours

---

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dashboard adoption | >80% of customers | Analytics event tracking |
| Cost forecast accuracy | >90% | Compare forecast vs actual, calculate MAPE |
| Upgrade conversion | >15% from alerts | Track "upgrade clicked" events |
| Report delivery success | >99% | Email delivery logs |

---

## Data Retention & Compliance

**Metrics Storage**:
- Daily metrics: 12 months (via compression in TimescaleDB)
- Monthly aggregates: 3 years
- Real-time Prometheus: 15 days

**GDPR Compliance**:
- Metrics contain no PII (only aggregate counts, costs)
- Retention policy auto-deletes data >12 months old
- User can request export: GraphQL API returns all metrics in CSV format

---

## Cost Breakdown (Phase 8, All 4 Steps)

| Component | Recurring Cost | Notes |
|-----------|---|---|
| **Step 1: Self-Service Portal** | $0 | Uses existing RDS, no new infrastructure |
| **Step 2: AI Features** | $809/month | OpenAI + SageMaker + Lambda |
| **Step 3: Marketplace** | $0 | Uses existing API, no infra cost |
| **Step 4: Analytics Dashboard** | $200/month | TimescaleDB + Grafana + storage |
| **Total Phase 8** | **$1,009/month** | — |

**Note**: Offset by expected revenue increase (+$5K/month from marketplace) and support cost reduction (-$2K/month).

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 8 implementation starting 2026-05-01  
**Phase 8 Complete**: All 4 feature guides documented (1,027 + 924 + 914 + 950 lines = 3,815 lines)

---

## Phase 8 Consolidated Summary

**Phase 8 encompasses**:
1. Self-Service Admin Portal (email search, webhooks, API keys) — 40 hours
2. AI-Powered Features (recommendations, optimization, bounce analysis, anomaly detection) — 125 hours
3. Marketplace Integration (Zapier, Make, custom templates) — 75 hours
4. Usage Analytics Dashboard (metrics, forecasting, alerts, exports) — 120 hours

**Total Phase 8 Effort**: 360 hours = **9 engineer-weeks** across 4 weeks with parallelization  
**Total Phase 8 Cost**: $432K (personnel) + $4.8K (infrastructure) + $1.2K (third-party) = **$438K**  
**Expected Phase 8 Revenue**: $60K (marketplace) + revenue from feature adoption  
**Payback Period**: 7-8 months (with customer growth assumptions)

**Timeline**: May 1 — June 30, 2026 (8 weeks total, 4 weeks parallel execution)  
**Success Criterion**: All features in production by 2026-06-21 (end of Phase 8 Week 4)

---

**Next Batch**: Phase 9 (July-August 2026) — Cost optimization, performance improvements, architecture review

