# Fanning Out Tail Worker Events to Multiple Observability Destinations

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single production Worker emits trace data but your observability stack spans Datadog for alerting, Grafana Loki for log aggregation, and a D1 table for long-term SQL-queryable error history. Writing to each destination serially risks a slow or failed call to one backend blocking the others and adding tail latency. This article wires a Tail Worker that fans out concurrently to all three destinations using `Promise.allSettled()`, with a sampling strategy that captures 100% of errors and 1% of successes.

## Context

Tail Workers receive a `TraceItem[]` array representing a batch of recent invocations from bound producer Workers. They run in a separate isolate after the producer returns a response, so they do not add latency to end-user requests. `Promise.allSettled()` ensures all destinations are attempted regardless of individual failures and returns per-destination results for diagnostics. The `wrangler.toml` `[[tail_consumers]]` block can bind a single Tail Worker to multiple producers. Sampling inside the Tail Worker (rather than at the producer) keeps the producer's CPU budget clean.

## Tail Worker Implementation

```typescript
// src/tail-fanout.ts

export interface Env {
  DATADOG_API_KEY: string;
  LOKI_ENDPOINT: string;       // e.g. https://logs-prod.grafana.net
  LOKI_AUTH: string;           // Basic base64 encoded user:token
  DB: D1Database;
}

interface FanoutResult {
  destination: string;
  ok: boolean;
  status?: number;
  error?: string;
}

function shouldSample(event: TraceItem): boolean {
  const hasException = event.exceptions.length > 0;
  const status = event.response?.status ?? 0;
  const isError = hasException || status >= 500;
  // 100% errors, 1% successes
  return isError || Math.random() < 0.01;
}

async function toDatadog(events: TraceItem[], env: Env): Promise<FanoutResult> {
  const logs = events.map(e => ({
    ddsource: 'cloudflare-workers',
    ddtags: `script:${e.scriptName ?? 'unknown'}`,
    hostname: 'cloudflare',
    message: e.exceptions[0]?.message ?? 'trace',
    status: e.response?.status ?? 0,
    duration: e.wallTimeMs ?? 0,
  }));

  const res = await fetch('https://http-intake.logs.datadoghq.com/api/v2/logs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'DD-API-KEY': env.DATADOG_API_KEY,
    },
    body: JSON.stringify(logs),
  });
  return { destination: 'datadog', ok: res.ok, status: res.status };
}

async function toLoki(events: TraceItem[], env: Env): Promise<FanoutResult> {
  const streams = events.map(e => ({
    stream: { job: 'cloudflare-workers', script: e.scriptName ?? 'unknown' },
    values: [[
      String(Date.now() * 1_000_000), // nanosecond timestamp
      JSON.stringify({
        message: e.exceptions[0]?.message ?? 'trace',
        status: e.response?.status,
        wallTimeMs: e.wallTimeMs,
      }),
    ]],
  }));

  const res = await fetch(`${env.LOKI_ENDPOINT}/loki/api/v1/push`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Basic ${env.LOKI_AUTH}`,
    },
    body: JSON.stringify({ streams }),
  });
  return { destination: 'loki', ok: res.ok, status: res.status };
}

async function toD1(events: TraceItem[], env: Env): Promise<FanoutResult> {
  const stmt = env.DB.prepare(
    'INSERT INTO error_log (script, message, status, wall_time_ms, created_at) VALUES (?, ?, ?, ?, ?)'
  );
  const batch = events
    .filter(e => e.exceptions.length > 0 || (e.response?.status ?? 0) >= 500)
    .map(e => stmt.bind(
      e.scriptName ?? 'unknown',
      e.exceptions[0]?.message?.slice(0, 512) ?? '',
      e.response?.status ?? 0,
      e.wallTimeMs ?? 0,
      new Date().toISOString(),
    ));

  if (batch.length === 0) return { destination: 'd1', ok: true };

  try {
    await env.DB.batch(batch);
    return { destination: 'd1', ok: true };
  } catch (err: unknown) {
    return { destination: 'd1', ok: false, error: String(err) };
  }
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    // Apply sampling
    const sampled = events.filter(shouldSample);
    if (sampled.length === 0) return;

    const results = await Promise.allSettled([
      toDatadog(sampled, env),
      toLoki(sampled, env),
      toD1(sampled, env),
    ]);

    // Log any settlement failures to console (visible in wrangler tail)
    for (const result of results) {
      if (result.status === 'rejected') {
        console.error('fanout destination threw:', result.reason);
      } else if (!result.value.ok) {
        console.warn('fanout destination non-ok:', result.value);
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema for error_log

```sql
-- Run once with: wrangler d1 execute my-db --file=schema.sql
CREATE TABLE IF NOT EXISTS error_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  script      TEXT    NOT NULL,
  message     TEXT    NOT NULL,
  status      INTEGER NOT NULL,
  wall_time_ms INTEGER,
  created_at  TEXT    NOT NULL
);
CREATE INDEX idx_error_log_script ON error_log(script);
CREATE INDEX idx_error_log_created_at ON error_log(created_at);
```

## wrangler.toml Configuration

```toml
# wrangler.toml for the Tail Worker itself
name = "tail-fanout-worker"
main = "src/tail-fanout.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "<your-d1-id>"

[vars]
LOKI_ENDPOINT = "https://logs-prod.grafana.net"

[secrets]
# Set via: wrangler secret put DATADOG_API_KEY
# Set via: wrangler secret put LOKI_AUTH

# In the PRODUCER worker's wrangler.toml, bind this tail worker:
# [[tail_consumers]]
# service = "tail-fanout-worker"
```

## Sampling Strategy Reference

| Event type | Sample rate | Rationale |
|---|---|---|
| Exception / 5xx | 100% | Every error must be captured |
| 4xx client errors | 10% | High volume, mostly expected |
| 2xx success | 1% | Latency baseline only |
| Cron triggers | 100% | Low volume, always relevant |

## Anti-patterns

- **Awaiting destinations serially** — a 2-second Datadog timeout blocks Loki and D1 writes; always fan out with `Promise.allSettled()`.
- **Sampling in the producer Worker** — adds CPU cost to hot-path requests; delegate sampling decisions to the Tail Worker.
- **Writing all trace fields to D1** — D1 row size and batch limits mean you should store only error-relevant events in D1 and use Analytics Engine or Loki for full traces.
- **Binding a single Tail Worker to dozens of producers without a routing header** — add `scriptName` filtering inside the Tail Worker so destination rules can be scoped per producer.

## Gotchas

- Tail Workers have a 10-second CPU time limit per batch; if your fanout targets are slow, `ctx.waitUntil()` will not extend this limit.
- `TraceItem.wallTimeMs` is the total wall time including network time for subrequests; it is not equivalent to Worker CPU time.
- Loki's push endpoint returns HTTP 204 on success, not 200; check `res.ok` (true for 2xx) rather than `res.status === 200`.
- A Tail Worker cannot itself have a Tail Worker attached to it — do not create recursive tail chains.
- `wrangler tail` on the producer will show Tail Worker logs too if they share the same account; filter by script name.

## Verification

```bash
# 1. Deploy both workers
wrangler deploy --config wrangler-producer.toml
wrangler deploy --config wrangler-tail.toml

# 2. Generate test errors against the producer
for i in {1..5}; do curl -sf https://my-producer.example.com/error-test || true; done

# 3. Verify D1 received error rows
wrangler d1 execute my-db --command "SELECT script, message, status FROM error_log ORDER BY id DESC LIMIT 5"

# 4. Watch Tail Worker live logs
wrangler tail tail-fanout-worker --format pretty
```

## Related

- `workers-error-boundary-analytics-engine.md`
- `alert-deduplication-workers-kv-pagerduty.md`
- `durable-objects-state-drift-monitoring.md`

## Sources

- Cloudflare Tail Workers — https://developers.cloudflare.com/workers/observability/tail-workers/
- Datadog Logs Intake API — https://docs.datadoghq.com/api/latest/logs/#send-logs
- Grafana Loki Push API — https://grafana.com/docs/loki/latest/reference/loki-http-api/#push-log-entries-to-loki
