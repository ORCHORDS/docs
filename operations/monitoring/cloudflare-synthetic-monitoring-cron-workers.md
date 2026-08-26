# Synthetic Monitoring with Cron Triggers and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need continuous external uptime monitoring for critical API endpoints and want to avoid third-party SaaS fees, while keeping probes, uptime history, and alerts entirely on Cloudflare infrastructure.

## Context

A Worker with a Cron Trigger fires on a schedule (as often as every minute on paid plans). Each invocation sends HTTP probes to a list of endpoints, measures response time and HTTP status, persists results to D1, and evaluates consecutive-failure alerting logic. PagerDuty Events API v2 is used for on-call escalation. All state lives in D1 — no KV, no external dependencies.

---

## Core Synthetic Monitor Worker

```typescript
// src/synthetic-monitor.ts
export interface Env {
  DB: D1Database;
  PAGERDUTY_ROUTING_KEY: string;
  PROBE_TIMEOUT_MS: string;        // default "10000"
  FAILURE_THRESHOLD: string;       // consecutive failures before alert, default "3"
}

interface EndpointConfig {
  name: string;
  url: string;
  method?: string;
  expectedStatus?: number;
  expectedBodyContains?: string;
}

const ENDPOINTS: EndpointConfig[] = [
  {
    name: 'api-health',
    url: 'https://api.example.com/health',
    expectedStatus: 200,
    expectedBodyContains: '"status":"ok"',
  },
  {
    name: 'api-checkout',
    url: 'https://api.example.com/checkout',
    method: 'OPTIONS',
    expectedStatus: 204,
  },
  {
    name: 'www-homepage',
    url: 'https://www.example.com/',
    expectedStatus: 200,
  },
];

async function probeEndpoint(
  cfg: EndpointConfig,
  timeoutMs: number
): Promise<{ ok: boolean; status: number; latencyMs: number; error?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const start = performance.now();

  try {
    const resp = await fetch(cfg.url, {
      method: cfg.method ?? 'GET',
      signal: controller.signal,
      headers: { 'User-Agent': 'orchords-synthetic/1.0' },
    });
    const latencyMs = Math.round(performance.now() - start);
    clearTimeout(timer);

    const body = await resp.text();
    const statusOk = resp.status === (cfg.expectedStatus ?? 200);
    const bodyOk = cfg.expectedBodyContains
      ? body.includes(cfg.expectedBodyContains)
      : true;

    return {
      ok: statusOk && bodyOk,
      status: resp.status,
      latencyMs,
      error: !statusOk
        ? `Unexpected status ${resp.status}`
        : !bodyOk
        ? 'Body assertion failed'
        : undefined,
    };
  } catch (err) {
    clearTimeout(timer);
    return {
      ok: false,
      status: 0,
      latencyMs: Math.round(performance.now() - start),
      error: String(err),
    };
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const timeoutMs = parseInt(env.PROBE_TIMEOUT_MS ?? '10000', 10);
    const failureThreshold = parseInt(env.FAILURE_THRESHOLD ?? '3', 10);

    for (const cfg of ENDPOINTS) {
      const result = await probeEndpoint(cfg, timeoutMs);

      // Persist result
      await env.DB.prepare(
        `INSERT INTO synthetic_checks (endpoint, status, latency_ms, ok, error, checked_at)
         VALUES (?, ?, ?, ?, ?, datetime('now'))`
      ).bind(
        cfg.name,
        result.status,
        result.latencyMs,
        result.ok ? 1 : 0,
        result.error ?? null
      ).run();

      // Evaluate consecutive failures
      if (!result.ok) {
        const { results } = await env.DB.prepare(
          `SELECT ok FROM synthetic_checks
           WHERE endpoint = ?
           ORDER BY checked_at DESC
           LIMIT ?`
        ).bind(cfg.name, failureThreshold).all<{ ok: number }>();

        const allFailed =
          results.length === failureThreshold &&
          results.every((r) => r.ok === 0);

        if (allFailed) {
          await triggerPagerDuty(env.PAGERDUTY_ROUTING_KEY, cfg.name, result);
        }
      }
    }
  },
};
```

---

## D1 Schema

```sql
-- migrations/0001_synthetic_checks.sql
CREATE TABLE IF NOT EXISTS synthetic_checks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint    TEXT    NOT NULL,
  status      INTEGER NOT NULL,
  latency_ms  INTEGER NOT NULL,
  ok          INTEGER NOT NULL DEFAULT 1,  -- 1=pass, 0=fail
  error       TEXT,
  checked_at  TEXT    NOT NULL
);

CREATE INDEX idx_sc_endpoint_checked ON synthetic_checks (endpoint, checked_at);

-- 24-hour uptime view
CREATE VIEW uptime_24h AS
  SELECT
    endpoint,
    COUNT(*)                               AS total_checks,
    SUM(ok)                                AS passed_checks,
    ROUND(100.0 * SUM(ok) / COUNT(*), 2)   AS uptime_pct,
    ROUND(AVG(latency_ms), 1)              AS avg_latency_ms
  FROM synthetic_checks
  WHERE checked_at >= datetime('now', '-24 hours')
  GROUP BY endpoint;
```

---

## PagerDuty Alert Function

```typescript
async function triggerPagerDuty(
  routingKey: string,
  endpointName: string,
  result: { status: number; latencyMs: number; error?: string }
): Promise<void> {
  await fetch('https://events.pagerduty.com/v2/enqueue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: routingKey,
      event_action: 'trigger',
      dedup_key: `synthetic-${endpointName}`,
      payload: {
        summary: `Synthetic check FAILED: ${endpointName}`,
        severity: 'critical',
        source: 'cloudflare-synthetic-monitor',
        custom_details: {
          endpoint: endpointName,
          http_status: result.status,
          latency_ms: result.latencyMs,
          error: result.error,
        },
      },
    }),
  });
}
```

---

## Uptime Percentage Query

```typescript
export async function getUptime24h(db: D1Database): Promise<Record<string, unknown>[]> {
  const result = await db.prepare(`SELECT * FROM uptime_24h ORDER BY uptime_pct ASC`).all();
  return result.results as Record<string, unknown>[];
}
```

---

## wrangler.toml

```toml
name = "synthetic-monitor"

[[triggers]]
crons = ["* * * * *"]   # every minute (requires Workers Paid plan)

[[d1_databases]]
binding       = "DB"
database_name = "synthetic-monitor-db"
database_id   = "<your-d1-id>"

[vars]
PROBE_TIMEOUT_MS   = "10000"
FAILURE_THRESHOLD  = "3"
```

---

## Anti-patterns

- **Probing from a single region** — Cron Triggers fire from a single PoP; use Workers for Platforms or queue-based fan-out to multi-region if geographic diversity is required.
- **Alerting on the first failure** — transient network blips cause false positives; always require N consecutive failures.
- **Storing full response bodies in D1** — synthetic_checks rows will balloon in size; store only the error string (bounded to e.g. 500 chars).
- **Not deduplicating PagerDuty alerts** — without `dedup_key`, every check interval fires a new incident; the dedup key suppresses repeat triggers while an incident is open.

## Gotchas

- Cron Triggers run at most once per minute and may be delayed by up to 30 seconds under high platform load.
- Workers cannot make outbound requests to `localhost` or RFC-1918 private addresses; probe only publicly routable URLs.
- The `AbortController` timer must be cleared on success to avoid a dangling reference causing the Worker to remain alive past its CPU budget.
- D1 `datetime('now')` returns UTC; ensure your uptime dashboards display times in UTC or convert server-side.

## Verification

1. Deploy the Worker and run the migration: `wrangler d1 execute synthetic-monitor-db --file migrations/0001_synthetic_checks.sql`
2. Trigger manually: `wrangler trigger --cron`
3. Check D1: `wrangler d1 execute synthetic-monitor-db --command "SELECT * FROM synthetic_checks ORDER BY checked_at DESC LIMIT 10;"`
4. Temporarily set an endpoint URL to `https://httpstat.us/503` and wait for 3 cron cycles; verify a PagerDuty incident is created.
5. Restore the URL; verify the incident auto-resolves on the next successful check (add a PagerDuty resolve call if needed).

## Related

- `d1-slow-query-detection-tail-workers.md`
- `durable-objects-websocket-connection-monitoring.md`
- `workers-latency-percentile-tracking-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developer.pagerduty.com/api-reference/YXBpOjI3NDgyNjU-pager-duty-v2-events-api
