# Anomaly Detection on Analytics Engine Time-Series Using Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Static threshold alerts on error rate miss gradual degradations and fire false positives during expected traffic surges. By running inference on a Workers AI model co-located on the Cloudflare network, a scheduled Worker can score each route's current metrics against its own learned baseline and raise alerts only when the deviation is statistically unusual — without any external ML infrastructure.

## Context

Workers AI exposes a `run()` method that executes Cloudflare-hosted models inside the same isolate runtime as the Worker. For anomaly detection on univariate time-series the `@cf/huggingface/distilbert-sst-2-int8` model is not the right fit; instead the approach uses the `@cf/mistral/mistral-7b-instruct-v0.1` model in a structured-output pattern where the prompt supplies a 24-bucket hourly time-series as a JSON array and asks the model to return an anomaly score between 0 and 1 with a one-line reason. For latency-sensitive paths, a simpler statistical z-score baseline computed from Analytics Engine data is calculated first; Workers AI is invoked only when the z-score crosses a soft threshold, keeping inference calls rare and token costs low.

## Analytics Engine — Fetch Hourly Buckets

```typescript
// lib/fetch-hourly-buckets.ts
export interface HourlyBucket {
  hour: string;
  requests: number;
  error_rate: number;
  p99_ms: number;
}

export async function fetchHourlyBuckets(
  accountId: string,
  apiToken: string,
  route: string,
  lookbackHours = 48,
): Promise<HourlyBucket[]> {
  const sql = `
    SELECT
      formatDateTime(toStartOfInterval(timestamp, INTERVAL '1' HOUR), '%Y-%m-%dT%H:00:00Z') AS hour,
      count()                                            AS requests,
      countIf(double2 >= 500) / count()                 AS error_rate,
      quantileWeighted(0.99)(double1, 1)                AS p99_ms
    FROM worker_requests
    WHERE timestamp >= now() - INTERVAL '${lookbackHours}' HOUR
      AND blob1 = '${route.replace(/'/g, "''")}'
    GROUP BY hour
    ORDER BY hour ASC
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: sql }),
    },
  );

  if (!res.ok) throw new Error(`AE error: ${await res.text()}`);
  const json = await res.json() as { data: HourlyBucket[] };
  return json.data;
}
```

## Z-Score Pre-Filter

```typescript
// lib/z-score.ts
export interface ZScoreResult {
  metric: "error_rate" | "p99_ms";
  current: number;
  mean: number;
  stddev: number;
  z: number;
  soft_anomaly: boolean;
}

export function zScoreCheck(
  buckets: { error_rate: number; p99_ms: number }[],
  metric: "error_rate" | "p99_ms",
  softThreshold = 2.5,
): ZScoreResult {
  // Use the first N-1 buckets as the training window; the last bucket is the current value
  const historical = buckets.slice(0, -1).map((b) => b[metric]);
  const current = buckets[buckets.length - 1][metric];

  const mean = historical.reduce((s, v) => s + v, 0) / historical.length;
  const variance = historical.reduce((s, v) => s + (v - mean) ** 2, 0) / historical.length;
  const stddev = Math.sqrt(variance);
  const z = stddev === 0 ? 0 : (current - mean) / stddev;

  return { metric, current, mean, stddev, z, soft_anomaly: Math.abs(z) >= softThreshold };
}
```

## Workers AI Structured Scoring

```typescript
// lib/ai-anomaly-scorer.ts
export interface Env {
  AI: Ai;
}

export interface AnomalyReport {
  route: string;
  score: number;   // 0 = normal, 1 = certain anomaly
  reason: string;
  metric: string;
  current_value: number;
}

export async function scoreWithAI(
  ai: Ai,
  route: string,
  metric: string,
  buckets: { hour: string; value: number }[],
  currentValue: number,
): Promise<AnomalyReport> {
  const seriesJson = JSON.stringify(buckets.map((b) => ({ t: b.hour, v: +b.value.toFixed(3) })));

  const prompt = `You are an observability expert. Given a time-series of hourly ${metric} values
for the HTTP route "${route}", determine whether the most recent value is anomalous.

Historical series (oldest to newest):
${seriesJson}

Current value (the point under evaluation): ${currentValue.toFixed(3)}

Respond with ONLY valid JSON in this exact shape:
{"score": <float 0.0-1.0>, "reason": "<one sentence, max 120 chars>"}

score 0.0 = perfectly normal, 1.0 = severe anomaly. Consider seasonality and trends.`;

  const response = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [{ role: "user", content: prompt }],
    max_tokens: 80,
    temperature: 0.1,
  });

  // The model returns text; parse the first JSON object from it
  const match = (response as { response: string }).response.match(/\{[\s\S]*?\}/);
  if (!match) throw new Error("AI response did not contain JSON");

  const parsed = JSON.parse(match[0]) as { score: number; reason: string };
  return { route, score: parsed.score, reason: parsed.reason, metric, current_value: currentValue };
}
```

## Scheduled Worker — Orchestration

```typescript
// workers/anomaly-detector/index.ts
import { fetchHourlyBuckets } from "../../lib/fetch-hourly-buckets.js";
import { zScoreCheck } from "../../lib/z-score.js";
import { scoreWithAI } from "../../lib/ai-anomaly-scorer.js";

export interface Env {
  AI: Ai;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  PAGERDUTY_KEY: string;
}

const ROUTES_TO_MONITOR = ["/api/v1/products", "/api/v1/search", "/api/v1/checkout"];
const AI_SCORE_ALERT_THRESHOLD = 0.75;
const SOFT_Z_THRESHOLD = 2.5;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    for (const route of ROUTES_TO_MONITOR) {
      const buckets = await fetchHourlyBuckets(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, route, 48);
      if (buckets.length < 6) continue;  // not enough data

      for (const metric of ["error_rate", "p99_ms"] as const) {
        const zResult = zScoreCheck(buckets, metric);
        if (!zResult.soft_anomaly) continue;  // skip AI call if z-score is normal

        const series = buckets.map((b) => ({ hour: b.hour, value: b[metric] }));
        const report = await scoreWithAI(env.AI, route, metric, series, zResult.current);

        if (report.score >= AI_SCORE_ALERT_THRESHOLD) {
          await triggerPagerDuty(env.PAGERDUTY_KEY, report);
        }
      }
    }
  },
};

async function triggerPagerDuty(routingKey: string, report: Awaited<ReturnType<typeof scoreWithAI>>): Promise<void> {
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: routingKey,
      event_action: "trigger",
      payload: {
        summary: `AI anomaly (score ${report.score.toFixed(2)}): ${report.route} ${report.metric} — ${report.reason}`,
        severity: report.score >= 0.9 ? "critical" : "warning",
        source: "workers-anomaly-detector",
        custom_details: report,
      },
    }),
  });
}
```

## Anti-patterns

- Calling Workers AI on every request in the hot path — model inference adds 200–800 ms; reserve it for the scheduled evaluation loop, not real-time handlers.
- Using AI scoring without the z-score pre-filter — every bucket would incur an AI call; the pre-filter reduces AI invocations to only genuine candidates.
- Trusting the model's raw text output without regex-extracting the JSON block — LLMs sometimes prepend conversational text; always parse the first `{…}` match.

## Gotchas

- Workers AI `@cf/mistral/mistral-7b-instruct-v0.1` has a cold-start latency of up to 3 s on free plans; a scheduled Worker with a 10-second cron is too short. Use a 5-minute or 30-minute cron.
- Analytics Engine only retains data for the account's configured retention period (default 3 months); if the `lookbackHours` window exceeds retention, buckets will be sparse and z-scores will be unreliable.

## Verification

```bash
# Trigger the anomaly detector cron manually via wrangler
wrangler scheduled-event anomaly-detector --trigger-type scheduled

# Inspect AI model latency via tail
wrangler tail anomaly-detector --format pretty | grep -E "AI|score|anomaly"

# Validate the z-score logic offline
npx tsx -e "
const { zScoreCheck } = await import('./lib/z-score.js');
const fake = Array.from({length:23}, () => ({error_rate:0.002,p99_ms:120}));
fake.push({error_rate:0.18, p99_ms:120});
console.log(zScoreCheck(fake,'error_rate'));
"
```

## Related

- `monitoring/anomaly-detection-alerts.md`
- `monitoring/analytics-engine-sql-api-programmatic-querying.md`
- `monitoring/cloudflare-analytics-engine.md`
- `monitoring/workers-error-alerting-pagerduty-integration.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
