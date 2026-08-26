# Dead Man's Switch Monitoring with Workers Cron

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A background service (queue consumer, scheduled job, external process) must report in periodically. If it goes silent — crashes, hangs, or loses connectivity — you want an alert fired within minutes. The "dead man's switch" pattern inverts normal alerting: silence is the failure condition.

## Context

Cloudflare Workers Cron Triggers run on a configurable schedule without an external orchestrator. Combined with D1 for persistent last-seen timestamps and an outbound HTTP call to a notification service (PagerDuty, Opsgenie, Slack webhook), you get a fully serverless dead man's switch with no external dependencies to monitor the monitor.

Two roles:
1. **Heartbeat endpoint** — receives HTTP pings from the monitored service, records the timestamp in D1.
2. **Watchdog Cron** — runs every minute, checks D1 for overdue services, fires an alert if the last heartbeat is older than the configured threshold.

---

## Section 1 — D1 schema

```sql
-- migrations/0001_heartbeats.sql
CREATE TABLE IF NOT EXISTS services (
  id            TEXT    PRIMARY KEY,
  display_name  TEXT    NOT NULL,
  threshold_sec INTEGER NOT NULL DEFAULT 300,  -- alert if silent > 5 min
  alert_url     TEXT    NOT NULL,              -- webhook to POST to
  last_seen_at  INTEGER,                       -- Unix ms, nullable = never seen
  alerted       INTEGER NOT NULL DEFAULT 0     -- 0/1 boolean; avoids alert storms
);

-- Seed example service
INSERT OR IGNORE INTO services (id, display_name, threshold_sec, alert_url)
VALUES (
  'nightly-etl',
  'Nightly ETL Job',
  900,
  'https://hooks.slack.com/services/T000/B000/xxxx'
);
```

## Section 2 — Worker entrypoint (heartbeat + watchdog)

```typescript
// dms-worker/src/index.ts
export interface Env {
  HEARTBEATS_DB: D1Database;
  API_SECRET: string;  // shared secret for heartbeat endpoint
}

interface Service {
  id:            string;
  display_name:  string;
  threshold_sec: number;
  alert_url:     string;
  last_seen_at:  number | null;
  alerted:       number;
}

export default {
  // Cron handler — runs on schedule
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runWatchdog(env));
  },

  // HTTP handler — receives heartbeat pings
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname.startsWith('/heartbeat/')) {
      return handleHeartbeat(request, url, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleHeartbeat(
  request: Request,
  url: URL,
  env: Env
): Promise<Response> {
  // Authenticate
  const secret = <redacted-secret>'x-api-secret');
  if (secret !== env.API_SECRET) {
    return new Response('Unauthorized', { status: 401 });
  }

  const serviceId = url.pathname.replace('/heartbeat/', '');
  if (!serviceId) return new Response('Bad Request', { status: 400 });

  const now = Date.now();
  const result = await env.HEARTBEATS_DB.prepare(
    `UPDATE services
     SET last_seen_at = ?, alerted = 0
     WHERE id = ?`
  ).bind(now, serviceId).run();

  if (result.meta.changes === 0) {
    return new Response('Service not found', { status: 404 });
  }

  return new Response(JSON.stringify({ ok: true, ts: now }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Section 3 — Watchdog logic

```typescript
// dms-worker/src/watchdog.ts
import type { Env, Service } from './index';

export async function runWatchdog(env: Env): Promise<void> {
  const now = Date.now();

  const { results } = await env.HEARTBEATS_DB.prepare(
    'SELECT * FROM services'
  ).all<Service>();

  const overdueServices = results.filter((svc) => {
    if (svc.last_seen_at === null) {
      // Never seen — only alert after 2× threshold to allow cold start
      return now > svc.threshold_sec * 2 * 1000;
    }
    const silentMs = now - svc.last_seen_at;
    return silentMs > svc.threshold_sec * 1000;
  });

  for (const svc of overdueServices) {
    if (svc.alerted === 1) continue;  // already alerted, wait for recovery

    await fireAlert(svc, now, env);

    await env.HEARTBEATS_DB.prepare(
      'UPDATE services SET alerted = 1 WHERE id = ?'
    ).bind(svc.id).run();
  }
}

async function fireAlert(svc: Service, now: number, _env: Env): Promise<void> {
  const silentFor = svc.last_seen_at
    ? Math.round((now - svc.last_seen_at) / 1000)
    : 'never';

  const body = JSON.stringify({
    text: `DEAD MAN'S SWITCH: *${svc.display_name}* has not reported in ` +
          `for ${silentFor} seconds (threshold: ${svc.threshold_sec}s).`,
  });

  const res = await fetch(svc.alert_url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });

  if (!res.ok) {
    console.error(`Alert failed for ${svc.id}: HTTP ${res.status}`);
  }
}
```

## Section 4 — wrangler.toml

```toml
# dms-worker/wrangler.toml
name = "dms-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[triggers]
crons = ["* * * * *"]  # every minute

[[d1_databases]]
binding     = "HEARTBEATS_DB"
database_name = "heartbeats"
database_id = "<your-d1-id>"

[vars]
# API_SECRET should be set as a secret, not a plain var
```

```bash
# Set the shared secret
wrangler secret put API_SECRET

# Deploy
wrangler deploy --config dms-worker/wrangler.toml

# Apply migration
wrangler d1 migrations apply heartbeats --remote

# Send a test heartbeat from the monitored service
curl -s -X POST https://dms-worker.example.com/heartbeat/nightly-etl \
  -H 'x-api-secret: your-secret'
```

## Anti-patterns

- **Alerting on every cron tick once overdue** — without the `alerted` flag you'll send a notification every minute until recovery. Set the flag and clear it on the next successful heartbeat.
- **Using KV for `last_seen_at`** — KV is eventually consistent. A crash scenario could produce a stale read that suppresses an alert. D1 is strongly consistent within a region.
- **Hard-coding thresholds** — store them per service in D1 so you can adjust without redeploying.
- **No authentication on the heartbeat endpoint** — anyone can reset a dead man's switch. Always verify a shared secret or mTLS.

## Gotchas

- Cron Workers have a 30-second CPU time limit on the Free plan and 15 minutes on Paid. Watchdog logic is O(services) and well within limits, but avoid heavy D1 queries in the loop.
- `ScheduledEvent` does not have a `request` property — you cannot access HTTP headers from a cron handler.
- Workers Cron fires "approximately" on schedule — expect ±30-second jitter. Account for this in your threshold values (add a buffer of at least 2× the cron interval).
- D1 in the free tier has a 100 k row-read limit per day. For a 1-minute cron with 10 services that's 14 400 reads/day — well within budget.

## Verification

```bash
# Check last_seen_at for all services
wrangler d1 execute heartbeats --remote \
  --command "SELECT id, display_name, last_seen_at, alerted FROM services;"

# Simulate silence: set last_seen_at to an hour ago
wrangler d1 execute heartbeats --remote \
  --command "UPDATE services SET last_seen_at = unixepoch() * 1000 - 3600000 WHERE id = 'nightly-etl';"

# Wait ~1 minute, then check alerted flag
wrangler d1 execute heartbeats --remote \
  --command "SELECT id, alerted FROM services;"
```

## Related

- `workers-multi-environment-status-dashboard.md` — aggregating health across environments
- `workers-tail-worker-request-sampling.md` — complementary observability pattern
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://en.wikipedia.org/wiki/Dead_man%27s_switch
