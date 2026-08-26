# Workers Cron Trigger Self-Healing Retry Pattern

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A scheduled Workers cron job (data sync, report generation, cache warm, webhook dispatch) fails silently when its target system is temporarily unavailable. Because cron triggers do not have built-in retry semantics — each scheduled event fires once and is gone — transient failures leave work permanently dropped until the next scheduled tick. You need the job to retry on failure without manual intervention and without sacrificing idempotency.

---

## Context

Cloudflare Workers cron triggers fire via the `scheduled` event handler. Each invocation is independent: there is no retry queue, no built-in backoff, and no failure notification beyond the `outcome` field in the Tail Worker trace. The next cron tick fires regardless of whether the previous one succeeded.

The self-healing retry pattern works by:

1. Persisting the job state (pending/running/succeeded/failed) in D1 or KV at the start of each run.
2. On failure, persisting the failure with a `retry_after` timestamp and a retry counter.
3. On the next cron tick, checking for unresolved failures whose `retry_after` is in the past.
4. Re-running failed jobs with exponential backoff until they succeed or exceed `max_retries`.
5. Using idempotency keys to ensure re-runs are safe.

This pattern is equivalent to a lightweight, self-contained job queue backed by D1 or KV.

---

## Data Model in D1

```sql
-- migrations/cron_jobs.sql
CREATE TABLE IF NOT EXISTS cron_jobs (
  job_id       TEXT    NOT NULL PRIMARY KEY,
  job_name     TEXT    NOT NULL,
  status       TEXT    NOT NULL DEFAULT 'pending',  -- pending | running | succeeded | failed
  attempt      INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  retry_after  INTEGER,          -- unix timestamp; null means "run now"
  last_error   TEXT,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at   INTEGER NOT NULL DEFAULT (unixepoch())
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS cron_jobs_runnable
  ON cron_jobs (status, retry_after)
  WHERE status IN ('pending', 'failed');
```

---

## Core Retry Worker

```typescript
interface Env {
  DB: D1Database;
}

const MAX_ATTEMPTS = 5;
const BASE_DELAY_SECONDS = 30;

// Exponential backoff: 30s, 60s, 120s, 240s, 480s
function retryAfterSeconds(attempt: number): number {
  return BASE_DELAY_SECONDS * Math.pow(2, attempt - 1);
}

async function markRunning(db: D1Database, jobId: string): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE cron_jobs
       SET status = 'running', attempt = attempt + 1, updated_at = unixepoch()
       WHERE job_id = ?1
         AND status IN ('pending', 'failed')
         AND (retry_after IS NULL OR retry_after <= unixepoch())
       RETURNING attempt`
    )
    .bind(jobId)
    .first<{ attempt: number }>();
  return result !== null;
}

async function markSucceeded(db: D1Database, jobId: string): Promise<void> {
  await db
    .prepare(
      `UPDATE cron_jobs
       SET status = 'succeeded', last_error = NULL, updated_at = unixepoch()
       WHERE job_id = ?1`
    )
    .bind(jobId)
    .run();
}

async function markFailed(
  db: D1Database,
  jobId: string,
  attempt: number,
  error: string
): Promise<void> {
  if (attempt >= MAX_ATTEMPTS) {
    await db
      .prepare(
        `UPDATE cron_jobs
         SET status = 'failed', last_error = ?2, retry_after = NULL, updated_at = unixepoch()
         WHERE job_id = ?1`
      )
      .bind(jobId, `EXHAUSTED: ${error}`)
      .run();
    console.error(`Job ${jobId} exhausted all retries: ${error}`);
    return;
  }

  const retryAfter = Math.floor(Date.now() / 1000) + retryAfterSeconds(attempt);
  await db
    .prepare(
      `UPDATE cron_jobs
       SET status = 'failed', last_error = ?2, retry_after = ?3, updated_at = unixepoch()
       WHERE job_id = ?1`
    )
    .bind(jobId, error, retryAfter)
    .run();
}
```

---

## Scheduled Handler with Self-Healing

```typescript
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runScheduledJobs(env, event.cron));
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    // Health-check endpoint — manually trigger a run for testing
    if (new URL(request.url).pathname === "/trigger") {
      await runScheduledJobs(env, "manual");
      return new Response("triggered");
    }
    return new Response("ok");
  },
};

async function runScheduledJobs(env: Env, cronExpression: string): Promise<void> {
  // Find all runnable jobs (pending or failed with retry_after in the past)
  const runnable = await env.DB.prepare(
    `SELECT job_id, job_name, attempt
     FROM cron_jobs
     WHERE status IN ('pending', 'failed')
       AND (retry_after IS NULL OR retry_after <= unixepoch())
     ORDER BY retry_after ASC
     LIMIT 20`
  ).all<{ job_id: string; job_name: string; attempt: number }>();

  for (const job of runnable.results) {
    await executeJob(env, job.job_id, job.job_name, job.attempt);
  }
}

async function executeJob(
  env: Env,
  jobId: string,
  jobName: string,
  lastAttempt: number
): Promise<void> {
  // Atomic claim — prevents double-execution if multiple isolates race
  const claimed = await markRunning(env.DB, jobId);
  if (!claimed) return; // Another isolate claimed it first

  const attempt = lastAttempt + 1;

  try {
    await dispatch(jobName, env);
    await markSucceeded(env.DB, jobId);
    console.log(`Job ${jobId} (${jobName}) succeeded on attempt ${attempt}`);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    await markFailed(env.DB, jobId, attempt, errorMsg);
    console.error(`Job ${jobId} (${jobName}) failed attempt ${attempt}: ${errorMsg}`);
  }
}

// Dispatch to the correct job handler by name
async function dispatch(jobName: string, env: Env): Promise<void> {
  switch (jobName) {
    case "sync-products":
      await syncProducts(env);
      break;
    case "warm-cache":
      await warmCache(env);
      break;
    default:
      throw new Error(`Unknown job: ${jobName}`);
  }
}
```

---

## Seeding Initial Jobs

```typescript
// One-time setup: insert the job definitions into D1
async function seedJobs(db: D1Database): Promise<void> {
  const jobs = [
    { job_id: "sync-products-daily", job_name: "sync-products", max_attempts: 5 },
    { job_id: "warm-cache-hourly", job_name: "warm-cache", max_attempts: 3 },
  ];

  const stmt = db.prepare(
    `INSERT OR IGNORE INTO cron_jobs (job_id, job_name, max_attempts)
     VALUES (?1, ?2, ?3)`
  );

  await db.batch(
    jobs.map((j) => stmt.bind(j.job_id, j.job_name, j.max_attempts))
  );
}
```

---

## Idempotency with an Idempotency Key

For jobs that call external APIs or write to databases, wrap each operation with an idempotency key derived from the `job_id` and `attempt` number.

```typescript
async function syncProducts(env: Env): Promise<void> {
  const idempotencyKey = `sync-products-${new Date().toISOString().slice(0, 10)}`;

  // Check if this idempotency key was already used today
  const existing = await env.DB.prepare(
    "SELECT 1 FROM cron_jobs WHERE job_id = ?1 AND status = 'succeeded'"
  ).bind("sync-products-daily").first();

  if (existing) {
    console.log("Already synced today, skipping");
    return;
  }

  const response = await fetch("https://api.shop.example.com/products/sync", {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
      Authorization: `Bearer ${env.SHOP_TOKEN}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Sync failed: ${response.status} ${await response.text()}`);
  }
}
```

---

## KV-Based Alternative for Simple Cases

For Workers that cannot use D1, KV provides a lightweight fallback. Trade-off: KV is eventually consistent, so concurrent isolates may not see each other's writes immediately. Add a cron cadence long enough for KV to propagate (> 60 s recommended).

```typescript
interface KvJobState {
  status: "pending" | "running" | "succeeded" | "failed";
  attempt: number;
  retryAfter: number | null;
  lastError: string | null;
}

async function getJobState(kv: KVNamespace, jobId: string): Promise<KvJobState> {
  const raw = await kv.get(jobId, "json") as KvJobState | null;
  return raw ?? { status: "pending", attempt: 0, retryAfter: null, lastError: null };
}

async function setJobState(
  kv: KVNamespace,
  jobId: string,
  state: KvJobState
): Promise<void> {
  await kv.put(jobId, JSON.stringify(state), { expirationTtl: 86400 * 7 });
}
```

---

## Anti-patterns

- **Relying on the Tail Worker to re-trigger failed jobs.** Tail Workers are observability tools, not execution engines. They cannot re-dispatch a cron event.
- **Storing retry state in a module-level variable.** Isolates are ephemeral; module-level state is lost between invocations. Always persist retry state in D1 or KV.
- **Retrying without exponential backoff.** Retrying immediately and repeatedly hammers a temporarily unavailable upstream and prolongs the outage. Exponential backoff gives the target system time to recover.
- **No max_attempts ceiling.** Without a ceiling, a permanently broken job retries forever, accumulating noise and wasting compute budget. Set a `max_attempts` and page on exhaustion.
- **Non-idempotent job logic.** If a job fails after partial completion (e.g., 500 rows written out of 1000), a retry from scratch may duplicate the first 500 rows. Design job handlers with checkpointing or idempotency keys.

---

## Gotchas

- **Cron jitter.** Cloudflare does not guarantee exact cron fire times; jitter of ±30 s is normal. Design retry windows that are at least 2× the expected jitter.
- **`ctx.waitUntil()` is required.** Without `waitUntil()`, the Worker's execution context closes as soon as the `scheduled()` handler returns. Async database writes may not complete. Always wrap async work in `ctx.waitUntil()`.
- **D1 write lock contention.** D1 is a single-writer SQLite database. If multiple cron jobs run simultaneously and all try to update `cron_jobs` rows, they will serialize on the write lock. Batch your `UPDATE` statements where possible.
- **Cron expression resolution.** The `event.cron` field contains the cron expression that triggered the invocation (e.g., `"0 * * * *"`). Use it to distinguish multiple cron triggers routed to the same handler.

---

## Verification

```typescript
// Check job states from a fetch endpoint for manual inspection
async function handleStatus(env: Env): Promise<Response> {
  const jobs = await env.DB.prepare(
    `SELECT job_id, job_name, status, attempt, last_error, retry_after
     FROM cron_jobs
     ORDER BY updated_at DESC
     LIMIT 50`
  ).all();

  return Response.json(jobs.results);
}
```

Set up a Cloudflare notification (Workers error rate alert) to page when a job exceeds `max_attempts`. Use Logpush to ship the structured log output to a log aggregator for percentile tracking of job durations and failure rates.

---

## Related

- `workers-queues-background-offload.md`
- `durable-objects-alarm-write-coalescing.md`
- `d1-batch-query-performance-optimization.md`
- `workers-cpu-time-optimization.md`
- `kv-eventual-consistency-stale-data.md`

---

## Sources

- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Workers `ctx.waitUntil()`: https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- D1 `db.batch()`: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/#dbbatch
- Exponential backoff best practices: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
