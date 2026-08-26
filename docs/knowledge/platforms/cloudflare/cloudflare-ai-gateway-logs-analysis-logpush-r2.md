# AI Gateway Request Log Analysis via Logpush to R2

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Aggregating AI Gateway costs and latencies from raw logs at scale

AI Gateway emits per-request logs (model, provider, token counts, latency, cache hit/miss, cost
estimate) but the dashboard only shows rolling windows. For finance reporting, anomaly detection,
and per-customer cost attribution you need the raw logs in a queryable store you control.

Logpush can stream AI Gateway logs to R2 as newline-delimited JSON objects, one file per batch.
A Cloudflare Workers Cron Trigger reads the previous hour's R2 objects, aggregates cost and
latency by provider/model/customer, and writes summary rows to D1. From D1 you can query with
any Postgres-compatible client or serve the data through a Workers API.

This pattern keeps hot-path latency untouched — all aggregation is asynchronous — and costs far
less than forwarding every log to a third-party observability SaaS.

## Context

- AI Gateway account-level logging must be enabled (dashboard → AI Gateway → Logging)
- Logpush job targets R2 bucket: `ai-gateway-logs`
- Workers Cron Trigger runs every hour at `:05` (5 min after the hour to allow log flush)
- D1 database: `ai-metrics`
- Wrangler 3.x

## Enable AI Gateway Logging and Configure Logpush

Enable logging in the dashboard or via API, then create the Logpush job:

```bash
# Create R2 bucket
wrangler r2 bucket create ai-gateway-logs

# Create Logpush job via Cloudflare API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ai-gateway-to-r2",
    "logpull_options": "fields=EventTimestampMs,GatewayId,Provider,Model,RequestTokens,ResponseTokens,TotalTokens,CostUsd,DurationMs,CacheStatus,CustomerId,StatusCode",
    "destination_conf": "r2://ai-gateway-logs/{DATE}/{HOUR}/{FILENAME}",
    "dataset": "ai_gateway_requests",
    "enabled": true
  }'
```

The `{DATE}/{HOUR}` path pattern produces keys like `2026-08-22/14/part-000001.json.gz`.

## D1 Summary Schema

```sql
-- Run once: wrangler d1 execute ai-metrics --file=schema.sql
CREATE TABLE IF NOT EXISTS ai_cost_summary (
  id TEXT PRIMARY KEY,
  hour_bucket TEXT NOT NULL,       -- '2026-08-22T14:00:00Z'
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  customer_id TEXT NOT NULL DEFAULT '',
  request_count INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  p50_duration_ms REAL,
  p95_duration_ms REAL,
  cache_hit_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  UNIQUE(hour_bucket, provider, model, customer_id)
);

CREATE INDEX idx_summary_hour ON ai_cost_summary(hour_bucket DESC);
CREATE INDEX idx_summary_customer ON ai_cost_summary(customer_id, hour_bucket DESC);
```

## Scheduled Aggregation Worker

```ts
// src/aggregate-worker.ts
interface Env {
  AI_LOGS_BUCKET: R2Bucket;
  AI_METRICS_DB: D1Database;
}

interface LogRecord {
  EventTimestampMs: number;
  Provider: string;
  Model: string;
  RequestTokens: number;
  ResponseTokens: number;
  TotalTokens: number;
  CostUsd: number;
  DurationMs: number;
  CacheStatus: string;
  CustomerId: string;
  StatusCode: number;
}

type AggKey = string; // "provider|model|customerId"

interface Agg {
  requestCount: number;
  totalTokens: number;
  costUsd: number;
  durations: number[];
  cacheHits: number;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // Process the previous complete hour
    const now = new Date(event.scheduledTime);
    const prevHour = new Date(now);
    prevHour.setUTCHours(now.getUTCHours() - 1, 0, 0, 0);
    const date = prevHour.toISOString().slice(0, 10);          // 2026-08-22
    const hour = String(prevHour.getUTCHours()).padStart(2, '0'); // 13
    const hourBucket = `${date}T${hour}:00:00Z`;

    // List all objects for that hour
    const prefix = `${date}/${hour}/`;
    const listed = await env.AI_LOGS_BUCKET.list({ prefix });

    const aggregates = new Map<AggKey, Agg>();

    for (const obj of listed.objects) {
      const r2Object = await env.AI_LOGS_BUCKET.get(obj.key);
      if (!r2Object) continue;

      const text = await r2Object.text();
      const lines = text.split('\n').filter(Boolean);

      for (const line of lines) {
        let record: LogRecord;
        try { record = JSON.parse(line); } catch { continue; }
        if (record.StatusCode >= 500) continue; // skip errors

        const key: AggKey = `${record.Provider}|${record.Model}|${record.CustomerId ?? ''}`;
        const agg: Agg = aggregates.get(key) ?? { requestCount: 0, totalTokens: 0, costUsd: 0, durations: [], cacheHits: 0 };
        agg.requestCount++;
        agg.totalTokens += record.TotalTokens ?? 0;
        agg.costUsd += record.CostUsd ?? 0;
        agg.durations.push(record.DurationMs ?? 0);
        if (record.CacheStatus === 'HIT') agg.cacheHits++;
        aggregates.set(key, agg);
      }
    }

    // Upsert summaries into D1
    const stmts: D1PreparedStatement[] = [];
    for (const [key, agg] of aggregates) {
      const [provider, model, customerId] = key.split('|');
      agg.durations.sort((a, b) => a - b);
      const p50 = percentile(agg.durations, 0.5);
      const p95 = percentile(agg.durations, 0.95);

      stmts.push(
        env.AI_METRICS_DB.prepare(
          `INSERT INTO ai_cost_summary
             (id,hour_bucket,provider,model,customer_id,request_count,total_tokens,cost_usd,p50_duration_ms,p95_duration_ms,cache_hit_count)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(hour_bucket,provider,model,customer_id) DO UPDATE SET
             request_count=request_count+excluded.request_count,
             total_tokens=total_tokens+excluded.total_tokens,
             cost_usd=cost_usd+excluded.cost_usd,
             cache_hit_count=cache_hit_count+excluded.cache_hit_count`
        ).bind(
          crypto.randomUUID(), hourBucket, provider, model, customerId ?? '',
          agg.requestCount, agg.totalTokens, agg.costUsd, p50, p95, agg.cacheHits
        )
      );
    }

    // D1 batch — max 100 statements per batch
    for (let i = 0; i < stmts.length; i += 100) {
      await env.AI_METRICS_DB.batch(stmts.slice(i, i + 100));
    }

    console.log(`Aggregated ${aggregates.size} groups for hour ${hourBucket}`);
  },
};

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.floor(sorted.length * p);
  return sorted[Math.min(idx, sorted.length - 1)];
}
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "ai-gateway-aggregator"
main = "src/aggregate-worker.ts"
compatibility_date = "2026-08-01"

[triggers]
crons = ["5 * * * *"]  # every hour at :05

[[r2_buckets]]
binding = "AI_LOGS_BUCKET"
bucket_name = "ai-gateway-logs"

[[d1_databases]]
binding = "AI_METRICS_DB"
database_name = "ai-metrics"
database_id = "YOUR_D1_ID"
```

## Anti-patterns

- Do not parse gzipped R2 objects in Workers without streaming — buffer the whole object and decompress in memory
- Do not run the cron at `:00` — Logpush may still be flushing the previous hour's tail; use `:05` minimum
- Do not aggregate across days in a single cron run — scope each run to exactly one hour prefix
- Do not store raw log lines in D1 — D1 row limits and cost make R2 the correct store for raw data

## Gotchas

- R2 `list()` returns at most 1000 objects per call; use `listed.truncated` and `listed.cursor` to paginate
- Logpush objects may be gzip-compressed; check `Content-Encoding` on the R2 object or configure the job with `compression=none`
- `CostUsd` in AI Gateway logs is an estimate based on provider list prices, not your negotiated rate
- D1 `batch()` is limited to 100 statements; loop in chunks as shown above

## Verification

```ts
// Query D1 for top-5 most expensive models in the last 24 hours
const result = await env.AI_METRICS_DB.prepare(`
  SELECT provider, model, SUM(cost_usd) as total_cost, SUM(request_count) as calls
  FROM ai_cost_summary
  WHERE hour_bucket >= datetime('now','-24 hours')
  GROUP BY provider, model
  ORDER BY total_cost DESC
  LIMIT 5
`).all();
console.log(result.results);
```

## Related

- documentation/docs/policies/cloudflare/ai-gateway-best-practices.md
- documentation/docs/policies/cloudflare/ai-gateway-fallback-caching-streaming.md
- documentation/docs/policies/cloudflare/logpush-best-practices.md
- documentation/docs/policies/cloudflare/r2-best-practices.md
- documentation/docs/policies/cloudflare/d1-best-practices.md

## Sources

- https://developers.cloudflare.com/ai-gateway/observability/logging/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
