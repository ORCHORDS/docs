# Durable Objects Request Queue Depth Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Durable Objects process requests serially in a single-threaded event loop. Under load
spikes the incoming request queue grows, adding latency that is invisible in standard
P50/P99 metrics because those only measure requests that have already completed. By
the time you see high-latency alerts, the queue may already be thousands of entries
deep and clients are experiencing timeouts.

This article shows how to instrument Durable Objects so that queue depth is measured
and emitted to Analytics Engine on every request, enabling proactive alerts before
latency SLOs are breached.

---

## Context

Cloudflare does not expose a native "queue depth" counter for Durable Objects. The
queue depth must be inferred by counting the number of concurrent in-flight requests
within the DO using an atomic counter on the class instance. Because all requests are
processed in the same isolate, a simple instance-level integer is safe without locks.

example project uses Durable Objects for session state, rate-limiting, and real-time collaboration
cursors. Queue depth spikes on the rate-limit DOs during traffic bursts correlate with
upstream 429 errors reaching the client.

---

## Instance-Level Queue Counter

```typescript
// src/durable-objects/monitored-base.ts

export abstract class MonitoredDurableObject implements DurableObject {
  protected state: DurableObjectState;
  protected env: Env;

  private _queueDepth = 0;
  private _totalRequests = 0;
  private _className: string;

  constructor(state: DurableObjectState, env: Env, className: string) {
    this.state = state;
    this.env = env;
    this._className = className;
  }

  /**
   * Wrap every fetch() override with this to get queue depth tracking.
   * Usage: return this.tracked(request, () => this.handleFetch(request));
   */
  protected async tracked(
    request: Request,
    handler: () => Promise<Response>,
  ): Promise<Response> {
    this._queueDepth++;
    this._totalRequests++;
    const depth = this._queueDepth; // capture at entry
    const start = Date.now();

    try {
      const response = await handler();
      const durationMs = Date.now() - start;
      this._emitMetric(request, depth, durationMs, 'ok');
      return response;
    } catch (err) {
      const durationMs = Date.now() - start;
      this._emitMetric(request, depth, durationMs, 'error');
      throw err;
    } finally {
      this._queueDepth--;
    }
  }

  private _emitMetric(
    request: Request,
    depthAtEntry: number,
    durationMs: number,
    outcome: 'ok' | 'error',
  ): void {
    const url = new URL(request.url);
    // Non-blocking; Analytics Engine writeDataPoint is synchronous and fast
    (this.env as unknown as { AE: AnalyticsEngineDataset }).AE?.writeDataPoint({
      blobs: [
        this._className,
        url.pathname,
        outcome,
        this.state.id.toString().slice(0, 8), // shard prefix for grouping
      ],
      doubles: [depthAtEntry, durationMs, this._totalRequests],
      indexes: [this._className],
    });
  }
}
```

---

## Concrete Durable Object Implementation

```typescript
// src/durable-objects/rate-limiter.ts
import { MonitoredDurableObject } from './monitored-base';

export class RateLimiterDO extends MonitoredDurableObject {
  constructor(state: DurableObjectState, env: Env) {
    super(state, env, 'RateLimiterDO');
  }

  async fetch(request: Request): Promise<Response> {
    return this.tracked(request, () => this._handleFetch(request));
  }

  private async _handleFetch(request: Request): Promise<Response> {
    const key = new URL(request.url).searchParams.get('key') ?? 'default';
    const current = ((await this.state.storage.get<number>(key)) ?? 0) + 1;
    await this.state.storage.put(key, current);

    if (current > 100) {
      return new Response('Rate limit exceeded', { status: 429 });
    }
    return new Response(JSON.stringify({ allowed: true, count: current }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
```

---

## Analytics Engine Queue Depth Queries

```sql
-- Peak queue depth per DO class over the last hour (5-minute buckets)
SELECT
  toStartOfFiveMinutes(timestamp)      AS bucket,
  blob1                                AS do_class,
  MAX(_sample_interval * double1)      AS peak_queue_depth,
  AVG(_sample_interval * double1)      AS avg_queue_depth,
  COUNT(*)                             AS requests
FROM example project_DO_METRICS
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY bucket, do_class
ORDER BY bucket DESC, do_class;

-- Queue depth percentiles for a specific DO class (last 15 min)
SELECT
  quantile(0.50)(_sample_interval * double1)  AS p50_depth,
  quantile(0.95)(_sample_interval * double1)  AS p95_depth,
  quantile(0.99)(_sample_interval * double1)  AS p99_depth,
  MAX(_sample_interval * double1)             AS max_depth
FROM example project_DO_METRICS
WHERE blob1 = 'RateLimiterDO'
  AND timestamp >= NOW() - INTERVAL '15' MINUTE;

-- Identify hot shards by shard prefix
SELECT
  blob4                              AS shard_prefix,
  MAX(double1)                       AS max_queue_depth,
  COUNT(*)                           AS request_count,
  AVG(double2)                       AS avg_duration_ms
FROM example project_DO_METRICS
WHERE blob1 = 'RateLimiterDO'
  AND timestamp >= NOW() - INTERVAL '30' MINUTE
GROUP BY shard_prefix
ORDER BY max_queue_depth DESC
LIMIT 20;
```

---

## Alert: Queue Depth Burn Rate

```typescript
// src/workers/do-queue-alert.ts
// Cron Worker: runs every minute, fires PagerDuty if p95 queue depth > threshold

interface Env {
  AE_ACCOUNT_ID: string;
  AE_API_TOKEN: string;
  PD_ROUTING_KEY: string;
}

const THRESHOLD_P95_DEPTH = 20;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT
        blob1                                             AS do_class,
        quantile(0.95)(_sample_interval * double1)       AS p95_depth
      FROM example project_DO_METRICS
      WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
      GROUP BY do_class
      HAVING p95_depth > ${THRESHOLD_P95_DEPTH}
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.AE_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.AE_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: sql }),
      },
    );

    const { data } = (await res.json()) as { data: Array<{ do_class: string; p95_depth: number }> };
    if (!data || data.length === 0) return;

    for (const row of data) {
      await fetch('https://events.pagerduty.com/v2/enqueue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_key: env.PD_ROUTING_KEY,
          event_action: 'trigger',
          dedup_key: `do-queue-depth-${row.do_class}`,
          payload: {
            summary: `DO queue depth P95 = ${row.p95_depth} for ${row.do_class}`,
            severity: row.p95_depth > 50 ? 'critical' : 'warning',
            source: 'example project-do-queue-monitor',
            custom_details: row,
          },
        }),
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Wrangler Configuration

```toml
# wrangler.toml (excerpt)
[[durable_objects.bindings]]
name       = "RATE_LIMITER"
class_name = "RateLimiterDO"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "example project_DO_METRICS"

[triggers]
crons = ["* * * * *"]   # do-queue-alert Worker
```

---

## Anti-patterns

- **Measuring queue depth from the caller** — network round-trips and connection overhead
  make external measurement inaccurate; only in-process counters are reliable.
- **Using `state.storage` to persist the counter** — storage I/O adds latency; keep
  the counter as an in-memory instance variable only.
- **Alerting on average depth** — average masks spikes; always alert on P95 or P99.
- **Emitting a data point per byte rather than per request** — doubles the write volume
  and dilutes averages; emit once per request in the `finally` block.

---

## Gotchas

- When a DO is evicted and recreated, `_queueDepth` resets to 0. This is correct
  behaviour — a fresh instance has no backlog — but can cause apparent metric resets
  during low-traffic periods.
- `depthAtEntry` captures the value *before* the handler awaits, which is the best
  proxy for "requests waiting ahead of me." The counter decrements in `finally`, so
  concurrent requests see an accurate in-flight count.
- Analytics Engine `MAX()` across data points already aggregated by the engine may
  differ from true wall-clock peak; sample every request for accuracy.
- If a DO serves WebSocket connections, each connection's message loop counts as one
  long-running request and permanently increments the depth counter. Add a separate
  WebSocket message path that does not call `tracked()`.

---

## Verification

```bash
# Confirm metrics arriving in Analytics Engine
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1 AS do_class, COUNT(*) AS n, MAX(double1) AS max_depth FROM example project_DO_METRICS WHERE timestamp >= NOW() - INTERVAL '"'"'5'"'"' MINUTE GROUP BY do_class"}' \
  | jq '.data'

# Load-test a single DO to observe queue depth climbing
npx wrangler dev &
ab -n 500 -c 50 "http://localhost:8787/rate-limit?key=test"
```

---

## Related

- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-websocket-connection-monitoring.md`
- `durable-objects-storage-quota-headroom-monitoring.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `analytics-engine-multi-tenant-usage-metering.md`

---

## Sources

- Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- Analytics Engine writeDataPoint: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- Durable Objects performance: https://developers.cloudflare.com/durable-objects/best-practices/
- PagerDuty Events API v2: https://developer.pagerduty.com/docs/events-api-v2/overview/
