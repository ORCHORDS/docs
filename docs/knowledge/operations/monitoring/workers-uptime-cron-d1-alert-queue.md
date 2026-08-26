# Uptime Monitoring with Cron Triggers, D1, and Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need a lightweight uptime monitor that checks a set of URLs on a fixed schedule, persists check history in D1, and sends PagerDuty or Slack alerts after consecutive failures — all without managing external infrastructure. Cloudflare Cron Triggers, D1, and Queues make this possible entirely within the Workers platform.

---

## Context
Cloudflare Cron Triggers fire the Worker's `scheduled()` handler on a cron schedule (minimum 1-minute intervals on the Workers Paid plan, 1-hour on Free). Each invocation fetches the configured target URLs, records `{ url, status, latency, ts }` in a D1 `uptime_checks` table, and checks the last N consecutive results for each URL. When a URL has failed N times in a row, the handler enqueues an alert message. The Queue consumer sends the alert to PagerDuty (Events v2 API) or Slack (Incoming Webhooks). D1 also serves as the data source for a 30-day availability dashboard query.

---

## Setup / Config

```toml
# wrangler.toml
name = "uptime-monitor"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["*/5 * * * *"]   # every 5 minutes

[[d1_databases]]
binding = "DB"
database_name = "uptime"
database_id = "YOUR_DATABASE_ID"

[[queues.producers]]
binding = "ALERT_QUEUE"
queue = "uptime-alerts"

[[queues.consumers]]
queue = "uptime-alerts"
max_batch_size = 10
max_batch_timeout = 30

[vars]
CONSECUTIVE_FAILURE_THRESHOLD = "3"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T.../B.../..."
PAGERDUTY_ROUTING_KEY = "your-32-char-routing-key"
# Comma-separated list of URLs to monitor
TARGET_URLS = "https://example.com,https://api.example.com/health"
```

```bash
# Create the D1 database
wrangler d1 create uptime

# Apply the schema
wrangler d1 execute uptime --file ./schema.sql
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS uptime_checks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  url         TEXT    NOT NULL,
  status      INTEGER NOT NULL,   -- HTTP status code, or 0 for network error
  latency_ms  REAL    NOT NULL,
  ok          INTEGER NOT NULL,   -- 1 = success (2xx), 0 = failure
  ts          INTEGER NOT NULL    -- Unix timestamp seconds
);

CREATE INDEX IF NOT EXISTS idx_uptime_url_ts ON uptime_checks(url, ts DESC);

CREATE TABLE IF NOT EXISTS alert_state (
  url         TEXT PRIMARY KEY,
  alerted_at  INTEGER             -- Unix timestamp of last alert sent, NULL if resolved
);
```

---

## Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  ALERT_QUEUE: Queue<AlertMessage>;
  CONSECUTIVE_FAILURE_THRESHOLD: string;
  SLACK_WEBHOOK_URL: string;
  PAGERDUTY_ROUTING_KEY: string;
  TARGET_URLS: string;
}

export interface UptimeCheck {
  url: string;
  status: number;
  latency_ms: number;
  ok: number;
  ts: number;
}

export interface AlertMessage {
  url: string;
  consecutiveFailures: number;
  lastStatus: number;
  ts: number;
}

/** Fetch a single URL and record the result. */
async function checkUrl(url: string): Promise<UptimeCheck> {
  const start = Date.now();
  let status = 0;
  let ok = 0;

  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "follow",
      signal: AbortSignal.timeout(10_000), // 10-second timeout
    });
    status = response.status;
    ok = response.ok ? 1 : 0;
  } catch {
    // Network error, DNS failure, timeout, etc.
    status = 0;
    ok = 0;
  }

  return {
    url,
    status,
    latency_ms: Date.now() - start,
    ok,
    ts: Math.floor(Date.now() / 1000),
  };
}

/** Persist a check result to D1. */
async function saveCheck(db: D1Database, check: UptimeCheck): Promise<void> {
  await db
    .prepare(
      "INSERT INTO uptime_checks (url, status, latency_ms, ok, ts) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(check.url, check.status, check.latency_ms, check.ok, check.ts)
    .run();
}

/** Count consecutive failures for a URL (most recent N checks). */
async function countConsecutiveFailures(
  db: D1Database,
  url: string,
  limit: number
): Promise<number> {
  const rows = await db
    .prepare(
      "SELECT ok FROM uptime_checks WHERE url = ? ORDER BY ts DESC LIMIT ?"
    )
    .bind(url, limit)
    .all<{ ok: number }>();

  let count = 0;
  for (const row of rows.results) {
    if (row.ok === 0) count++;
    else break; // stop at first success
  }
  return count;
}

/**
 * Determine whether an alert should fire:
 * - Threshold consecutive failures must be reached
 * - Must not already have an active (unresolved) alert
 */
async function shouldAlert(
  db: D1Database,
  url: string,
  failures: number,
  threshold: number
): Promise<boolean> {
  if (failures < threshold) return false;

  const state = await db
    .prepare("SELECT alerted_at FROM alert_state WHERE url = ?")
    .bind(url)
    .first<{ alerted_at: number | null }>();

  // Already alerted and not yet resolved
  return state === null || state.alerted_at === null;
}

/** Mark alert as sent in D1. */
async function markAlerted(db: D1Database, url: string, ts: number): Promise<void> {
  await db
    .prepare(
      "INSERT INTO alert_state (url, alerted_at) VALUES (?, ?) ON CONFLICT(url) DO UPDATE SET alerted_at = excluded.alerted_at"
    )
    .bind(url, ts)
    .run();
}

/** Clear alert state when URL recovers. */
async function clearAlertState(db: D1Database, url: string): Promise<void> {
  await db
    .prepare("UPDATE alert_state SET alerted_at = NULL WHERE url = ?")
    .bind(url)
    .run();
}

export default {
  /** Cron handler — runs on schedule */
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const urls = env.TARGET_URLS.split(",").map((u) => u.trim()).filter(Boolean);
    const threshold = parseInt(env.CONSECUTIVE_FAILURE_THRESHOLD, 10);

    // Run all checks concurrently
    const checks = await Promise.all(urls.map((url) => checkUrl(url)));

    // Persist and evaluate each result
    await Promise.all(
      checks.map(async (check) => {
        await saveCheck(env.DB, check);

        if (check.ok === 1) {
          // URL recovered — clear alert state so next failure triggers a fresh alert
          await clearAlertState(env.DB, check.url);
          return;
        }

        const failures = await countConsecutiveFailures(env.DB, check.url, threshold);

        if (await shouldAlert(env.DB, check.url, failures, threshold)) {
          const msg: AlertMessage = {
            url: check.url,
            consecutiveFailures: failures,
            lastStatus: check.status,
            ts: check.ts,
          };
          await env.ALERT_QUEUE.send(msg);
          await markAlerted(env.DB, check.url, check.ts);
          console.log(`[uptime] alert queued for ${check.url} after ${failures} failures`);
        }
      })
    );
  },

  /** Queue consumer — sends the actual alert */
  async queue(
    batch: MessageBatch<AlertMessage>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      const alert = message.body;

      // Send to Slack
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `*Uptime Alert*: \`${alert.url}\` has failed ${alert.consecutiveFailures} times in a row (last HTTP ${alert.lastStatus}).`,
        }),
      });

      // Send to PagerDuty Events v2
      await fetch("https://events.pagerduty.com/v2/enqueue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_ROUTING_KEY,
          event_action: "trigger",
          dedup_key: `uptime-${encodeURIComponent(alert.url)}`,
          payload: {
            summary: `${alert.url} is down (${alert.consecutiveFailures} consecutive failures)`,
            severity: "critical",
            source: "cloudflare-uptime-monitor",
            custom_details: {
              url: alert.url,
              last_http_status: alert.lastStatus,
              consecutive_failures: alert.consecutiveFailures,
              ts: new Date(alert.ts * 1000).toISOString(),
            },
          },
        }),
      });

      message.ack();
    }
  },

  // Needed so the Worker handles both scheduled and queue events
  async fetch(_request: Request, _env: Env): Promise<Response> {
    return new Response("uptime monitor", { status: 200 });
  },
};
```

---

## 30-Day Availability Query

```sql
-- Availability percentage per URL over the last 30 days
SELECT
  url,
  COUNT(*)                                              AS total_checks,
  SUM(ok)                                               AS successful_checks,
  ROUND(SUM(ok) * 100.0 / COUNT(*), 4)                 AS availability_pct,
  ROUND(AVG(latency_ms), 2)                             AS avg_latency_ms,
  ROUND(MAX(latency_ms), 2)                             AS max_latency_ms
FROM uptime_checks
WHERE ts >= strftime('%s', 'now', '-30 days')
GROUP BY url
ORDER BY availability_pct ASC;
```

```bash
# Run the availability report from the CLI
wrangler d1 execute uptime \
  --command "SELECT url, ROUND(SUM(ok)*100.0/COUNT(*),4) AS avail_pct FROM uptime_checks WHERE ts >= strftime('%s','now','-30 days') GROUP BY url ORDER BY avail_pct ASC;"
```

---

## Anti-patterns
- **Sending the alert inside the `scheduled()` handler with `await fetch()`** — if the downstream alert service is slow or flaky, the cron handler timeout (30 seconds) can be exhausted; always delegate alerting to the Queue consumer.
- **Not deduplicating alerts** — without the `alert_state` table, every cron tick while a URL is down will trigger a new page; use `dedup_key` in PagerDuty and the `alert_state` guard in D1.
- **Checking a single data point for failure** — a single 503 during a rolling deploy is not an outage; always require N consecutive failures before alerting.
- **Storing raw HTML responses in D1** — the `status` integer and `latency_ms` float are sufficient; storing response bodies inflates the database rapidly.
- **Using a 1-minute cron on the Free plan** — Free-tier Workers support minimum 1-hour cron intervals; use the Paid plan for 1- or 5-minute checks.

---

## Gotchas
- `AbortSignal.timeout()` requires `compatibility_date` ≥ `2023-03-01`; earlier dates need a manual `AbortController` with `setTimeout`.
- Cron Triggers do not retry on failure; if `scheduled()` throws, the check is simply skipped. Wrap the body in a `try/catch` and log the error.
- D1 `strftime('%s', 'now', '-30 days')` uses SQLite's datetime functions which are available in D1; do not use JavaScript `Date` arithmetic in SQL strings.
- The Queue consumer for `uptime-alerts` must be exported from the same Worker entrypoint (the `queue` export on the default export object) or as a separate Worker that consumes the same queue.
- PagerDuty's `dedup_key` must be consistent across retries for the same incident; use a stable key like `uptime-${encodeURIComponent(url)}` rather than including the timestamp.

---

## Verification

```bash
# Deploy the Worker
wrangler deploy

# Manually trigger the cron (only available in dashboard or via wrangler for testing)
wrangler dev --test-scheduled
# Then press 'S' in the wrangler dev REPL to fire the scheduled handler

# Check that rows were inserted
wrangler d1 execute uptime \
  --command "SELECT url, status, ok, latency_ms FROM uptime_checks ORDER BY ts DESC LIMIT 10;"

# Simulate a failure: point a test URL to a non-existent host,
# wait for 3 cron intervals, then check the alert_state table
wrangler d1 execute uptime \
  --command "SELECT * FROM alert_state;"
# Expected: alerted_at IS NOT NULL for the failing URL

# Check Slack: a message should appear in the configured channel
# Check PagerDuty: an incident should be open with dedup_key matching the URL
```

---

## Related
- `workers-d1-query-trace-structured-log.md`
- `workers-opentelemetry-trace-export-d1.md`

---

## Sources
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers Queues — https://developers.cloudflare.com/queues/
- PagerDuty Events API v2 — https://developer.pagerduty.com/api-reference/YXBpOjI3NDgyNjU-pager-duty-v2-events-api
- Slack Incoming Webhooks — https://api.slack.com/messaging/webhooks
