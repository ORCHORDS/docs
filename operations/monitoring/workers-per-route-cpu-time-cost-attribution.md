# Workers Per-Route CPU Time Cost Attribution

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Workers bill grows each month but `wrangler tail` only shows aggregate CPU time. You cannot tell whether the `/api/search` route, the `/webhooks/stripe` handler, or a background fan-out is the culprit. Without per-route attribution you optimise the wrong code path or over-provision the wrong Worker.

## Context

Cloudflare bills Workers on CPU time, not wall-clock time. The runtime exposes `ctx.waitUntil` CPU alongside synchronous CPU in the same bucket. Analytics Engine lets you write one data point per request (up to 25 blobs, 25 doubles, 1 index). Writing the route label + CPU ms per request gives a low-cardinality, queryable cost ledger at near-zero marginal overhead. Tail Workers receive the `cpuTime` field only after the request completes, making them the correct integration point.

---

## 1. Route Fingerprinting Middleware

Attach a route label early in the request lifecycle so the Tail Worker can read it from a response header.

```typescript
// src/middleware/route-label.ts
export function labelRoute(request: Request, label: string): string {
  // Normalise dynamic segments: /users/123 -> /users/:id
  return label
    .replace(/\/[0-9a-f]{8,}/gi, '/:id')
    .replace(/\/\d+/g, '/:n');
}

export async function withRouteLabel(
  request: Request,
  label: string,
  handler: () => Promise<Response>
): Promise<Response> {
  const res = await handler();
  const headers = new Headers(res.headers);
  headers.set('X-Route-Label', labelRoute(request, label));
  return new Response(res.body, { status: res.status, headers });
}
```

---

## 2. Tail Worker — CPU Attribution Writer

```typescript
// tail-worker/cpu-attribution.ts
export interface Env {
  AE_DATASET: AnalyticsEngineDataset;
}

interface TailEvent {
  event: { request: { url: string }; response?: { headers: Record<string, string> } };
  cpuTime: number;       // ms of CPU consumed this invocation
  wallTime: number;
  outcome: string;
  scriptName: string;
}

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const ev of events) {
      const url = new URL(ev.event.request.url);
      const routeLabel =
        ev.event.response?.headers?.['x-route-label'] ??
        normalisePath(url.pathname);

      env.AE_DATASET.writeDataPoint({
        indexes: [routeLabel],
        blobs: [
          ev.scriptName,
          ev.outcome,           // 'ok' | 'exception' | 'exceeded-cpu' | 'canceled'
          url.hostname,
        ],
        doubles: [
          ev.cpuTime,           // ms CPU — the billing unit
          ev.wallTime,
          ev.cpuTime / Math.max(ev.wallTime, 1), // CPU ratio
        ],
      });
    }
  },
} satisfies ExportedHandler<Env>;

function normalisePath(pathname: string): string {
  return pathname
    .replace(/\/[0-9a-f]{8,}/gi, '/:id')
    .replace(/\/\d+/g, '/:n');
}
```

---

## 3. Analytics Engine SQL Queries

```sql
-- Top routes by total CPU ms in the last 24 h
SELECT
  index1                            AS route,
  SUM(_sample_interval * double1)   AS total_cpu_ms,
  COUNT()                           AS requests,
  AVG(double1)                      AS avg_cpu_ms,
  quantileWeighted(0.99)(double1, _sample_interval) AS p99_cpu_ms
FROM cpu_attribution
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY route
ORDER BY total_cpu_ms DESC
LIMIT 20;

-- Routes exceeding 30 ms CPU per request (Workers free-tier CPU limit per invocation)
SELECT
  index1      AS route,
  COUNT()     AS over_budget_count,
  AVG(double1) AS avg_cpu_ms
FROM cpu_attribution
WHERE timestamp > NOW() - INTERVAL '1' HOUR
  AND double1 > 30
GROUP BY route
ORDER BY over_budget_count DESC;

-- CPU ratio trend — routes where CPU ≈ wall time (no I/O overlap, blocking code)
SELECT
  index1         AS route,
  AVG(double3)   AS avg_cpu_ratio
FROM cpu_attribution
WHERE timestamp > NOW() - INTERVAL '6' HOUR
GROUP BY route
HAVING avg_cpu_ratio > 0.85
ORDER BY avg_cpu_ratio DESC;
```

---

## 4. Cost Estimation Worker

```typescript
// src/cost-estimate.ts
// Cloudflare Workers paid plan: $0.02 per million GB-seconds of CPU
// 1 ms CPU @ 128 MB ~ 0.128 MB-seconds = 1.28e-10 GB-seconds

const COST_PER_GB_SECOND = 0.02 / 1_000_000; // $

export function estimateCostUsd(cpuMs: number, memoryMb = 128): number {
  const gbSeconds = (cpuMs / 1_000) * (memoryMb / 1_024);
  return gbSeconds * COST_PER_GB_SECOND;
}

// Fetch route attribution and compute daily cost breakdown
export async function routeCostReport(
  accountId: string,
  apiToken: string,
  dataset: string
): Promise<{ route: string; costUsd: number; requests: number }[]> {
  const sql = `
    SELECT index1 AS route,
           SUM(_sample_interval * double1) AS total_cpu_ms,
           COUNT() AS requests
    FROM ${dataset}
    WHERE timestamp > NOW() - INTERVAL '1' DAY
    GROUP BY route ORDER BY total_cpu_ms DESC LIMIT 50
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    { method: 'POST', headers: { Authorization: `Bearer ${apiToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ query: sql }) }
  );
  const { data } = (await res.json()) as { data: { route: string; total_cpu_ms: number; requests: number }[] };
  return data.map(r => ({
    route: r.route,
    requests: r.requests,
    costUsd: estimateCostUsd(r.total_cpu_ms),
  }));
}
```

---

## 5. Alerting on CPU Budget Breach

```typescript
// alert-worker/cpu-budget-alert.ts
// Cron trigger: every 15 minutes
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const rows = await routeCostReport(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, 'cpu_attribution');
    const DAILY_BUDGET_USD = 5.0;
    const totalToday = rows.reduce((s, r) => s + r.costUsd, 0);

    if (totalToday > DAILY_BUDGET_USD * 0.8) {
      const top3 = rows.slice(0, 3).map(r => `${r.route}: $${r.costUsd.toFixed(4)}`).join('\n');
      await sendSlackAlert(env.SLACK_WEBHOOK, {
        text: `Workers CPU budget at ${((totalToday / DAILY_BUDGET_USD) * 100).toFixed(0)}% — top routes:\n${top3}`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Writing CPU data from inside the request handler** — CPU time is only finalised after the response is sent; Tail Workers are the only reliable source.
- **High-cardinality route keys** — including raw user IDs or UUIDs in the index blows up cardinality and wastes index slots. Always normalise dynamic segments.
- **Ignoring `_sample_interval`** in SUM aggregations — if Tail Workers sample at < 100%, totals will be wrong without weighting by `_sample_interval`.

## Gotchas

- `cpuTime` in a Tail Event is the **total** CPU for the invocation including `waitUntil` tasks that completed before the tail event was dispatched; long-running background work may shift attribution to the triggering request.
- Tail Workers themselves consume CPU on the same account quota — keep the tail writer lean (no JSON.stringify of full bodies).
- Analytics Engine write limits are 25 writes/second per dataset per Worker instance; high-traffic Workers should batch or sample.
- The `exceeded-cpu` outcome means the Worker was killed; these events still appear in the Tail stream with `cpuTime` equal to the limit that was hit.

## Verification

```bash
# Confirm tail worker is receiving events with cpuTime
wrangler tail cpu-attribution-tail --format json | jq '.cpuTime'

# Query AE for last 5 minutes of data
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT index1, COUNT(), AVG(double1) FROM cpu_attribution WHERE timestamp > NOW() - INTERVAL '\''5'\'' MINUTE GROUP BY index1 LIMIT 10"}' \
  | jq '.data'
```

## Related

- `workers-cpu-time-percentile-analytics-engine.md`
- `tail-worker-cold-start-attribution.md`
- `workers-tail-worker-sampling-high-traffic.md`
- `cloudflare-billing-cost-anomaly-detection.md`
- `observability-cost-control.md`

## Sources

- Cloudflare Workers Pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Tail Workers documentation: https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers Runtime APIs — CPU time: https://developers.cloudflare.com/workers/runtime-apis/performance/
