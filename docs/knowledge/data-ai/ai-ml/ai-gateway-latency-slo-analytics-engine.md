# AI Gateway Latency SLO Tracking with Analytics Engine

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Your AI Gateway handles hundreds of inference requests per minute across multiple models and providers. P99 latency occasionally spikes, but you only discover the breach after users complain. You need real-time SLO burn-rate alerting and a durable time-series store for latency percentiles — without spinning up external observability infrastructure.

## Context

Cloudflare Analytics Engine is a time-series write-optimized store built into the Workers runtime. Each data point (a "blobs + doubles" row) is written with `writeDataPoint` at zero cold-start cost. AI Gateway exposes a `cf-aig-log-id` header and optional webhook/log push, but you can also intercept every request through a proxy Worker sitting in front of the gateway. This proxy measures wall-clock latency for each inference call and writes a structured data point to Analytics Engine, enabling SQL-style queries over the Workers Analytics Engine GraphQL or REST API.

SLO definition used in this article: P95 first-token latency ≤ 1500 ms, P99 ≤ 4000 ms over any rolling 5-minute window.

---

## 1. Proxy Worker Setup

The proxy Worker sits between your application and the AI Gateway universal endpoint. It records `start` before forwarding, captures `ttfb` (time-to-first-byte for streaming), and writes a data point regardless of success or failure.

```typescript
// src/gateway-slo-proxy.ts
export interface Env {
  AI_GATEWAY_URL: string;       // https://gateway.ai.cloudflare.com/v1/{account}/{gateway}
  AI_GATEWAY_TOKEN: string;
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const model = url.searchParams.get('model') ?? 'unknown';
    const provider = url.searchParams.get('provider') ?? 'unknown';
    const tenant = request.headers.get('x-tenant-id') ?? 'default';

    const gatewayUrl = `${env.AI_GATEWAY_URL}/${provider}/${url.pathname.replace(/^\//, '')}`;
    const upstreamReq = new Request(gatewayUrl, {
      method: request.method,
      headers: {
        ...Object.fromEntries(request.headers),
        Authorization: `Bearer ${env.AI_GATEWAY_TOKEN}`,
      },
      body: request.body,
    });

    const start = Date.now();
    let ttfb: number | null = null;
    let statusCode = 0;
    let errored = false;

    try {
      const response = await fetch(upstreamReq);
      statusCode = response.status;

      // Intercept first byte for streaming TTFB measurement
      const { readable, writable } = new TransformStream();
      const writer = writable.getWriter();
      const reader = response.body!.getReader();

      ctx.waitUntil((async () => {
        while (true) {
          const { done, value } = await reader.read();
          if (ttfb === null) { ttfb = Date.now() - start; }
          if (done) { await writer.close(); break; }
          await writer.write(value);
        }
      })());

      ctx.waitUntil(writeLatencyPoint(env, { model, provider, tenant, start, ttfb: ttfb ?? 0, statusCode, errored }));

      return new Response(readable, {
        status: response.status,
        headers: response.headers,
      });
    } catch (err) {
      errored = true;
      statusCode = 500;
      ctx.waitUntil(writeLatencyPoint(env, { model, provider, tenant, start, ttfb: Date.now() - start, statusCode, errored }));
      throw err;
    }
  },
};

async function writeLatencyPoint(
  env: Env,
  p: { model: string; provider: string; tenant: string; start: number; ttfb: number; statusCode: number; errored: boolean }
) {
  env.ANALYTICS.writeDataPoint({
    blobs: [p.model, p.provider, p.tenant, p.errored ? '1' : '0'],
    doubles: [p.ttfb, p.statusCode, p.start],
    indexes: [p.tenant],
  });
}
```

---

## 2. Analytics Engine Schema Convention

Analytics Engine rows use positional blobs and doubles. Document the schema once and keep it stable — column positions are the contract.

```
blobs[0]   = model          (e.g. "@cf/meta/llama-3.1-8b-instruct")
blobs[1]   = provider       (e.g. "workers-ai", "openai")
blobs[2]   = tenant         (e.g. "acme-corp")
blobs[3]   = errored        ("0" | "1")

doubles[0] = ttfb_ms        (number, time-to-first-byte)
doubles[1] = http_status    (200, 429, 500 …)
doubles[2] = epoch_ms       (Date.now() at request start)

indexes[0] = tenant         (for fast per-tenant filtering)
```

---

## 3. Querying Latency Percentiles

Use the Analytics Engine SQL API (available via REST or GraphQL) to compute percentiles over rolling windows. Approximate quantiles via `quantilesMerge` or use the `quantile` function depending on your endpoint version.

```typescript
// scripts/query-slo.ts  (runs via `wrangler dev --local` or in a scheduled Worker)
async function fetchP95P99(accountId: string, apiToken: string, tenantId: string): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - 5 * 60; // 5-minute rolling window

  const sql = `
    SELECT
      blob1 AS model,
      quantileIf(0.95)(double1, blob4 = '0') AS p95_ttfb_ms,
      quantileIf(0.99)(double1, blob4 = '0') AS p99_ttfb_ms,
      countIf(blob4 = '1') AS error_count,
      count() AS total
    FROM metricsDataset
    WHERE
      timestamp >= toDateTime(${windowStart})
      AND index1 = '${tenantId}'
    GROUP BY model
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: sql }),
    }
  );
  const data = await res.json() as { data: Array<{ model: string; p95_ttfb_ms: number; p99_ttfb_ms: number }> };

  for (const row of data.data) {
    const sloBreached = row.p95_ttfb_ms > 1500 || row.p99_ttfb_ms > 4000;
    console.log(`[${row.model}] P95=${row.p95_ttfb_ms}ms P99=${row.p99_ttfb_ms}ms SLO=${sloBreached ? 'BREACH' : 'OK'}`);
  }
}
```

---

## 4. Scheduled Burn-Rate Alert Worker

A Cron Trigger Worker queries the last 5 minutes of data every minute and pushes an alert to a webhook when the error budget is burning faster than 2×.

```typescript
// src/slo-alert.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  ALERT_WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const p99 = await queryP99(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);
    if (p99 > 4000) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `🔴 AI Gateway P99 SLO breach: ${p99}ms > 4000ms threshold` }),
      });
    }
  },
};

async function queryP99(accountId: string, token: string): Promise<number> {
  const sql = `
    SELECT quantile(0.99)(double1) AS p99
    FROM metricsDataset
    WHERE timestamp >= now() - INTERVAL '5' MINUTE
      AND blob4 = '0'
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ query: sql }) }
  );
  const body = await res.json() as { data: [{ p99: number }] };
  return body.data[0]?.p99 ?? 0;
}
```

wrangler.toml:
```toml
[triggers]
crons = ["* * * * *"]

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "ai_gateway_latency"
```

---

## 5. Dashboard Query Patterns

Common SQL patterns for operational dashboards:

```sql
-- Hourly P50/P95/P99 by model (last 24 h)
SELECT
  toStartOfHour(timestamp) AS hour,
  blob1 AS model,
  quantile(0.50)(double1) AS p50,
  quantile(0.95)(double1) AS p95,
  quantile(0.99)(double1) AS p99
FROM metricsDataset
WHERE timestamp >= now() - INTERVAL '24' HOUR
  AND blob4 = '0'
GROUP BY hour, model
ORDER BY hour DESC;

-- Error rate by provider (last 1 h)
SELECT
  blob2 AS provider,
  countIf(blob4 = '1') / count() AS error_rate
FROM metricsDataset
WHERE timestamp >= now() - INTERVAL '1' HOUR
GROUP BY provider;
```

---

## Anti-patterns

- **Writing synchronously before returning the response** — always use `ctx.waitUntil(writeDataPoint(...))` so the data point write does not block the response.
- **Using `Date.now()` after `await fetch()`** — for wall-clock latency, capture `start` before the upstream fetch, not after.
- **One dataset for everything** — if you have unrelated metric types, use separate `analytics_engine_datasets` bindings to avoid blob/double collision.
- **Querying without index filtering** — `indexes[0]` is the partition key; always filter on it when you care about per-tenant performance to keep queries fast.

## Gotchas

- Analytics Engine data points are eventually consistent; allow up to 60 seconds before a freshly written point appears in queries.
- The `quantile()` function in Analytics Engine SQL is an approximation (t-digest). For exact percentiles at low cardinality, aggregate raw rows into D1 instead.
- Analytics Engine retains data for 31 days by default; for longer SLO history, export daily rollups to R2 via a scheduled Worker.
- TTFB for non-streaming (buffered) responses equals total response time — the proxy cannot distinguish first-byte from last-byte unless the upstream streams.
- Cron Trigger granularity is 1 minute minimum; sub-minute burn-rate detection requires an external alerting system polling the SQL API.

## Verification

1. Send 20 test requests through the proxy Worker and confirm data points appear in Analytics Engine within 60 seconds using the REST SQL API.
2. Artificially inject a slow request (sleep before forwarding) and verify P99 rises in the next query window.
3. Trigger the scheduled alert Worker manually (`wrangler dev --test-scheduled`) and confirm the webhook fires when P99 > 4000 ms.
4. Check the `ANALYTICS` binding is declared in both `wrangler.toml` and the Worker `Env` interface.

## Related

- `cloudflare-ai-gateway-observability.md`
- `ai-gateway-logging.md`
- `ai-gateway-budget-caps-spend-control.md`
- `ai-gateway-rate-limiting.md`
- `ai-cost-monitoring.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
