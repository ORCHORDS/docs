# Platform Health Score Dashboard: Aggregating Moderation Metrics with Analytics Engine

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

example project's Trust & Safety team needs a single real-time view of platform health: appeal rates, active takedowns, CIB cluster growth, shadow-ban churn, spam detection accuracy, and content removal latency. These signals are scattered across D1 tables, Workers logs, and Queue depths. Without a unified dashboard, deteriorating health goes undetected until user complaints spike.

---

## Context

Cloudflare Analytics Engine (AE) is a time-series write API built into Workers. Each Worker can write data points (called "data blobs") at up to 25 writes per invocation. AE stores them in a columnar format queryable via the Workers Analytics API (SQL-like syntax) or the Cloudflare GraphQL Analytics API. It is purpose-built for high-cardinality, high-frequency event streams — exactly what moderation pipelines produce.

The architecture:
1. **Instrumentation layer** — Workers throughout the platform write moderation events to AE.
2. **Query layer** — a dashboard Worker aggregates AE data via the Analytics API and serves JSON to the dashboard.
3. **Visualization layer** — a static HTML artifact renders the JSON as real-time charts.
4. **Alerting layer** — a Scheduled Worker evaluates thresholds and posts to Slack/PagerDuty.

---

## Section 1: Analytics Engine Dataset Design

AE datasets use a schema-less blob format. Define a consistent structure in a shared type so all Workers agree on field names.

```typescript
// src/analytics/moderation-events.ts

/**
 * Moderation event written to Analytics Engine.
 * All numeric fields map to AE's double1..double20.
 * All string fields map to AE's blob1..blob20.
 */
export interface ModerationEvent {
  // Blobs (string dimensions)
  eventType:    string; // SHADOW_BAN | TAKEDOWN | CIB_CLUSTER | APPEAL | SPAM_HIT | FALSE_POSITIVE
  reasonCode:   string; // SPAM | CIB | CSAM_ADJACENT | ABUSE | DMCA | OTHER
  actorType:    string; // SYSTEM | MODERATOR | USER_REPORT
  region:       string; // Cloudflare colo region (e.g. "eu", "us-east")
  severity:     string; // LOW | MEDIUM | HIGH | CRITICAL

  // Doubles (numeric measures)
  itemCount:    number; // number of items affected
  latencyMs:    number; // time from report to action (ms)
  confidence:   number; // 0.0–1.0 for automated decisions
  appealCount:  number; // cumulative appeals at time of write
}

export function writeModerationEvent(
  env: { MODERATION_AE: AnalyticsEngineDataset },
  event: ModerationEvent
): void {
  // AE writeDataPoint is fire-and-forget; no await needed
  env.MODERATION_AE.writeDataPoint({
    blobs:   [
      event.eventType,
      event.reasonCode,
      event.actorType,
      event.region,
      event.severity,
    ],
    doubles: [
      event.itemCount,
      event.latencyMs,
      event.confidence,
      event.appealCount,
    ],
    indexes: [event.eventType], // primary index for faster event-type scans
  });
}
```

---

## Section 2: Instrumentation in Existing Workers

Drop the write call into existing enforcement paths with minimal code change.

```typescript
// src/moderation/shadow-ban.ts  (updated excerpt)
import { writeModerationEvent } from '../analytics/moderation-events';

export async function applyShadowBan(env: Env, opts: ShadowBanOptions): Promise<void> {
  // ... existing D1 write ...

  writeModerationEvent(env, {
    eventType:   'SHADOW_BAN',
    reasonCode:  opts.reasonCode,
    actorType:   opts.appliedBy.startsWith('system') ? 'SYSTEM' : 'MODERATOR',
    region:      env.CF_REGION ?? 'unknown',
    severity:    opts.visibility === 'removed' ? 'HIGH' : 'MEDIUM',
    itemCount:   1,
    latencyMs:   0,          // detection-to-action latency tracked separately
    confidence:  0,
    appealCount: 0,
  });
}

// src/workers/takedown-consumer.ts  (updated excerpt)
async function processItems(env: Env, jobId: string, items: Array<{ id: string; type: string }>): Promise<void> {
  const start = Date.now();
  // ... existing removal logic ...
  const latencyMs = Date.now() - start;

  writeModerationEvent(env, {
    eventType:   'TAKEDOWN',
    reasonCode:  'OTHER',
    actorType:   'SYSTEM',
    region:      env.CF_REGION ?? 'unknown',
    severity:    'HIGH',
    itemCount:   items.length,
    latencyMs,
    confidence:  1.0,
    appealCount: 0,
  });
}
```

---

## Section 3: Analytics Engine Query Worker

The dashboard backend queries AE via the Cloudflare Analytics API (REST endpoint authenticated with an API token).

```typescript
// src/workers/health-dashboard-api.ts
import type { Env } from '../types';

const AE_API = 'https://api.cloudflare.com/client/v4/accounts';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/health-scores') {
      const scores = await aggregateHealthScores(env);
      return Response.json(scores, {
        headers: { 'Cache-Control': 's-maxage=60' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function aggregateHealthScores(env: Env): Promise<Record<string, unknown>> {
  const since = new Date(Date.now() - 86_400_000).toISOString(); // last 24h

  const query = `
    SELECT
      blob1                                         AS event_type,
      COUNT()                                       AS total_events,
      SUM(double1)                                  AS total_items,
      AVG(double2)                                  AS avg_latency_ms,
      AVG(double3)                                  AS avg_confidence,
      SUM(CASE WHEN blob2 = 'FALSE_POSITIVE' THEN 1 ELSE 0 END) AS false_positives
    FROM example project_MODERATION
    WHERE timestamp > toDateTime('${since}')
    GROUP BY blob1
    ORDER BY total_events DESC
  `;

  const resp = await fetch(
    `${AE_API}/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method:  'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type':  'application/json',
      },
      body: JSON.stringify({ query }),
    }
  );

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Analytics Engine query failed: ${resp.status} ${text}`);
  }

  const { data } = await resp.json<{ data: Record<string, unknown>[] }>();

  return {
    generatedAt:    new Date().toISOString(),
    windowHours:    24,
    byEventType:    data,
    healthScore:    computeHealthScore(data),
  };
}

function computeHealthScore(rows: Record<string, unknown>[]): number {
  // Composite score 0–100. Deduct points for:
  // - High false positive rate
  // - High average latency
  // - Large appeal volume
  let score = 100;

  for (const row of rows) {
    const fp      = Number(row['false_positives'] ?? 0);
    const total   = Number(row['total_events']    ?? 1);
    const latency = Number(row['avg_latency_ms']  ?? 0);

    const fpRate = fp / total;
    if (fpRate > 0.05) score -= 10;       // > 5% FP rate
    if (fpRate > 0.15) score -= 20;       // > 15% FP rate

    if (latency > 5_000)  score -= 5;     // > 5s avg latency
    if (latency > 30_000) score -= 15;    // > 30s avg latency
  }

  return Math.max(0, score);
}
```

---

## Section 4: Scheduled Alerting Worker

```typescript
// src/workers/health-alert.ts  — scheduled cron: "*/15 * * * *"
import type { Env } from '../types';

const ALERT_THRESHOLD = 70; // score below this triggers a page

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const resp  = await fetch('https://api.example.com/api/health-scores', {
      headers: { Authorization: `Bearer ${env.INTERNAL_API_TOKEN}` },
    });
    const data  = await resp.json<{ healthScore: number }>();
    const score = data.healthScore;

    if (score < ALERT_THRESHOLD) {
      await sendSlackAlert(env, score);
    }
  },
};

async function sendSlackAlert(env: Env, score: number): Promise<void> {
  await fetch(env.SLACK_WEBHOOK_URL, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      text: `:warning: example project Platform Health Score: *${score}/100* — below threshold ${ALERT_THRESHOLD}. Review moderation dashboard immediately.`,
    }),
  });
}
```

---

## Section 5: KPI Definitions and Thresholds

| KPI | Formula | Green | Yellow | Red |
|-----|---------|-------|--------|-----|
| False Positive Rate | FP / (FP + TP) | < 5% | 5–15% | > 15% |
| Median Action Latency | P50 of `latencyMs` | < 2s | 2–10s | > 10s |
| Appeal Rate | Appeals / Total Actions | < 3% | 3–8% | > 8% |
| CIB Cluster Growth | New clusters / 24h | < 5 | 5–20 | > 20 |
| Shadow Ban Churn | Lifts / Active Bans / day | < 10% | 10–25% | > 25% |
| Takedown Completion | Removed / Queued | > 95% | 80–95% | < 80% |

---

## Section 6: Dashboard Artifact Query Examples

Additional AE SQL patterns for the live dashboard panels:

```sql
-- Hourly action volume (last 7 days)
SELECT
  toStartOfHour(timestamp) AS hour,
  blob1                    AS event_type,
  COUNT()                  AS actions
FROM example project_MODERATION
WHERE timestamp > now() - INTERVAL '7' DAY
GROUP BY hour, event_type
ORDER BY hour DESC;

-- Regional distribution of enforcement actions
SELECT
  blob4       AS region,
  COUNT()     AS actions,
  AVG(double3) AS avg_confidence
FROM example project_MODERATION
WHERE timestamp > now() - INTERVAL '24' HOUR
GROUP BY region
ORDER BY actions DESC;

-- Latency percentiles by reason code
SELECT
  blob2                          AS reason_code,
  quantile(0.5)(double2)        AS p50_ms,
  quantile(0.95)(double2)       AS p95_ms,
  quantile(0.99)(double2)       AS p99_ms
FROM example project_MODERATION
WHERE timestamp > now() - INTERVAL '24' HOUR
GROUP BY reason_code;
```

---

## Anti-patterns

- **Querying D1 aggregates for the dashboard** — D1 is an OLTP store; GROUP BY across millions of rows in a request path will timeout and starve normal traffic. AE is the right store for aggregates.
- **Writing AE events synchronously with `await`** — `writeDataPoint` is a fire-and-forget API; awaiting it wastes CPU time in the Worker.
- **A single health score number without breakdowns** — a composite score hides which dimension is degrading. Always surface per-event-type and per-region sub-scores.
- **Hardcoding the 24h window in the query** — make window size a query parameter so the dashboard can show hourly, daily, and weekly views without code changes.
- **Storing PII in AE blobs** — AE data is retained for 90 days and queryable by anyone with an API token; never include account IDs, email addresses, or IP addresses in event blobs.

---

## Gotchas

- AE is eventually consistent. Data written now may not appear in queries for up to 60 seconds. Do not use AE for real-time circuit breaker decisions; use KV for that.
- AE `writeDataPoint` silently drops events if the dataset does not exist. Create the dataset in the Cloudflare dashboard under **Workers → Analytics Engine** before deploying the instrumentation.
- AE SQL uses ClickHouse-compatible syntax, not standard ANSI SQL. `COUNT()` (no argument) instead of `COUNT(*)`, `quantile(0.95)(col)` instead of `PERCENTILE_CONT(0.95)`.
- The Workers Analytics Engine binding must be declared in `wrangler.toml`:
  ```toml
  [[analytics_engine_datasets]]
  binding = "MODERATION_AE"
  dataset = "example project_MODERATION"
  ```
- AE has a soft limit of 25 `writeDataPoint` calls per Worker invocation. Batch high-volume events where possible.

---

## Verification

```bash
# 1. Trigger a few moderation events manually, then query AE
wrangler tail --name secure-submit --format json | jq '.logs'

# 2. Query AE directly to confirm events arrived
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT blob1, COUNT() AS n FROM example project_MODERATION WHERE timestamp > now() - INTERVAL 1 HOUR GROUP BY blob1"}' \
  | jq .

# 3. Load the dashboard and confirm health score renders
curl https://api.example.com/api/health-scores | jq .healthScore

# 4. Manually drop the score below threshold and confirm Slack alert fires
# (Temporarily override computeHealthScore to return 50 in staging)
```

---

## Related

- `dora-metrics.md`
- `observability-vs-monitoring.md`
- `alert-fatigue-management.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `shadow-banning-reach-limiting-d1-workers.md`

---

## Sources

- Cloudflare Analytics Engine documentation — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- ClickHouse SQL reference — https://clickhouse.com/docs/en/sql-reference/
- DORA Metrics (Accelerate) — https://dora.dev/
- DSA Article 15 (Transparency Reporting) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
