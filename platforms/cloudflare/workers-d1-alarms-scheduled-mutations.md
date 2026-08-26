# Scheduling D1 Mutations with Durable Object Alarms

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to run batched D1 mutations on a reliable schedule — for example, expiring stale sessions, computing daily aggregates, or flushing a write-ahead buffer. Cron-triggered Workers can do this, but Durable Object alarms provide finer-grained control, retry-on-failure semantics, and per-object progress tracking.

## Context

- Runtime: Cloudflare Workers + Durable Objects + D1
- Alarm granularity: minimum ~1 second (practical minimum ~10 seconds for reliability)
- Retry behavior: Cloudflare retries the alarm handler with exponential back-off if it throws
- D1 binding: available inside Durable Objects via `env`

---

## Section 1 — Architecture Overview

```
HTTP Worker (trigger)
       │
       ▼
Durable Object (Scheduler)
  ├── alarm() → runs batched D1 mutations
  ├── D1 `job_progress` table → tracks cursor / last_run
  └── reschedules itself after each successful run
```

The Durable Object stores the current job cursor in D1 so progress survives restarts. The alarm fires, processes a batch, writes progress, and schedules the next alarm.

---

## Section 2 — D1 Schema

```sql
-- migrations/001_scheduler.sql

-- Table that holds pending work (example: unprocessed events)
CREATE TABLE IF NOT EXISTS pending_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  payload     TEXT    NOT NULL,
  processed   INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL
);

-- Progress table — one row per job
CREATE TABLE IF NOT EXISTS job_progress (
  job_id      TEXT    PRIMARY KEY,
  last_id     INTEGER NOT NULL DEFAULT 0,  -- last processed row id
  last_run_at INTEGER,
  run_count   INTEGER NOT NULL DEFAULT 0
);

-- Destination: processed events archive
CREATE TABLE IF NOT EXISTS processed_events (
  id          INTEGER PRIMARY KEY,
  payload     TEXT    NOT NULL,
  processed_at INTEGER NOT NULL
);
```

```bash
wrangler d1 execute prod-db --file=migrations/001_scheduler.sql
```

---

## Section 3 — Durable Object with Alarm Handler

```typescript
// src/scheduler.ts
export interface Env {
  DB: D1Database;
}

const JOB_ID = 'event-processor';
const BATCH_SIZE = 100;
const INTERVAL_MS = 60_000; // run every 60 seconds

export class Scheduler implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/start') {
      // Ensure the alarm is set; idempotent
      const current = await this.state.storage.getAlarm();
      if (!current) {
        await this.state.storage.setAlarm(Date.now() + INTERVAL_MS);
        return new Response(JSON.stringify({ ok: true, status: 'alarm_set' }), {
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ ok: true, status: 'already_running' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/status') {
      const nextAlarm = await this.state.storage.getAlarm();
      const progress = await this.env.DB
        .prepare('SELECT * FROM job_progress WHERE job_id = ?')
        .bind(JOB_ID)
        .first();
      return new Response(
        JSON.stringify({ nextAlarmAt: nextAlarm, progress }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    if (url.pathname === '/stop') {
      await this.state.storage.deleteAlarm();
      return new Response(JSON.stringify({ ok: true, status: 'stopped' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not Found', { status: 404 });
  }

  async alarm(): Promise<void> {
    console.log(`[scheduler] alarm fired at ${new Date().toISOString()}`);

    try {
      await this.processBatch();
    } catch (err) {
      console.error('[scheduler] batch failed, alarm will retry:', err);
      // Re-throw so Cloudflare retries with exponential back-off
      throw err;
    }

    // Schedule the next run
    await this.state.storage.setAlarm(Date.now() + INTERVAL_MS);
    console.log('[scheduler] next alarm scheduled');
  }

  private async processBatch(): Promise<void> {
    // 1. Load cursor
    const progress = await this.env.DB
      .prepare('SELECT last_id FROM job_progress WHERE job_id = ?')
      .bind(JOB_ID)
      .first<{ last_id: number }>();

    const lastId = progress?.last_id ?? 0;

    // 2. Fetch next batch
    const { results: rows } = await this.env.DB
      .prepare(
        `SELECT id, payload FROM pending_events
         WHERE id > ? AND processed = 0
         ORDER BY id ASC LIMIT ?`
      )
      .bind(lastId, BATCH_SIZE)
      .all<{ id: number; payload: string }>();

    if (rows.length === 0) {
      console.log('[scheduler] no pending events');
      return;
    }

    const now = Date.now();
    const maxId = Math.max(...rows.map(r => r.id));

    // 3. Insert into processed archive
    const placeholders = rows.map(() => '(?, ?, ?)').join(', ');
    const values = rows.flatMap(r => [r.id, r.payload, now]);
    await this.env.DB
      .prepare(
        `INSERT OR IGNORE INTO processed_events (id, payload, processed_at)
         VALUES ${placeholders}`
      )
      .bind(...values)
      .run();

    // 4. Mark source rows as processed
    const ids = rows.map(r => r.id);
    await this.env.DB
      .prepare(
        `UPDATE pending_events SET processed = 1
         WHERE id IN (${ids.map(() => '?').join(',')})`
      )
      .bind(...ids)
      .run();

    // 5. Update progress cursor
    await this.env.DB
      .prepare(
        `INSERT INTO job_progress (job_id, last_id, last_run_at, run_count)
         VALUES (?, ?, ?, 1)
         ON CONFLICT(job_id) DO UPDATE SET
           last_id = excluded.last_id,
           last_run_at = excluded.last_run_at,
           run_count = job_progress.run_count + 1`
      )
      .bind(JOB_ID, maxId, now)
      .run();

    console.log(`[scheduler] processed ${rows.length} events up to id=${maxId}`);
  }
}
```

---

## Section 4 — Worker Entry Point

```typescript
// src/index.ts
import { Scheduler } from './scheduler';
export { Scheduler };

export interface Env {
  DB: D1Database;
  SCHEDULER: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Route scheduler control requests to the single global DO instance
    if (url.pathname.startsWith('/scheduler/')) {
      const id = env.SCHEDULER.idFromName('global-scheduler');
      const stub = env.SCHEDULER.get(id);
      // Rewrite path: /scheduler/start → /start
      const newUrl = new URL(request.url);
      newUrl.pathname = url.pathname.replace('/scheduler', '');
      return stub.fetch(new Request(newUrl, request));
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Section 5 — wrangler.toml

```toml
# wrangler.toml
name = "d1-scheduler"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "SCHEDULER"
class_name = "Scheduler"

[[migrations]]
tag = "v1"
new_classes = ["Scheduler"]

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

---

## Anti-patterns

- Re-throwing alarm errors without logging — always log before re-throwing so Cloudflare's retry loop is visible in logs.
- Using `setTimeout` instead of `storage.setAlarm()` inside a Durable Object — `setTimeout` does not survive hibernation.
- Processing unbounded batches — always use `LIMIT` to cap the batch size; large batches can exceed the 30-second alarm wall time.
- Storing cursor state only in Durable Object storage (not D1) — if the DO is evicted, you lose cursor position; D1 is durable.
- Running multiple Durable Objects for the same job without coordination — a single named instance (`idFromName`) prevents duplicate processing.

## Gotchas

- The minimum alarm interval is not enforced to millisecond precision; ~10-second granularity is realistic.
- `getAlarm()` returns `null` if no alarm is set — always check before deciding whether to schedule.
- D1 batch INSERT with spread `...values` is limited by SQLite parameter count (~999); split very large batches.
- Durable Objects that throw from `alarm()` are retried with exponential back-off up to a platform-defined limit — idempotent operations are essential.
- `wrangler dev` supports Durable Object alarms only with `--local` flag and local persistence enabled.

## Verification

```bash
# Deploy
wrangler deploy

# Start the scheduler
curl -X POST https://d1-scheduler.example.com/scheduler/start

# Check status
curl https://d1-scheduler.example.com/scheduler/status | jq .

# Insert test rows to process
wrangler d1 execute prod-db --command \
  "INSERT INTO pending_events (payload, created_at) VALUES ('{\"test\":1}', unixepoch() * 1000);"

# Wait for the next alarm (up to 60 seconds), then verify
wrangler d1 execute prod-db --command \
  "SELECT COUNT(*) as processed FROM processed_events;"

# Stop the scheduler
curl -X POST https://d1-scheduler.example.com/scheduler/stop
```

## Related

- `documentation/categories/cloudflare/workers-smart-placement-auto-performance.md`
- `documentation/categories/cloudflare/cloudflare-zaraz-custom-event-workers-backend.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/durable-objects/
