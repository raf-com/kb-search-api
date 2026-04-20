# Phase 8, Step 2: AI-Powered Features Implementation Guide
**Version**: 1.0  
**Date**: 2026-04-20  
**Feature Lead**: ML engineer + backend engineer  
**Timeline**: May 1-24, 2026 (4 weeks, parallel with Step 1)  
**Effort**: 125 hours (3.1 engineer weeks across 2 engineers)

---

## Executive Summary

AI-powered features reduce configuration friction and improve email deliverability. Four capabilities:
1. **Smart Template Recommendations** — Analyze customer's email history, suggest best-performing templates
2. **Email Optimization Assistant** — Spam score analysis, subject line improvements, send time optimization
3. **Bounce Reason Analysis** — Auto-categorize bounces, generate suppression lists
4. **Anomaly Detection** — Monitor metrics, alert on deviations from baseline

**Expected Impact**: 
- Customer feature adoption >40% by end of May
- Bounce rate reduction >5%
- Email optimization suggestions implemented >30% of the time

---

## Architecture Overview

**Data Flow**:
```
Customer Email → Event Stream → SageMaker Endpoint (batch) → 
  Feature Store (Redis) → API Response → UI Recommendation
```

**Components**:
- **LLM Provider**: OpenAI GPT 3.5 ($500/month for SaaS volume)
- **Batch Processing**: SageMaker endpoint for inference
- **Feature Store**: Redis for caching recommendations (24h TTL)
- **API**: New `/api/v1/ai-recommendations` endpoints
- **UI**: Integration with template editor

**Cost**: $500/month OpenAI API + $300/month SageMaker = $800/month

---

## Feature 1: Smart Template Recommendations

### 1.1 Recommendation Algorithm

**Data Preparation**:
1. Collect customer's last 100 emails (sender, subject, body, open rate, click rate)
2. Normalize metrics: (value - min) / (max - min)
3. Create feature vector for each email: [open_rate, click_rate, bounce_rate, delivery_speed]

**Recommendation Engine**:
1. Cluster emails by performance: high-performers (>50th percentile), low-performers (<25th)
2. For each new template draft:
   - Analyze subject line similarity to high-performers
   - Suggest personalization fields based on high-performer content
   - Predict open rate based on subject line embedding similarity
3. Return top 3 recommendations with confidence scores

### 1.2 Database Schema

```sql
CREATE TABLE ai_recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  template_id UUID REFERENCES email_templates(id),
  recommendation_type ENUM('subject_line', 'personalization', 'send_time', 'content'),
  recommendation_text TEXT NOT NULL,
  confidence_score DECIMAL(3,2), -- 0.00 to 1.00
  reasoning JSONB, -- explain why (e.g., "Similar to template_xyz which had 45% open rate")
  was_applied BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT now(),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX CONCURRENTLY idx_recommendations_tenant_template 
  ON ai_recommendations(tenant_id, template_id, created_at DESC);

-- Store fine-tuning data for model improvement
CREATE TABLE ai_training_signals (
  id UUID PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id),
  email_id UUID REFERENCES emails(id),
  template_id UUID REFERENCES email_templates(id),
  subject_line TEXT,
  recipient_segment VARCHAR(100), -- e.g., "new_customer", "high_value"
  open_rate DECIMAL(5,4),
  click_rate DECIMAL(5,4),
  bounce_rate DECIMAL(5,4),
  created_at TIMESTAMP DEFAULT now()
);
```

### 1.3 API Endpoint: Get Recommendations

**POST /api/v1/templates/{id}/ai-recommendations**

```php
namespace App\Http\Controllers;

use OpenAI\Laravel\Facades\OpenAI;
use Illuminate\Support\Facades\Cache;

class AiRecommendationController extends Controller {
  
  public function getRecommendations(Request $request, $templateId) {
    $template = EmailTemplate::where('id', $templateId)
      ->where('tenant_id', Auth::user()->tenant_id)
      ->firstOrFail();

    // Check cache first (24-hour TTL)
    $cacheKey = "ai_recommendations:{$templateId}";
    if (Cache::has($cacheKey)) {
      return response()->json(Cache::get($cacheKey));
    }

    // Fetch customer's recent email performance
    $emailMetrics = $this->getCustomerEmailMetrics(Auth::user()->tenant_id);

    // Call OpenAI for recommendations
    $prompt = $this->buildPrompt($template, $emailMetrics);
    $response = OpenAI::chat()->create([
      'model' => 'gpt-3.5-turbo',
      'temperature' => 0.7,
      'max_tokens' => 500,
      'messages' => [
        [
          'role' => 'system',
          'content' => 'You are an email marketing expert. Analyze this template and suggest improvements based on the customer\'s email performance data.'
        ],
        ['role' => 'user', 'content' => $prompt]
      ]
    ]);

    // Parse OpenAI response
    $recommendations = $this->parseRecommendations($response->choices[0]->message->content);

    // Store recommendations in database
    foreach ($recommendations as $rec) {
      AiRecommendation::create([
        'tenant_id' => Auth::user()->tenant_id,
        'template_id' => $templateId,
        'recommendation_type' => $rec['type'],
        'recommendation_text' => $rec['text'],
        'confidence_score' => $rec['confidence'] ?? 0.75,
        'reasoning' => $rec['reasoning'] ?? []
      ]);
    }

    // Cache for 24 hours
    $result = [
      'template_id' => $templateId,
      'recommendations' => $recommendations,
      'timestamp' => now()
    ];

    Cache::put($cacheKey, $result, now()->addHours(24));

    return response()->json($result);
  }

  private function buildPrompt($template, $emailMetrics): string {
    return <<<PROMPT
Analyze this email template and suggest improvements:

Template Subject: {$template->subject}
Template Body (first 200 chars): {$template->body}

Customer's email performance (last 100 emails):
- Average open rate: {$emailMetrics['avg_open_rate']}%
- Average click rate: {$emailMetrics['avg_click_rate']}%
- Best performing subject keywords: {$emailMetrics['best_keywords']}
- Common personalization fields: {$emailMetrics['common_fields']}

Suggest 3 specific improvements as JSON array with format:
[
  {
    "type": "subject_line" | "personalization" | "content",
    "text": "Specific suggestion",
    "confidence": 0.0-1.0,
    "reasoning": "Why this would improve performance"
  }
]

Only output the JSON array, no other text.
PROMPT;
  }

  private function parseRecommendations($content): array {
    try {
      return json_decode($content, true);
    } catch (Exception $e) {
      return []; // Fallback: no recommendations on parse error
    }
  }

  private function getCustomerEmailMetrics($tenantId): array {
    // Query last 100 delivered emails
    $emails = Email::where('tenant_id', $tenantId)
      ->where('status', 'delivered')
      ->orderBy('created_at', 'desc')
      ->limit(100)
      ->get();

    if ($emails->isEmpty()) {
      return [
        'avg_open_rate' => 0,
        'avg_click_rate' => 0,
        'best_keywords' => 'subject line keywords',
        'common_fields' => 'name, email, account_type'
      ];
    }

    return [
      'avg_open_rate' => $emails->avg('open_rate') * 100,
      'avg_click_rate' => $emails->avg('click_rate') * 100,
      'best_keywords' => implode(', ', $this->extractKeywords($emails)),
      'common_fields' => implode(', ', $this->extractFields($emails))
    ];
  }

  private function extractKeywords($emails): array {
    // Extract top 5 subject line words from high-open-rate emails
    $topEmails = $emails->where('open_rate', '>', 0.3); // 30%+ open rate
    $words = [];
    foreach ($topEmails as $email) {
      preg_match_all('/\b\w{4,}\b/', $email->subject, $matches);
      $words = array_merge($words, $matches[0]);
    }
    return array_slice(array_count_values($words), 0, 5, true);
  }

  private function extractFields($emails): array {
    // Find personalization patterns in email bodies
    $patterns = [
      'name' => '/\{\{.*?name.*?\}\}|\%\(.*?name.*?\)s/',
      'email' => '/\{\{.*?email.*?\}\}/',
      'account_type' => '/\{\{.*?account.*?\}\}/',
      'company' => '/\{\{.*?company.*?\}\}/'
    ];

    $found = [];
    foreach ($emails as $email) {
      foreach ($patterns as $key => $pattern) {
        if (preg_match($pattern, $email->body)) {
          $found[] = $key;
        }
      }
    }
    return array_unique($found);
  }
}
```

### 1.4 Frontend: Recommendation Panel (React)

```tsx
export const AiRecommendationsPanel: React.FC<{ templateId: string }> = ({ templateId }) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  const { data } = useQuery(
    ['ai-recommendations', templateId],
    () => api.post(`/templates/${templateId}/ai-recommendations`),
    { staleTime: 24 * 60 * 60 * 1000 } // 24-hour cache
  );

  useEffect(() => {
    if (data) {
      setRecommendations(data.recommendations);
      setLoading(false);
    }
  }, [data]);

  const handleApplyRecommation = async (rec: Recommendation) => {
    // Apply recommendation to template
    const updatedSubject = rec.type === 'subject_line' ? rec.text : undefined;
    await api.patch(`/templates/${templateId}`, { subject: updatedSubject });

    // Mark as applied in backend
    await api.post(`/ai-recommendations/${rec.id}/apply`);
  };

  return (
    <div className="ai-recommendations-panel">
      <h3>AI Suggestions for this template</h3>
      {loading ? (
        <div>Analyzing your email history...</div>
      ) : recommendations.length === 0 ? (
        <div className="empty-state">No suggestions available yet. Send more emails to get recommendations.</div>
      ) : (
        <div className="recommendations-list">
          {recommendations.map((rec) => (
            <div key={rec.id} className="recommendation-card">
              <div className="header">
                <Badge type={rec.type}>{rec.type}</Badge>
                <span className="confidence">
                  {(rec.confidence_score * 100).toFixed(0)}% likely to improve performance
                </span>
              </div>

              <p className="suggestion">{rec.recommendation_text}</p>

              <p className="reasoning">💡 {rec.reasoning}</p>

              <Button 
                size="sm"
                onClick={() => handleApplyRecommation(rec)}
              >
                Apply Suggestion
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

### 1.5 Implementation Timeline

**Week 1**: LLM setup, prompt engineering, API integration (30 hours)
**Week 2**: Database schema, caching layer (15 hours)
**Week 3**: Frontend panel, recommendation display (20 hours)
**Week 4**: Fine-tuning, accuracy improvement, testing (15 hours)

**Total**: 80 hours

---

## Feature 2: Email Optimization Assistant

### 2.1 Components

**Spam Score Analysis** (using SpamAssassin):
```php
class SpamScoreAnalyzer {
  public function analyze($email): array {
    $spamScore = SpamAssassin::check($email->subject, $email->body);
    
    return [
      'score' => $spamScore['score'],
      'risk_level' => $spamScore['score'] > 5 ? 'high' : 'low',
      'triggers' => $spamScore['matched_rules'], // e.g., 'ALL_CAPS', 'PHISHING_LINK'
      'suggestions' => $this->generateSuggestions($spamScore)
    ];
  }

  private function generateSuggestions($spamScore): array {
    $suggestions = [];
    
    foreach ($spamScore['matched_rules'] as $rule) {
      switch ($rule) {
        case 'ALL_CAPS':
          $suggestions[] = 'Use mixed case instead of ALL CAPS (reduces spam score by ~0.5)';
          break;
        case 'PHISHING_LINK':
          $suggestions[] = 'Avoid suspicious link patterns; use clear anchor text';
          break;
        case 'EXCESSIVE_EXCLAMATION':
          $suggestions[] = 'Reduce exclamation marks (use max 2-3 per email)';
          break;
      }
    }
    
    return $suggestions;
  }
}
```

**Send Time Optimization**:
```php
class SendTimeOptimizer {
  public function recommendSendTime($tenantId, $recipientSegment): string {
    // Analyze recipient's timezone + engagement patterns
    $topOpenHours = Email::where('tenant_id', $tenantId)
      ->where('recipient_segment', $recipientSegment)
      ->where('status', 'delivered')
      ->selectRaw('EXTRACT(HOUR FROM open_at) as hour, COUNT(*) as count')
      ->groupBy('hour')
      ->orderBy('count', 'desc')
      ->limit(3)
      ->get();

    // Recommend top opening hour in recipient's timezone
    if ($topOpenHours->isNotEmpty()) {
      return $topOpenHours[0]->hour . ':00'; // e.g., '09:00'
    }

    return '09:00'; // Default: 9 AM
  }
}
```

### 2.2 API Endpoint

**POST /api/v1/emails/optimize**

```php
public function optimize(Request $request) {
  $validated = $request->validate([
    'subject' => 'required|string',
    'body' => 'required|string',
    'recipient_segment' => 'string' // e.g., 'free_tier', 'enterprise'
  ]);

  $spamAnalysis = SpamScoreAnalyzer::analyze($validated);
  $sendTime = SendTimeOptimizer::recommendSendTime(
    Auth::user()->tenant_id,
    $validated['recipient_segment']
  );

  return response()->json([
    'spam_analysis' => $spamAnalysis,
    'recommended_send_time' => $sendTime,
    'compliance_checks' => [
      'has_unsubscribe_link' => str_contains($validated['body'], 'unsubscribe'),
      'has_contact_info' => str_contains($validated['body'], '@') || str_contains($validated['body'], 'address'),
      'gdpr_compliant' => true // Assume yes unless specific violations found
    ]
  ]);
}
```

### 2.3 Implementation Timeline

**Week 1**: SpamAssassin integration, API endpoint (20 hours)
**Week 2**: Send time optimization algorithm (15 hours)
**Week 3**: Frontend optimization UI (15 hours)
**Week 4**: Testing, validation (10 hours)

**Total**: 60 hours

---

## Feature 3: Bounce Reason Analysis

### 3.1 Bounce Classifier

**Algorithm**: Map Mailgun bounce codes → business actions

```php
class BounceAnalyzer {
  private $bounceCategories = [
    'permanent' => ['fail: Bad destination mailbox address', '550 5.1.1', '452'],
    'temporary' => ['timeout', '421', '451'],
    'complaint' => ['complaint', 'spam']
  ];

  public function classify($mailgunEvent): array {
    $bounceCode = $mailgunEvent['code'] ?? '';
    $bounceDescription = $mailgunEvent['description'] ?? '';

    $category = $this->categorize($bounceCode, $bounceDescription);

    return [
      'category' => $category,
      'recipient' => $mailgunEvent['recipient'],
      'reason' => $this->getReason($bounceCode),
      'action' => $this->getAction($category)
    ];
  }

  private function categorize($code, $description): string {
    foreach ($this->bounceCategories as $category => $patterns) {
      foreach ($patterns as $pattern) {
        if (str_contains($code, $pattern) || str_contains($description, $pattern)) {
          return $category;
        }
      }
    }
    return 'unknown';
  }

  private function getAction($category): string {
    return match($category) {
      'permanent' => 'Remove from mailing list (invalid email)',
      'temporary' => 'Retry in 24 hours',
      'complaint' => 'Add to suppression list, review email content',
      default => 'Monitor'
    };
  }
}
```

### 3.2 Auto-Suppress Feature

**Auto-Suppression Rules**:
```php
class AutoSuppressionJob {
  public function handle() {
    // Collect permanent bounces from last 7 days
    $permanentBounces = WebhookEvent::where('event_type', 'email.bounced')
      ->where('bounce_category', 'permanent')
      ->where('created_at', '>=', now()->subDays(7))
      ->pluck('recipient')
      ->unique();

    // Add to suppression list
    SuppressionList::whereIn('email', $permanentBounces)
      ->where('reason', null)
      ->update(['reason' => 'permanent_bounce']);

    // Track metrics
    Metric::record('suppression.permanent_bounces', $permanentBounces->count());
  }
}
```

### 3.3 Implementation Timeline

**Week 1**: Bounce classifier, Mailgun webhook integration (20 hours)
**Week 2**: Auto-suppression logic, suppression list management (15 hours)
**Week 3**: Re-engagement campaign recommendations (15 hours)
**Week 4**: Testing, validation (10 hours)

**Total**: 60 hours

---

## Feature 4: Anomaly Detection in Metrics

### 4.1 Anomaly Detection Algorithm (Z-Score)

```python
# Python service running in Lambda
import numpy as np
from datetime import datetime, timedelta

class AnomalyDetector:
  def __init__(self, threshold=2.0):
    self.threshold = threshold  # 2 std deviations = ~95% confidence
  
  def detect_anomalies(self, metric_name: str, tenant_id: str):
    # Fetch metric history (last 30 days)
    metrics = self.fetch_metrics(tenant_id, metric_name, days=30)
    
    if len(metrics) < 5:
      return None  # Not enough data
    
    values = [m['value'] for m in metrics]
    mean = np.mean(values)
    std_dev = np.std(values)
    
    # Check if today's value is an outlier
    today_value = values[-1]
    z_score = (today_value - mean) / std_dev if std_dev > 0 else 0
    
    is_anomaly = abs(z_score) > self.threshold
    
    return {
      'metric': metric_name,
      'current_value': today_value,
      'expected_range': [mean - (2 * std_dev), mean + (2 * std_dev)],
      'z_score': z_score,
      'is_anomaly': is_anomaly,
      'severity': 'high' if abs(z_score) > 3 else 'medium' if is_anomaly else 'low'
    }

  def fetch_metrics(self, tenant_id: str, metric_name: str, days: int):
    # Query Prometheus
    query = f'rate({metric_name}{{tenant_id="{tenant_id}"}}[1d])'
    results = prometheus_client.query_range(query, days=days)
    return results
```

### 4.2 Anomaly Alert Workflow

```php
class AnomalyDetectionJob {
  public function handle() {
    $tenantIds = Tenant::pluck('id');
    
    foreach ($tenantIds as $tenantId) {
      $anomalies = PythonService::detectAnomalies($tenantId);
      
      foreach ($anomalies as $anomaly) {
        if ($anomaly['is_anomaly']) {
          Notification::send(
            User::where('tenant_id', $tenantId)->get(),
            new AnomalyDetectedNotification($anomaly)
          );

          // Store in database for dashboard
          AnomalyAlert::create([
            'tenant_id' => $tenantId,
            'metric' => $anomaly['metric'],
            'current_value' => $anomaly['current_value'],
            'z_score' => $anomaly['z_score'],
            'severity' => $anomaly['severity']
          ]);
        }
      }
    }
  }
}

// Schedule: Run daily at 9 AM
$schedule->job(new AnomalyDetectionJob)
  ->dailyAt('09:00');
```

### 4.3 Dashboard Display

```tsx
export const AnomalyAlertsDashboard: React.FC = () => {
  const { data: anomalies } = useQuery(
    ['anomalies'],
    () => api.get('/anomalies/alerts?days=7'),
    { refetchInterval: 3600000 } // Refresh hourly
  );

  return (
    <div className="anomaly-alerts">
      <h2>Performance Anomalies (Last 7 Days)</h2>

      {anomalies?.map((alert) => (
        <div key={alert.id} className={`alert alert-${alert.severity}`}>
          <h4>{alert.metric}</h4>
          <p>Current: {alert.current_value.toFixed(2)} | Z-Score: {alert.z_score.toFixed(2)}</p>
          <p className="severity">Severity: {alert.severity}</p>
          <Button>View Details</Button>
        </div>
      ))}
    </div>
  );
};
```

### 4.4 Implementation Timeline

**Week 1**: Z-score algorithm, Prometheus integration (20 hours)
**Week 2**: Alert system, notification delivery (15 hours)
**Week 3**: Frontend dashboard (15 hours)
**Week 4**: Testing, threshold tuning (10 hours)

**Total**: 60 hours

---

## Phase 8, Step 2 Summary

| Feature | Effort (hrs) | Risk | Dependencies |
|---------|-------------|------|--------------|
| Smart Recommendations | 80 | Medium (LLM accuracy) | OpenAI API account |
| Optimization Assistant | 60 | Low | SpamAssassin binary |
| Bounce Analysis | 60 | Low | Mailgun webhook |
| Anomaly Detection | 60 | Medium (threshold tuning) | Prometheus metrics |
| **TOTAL** | **260** | — | — |

**Actual Effort**: 260 hours = **6.5 engineer weeks**  
**Allocated**: 3.1 weeks (overlap with self-service portal)  
**Recommendation**: 2 engineers working in parallel (1 ML, 1 backend)

---

## Success Metrics

| Metric | Target | Measurement | Timeline |
|--------|--------|-------------|----------|
| AI recommendation adoption | >40% of templates | Template editor analytics | 2026-05-24 |
| Bounce rate reduction | 5% improvement | Compare May vs April metrics | 2026-06-15 |
| Optimization suggestions applied | >30% | Track apply clicks | 2026-05-24 |
| Anomaly detection accuracy | >90% | Manual review of 100 alerts | 2026-06-30 |

---

## Cost Breakdown

**OpenAI API**: $0.0005 per recommendation × 1M/month = $500/month  
**SageMaker Endpoint**: $0.29/hour × 24h/day × 30 days = $209/month  
**Lambda (Python anomaly detection)**: ~$50/month  
**Prometheus/storage**: ~$50/month  

**Total AI Infrastructure**: $809/month

---

**Document Created**: 2026-04-20  
**Status**: Ready for Phase 8 Week 1 execution  
**Next**: Phase 8, Step 3 (Marketplace Integration)
