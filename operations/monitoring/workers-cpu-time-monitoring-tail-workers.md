# Monitoring Worker CPU Time with Tail Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers on the Unbound usage model are billed partly by CPU time and will be terminated if they exceed the 30-second CPU limit. You need to detect individual invocations that consume more than 50 ms of CPU (approaching the Bundled plan limit or signalling pathological compute), store them durably, and receive a weekly statistical summary with P95/P99 figures so you can prioritise optimisation work.

---

## Context

Cloudflare Tail Workers receive a `TailEvent` for every invocation of a watched Worker, including the `cpuTime` field expressed in milliseconds. Tail Workers run asynchronously after the primary Worker has returned, so they impose no latency on the critical path. By filtering events where `cpuTime > 50` in the Tail Worker and persisting matching rows to D1, you build a queryable history of expensive invocations without external infrastructure. A scheduled Cron Trigger on the same Worker computes P95/P99 from accumulated rows weekly and posts a Slack message.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "cpu-tail-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

# Attach as a tail consumer of the worker you want to monitor
[tail_consumers]
bindings = [
  { service = "my-primary-worker" }
]

[[d1_databases]]
binding = "DB"
database_name = "monitoring"
database_id = "<your-d1-database-id>"

[vars]
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
CPU_THRESHOLD_MS = "50"
```

```sql
-- D1 migration: 0001_create_cpu_events.sql
CREATE TABLE IF NOT EXISTS cpu_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id    TEXT    NOT NULL UNIQUE,  -- prevents duplicate tail deliveries
  worker_name TEXT    NOT NULL,
  script_name TEXT    NOT NULL,
  cpu_time_ms REAL    NOT NULL,
  wall_time_ms REAL   NOT NULL,
  outcome     TEXT    NOT NULL,
  recorded_at INTEGER NOT NULL          -- Unix epoch seconds
);

CREATE INDEX IF NOT EXISTS idx_cpu_events_recorded_at ON cpu_events (recorded_at);
CREATE INDEX IF NOT EXISTS idx_cpu_events_cpu_time    ON cpu_events (cpu_time_ms);
```

---

## Section 2 — Tail Worker implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  SLACK_WEBHOOK_URL: string;
  CPU_THRESHOLD_MS: string;
}

// TailEvent shape as provided by the Workers runtime
interface TailItem {
  scriptName: string;
  outcome: string;
  cpuTime: number;      // milliseconds of CPU consumed
  wallTime: number;     // milliseconds of wall-clock time consumed
  eventTimestamp: number; // Unix epoch ms
  logs: { message: string[]; level: string; timestamp: number }[];
  exceptions: { name: string; message: string; timestamp: number }[];
}

async function persistCpuEvents(
  db: D1Database,
  events: TailItem[],
  thresholdMs: number
): Promise<void> {
  const aboveThreshold = events.filter((e) => e.cpuTime > thresholdMs);
  if (aboveThreshold.length === 0) return;

  // Build a batch insert to avoid N round-trips to D1
  const statements = aboveThreshold.map((e) => {
    // Deterministic event ID from script name + timestamp avoids duplicates
    // on tail re-delivery (Tail Workers have at-least-once delivery)
    const eventId = `${e.scriptName}:${e.eventTimestamp}`;
    return db.prepare(
      `INSERT OR IGNORE INTO cpu_events
         (event_id, worker_name, script_name, cpu_time_ms, wall_time_ms, outcome, recorded_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      eventId,
      e.scriptName,
      e.scriptName,
      e.cpuTime,
      e.wallTime,
      e.outcome,
      Math.floor(e.eventTimestamp / 1000)
    );
  });

  // D1 batch executes all statements in a single round-trip
  await db.batch(statements);
}

export default {
  // Tail handler — receives batched TailItems from the watched Worker
  async tail(events: TailItem[], env: Env): Promise<void> {
    const thresholdMs = parseFloat(env.CPU_THRESHOLD_MS ?? "50");
    await persistCpuEvents(env.DB, events, thresholdMs);
  },

  // Scheduled handler — runs weekly to compute percentiles and post to Slack
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await postWeeklyReport(env);
  },
};

async function postWeeklyReport(env: Env): Promise<void> {
  const sevenDaysAgo = Math.floor(Date.now() / 1000) - 7 * 24 * 60 * 60;

  // D1 does not have a built-in PERCENTILE function, so we fetch all recent
  // cpu_time_ms values sorted and compute percentiles in JavaScript.
  const result = await env.DB.prepare(
    `SELECT cpu_time_ms, script_name
     FROM cpu_events
     WHERE recorded_at >= ?
     ORDER BY cpu_time_ms ASC`
  )
    .bind(sevenDaysAgo)
    .all<{ cpu_time_ms: number; script_name: string }>();

  if (!result.results || result.results.length === 0) {
    console.log("No CPU events above threshold in the past 7 days.");
    return;
  }

  const values = result.results.map((r) => r.cpu_time_ms);
  const p95 = percentile(values, 95);
  const p99 = percentile(values, 99);
  const maxCpu = values[values.length - 1];
  const count = values.length;

  const message = {
    text: `:hourglass: *CPU Time Weekly Report* (events > ${env.CPU_THRESHOLD_MS} ms threshold)`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: [
            `:hourglass: *CPU Time Weekly Report*`,
            `Events above threshold (7 days): *${count}*`,
            `P95 CPU time: *${p95.toFixed(1)} ms*`,
            `P99 CPU time: *${p99.toFixed(1)} ms*`,
            `Max CPU time: *${maxCpu.toFixed(1)} ms*`,
          ].join("\n"),
        },
      },
    ],
  };

  const resp = await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message),
  });

  if (!resp.ok) {
    throw new Error(`Slack webhook failed: ${resp.status} ${await resp.text()}`);
  }
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const index = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
}
```

---

## Section 3 — Cron schedule in wrangler.toml

```toml
# Add to wrangler.toml under the cpu-tail-worker stanza
[triggers]
crons = ["0 9 * * 1"]  # Every Monday at 09:00 UTC
```

---

## Anti-patterns

- **Inserting one row per D1 call** — A tail batch can contain dozens of events. Always use `db.batch()` to send a single round-trip per tail invocation; individual `await db.prepare(...).run()` calls in a loop exhaust the D1 row-write budget quickly and add unnecessary latency to the tail Worker.
- **Trusting cpuTime without deduplication** — Tail Workers guarantee at-least-once delivery. Without `INSERT OR IGNORE` on a unique `event_id`, re-delivered tail events inflate your percentile data.
- **Fetching all rows to compute percentiles** — For very high-traffic Workers this result set can grow large. Rotate or prune the `cpu_events` table regularly (e.g., delete rows older than 30 days in the same scheduled handler).
- **Alerting on every single high-CPU event** — Tail Workers process events in bursts. Fire Slack alerts only in the scheduled job to avoid webhook rate-limit errors and alert fatigue.

---

## Gotchas

- The `cpuTime` field is only populated when the Tail Worker is deployed as a tail consumer via `wrangler.toml` or the API; it is not available in `wrangler tail` log streaming.
- Tail Workers must be deployed separately from the Worker they observe. They share the same account but are distinct scripts.
- D1 `batch()` accepts a maximum of 100 statements per call. If a tail event batch exceeds 100 high-CPU items, split it into chunks of 100 before calling `batch()`.
- The `scheduled` handler must be exported from the same `default` export object as `tail`; they cannot be split across files without a re-export.
- Workers on the Bundled plan have a 10 ms CPU-time limit per invocation, not 50 ms. Adjust `CPU_THRESHOLD_MS` to match your plan.

---

## Verification

```bash
# 1. Apply the D1 migration
npx wrangler d1 execute monitoring --file=migrations/0001_create_cpu_events.sql

# 2. Deploy the tail worker
npx wrangler deploy

# 3. Trigger a deliberately slow invocation on your primary worker
curl https://my-primary-worker.example.com/slow-endpoint

# 4. Query D1 for the recorded event (allow ~5 seconds for tail delivery)
npx wrangler d1 execute monitoring \
  --command "SELECT * FROM cpu_events ORDER BY recorded_at DESC LIMIT 10"

# 5. Manually trigger the weekly report cron
npx wrangler trigger scheduled --name cpu-tail-worker --cron "0 9 * * 1"
```

---

## Related

- `workers-request-tracing-analytics-engine.md`
- `workers-error-rate-alerting-analytics-engine.md`
- `queue-consumer-lag-monitoring-d1-workers.md`

---

## Sources

- Cloudflare Tail Workers documentation — https://developers.cloudflare.com/workers/observability/tail-workers/
- D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Workers CPU time limits — https://developers.cloudflare.com/workers/platform/limits/#cpu-time
