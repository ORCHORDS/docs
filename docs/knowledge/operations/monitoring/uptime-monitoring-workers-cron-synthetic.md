# Uptime Monitoring Workers Cron Synthetic Checks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) has no automated uptime checks; incidents are
reported by users before the team notices. External synthetic
monitoring SaaS products add cost and introduce an external
dependency that itself can have outages. The team wants scheduled
health checks that run inside the Cloudflare network, persist uptime
history to D1, track incident state in KV, and push Slack
notifications without requiring an external monitoring platform.

## Context

Cloudflare Workers cron triggers execute a Worker's `scheduled`
handler on a POSIX-style cron schedule. The Worker can issue HTTP
requests to monitored endpoints, write pass/fail results to D1, and
read/write incident state from KV. Slack incoming webhooks accept
POST requests with a JSON body and deliver formatted messages to a
channel. This pattern runs entirely on the Cloudflare network with
zero external SaaS dependencies for the monitoring path itself.

## Worker and cron trigger setup

```toml
# wrangler.toml
name = "example project-uptime-monitor"
main = "src/monitor.ts"
compatibility_date = "2026-06-01"

[triggers]
crons = ["*/5 * * * *"]   # every 5 minutes

[[kv_namespaces]]
binding  = "INCIDENT_STATE"
id       = "KV_NAMESPACE_ID_HERE"

[[d1_databases]]
binding       = "UPTIME_LOG"
database_name = "example project-uptime"
database_id   = "D1_DATABASE_ID_HERE"

[vars]
SLACK_WEBHOOK_URL = ""   # set via wrangler secret
```

```typescript
// src/monitor.ts
const CHECKS: HealthCheck[] = [
  { name: 'api-health',   url: 'https://example.com/api/health',  timeout: 5000 },
  { name: 'web-home',     url: 'https://example.com/',            timeout: 8000 },
  { name: 'auth-check',   url: 'https://example.com/api/auth/status', timeout: 5000 },
];

export default {
  async scheduled(
    _event: ScheduledEvent,
    env:    Env,
    ctx:    ExecutionContext,
  ): Promise<void> {
    ctx.waitUntil(runChecks(env));
  },
};
```

## Health check execution

```typescript
interface HealthCheck { name: string; url: string; timeout: number; }
interface CheckResult {
  name:        string;
  up:          boolean;
  statusCode:  number;
  latencyMs:   number;
  error:       string | null;
  checkedAt:   string;   // ISO-8601
}

async function runChecks(env: Env): Promise<void> {
  const results: CheckResult[] = await Promise.all(
    CHECKS.map((check) => runSingleCheck(check)),
  );

  await Promise.all([
    writeToD1(results, env),
    handleIncidentState(results, env),
  ]);
}

async function runSingleCheck(check: HealthCheck): Promise<CheckResult> {
  const start = Date.now();
  try {
    const res = await fetch(check.url, {
      method:  'GET',
      signal:  AbortSignal.timeout(check.timeout),
      headers: { 'User-Agent': 'example project-uptime-monitor/1.0' },
    });
    return {
      name:       check.name,
      up:         res.ok,
      statusCode: res.status,
      latencyMs:  Date.now() - start,
      error:      null,
      checkedAt:  new Date().toISOString(),
    };
  } catch (err: any) {
    return {
      name:       check.name,
      up:         false,
      statusCode: 0,
      latencyMs:  Date.now() - start,
      error:      err.message ?? 'timeout',
      checkedAt:  new Date().toISOString(),
    };
  }
}
```

## D1 uptime log schema and queries

```sql
-- Run once via wrangler d1 execute example project-uptime --file=schema.sql
CREATE TABLE IF NOT EXISTS uptime_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,
  up          INTEGER NOT NULL,   -- 1 = up, 0 = down
  status_code INTEGER NOT NULL,
  latency_ms  INTEGER NOT NULL,
  error       TEXT,
  checked_at  TEXT    NOT NULL    -- ISO-8601
);

CREATE INDEX IF NOT EXISTS idx_uptime_name_time
  ON uptime_log (name, checked_at DESC);
```

```typescript
async function writeToD1(
  results: CheckResult[],
  env:     Env,
): Promise<void> {
  const stmts = results.map((r) =>
    env.UPTIME_LOG.prepare(
      `INSERT INTO uptime_log
         (name, up, status_code, latency_ms, error, checked_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).bind(r.name, r.up ? 1 : 0, r.statusCode, r.latencyMs, r.error, r.checkedAt),
  );
  await env.UPTIME_LOG.batch(stmts);
}
```

Querying uptime percentage and average latency:

```sql
-- 24-hour uptime % per endpoint
SELECT
  name,
  round(SUM(up) * 100.0 / COUNT(*), 2)  AS uptime_pct,
  round(AVG(latency_ms), 0)             AS avg_latency_ms,
  COUNT(*)                              AS checks
FROM uptime_log
WHERE checked_at > datetime('now', '-24 hours')
GROUP BY name
ORDER BY uptime_pct ASC;

-- Last 10 failures for a given endpoint
SELECT checked_at, status_code, latency_ms, error
FROM uptime_log
WHERE name = 'api-health' AND up = 0
ORDER BY checked_at DESC
LIMIT 10;
```

## KV incident state and Slack notification

```typescript
// KV key: "incident:{name}" — value: ISO-8601 of incident start or null

async function handleIncidentState(
  results: CheckResult[],
  env:     Env,
): Promise<void> {
  for (const result of results) {
    const kvKey      = `incident:${result.name}`;
    const openedAt   = await env.INCIDENT_STATE.get(kvKey);
    const wasDown    = openedAt !== null;
    const isDown     = !result.up;

    if (isDown && !wasDown) {
      // Incident opens
      await env.INCIDENT_STATE.put(kvKey, result.checkedAt);
      await notifySlack(env, {
        type:      'open',
        name:      result.name,
        openedAt:  result.checkedAt,
        error:     result.error ?? `HTTP ${result.statusCode}`,
      });
    } else if (!isDown && wasDown) {
      // Incident resolves
      await env.INCIDENT_STATE.delete(kvKey);
      await notifySlack(env, {
        type:      'resolve',
        name:      result.name,
        openedAt:  openedAt!,
        resolvedAt: result.checkedAt,
      });
    }
  }
}

async function notifySlack(
  env:     Env,
  payload: { type: string; name: string; openedAt: string; error?: string; resolvedAt?: string },
): Promise<void> {
  const icon    = payload.type === 'open' ? ':red_circle:' : ':large_green_circle:';
  const message = payload.type === 'open'
    ? `${icon} *example project DOWN* — \`${payload.name}\` is unreachable since ${payload.openedAt}.\nError: ${payload.error}`
    : `${icon} *example project RECOVERED* — \`${payload.name}\` is back up.\nDowntime from ${payload.openedAt} to ${payload.resolvedAt}`;

  await fetch(env.SLACK_WEBHOOK_URL, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ text: message }),
  });
}
```

| KV key format         | Value                  | TTL    | Meaning              |
|-----------------------|------------------------|--------|----------------------|
| `incident:api-health` | `2026-08-22T14:05:00Z` | none   | Incident open since  |
| (absent)              | —                      | —      | Endpoint is up       |

## Uptime SLO calculation from D1

```sql
-- 30-day uptime % (288 checks/day at 5-min interval = 8640 checks)
SELECT
  name,
  COUNT(*)                                AS total_checks,
  SUM(up)                                 AS up_checks,
  round(SUM(up) * 100.0 / COUNT(*), 4)   AS uptime_pct,
  round(
    (COUNT(*) - SUM(up)) * 5.0 / 60, 1
  )                                       AS downtime_minutes
FROM uptime_log
WHERE checked_at > datetime('now', '-30 days')
GROUP BY name;
```

A 99.9% SLO over 30 days allows 43.2 minutes of downtime.
At 5-minute check intervals, that is 8–9 failing checks before
the SLO budget is consumed.

## Anti-patterns

- **Running checks every 1 minute** — D1 accumulates 1 440 rows/day
  per endpoint at 1-min intervals; at 5-min intervals it is 288,
  which is trivially queryable. For 1-min resolution, use Cloudflare
  Queues to batch inserts.
- **Not using `AbortSignal.timeout`** — a hanging upstream server
  can block the Worker until the 30 s CPU time limit; always set an
  explicit timeout per check.
- **Storing incident state in D1** — D1 reads inside a scheduled
  Worker add latency and count against D1 row reads; KV is the right
  store for tiny, frequently-read key/value state.
- **Alerting on the first failure** — a single 5-min check failure
  can be a transient network blip; require 2 consecutive failures
  (openedAt set after second failure) before notifying Slack.
- **Deleting D1 uptime rows** — historical uptime data is audit
  evidence for SLO reviews; set a retention policy via scheduled
  cleanup rather than deleting on read.

## Gotchas

- Cron triggers have a minimum interval of 1 minute on all plans.
  Sub-minute synthetic checking requires an external trigger or
  Durable Object alarms.
- `ctx.waitUntil` is required in scheduled handlers: without it,
  the Worker may terminate before D1 writes and Slack notifications
  complete.
- D1 `batch()` is not transactional across multiple statements in
  the current API; a partial failure leaves some rows written.
  Wrap critical inserts in explicit transactions with
  `BEGIN`/`COMMIT` if all-or-nothing semantics are needed.
- KV `get` returns `null` for missing keys and `null` for expired
  keys — the two cases are indistinguishable, which is acceptable
  here since both mean "no open incident".
- Slack webhook URLs are secrets; never commit them to the repo.
  Store via `wrangler secret put SLACK_WEBHOOK_URL`.

## Verification

- Deploy to staging; temporarily point a check URL at a non-existent
  path; confirm Slack alert fires within 10 min (two cron cycles).
- Fix the URL; confirm Slack recovery message fires on the next
  passing check.
- Query D1: `SELECT COUNT(*) FROM uptime_log WHERE checked_at >
  datetime('now', '-1 hour')` — should show 12 rows per endpoint
  after one hour (5-min interval × 3 checks = 36 total rows).
- Verify KV incident key is absent after recovery:
  `wrangler kv key get --binding=INCIDENT_STATE "incident:api-health"`.
- Confirm `SLACK_WEBHOOK_URL` is not exposed in `wrangler.toml`:
  `grep SLACK_WEBHOOK_URL wrangler.toml` must return no match.

## Related

- `documentation/docs/policies/monitoring/cron-job-monitoring.md`
- `documentation/docs/policies/monitoring/synthetic-monitoring-uptime-checks.md`
- `documentation/docs/policies/monitoring/health-check-endpoint-design.md`
- `documentation/docs/policies/monitoring/uptime-monitoring-patterns.md`
- `documentation/docs/policies/monitoring/slo-error-budgets-burn-rate-alerting.md`
- `documentation/docs/policies/cloudflare/d1-database-patterns.md`

## Sources

- Workers cron triggers —
  https://developers.cloudflare.com/workers/configuration/cron-triggers/
- D1 batch API —
  https://developers.cloudflare.com/d1/worker-api/prepared-statements/#batch-statements
- Workers KV —
  https://developers.cloudflare.com/kv/api/
- Slack incoming webhooks —
  https://api.slack.com/messaging/webhooks
- `AbortSignal.timeout` (MDN) —
  https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
