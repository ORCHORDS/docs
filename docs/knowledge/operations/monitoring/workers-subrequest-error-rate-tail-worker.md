# Workers Subrequest Error Rate — Tail Worker

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker proxies requests to multiple upstream APIs or internal services. Individual
subrequest failures are swallowed, retried, or masked by fallback logic, so the top-level
response status looks healthy while a high fraction of subrequests silently fail. You need
per-upstream, per-status-class error rates tracked continuously so you can alert when a
third-party API degrades or an internal service starts returning 5xx.

## Context

Workers cannot directly instrument `fetch()` subrequest outcomes in a Tail Worker — Tail
Workers receive the *invocation* envelope, not individual subrequest details. The pattern
is to instrument subrequests inline in the primary Worker (wrapping `fetch`), emit structured
logs, and collect them in a Tail Worker that writes per-upstream error blobs to Analytics
Engine. This gives you a queryable, low-cost time series without an external log sink.

---

## 1. Instrumented `fetch` Wrapper

```typescript
// src/lib/tracked-fetch.ts
export interface SubrequestRecord {
  upstream: string;
  statusCode: number;
  latencyMs: number;
  isError: boolean;
}

const RECORDS_KEY = Symbol('subrequest_records');

export function getSubrequestRecords(ctx: ExecutionContext): SubrequestRecord[] {
  // Attach records bag to the ExecutionContext via a module-level WeakMap
  return subrequestBag.get(ctx) ?? [];
}

const subrequestBag = new WeakMap<object, SubrequestRecord[]>();

export async function trackedFetch(
  ctx: ExecutionContext,
  upstream: string,
  input: RequestInfo,
  init?: RequestInit
): Promise<Response> {
  let records = subrequestBag.get(ctx);
  if (!records) {
    records = [];
    subrequestBag.set(ctx, records);
  }

  const start = Date.now();
  let statusCode = 0;

  try {
    const response = await fetch(input, init);
    statusCode = response.status;
    return response;
  } catch (err) {
    statusCode = 0; // network error
    throw err;
  } finally {
    records.push({
      upstream,
      statusCode,
      latencyMs: Date.now() - start,
      isError: statusCode === 0 || statusCode >= 500 || statusCode === 429,
    });
  }
}
```

## 2. Emitting Subrequest Logs from the Primary Worker

```typescript
// src/index.ts
import { trackedFetch, getSubrequestRecords } from './lib/tracked-fetch';

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Normal request handling — use trackedFetch for all upstream calls
    const [weatherResp, pricesResp] = await Promise.all([
      trackedFetch(ctx, 'weather-api', 'https://api.weather.example/current'),
      trackedFetch(ctx, 'prices-api', 'https://prices.internal/latest'),
    ]);

    // Emit one Analytics Engine blob per subrequest in waitUntil
    ctx.waitUntil(
      (async () => {
        const records = getSubrequestRecords(ctx);
        for (const rec of records) {
          env.ANALYTICS.writeDataPoint({
            blobs: [rec.upstream, String(rec.statusCode), rec.isError ? 'error' : 'ok'],
            doubles: [rec.latencyMs, rec.isError ? 1 : 0],
            indexes: [rec.upstream],
          });
        }
      })()
    );

    return new Response(JSON.stringify({ weather: await weatherResp.json() }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

## 3. Tail Worker — Structured Log Collection

```typescript
// tail/index.ts — captures console.log blobs emitted by the primary Worker
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const event of events) {
      for (const log of event.logs ?? []) {
        if (log.level !== 'log') continue;

        // Primary Worker emits JSON lines for subrequest records
        let record: { upstream?: string; status?: number; latencyMs?: number; isError?: boolean };
        try {
          record = JSON.parse(String(log.message[0]));
        } catch {
          continue;
        }

        if (!record.upstream) continue;

        env.ANALYTICS.writeDataPoint({
          blobs: [
            record.upstream,
            String(record.status ?? 0),
            record.isError ? 'error' : 'ok',
            event.scriptName ?? '',
          ],
          doubles: [record.latencyMs ?? 0, record.isError ? 1 : 0],
          indexes: [record.upstream],
        });
      }
    }
  },
};
```

## 4. Analytics Engine SQL — Per-Upstream Error Rate

```sql
-- Error rate by upstream for the last 15 minutes
SELECT
  blob1                                              AS upstream,
  SUM(_sample_interval * double2)                   AS error_count,
  SUM(_sample_interval)                             AS total_requests,
  SUM(_sample_interval * double2)
    / SUM(_sample_interval)                         AS error_rate,
  quantileWeighted(0.95)(double1, _sample_interval) AS p95_latency_ms
FROM subrequest_metrics
WHERE timestamp >= NOW() - INTERVAL '15' MINUTE
GROUP BY blob1
ORDER BY error_rate DESC
```

```sql
-- Rolling 5-minute error rate for alerting (run from scheduled Worker)
SELECT
  blob1                                   AS upstream,
  SUM(_sample_interval * double2)
    / SUM(_sample_interval)               AS error_rate_5m
FROM subrequest_metrics
WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
  AND double2 > 0   -- only include invocations that had at least one error
GROUP BY blob1
HAVING error_rate_5m > 0.10   -- flag upstreams above 10% error rate
```

## 5. Scheduled Alert Worker

```typescript
// monitor/subrequest-alert.ts — runs every 3 minutes
export interface Env {
  ANALYTICS_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  ALERT_WEBHOOK: string;
}

const ERROR_RATE_THRESHOLD = 0.1;

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const query = `
      SELECT blob1 AS upstream,
             SUM(_sample_interval * double2) / SUM(_sample_interval) AS err_rate
      FROM subrequest_metrics
      WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
      GROUP BY blob1
      HAVING err_rate > ${ERROR_RATE_THRESHOLD}
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.ANALYTICS_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
      }
    );
    const json = (await res.json()) as { data: Array<{ upstream: string; err_rate: number }> };

    for (const row of json.data) {
      await fetch(env.ALERT_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `[subrequest-alert] upstream=${row.upstream} error_rate=${(row.err_rate * 100).toFixed(1)}% (5m window)`,
        }),
      });
    }
  },
};
```

## 6. Console-log Structured Emit (Alternative to Binding)

```typescript
// Alternative: emit via console.log for Tail Worker collection,
// when an Analytics Engine binding on the primary Worker is not available.
function logSubrequest(rec: SubrequestRecord): void {
  console.log(JSON.stringify({
    event: 'subrequest',
    upstream: rec.upstream,
    status: rec.statusCode,
    latencyMs: rec.latencyMs,
    isError: rec.isError,
  }));
}
```

---

## Anti-patterns

- **Counting only top-level Worker `outcome !== 'ok'`**: a Worker can return 200 while all
  subrequests to a critical upstream are failing (your fallback cache is hiding it).
- **Using `fetch` without a timeout**: a hung subrequest consumes CPU time budget and inflates
  p99 latency without producing a 5xx — wrap with `AbortController` and a deadline.
- **Emitting one Analytics Engine blob per request instead of per subrequest**: you lose the
  per-upstream dimension needed to distinguish which of several upstreams is degraded.
- **Alerting on raw error count instead of error rate**: high-traffic services will always
  have some absolute error count; rate is the meaningful signal.

## Gotchas

- `event.logs` in a Tail Worker is only populated when the primary Worker emits `console.log`
  calls; structured fetch telemetry written only to an Analytics Engine binding does **not**
  appear in `event.logs`.
- Tail Workers are sampled at high request volumes (Workers Tail sampling kicks in above
  ~50 rps per isolate by default). Use the Analytics Engine binding directly in the primary
  Worker for accurate counts at scale.
- `status === 429` from an upstream is an application-level rate-limit, not a network error.
  Track it as a separate `isRateLimited` dimension rather than conflating it with 5xx errors.
- Analytics Engine's SQL API imposes a 10,000-row response limit per query; group and
  aggregate in SQL rather than pulling raw rows.

## Verification

```bash
# Check that subrequest blobs are being written
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT blob1, count() FROM subrequest_metrics WHERE timestamp >= NOW() - INTERVAL '\''1'\'' HOUR GROUP BY blob1 LIMIT 20"}'

# Verify Tail Worker is receiving events
wrangler tail my-tail-worker --format pretty 2>&1 | grep '"event":"subrequest"' | head -5
```

## Related

- `workers-subrequest-waterfall-tail.md`
- `workers-subrequest-limit-headroom-monitoring.md`
- `tail-worker-structured-error-classification-d1.md`
- `tail-worker-fan-out-multi-destination-logging.md`
- `cloudflare-analytics-engine-custom-metrics.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/platform/limits/#subrequests
