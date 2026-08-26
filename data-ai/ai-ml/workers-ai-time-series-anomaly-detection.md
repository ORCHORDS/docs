# Workers AI Time-Series Anomaly Detection

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your application emits per-minute metrics (error rates, latency percentiles, request counts) stored in Cloudflare Analytics Engine or D1, and you need to detect anomalies in real time at the edge without running a dedicated monitoring server.

## Context
Cloudflare Workers can act as both a metrics ingestion endpoint and an anomaly detection engine. A Cron Trigger fires every minute to pull recent metric windows from D1 or Analytics Engine, computes statistical baselines (rolling mean and standard deviation), and optionally invokes a Workers AI text-generation model to interpret multi-signal anomalies in natural language for alert payloads. Alerts are dispatched through Queues to downstream notification handlers.

## Metric Ingestion into D1

Accept per-minute metric pushes from your application and store them in a D1 table. Keep only a rolling 24-hour window to bound storage.

```typescript
// src/ingest.ts
interface Env {
  DB: D1Database;
}

export interface MetricPoint {
  series: string;     // e.g. "api.error_rate.us-east"
  value: number;
  ts: number;         // Unix seconds
}

export async function ingestMetrics(env: Env, points: MetricPoint[]): Promise<void> {
  const stmt = env.DB.prepare(
    'INSERT OR REPLACE INTO metrics (series, ts, value) VALUES (?, ?, ?)'
  );
  const batch = points.map((p) => stmt.bind(p.series, p.ts, p.value));
  await env.DB.batch(batch);

  // Prune older than 24 h
  const cutoff = Math.floor(Date.now() / 1000) - 86400;
  await env.DB.prepare('DELETE FROM metrics WHERE ts < ?').bind(cutoff).run();
}
```

D1 schema (run once via migration):
```sql
CREATE TABLE IF NOT EXISTS metrics (
  series TEXT NOT NULL,
  ts     INTEGER NOT NULL,
  value  REAL NOT NULL,
  PRIMARY KEY (series, ts)
);
```

## Rolling Window Statistics

Fetch the last N points for each monitored series and compute the rolling mean and standard deviation to establish a dynamic baseline.

```typescript
// src/stats.ts
interface Env {
  DB: D1Database;
}

export interface SeriesStats {
  series: string;
  mean: number;
  stdDev: number;
  latest: number;
  zScore: number;
}

export async function computeStats(
  env: Env,
  series: string,
  windowMinutes = 60
): Promise<SeriesStats> {
  const cutoff = Math.floor(Date.now() / 1000) - windowMinutes * 60;
  const { results } = await env.DB.prepare(
    'SELECT value FROM metrics WHERE series = ? AND ts >= ? ORDER BY ts ASC'
  )
    .bind(series, cutoff)
    .all<{ value: number }>();

  const values = results.map((r) => r.value);
  const n = values.length;

  if (n < 5) return { series, mean: 0, stdDev: 0, latest: values.at(-1) ?? 0, zScore: 0 };

  const mean = values.reduce((s, v) => s + v, 0) / n;
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
  const stdDev = Math.sqrt(variance);
  const latest = values.at(-1)!;
  const zScore = stdDev === 0 ? 0 : (latest - mean) / stdDev;

  return { series, mean, stdDev, latest, zScore };
}
```

## Anomaly Classification with Workers AI

When a z-score breach is detected (|z| > 3), invoke a Workers AI text model to produce a human-readable explanation of the anomaly in the context of all concurrently breaching series. This explanation populates the alert body.

```typescript
// src/classify-anomaly.ts
interface Env {
  AI: Ai;
}

interface AnomalyContext {
  anomalies: { series: string; zScore: number; mean: number; latest: number }[];
  windowMinutes: number;
}

export async function explainAnomalies(env: Env, ctx: AnomalyContext): Promise<string> {
  if (ctx.anomalies.length === 0) return '';

  const lines = ctx.anomalies.map(
    (a) =>
      `- ${a.series}: current=${a.latest.toFixed(4)}, baseline_mean=${a.mean.toFixed(4)}, z_score=${a.zScore.toFixed(2)}`
  );

  const prompt = [
    `You are a site-reliability engineer. The following metrics deviated more than 3 standard deviations`,
    `from their ${ctx.windowMinutes}-minute rolling baseline. Write a concise (2-3 sentence) plain-English`,
    `alert summary suitable for a PagerDuty incident title and body. Focus on likely impact and urgency.`,
    '',
    ...lines,
  ].join('\n');

  const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 120,
  }) as { response: string };

  return response.response.trim();
}
```

## Cron-Driven Anomaly Scan

A Cron Trigger fires every minute to scan all active metric series and dispatch Queue messages for each anomaly found.

```typescript
// src/cron.ts
interface Env {
  DB: D1Database;
  AI: Ai;
  ALERT_QUEUE: Queue;
}

const MONITORED_SERIES = [
  'api.error_rate',
  'api.p99_latency_ms',
  'checkout.success_rate',
  'cdn.cache_hit_rate',
];
const Z_THRESHOLD = 3;

export async function runAnomalyScan(env: Env): Promise<void> {
  const statsAll = await Promise.all(
    MONITORED_SERIES.map((s) => computeStats(env, s))
  );

  const anomalies = statsAll.filter((s) => Math.abs(s.zScore) > Z_THRESHOLD);
  if (anomalies.length === 0) return;

  const explanation = await explainAnomalies(env, { anomalies, windowMinutes: 60 });

  await env.ALERT_QUEUE.send({
    type: 'anomaly',
    ts: Date.now(),
    anomalies,
    explanation,
  });
}

import { computeStats } from './stats';
import { explainAnomalies } from './classify-anomaly';
```

## Wrangler Configuration

```jsonc
// wrangler.jsonc (relevant excerpts)
{
  "triggers": {
    "crons": ["* * * * *"]
  },
  "d1_databases": [
    { "binding": "DB", "database_name": "metrics-db", "database_id": "<id>" }
  ],
  "queues": {
    "producers": [{ "binding": "ALERT_QUEUE", "queue": "anomaly-alerts" }]
  },
  "ai": { "binding": "AI" }
}
```

Worker entry point that routes cron vs. HTTP:

```typescript
// src/index.ts
interface Env {
  DB: D1Database;
  AI: Ai;
  ALERT_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Metric ingestion endpoint
    if (request.method === 'POST' && new URL(request.url).pathname === '/ingest') {
      const points = await request.json<{ series: string; value: number; ts: number }[]>();
      await ingestMetrics(env, points);
      return new Response('OK');
    }
    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runAnomalyScan(env);
  },
};

import { ingestMetrics } from './ingest';
import { runAnomalyScan } from './cron';
```

## Anti-patterns
- Computing statistics over all-time data instead of a rolling window — baselines drift with product growth
- Using a fixed absolute threshold (e.g., error_rate > 5%) instead of a dynamic z-score — misses regressions in low-traffic periods
- Firing the anomaly LLM call on every cron tick even when no breach exists — wastes inference budget
- Sending one Queue message per anomalous data point rather than batching all anomalies in a single scan message
- Storing raw metric points without a TTL-based pruning job — D1 storage fills unbounded

## Gotchas
- Workers Cron Triggers have a minimum interval of one minute — sub-minute anomaly detection requires streaming ingest via WebSockets or Durable Objects
- D1 `batch()` is limited to 100 statements per call; chunk larger ingest batches accordingly
- `scheduled()` has a 30-second CPU time limit — keep the scan tight; defer heavy LLM calls to a Queue consumer
- z-score is meaningless with fewer than ~10 data points; guard with a minimum sample size before alerting
- Analytics Engine is append-only and queryable only via GraphQL — use D1 for mutable metric storage unless read-only BI is sufficient

## Verification
1. Ingest 60 minutes of synthetic `api.error_rate` data with a normal baseline of 0.01, then push a value of 0.08 and confirm a Queue message is sent.
2. Assert that `explainAnomalies` returns a non-empty string under 200 characters.
3. Run `wrangler dev --local` and trigger the cron with `wrangler dev --test-scheduled`.
4. Check D1 row count stays bounded at ~1,440 rows per series after 24 hours of ingestion.

## Related
- [AI Cold Start Patterns](ai-cold-start-patterns.md)
- [AI Cost Monitoring](ai-cost-monitoring.md)
- [Workers AI Queue Batch Processing](workers-ai-queue-batch-processing.md)
- [LLM Async Patterns](llm-async-patterns.md)

## Sources
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/#dbbatch
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/queues/get-started/
