# D1 Dead Letter Queue with Retry Tracking in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Background jobs in your Worker occasionally fail due to transient errors (third-party API timeouts, rate-limit responses) and you need a reliable retry mechanism with exponential back-off, a maximum attempt cap, and a dead-letter queue for jobs that exhaust their retries — without a separate queue service.

## Context
Cloudflare Queues is the preferred solution for durable message delivery, but many projects already have D1 in place and want to avoid an additional primitive. Storing job state in D1 gives you full SQL queryability over queue depth, failure reasons, and retry histories — invaluable for debugging stuck jobs. The pattern combines a `jobs` table (the queue) with a `job_attempts` table (the audit trail) and uses SQLite's `SELECT … FOR NO KEY UPDATE` equivalent via optimistic locking to claim jobs safely across concurrent Worker invocations.

## Schema Design

```sql
-- migrations/0030_job_queue.sql
CREATE TABLE IF NOT EXISTS jobs (
  id              TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  queue           TEXT    NOT NULL,
  payload         TEXT    NOT NULL,             -- JSON
  status          TEXT    NOT NULL DEFAULT 'pending', -- pending | running | done | dead
  attempts        INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 5,
  next_run_at     INTEGER NOT NULL DEFAULT (unixepoch()),
  last_error      TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_jobs_queue_status_next ON jobs (queue, status, next_run_at)
  WHERE status IN ('pending', 'running');

CREATE TABLE IF NOT EXISTS job_attempts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id     TEXT    NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  attempt_no INTEGER NOT NULL,
  started_at INTEGER NOT NULL,
  ended_at   INTEGER,
  outcome    TEXT,   -- 'success' | 'failure' | 'timeout'
  error_msg  TEXT
);

CREATE INDEX idx_job_attempts_job ON job_attempts (job_id, attempt_no);
```

## Claiming a Job (Optimistic Lock Pattern)

```typescript
// src/queue/claim-job.ts
export interface Job {
  id:           string;
  queue:        string;
  payload:      string;
  attempts:     number;
  maxAttempts:  number;
}

export async function claimNextJob(
  db: D1Database,
  queue: string,
  visibilityTimeoutSecs = 30,
): Promise<Job | null> {
  const now = Math.floor(Date.now() / 1000);
  const lockUntil = now + visibilityTimeoutSecs;

  // Select the oldest eligible job
  const job = await db.prepare(
    `SELECT id, queue, payload, attempts, max_attempts
     FROM   jobs
     WHERE  queue      = ?
       AND  status     = 'pending'
       AND  next_run_at <= ?
     ORDER  BY next_run_at ASC
     LIMIT  1`
  ).bind(queue, now).first<Job & { max_attempts: number }>();

  if (!job) return null;

  // Claim it with a conditional update — prevents double-claim under concurrency
  const { meta } = await db.prepare(
    `UPDATE jobs
     SET    status     = 'running',
            next_run_at = ?,         -- visibility timeout acts as a lock expiry
            updated_at = ?
     WHERE  id = ? AND status = 'pending'`
  ).bind(lockUntil, now, job.id).run();

  if (meta.changes === 0) return null; // lost the race — another Worker claimed it

  await db.prepare(
    `INSERT INTO job_attempts (job_id, attempt_no, started_at)
     VALUES (?, ?, ?)`
  ).bind(job.id, job.attempts + 1, now).run();

  return { id: job.id, queue: job.queue, payload: job.payload, attempts: job.attempts, maxAttempts: job.max_attempts };
}
```

## Processing and Completing a Job

```typescript
// src/queue/complete-job.ts
const BACKOFF_BASE_SECS = 5;

export async function completeJob(db: D1Database, jobId: string): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await db.batch([
    db.prepare(
      `UPDATE jobs
       SET    status     = 'done',
              updated_at = ?
       WHERE  id = ?`
    ).bind(now, jobId),
    db.prepare(
      `UPDATE job_attempts
       SET    ended_at = ?, outcome = 'success'
       WHERE  job_id = ? AND ended_at IS NULL`
    ).bind(now, jobId),
  ]);
}

export async function failJob(
  db: D1Database,
  jobId: string,
  error: string,
): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  const job = await db.prepare(
    `SELECT attempts, max_attempts FROM jobs WHERE id = ?`
  ).bind(jobId).first<{ attempts: number; max_attempts: number }>();

  if (!job) throw new Error(`Job ${jobId} not found`);

  const newAttempts = job.attempts + 1;
  const isDead = newAttempts >= job.max_attempts;
  const backoffSecs = BACKOFF_BASE_SECS * Math.pow(2, newAttempts - 1); // 5, 10, 20, 40…
  const nextRunAt = isDead ? now : now + backoffSecs;

  await db.batch([
    db.prepare(
      `UPDATE jobs
       SET    status      = ?,
              attempts    = ?,
              next_run_at = ?,
              last_error  = ?,
              updated_at  = ?
       WHERE  id = ?`
    ).bind(isDead ? 'dead' : 'pending', newAttempts, nextRunAt, error, now, jobId),
    db.prepare(
      `UPDATE job_attempts
       SET    ended_at = ?, outcome = 'failure', error_msg = ?
       WHERE  job_id = ? AND ended_at IS NULL`
    ).bind(now, error, jobId),
  ]);
}
```

## Enqueuing Jobs

```typescript
// src/queue/enqueue.ts
export interface EnqueueOptions {
  queue:       string;
  payload:     unknown;
  maxAttempts?: number;
  delaySeconds?: number;
}

export async function enqueue(
  db: D1Database,
  options: EnqueueOptions,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const runAt = now + (options.delaySeconds ?? 0);

  const result = await db.prepare(
    `INSERT INTO jobs (queue, payload, max_attempts, next_run_at)
     VALUES (?, ?, ?, ?)
     RETURNING id`
  ).bind(
    options.queue,
    JSON.stringify(options.payload),
    options.maxAttempts ?? 5,
    runAt,
  ).first<{ id: string }>();

  return result!.id;
}
```

## Cron-Driven Worker Consumer

```typescript
// src/scheduled.ts — consume up to 10 jobs per cron tick
import { claimNextJob, completeJob, failJob } from './queue';
import { processJob } from './handlers';

export async function handleScheduled(
  _event: ScheduledEvent,
  env: { DB: D1Database },
): Promise<void> {
  const CONCURRENCY = 10;
  const QUEUE = 'default';

  const tasks = Array.from({ length: CONCURRENCY }, async () => {
    const job = await claimNextJob(env.DB, QUEUE);
    if (!job) return;

    try {
      await processJob(job);
      await completeJob(env.DB, job.id);
    } catch (err) {
      await failJob(env.DB, job.id, String(err));
    }
  });

  await Promise.allSettled(tasks);
}

// Recover stalled jobs whose visibility window expired
async function recoverStalledJobs(db: D1Database): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await db.prepare(
    `UPDATE jobs
     SET    status     = 'pending',
            updated_at = ?
     WHERE  status     = 'running'
       AND  next_run_at < ?`
  ).bind(now, now).run();
}
```

## Monitoring Queries

```sql
-- Queue depth by status
SELECT queue, status, COUNT(*) AS cnt
FROM   jobs
GROUP  BY queue, status;

-- Dead jobs in the last 24 hours
SELECT id, queue, last_error, attempts, created_at
FROM   jobs
WHERE  status = 'dead'
  AND  updated_at >= unixepoch() - 86400
ORDER  BY updated_at DESC;

-- Average attempt count for completed jobs
SELECT queue,
       AVG(attempts) AS avg_attempts,
       MAX(attempts) AS max_attempts
FROM   jobs
WHERE  status = 'done'
GROUP  BY queue;
```

## Anti-patterns
- Running `UPDATE … SET status='running'` without checking `meta.changes === 0` — two concurrent Workers will both claim the same job
- Deleting jobs on completion — retain them for observability; use a separate archival job to purge rows older than your retention window
- Not recording `job_attempts` — without an audit trail you cannot distinguish a job that was never processed from one that failed silently
- Using `status = 'running'` as a permanent lock without a visibility timeout — a crashed Worker leaves jobs stuck in `running` forever

## Gotchas
- D1 does not support `SELECT FOR UPDATE`; simulate exclusive claiming with a conditional `UPDATE … WHERE status='pending'` and check `meta.changes`
- Cron Triggers fire at most once per minute; for sub-minute throughput, fan out processing within a single tick using `Promise.allSettled`
- `RETURNING id` requires SQLite 3.35+; D1 supports it as of mid-2024
- Exponential backoff with a `next_run_at` column requires a covering index on `(queue, status, next_run_at)` to avoid full table scans as the queue grows

## Verification

```bash
# Enqueue a test job and verify it appears
wrangler d1 execute MY_DB --local --command \
  "INSERT INTO jobs (queue, payload) VALUES ('default', '{\"action\":\"ping\"}');"

wrangler d1 execute MY_DB --local --command \
  "SELECT id, status, attempts, next_run_at FROM jobs ORDER BY created_at DESC LIMIT 5;"

# Simulate a failed job and verify DLQ behaviour
wrangler d1 execute MY_DB --local --command \
  "UPDATE jobs SET attempts = 4 WHERE status='pending' LIMIT 1;"
# Then trigger failJob and confirm status changes to 'dead' on next failure
```

## Related
- [d1-batch-operations-performance.md](d1-batch-operations-performance.md)
- [d1-materialized-view-simulation-cron.md](d1-materialized-view-simulation-cron.md)
- [d1-advisory-lock-pattern-workers.md](d1-advisory-lock-pattern-workers.md)
- [d1-upsert-conflict-resolution-workers.md](d1-upsert-conflict-resolution-workers.md)

## Sources
- Cloudflare Queues vs D1: https://developers.cloudflare.com/queues/
- SQLite conditional update pattern: https://www.sqlite.org/lang_update.html
- Exponential backoff best practices: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
