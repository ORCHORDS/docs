# Multi-Endpoint Health Check: Cron + D1 History + KV Status Cache

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an always-on health check system that probes multiple HTTP endpoints every minute, persists check history in D1 for trend analysis, caches the current status in KV for sub-millisecond reads, serves a JSON status page, and fires an alert after N consecutive failures — all without external uptime services.

## Context

- Workers Cron Trigger (every minute) probes endpoints
- D1 stores `checks` table with full history (pruned to 7 days)
- KV stores current aggregate status as serialised JSON (TTL 90s)
- Separate fetch handler serves `/status` JSON and `/status/ui` HTML
- Stack: Workers (TypeScript), D1, KV, Wrangler 3.x

---

## Step 1 — D1 Schema and KV Namespace

```bash
# Create resources
wrangler d1 create health-checks-db
wrangler kv:namespace create HEALTH_STATUS
```

```sql
-- migrations/0001_create_checks.sql
CREATE TABLE IF NOT EXISTS checks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint   TEXT    NOT NULL,
  status     INTEGER NOT NULL,   -- HTTP status, 0 = connection error
  latency_ms INTEGER NOT NULL,
  ok         INTEGER NOT NULL,   -- 1 = healthy, 0 = unhealthy
  checked_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checks_endpoint_time
  ON checks (endpoint, checked_at DESC);

-- Prune rows older than 7 days (called from cron)
CREATE INDEX IF NOT EXISTS idx_checks_time ON checks (checked_at);
```

```bash
wrangler d1 migrations apply health-checks-db --remote
```

## Step 2 — wrangler.toml

```toml
name = "health-check-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "health-checks-db"
database_id   = "<your-d1-id>"

[[kv_namespaces]]
binding = "HEALTH_KV"
id      = "<your-kv-id>"

[vars]
ENDPOINTS = "https://api.example.com/health,https://app.example.com/ping,https://admin.example.com/ready"
FAILURE_THRESHOLD = "3"   # consecutive failures before alert
ALERT_WEBHOOK_URL = ""    # Slack incoming webhook

[[triggers.crons]]
crons = ["* * * * *"]
```

## Step 3 — Worker Implementation

```typescript
// src/index.ts
interface Env {
  DB: D1Database;
  HEALTH_KV: KVNamespace;
  ENDPOINTS: string;
  FAILURE_THRESHOLD: string;
  ALERT_WEBHOOK_URL: string;
}

interface CheckResult {
  endpoint: string;
  status: number;
  latency_ms: number;
  ok: boolean;
  checked_at: string;
}

interface AggregateStatus {
  healthy: boolean;
  checks: CheckResult[];
  consecutive_failures: Record<string, number>;
  updated_at: string;
}

async function probeEndpoint(url: string): Promise<CheckResult> {
  const start = Date.now();
  const checked_at = new Date().toISOString();
  try {
    const res = await fetch(url, {
      method: 'GET',
      signal: AbortSignal.timeout(10_000),
      headers: { 'User-Agent': 'orchords-healthcheck/1.0' },
    });
    const latency_ms = Date.now() - start;
    return { endpoint: url, status: res.status, latency_ms, ok: res.ok, checked_at };
  } catch (err) {
    return { endpoint: url, status: 0, latency_ms: Date.now() - start, ok: false, checked_at };
  }
}

async function getConsecutiveFailures(
  db: D1Database,
  endpoint: string,
  threshold: number
): Promise<number> {
  // Count trailing failures (most recent rows first)
  const rows = await db
    .prepare(
      `SELECT ok FROM checks WHERE endpoint = ? ORDER BY checked_at DESC LIMIT ?`
    )
    .bind(endpoint, threshold + 5)
    .all<{ ok: number }>();

  let consecutive = 0;
  for (const row of rows.results ?? []) {
    if (row.ok === 0) consecutive++;
    else break;
  }
  return consecutive;
}

async function sendAlert(webhookUrl: string, message: string): Promise<void> {
  if (!webhookUrl) return;
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: message }),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const endpoints = env.ENDPOINTS.split(',').map(e => e.trim()).filter(Boolean);
    const threshold = parseInt(env.FAILURE_THRESHOLD, 10);

    // Probe all endpoints in parallel
    const results = await Promise.all(endpoints.map(probeEndpoint));

    // Persist to D1 in one batch
    const stmt = env.DB.prepare(
      `INSERT INTO checks (endpoint, status, latency_ms, ok, checked_at)
       VALUES (?, ?, ?, ?, ?)`
    );
    await env.DB.batch(
      results.map(r =>
        stmt.bind(r.endpoint, r.status, r.latency_ms, r.ok ? 1 : 0, r.checked_at)
      )
    );

    // Prune old data
    await env.DB
      .prepare(`DELETE FROM checks WHERE checked_at < datetime('now', '-7 days')`)
      .run();

    // Compute consecutive failure counts and check alert threshold
    const failures: Record<string, number> = {};
    for (const r of results) {
      if (!r.ok) {
        const count = await getConsecutiveFailures(env.DB, r.endpoint, threshold);
        failures[r.endpoint] = count;
        if (count >= threshold) {
          await sendAlert(
            env.ALERT_WEBHOOK_URL,
            `:red_circle: *ALERT* ${r.endpoint} has failed ${count} consecutive checks. Last status: ${r.status}`
          );
        }
      }
    }

    // Update KV cache
    const aggregate: AggregateStatus = {
      healthy: results.every(r => r.ok),
      checks: results,
      consecutive_failures: failures,
      updated_at: new Date().toISOString(),
    };
    await env.HEALTH_KV.put('current_status', JSON.stringify(aggregate), { expirationTtl: 90 });
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/status') {
      const cached = await env.HEALTH_KV.get('current_status');
      if (cached) {
        const data = JSON.parse(cached) as AggregateStatus;
        return Response.json(data, {
          headers: { 'Cache-Control': 'public, max-age=30' },
          status: data.healthy ? 200 : 503,
        });
      }
      return Response.json({ error: 'no data yet' }, { status: 503 });
    }

    if (url.pathname === '/status/history') {
      const endpoint = url.searchParams.get('endpoint') ?? '';
      const limit    = Math.min(parseInt(url.searchParams.get('limit') ?? '100', 10), 500);
      const rows = await env.DB
        .prepare(
          `SELECT endpoint, status, latency_ms, ok, checked_at
           FROM checks
           WHERE (? = '' OR endpoint = ?)
           ORDER BY checked_at DESC
           LIMIT ?`
        )
        .bind(endpoint, endpoint, limit)
        .all();
      return Response.json(rows.results);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Anti-patterns

- Running D1 writes synchronously inside `ctx.waitUntil` without batching — use `db.batch()` for all inserts per cron tick
- Setting KV TTL equal to the cron interval (60s) — if the cron is delayed, clients see stale 503 data; use 90s TTL
- Probing endpoints sequentially — `Promise.all` cuts total latency from N×10s to 10s
- Alerting on every single failure — wait for N consecutive failures to avoid noise from transient blips

## Gotchas

- D1 free tier: 5M row reads/day. With 3 endpoints × 1440 checks/day = 4320 inserts plus ~15k reads for failure counts — well within limits
- Workers Cron minimum interval is 1 minute; for sub-minute health checks use Durable Objects with `alarm()`
- KV reads are eventually consistent across regions; for a global fleet the cached status may lag by a few seconds
- `AbortSignal.timeout()` requires compatibility date ≥ 2023-03-01
- D1 `db.batch()` is atomic per batch; a single failed statement rolls back the entire batch

## Verification

```bash
# Trigger cron manually via API
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/health-check-worker/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq .

# Query D1 for last 10 checks
wrangler d1 execute health-checks-db --remote \
  --command "SELECT endpoint, status, latency_ms, ok, checked_at FROM checks ORDER BY checked_at DESC LIMIT 10;"

# Check KV current status
wrangler kv:key get --namespace-id=$KV_NS_ID current_status | jq .

# Hit the status endpoint
curl -s https://health-check-worker.<your-subdomain>.workers.dev/status | jq .
```

## Related

- `documentation/categories/monitoring/workers-slo-error-budget-burn-rate-analytics.md`
- `documentation/categories/monitoring/workers-anomaly-detection-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
