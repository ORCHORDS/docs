# Cron Triggers Silently Miss Executions During Cloudflare Maintenance Windows

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A scheduled Worker (Cron Trigger) that is supposed to run every hour skips one or more executions without any error in the Cloudflare dashboard or `wrangler tail`. Downstream data pipelines that depend on the cron output are out of date, and there is no audit trail showing which runs executed successfully versus which were missed. The gaps are only noticed after a downstream consumer alerts on stale data.

---

## Context

Cloudflare Cron Triggers offer at-least-once semantics during normal operation, but they do not guarantee execution during infrastructure maintenance windows, rollouts, or regional disruptions. There is no built-in dead-letter queue or missed-execution notification. A Worker that performs idempotent work without recording what it ran cannot distinguish a missed execution from a gap in the schedule. The fix has two parts: (1) write a `cron_runs` record to D1 at the start and end of every execution, and (2) add a recovery Cron that runs more frequently than the primary schedule, detects gaps in `cron_runs`, and backfills missed work.

---

## Root Cause

The scheduled handler performs work but writes no execution record. A missed execution leaves no trace, so there is no way to detect or recover from it.

```typescript
// BAD: no idempotency tracking — missed runs are invisible
export default {
  async scheduled(
    _controller: ScheduledController,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    // Performs work but records nothing
    const items = await fetchItemsToProcess(env);
    await processItems(items, env);
    // If this invocation never runs, no one will know
  },
};
```

## Fix

Create a `cron_runs` table in D1 to record each execution, then add a recovery cron that detects and backfills gaps.

```sql
-- migrations/0005_create_cron_runs.sql
CREATE TABLE IF NOT EXISTS cron_runs (
  scheduled_at  TEXT PRIMARY KEY, -- ISO-8601, the nominal schedule tick
  started_at    TEXT NOT NULL,
  finished_at   TEXT,             -- NULL while in-progress or if crashed
  status        TEXT NOT NULL DEFAULT 'started' -- 'started' | 'ok' | 'error'
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_status
  ON cron_runs (status, scheduled_at);
```

```typescript
// GOOD: idempotent cron with D1 tracking and gap detection
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

// Primary scheduled handler — runs every hour (*/60 * * * *)
export async function primaryScheduled(
  controller: ScheduledController,
  env: Env,
  ctx: ExecutionContext,
): Promise<void> {
  const scheduledAt = new Date(controller.scheduledTime).toISOString();
  const startedAt = new Date().toISOString();

  // Upsert a 'started' row — idempotent if retried
  await env.DB
    .prepare(
      `INSERT INTO cron_runs (scheduled_at, started_at, status)
       VALUES (?, ?, 'started')
       ON CONFLICT (scheduled_at) DO UPDATE SET
         started_at = excluded.started_at,
         status     = 'started',
         finished_at = NULL`,
    )
    .bind(scheduledAt, startedAt)
    .run();

  try {
    const items = await fetchItemsToProcess(env);
    await processItems(items, env);

    await env.DB
      .prepare(
        `UPDATE cron_runs
         SET finished_at = ?, status = 'ok'
         WHERE scheduled_at = ?`,
      )
      .bind(new Date().toISOString(), scheduledAt)
      .run();
  } catch (err) {
    await env.DB
      .prepare(
        `UPDATE cron_runs
         SET finished_at = ?, status = 'error'
         WHERE scheduled_at = ?`,
      )
      .bind(new Date().toISOString(), scheduledAt)
      .run();
    throw err; // Re-throw so Cloudflare marks the invocation as failed
  }
}

// Recovery handler — runs every 10 minutes (*/10 * * * *)
// Detects gaps where expected hourly ticks have no corresponding DB row
export async function recoveryScheduled(
  controller: ScheduledController,
  env: Env,
): Promise<void> {
  const now = new Date(controller.scheduledTime);
  const lookbackHours = 6; // Check the last 6 hours for missed ticks

  const expectedTicks: string[] = [];
  for (let h = 1; h <= lookbackHours; h++) {
    const tick = new Date(now);
    tick.setMinutes(0, 0, 0);
    tick.setHours(tick.getHours() - h);
    expectedTicks.push(tick.toISOString());
  }

  const placeholders = expectedTicks.map(() => '?').join(', ');
  const { results } = await env.DB
    .prepare(
      `SELECT scheduled_at FROM cron_runs
       WHERE scheduled_at IN (${placeholders})
         AND status = 'ok'`,
    )
    .bind(...expectedTicks)
    .all<{ scheduled_at: string }>();

  const successfulTicks = new Set(results.map((r) => r.scheduled_at));

  for (const tick of expectedTicks) {
    if (!successfulTicks.has(tick)) {
      console.warn(`Detected missed cron tick: ${tick} — backfilling`);
      // Replay the missed work for the specific tick
      await backfillForTick(tick, env);
    }
  }
}

async function backfillForTick(scheduledAt: string, env: Env): Promise<void> {
  const startedAt = new Date().toISOString();
  await env.DB
    .prepare(
      `INSERT INTO cron_runs (scheduled_at, started_at, status)
       VALUES (?, ?, 'started')
       ON CONFLICT (scheduled_at) DO UPDATE SET
         started_at = excluded.started_at,
         status     = 'started',
         finished_at = NULL`,
    )
    .bind(scheduledAt, startedAt)
    .run();

  try {
    const items = await fetchItemsToProcess(env);
    await processItems(items, env);
    await env.DB
      .prepare(
        `UPDATE cron_runs SET finished_at = ?, status = 'ok' WHERE scheduled_at = ?`,
      )
      .bind(new Date().toISOString(), scheduledAt)
      .run();
    console.log(`Backfill complete for tick: ${scheduledAt}`);
  } catch (err) {
    await env.DB
      .prepare(
        `UPDATE cron_runs SET finished_at = ?, status = 'error' WHERE scheduled_at = ?`,
      )
      .bind(new Date().toISOString(), scheduledAt)
      .run();
    console.error(`Backfill failed for tick: ${scheduledAt}`, err);
  }
}

// wrangler.toml cron configuration:
// [[triggers.crons]]
// crons = ["0 * * * *", "*/10 * * * *"]
//
// In the scheduled() handler, dispatch on controller.cron:
export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    if (controller.cron === '0 * * * *') {
      await primaryScheduled(controller, env, ctx);
    } else if (controller.cron === '*/10 * * * *') {
      await recoveryScheduled(controller, env);
    }
  },
};

declare function fetchItemsToProcess(env: Env): Promise<unknown[]>;
declare function processItems(items: unknown[], env: Env): Promise<void>;
```

## Verification

```bash
# Apply the migration
npx wrangler d1 migrations apply my-database --remote

# Trigger the scheduled handler manually to seed a 'ok' row
npx wrangler dev --test-scheduled
# In a second terminal:
curl http://localhost:8787/__scheduled?cron=0+*+*+*+*

# Verify the run was recorded
npx wrangler d1 execute my-database --remote \
  --command "SELECT * FROM cron_runs ORDER BY scheduled_at DESC LIMIT 5;"

# Simulate a missed tick by inserting a gap manually, then trigger the recovery handler
npx wrangler d1 execute my-database --remote \
  --command "DELETE FROM cron_runs WHERE scheduled_at = '$(date -u -d '2 hours ago' +%Y-%m-%dT%H:00:00.000Z)';"

curl http://localhost:8787/__scheduled?cron=*/10+*+*+*+*
# Recovery handler should log: 'Detected missed cron tick: ... — backfilling'

# Confirm the gap is now filled
npx wrangler d1 execute my-database --remote \
  --command "SELECT scheduled_at, status FROM cron_runs ORDER BY scheduled_at DESC LIMIT 10;"
```

---

## Anti-patterns

- **Relying on Cloudflare's cron history UI as the only audit log** — The dashboard shows recent invocations but does not guarantee you can detect missed ticks or correlate them with downstream effects. Always write your own execution record.
- **Non-idempotent scheduled work** — If `processItems` is not idempotent, backfilling a missed tick can create duplicate records. Design scheduled work so that re-running it for a given `scheduled_at` is safe.
- **Using a single `cron_runs` table for multiple jobs without a `job_name` column** — When the Worker handles more than one distinct scheduled task, add a `job_name TEXT NOT NULL` column and include it in the primary key to avoid conflicts.
- **Long-running recovery without a timeout** — The recovery handler runs in a Worker with a 30-second CPU limit (or 15 minutes on Enterprise). If backfilling 6 hours of gaps is too slow, push each missed tick onto a Queue and process it asynchronously.

---

## Gotchas

- `controller.scheduledTime` is the **nominal** schedule time (in milliseconds since epoch), not the actual invocation time. Use it as the primary key to ensure idempotency across retries.
- Cloudflare may invoke a scheduled handler more than once for the same tick during retries. The `ON CONFLICT ... DO UPDATE` upsert in the fix handles this safely.
- `controller.cron` is the cron expression string exactly as written in `wrangler.toml`. Spaces in the expression are preserved, so `*/10 * * * *` must be matched exactly.
- Workers scheduled via Cron Triggers have the same 30-second CPU time limit as request handlers unless you are on an Enterprise plan with extended limits.
- D1 writes from a scheduled handler succeed even without an incoming `request` object. The `ExecutionContext.waitUntil()` is still required for any async work started after the handler returns.

---

## Related

- `d1-query-timeout-full-table-scan.md`
- `workers-503-service-unavailable-subrequest-limit.md`

---

## Sources

- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Workers Limits (CPU time) — https://developers.cloudflare.com/workers/platform/limits/
- Idempotency patterns for distributed systems — https://aws.amazon.com/builders-library/making-retries-safe-with-idempotency-keys/
