# SOC 2 Availability (A1) Monitoring — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SOC 2 Type II audit covers the Availability Trust Service Criterion (A1). Auditors want evidence that (1) uptime commitments are monitored continuously, (2) degradations are detected and logged with timestamps, (3) SLA breach thresholds trigger documented incident response, and (4) the monitoring system itself cannot be disabled by the component it monitors.

## Context

Cloudflare Workers Cron Triggers run on Cloudflare's own infrastructure, independent of your origin. A scheduled Worker pings your service endpoints, records latency and status to D1, computes rolling SLA metrics, and pushes alerts to a Queue when SLA thresholds are breached. D1 is the durable evidence store auditors query. KV caches the live SLA dashboard.

---

## 1. Monitoring Schema

```sql
-- migrations/0003_availability.sql
CREATE TABLE uptime_checks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  endpoint    TEXT    NOT NULL,
  status_code INTEGER,
  latency_ms  INTEGER,
  result      TEXT    CHECK(result IN ('UP','DOWN','DEGRADED')) NOT NULL,
  region      TEXT    NOT NULL
);

CREATE TABLE sla_summaries (
  period_start INTEGER NOT NULL,
  period_end   INTEGER NOT NULL,
  endpoint     TEXT    NOT NULL,
  total_checks INTEGER NOT NULL,
  up_checks    INTEGER NOT NULL,
  uptime_pct   REAL    NOT NULL,
  p95_ms       INTEGER,
  PRIMARY KEY (period_start, endpoint)
);

CREATE TABLE availability_incidents (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at   INTEGER NOT NULL,
  resolved_at  INTEGER,
  endpoint     TEXT    NOT NULL,
  severity     TEXT    CHECK(severity IN ('P1','P2','P3')) NOT NULL,
  description  TEXT
);

CREATE INDEX idx_checks_ts       ON uptime_checks(ts);
CREATE INDEX idx_checks_endpoint ON uptime_checks(endpoint, ts);
```

## 2. Scheduled Health-Check Worker

```typescript
// src/scheduled/availabilityMonitor.ts
const ENDPOINTS = [
  { url: 'https://api.example.com/health', slaTarget: 99.9, timeoutMs: 3000 },
  { url: 'https://app.example.com/',       slaTarget: 99.5, timeoutMs: 5000 },
];

export async function runAvailabilityChecks(env: Env, ctx: ExecutionContext): Promise<void> {
  const ts = Math.floor(Date.now() / 1000);
  const region = (globalThis as any).colo ?? 'unknown';

  const results = await Promise.allSettled(
    ENDPOINTS.map((ep) => checkEndpoint(ep, ts, region, env)),
  );

  ctx.waitUntil(updateSlaSummaries(env));

  for (const r of results) {
    if (r.status === 'fulfilled' && r.value.result === 'DOWN') {
      await env.ALERT_QUEUE.send({ type: 'SLA_BREACH', ...r.value });
    }
  }
}

async function checkEndpoint(ep: { url: string; slaTarget: number; timeoutMs: number }, ts: number, region: string, env: Env) {
  const start = Date.now();
  let statusCode: number | null = null;
  let result: 'UP' | 'DOWN' | 'DEGRADED' = 'DOWN';

  try {
    const res = await fetch(ep.url, { signal: AbortSignal.timeout(ep.timeoutMs), cf: { cacheTtl: 0 } });
    statusCode = res.status;
    const latencyMs = Date.now() - start;
    result = res.status < 400 ? (latencyMs > ep.timeoutMs * 0.8 ? 'DEGRADED' : 'UP') : 'DOWN';

    await env.DB.prepare(
      `INSERT INTO uptime_checks (ts, endpoint, status_code, latency_ms, result, region) VALUES (?, ?, ?, ?, ?, ?)`,
    ).bind(ts, ep.url, statusCode, latencyMs, result, region).run();

    return { endpoint: ep.url, result, status_code: statusCode, latency_ms: latencyMs };
  } catch {
    await env.DB.prepare(
      `INSERT INTO uptime_checks (ts, endpoint, status_code, latency_ms, result, region) VALUES (?, ?, NULL, ?, 'DOWN', ?)`,
    ).bind(ts, ep.url, Date.now() - start, region).run();
    return { endpoint: ep.url, result: 'DOWN', status_code: null, latency_ms: Date.now() - start };
  }
}
```

## 3. Rolling SLA Summary

```typescript
export async function updateSlaSummaries(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  const window30d = now - 30 * 86400;

  const rows = await env.DB.prepare(
    `SELECT endpoint, COUNT(*) AS total, SUM(CASE WHEN result = 'UP' THEN 1 ELSE 0 END) AS up_count
     FROM uptime_checks WHERE ts >= ? GROUP BY endpoint`,
  ).bind(window30d).all<{ endpoint: string; total: number; up_count: number }>();

  for (const row of rows.results) {
    const uptimePct = (row.up_count / row.total) * 100;
    await env.DB.prepare(
      `INSERT OR REPLACE INTO sla_summaries (period_start, period_end, endpoint, total_checks, up_checks, uptime_pct)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).bind(window30d, now, row.endpoint, row.total, row.up_count, uptimePct).run();

    await env.KV.put(`sla:${row.endpoint}`, JSON.stringify({ uptimePct, updatedAt: now }), { expirationTtl: 300 });
  }
}
```

## 4. wrangler.toml

```toml
[[d1_databases]]
binding       = "DB"
database_name = "availability-db"
database_id   = "<your-d1-id>"

[[kv_namespaces]]
binding = "KV"
id      = "<your-kv-id>"

[[queues.producers]]
binding = "ALERT_QUEUE"
queue   = "availability-alerts"

[triggers]
crons = ["*/5 * * * *"]
```

## Anti-patterns

- Running the monitor as part of the same Worker as the monitored service.
- Using KV alone for evidence — KV lacks the query capability auditors need.
- Checking only once per hour — five-nines SLA requires frequent checks.
- Storing uptime percentage only, not raw check records.

## Gotchas

- Cron Triggers fire at most once per minute; for sub-minute checks, chain Durable Object alarms.
- `AbortSignal.timeout()` is available in Workers runtime v3+.
- Cloudflare Cron Triggers do not guarantee execution from a specific region.

## Verification

```bash
wrangler d1 execute availability-db \
  --command "SELECT ts, endpoint, result, latency_ms FROM uptime_checks ORDER BY ts DESC LIMIT 20;"

wrangler d1 execute availability-db \
  --command "SELECT endpoint, uptime_pct FROM sla_summaries ORDER BY period_end DESC;"
```

## Related

- `soc2-cc7-system-operations.md`
- `soc2-type2-controls-engineering.md`
- `business-continuity-plan.md`

## Sources

- AICPA TSC 2017 — Availability Criterion A1.1–A1.3
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1: https://developers.cloudflare.com/d1/
