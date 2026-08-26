# Async Job Queue Architecture with Cloudflare Queues and Durable Object State

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

A user uploads a CSV of 50 000 records and expects an email when processing is complete. A nightly import must run in the background without holding an open HTTP connection. An image resize job must be retried if the downstream service is temporarily unavailable. Your Workers are stateless and limited to 30 seconds (CPU) or 15 minutes (Workers Unbound) per invocation — you need a durable job queue that survives restarts, tracks job status, and supports retries with back-off.

---

## Context

Cloudflare Queues is a pull-based, at-least-once message queue built into the Cloudflare Workers ecosystem. A producer Worker sends a message; Cloudflare holds it; a consumer Worker batch-receives it and acknowledges (ACK) or rejects (NACK). Unacknowledged messages are retried automatically after a visibility timeout.

Cloudflare Queues handles delivery and retries. It does not track job status — that is the application's responsibility. Durable Objects (DOs) fill this gap: each job gets a DO instance that owns its state machine (`pending → running → completed / failed`), stores its progress, and exposes a status API without requiring a database query on every poll.

The architecture has three components:

1. **Producer Worker**: validates the request, enqueues the job message, creates the DO instance, stores initial metadata in D1.
2. **Cloudflare Queue**: durable buffer, at-least-once delivery, configurable retry policy.
3. **Consumer Worker + Durable Object**: receives the batch, delegates each job to its DO, performs the work, updates DO state and D1.

---

## Queue and Consumer Configuration

```toml
# wrangler.toml

[[queues.producers]]
queue   = "job-queue"
binding = "JOB_QUEUE"

[[queues.consumers]]
queue             = "job-queue"
max_batch_size    = 10       # Process up to 10 jobs per consumer invocation
max_batch_timeout = 5        # Wait up to 5 s to fill the batch before firing
max_retries       = 5        # Cloudflare retries each message up to 5 times
dead_letter_queue = "job-dlq"

[[durable_objects.bindings]]
name       = "JOB_STATE"
class_name = "JobStateDO"

[[migrations]]
tag         = "v1"
new_classes = ["JobStateDO"]
```

---

## Job State Machine (Durable Object)

```typescript
// src/job-state-do.ts
import { DurableObject } from 'cloudflare:workers';

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'dead';

export interface JobState {
  jobId:       string;
  jobType:     string;
  payload:     unknown;
  status:      JobStatus;
  progress:    number;        // 0–100
  result?:     unknown;
  error?:      string;
  attempts:    number;
  enqueuedAt:  string;
  startedAt?:  string;
  finishedAt?: string;
  updatedAt:   string;
}

export class JobStateDO extends DurableObject {
  /** Initialize a new job (called by the producer). */
  async init(state: Omit<JobState, 'updatedAt'>): Promise<void> {
    await this.ctx.storage.put<JobState>('state', {
      ...state,
      updatedAt: new Date().toISOString(),
    });
  }

  /** Mark job as running; returns false if it is already running (idempotent guard). */
  async startRunning(): Promise<boolean> {
    const state = await this.getState();
    if (state.status !== 'pending') return false;

    await this.ctx.storage.put<JobState>('state', {
      ...state,
      status:    'running',
      startedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    return true;
  }

  async updateProgress(progress: number, partial?: unknown): Promise<void> {
    const state = await this.getState();
    await this.ctx.storage.put<JobState>('state', {
      ...state,
      progress,
      result:    partial ?? state.result,
      updatedAt: new Date().toISOString(),
    });
  }

  async complete(result: unknown): Promise<void> {
    const state = await this.getState();
    await this.ctx.storage.put<JobState>('state', {
      ...state,
      status:     'completed',
      progress:   100,
      result,
      finishedAt: new Date().toISOString(),
      updatedAt:  new Date().toISOString(),
    });
  }

  async fail(error: string, isDead = false): Promise<void> {
    const state = await this.getState();
    await this.ctx.storage.put<JobState>('state', {
      ...state,
      status:     isDead ? 'dead' : 'failed',
      error,
      attempts:   state.attempts + 1,
      finishedAt: new Date().toISOString(),
      updatedAt:  new Date().toISOString(),
    });
  }

  async resetToPending(): Promise<void> {
    const state = await this.getState();
    await this.ctx.storage.put<JobState>('state', {
      ...state,
      status:    'pending',
      startedAt: undefined,
      updatedAt: new Date().toISOString(),
    });
  }

  /** Read the current state (used by status-check API). */
  async getState(): Promise<JobState> {
    const state = await this.ctx.storage.get<JobState>('state');
    if (!state) throw new Error('Job not initialised');
    return state;
  }
}
```

---

## Producer Worker: Enqueue a Job

```typescript
// src/handlers/enqueue-job.ts
import type { Env } from '../env';

export interface JobRequest {
  jobType: 'csv-import' | 'image-resize' | 'report-export';
  payload: unknown;
}

export async function enqueueJob(
  request: Request,
  env: Env,
  userId: string,
): Promise<Response> {
  const body = await request.json<JobRequest>();
  const jobId = crypto.randomUUID();
  const now   = new Date().toISOString();

  // 1. Create the DO instance for this job
  const stub = env.JOB_STATE.get(env.JOB_STATE.idFromName(jobId));
  await stub.init({
    jobId,
    jobType:    body.jobType,
    payload:    body.payload,
    status:     'pending',
    progress:   0,
    attempts:   0,
    enqueuedAt: now,
  });

  // 2. Write metadata to D1 for list/search queries
  await env.DB.prepare(`
    INSERT INTO jobs (id, user_id, job_type, status, enqueued_at)
    VALUES (?, ?, ?, 'pending', ?)
  `).bind(jobId, userId, body.jobType, now).run();

  // 3. Enqueue the message (Cloudflare Queues)
  await env.JOB_QUEUE.send({
    jobId,
    jobType: body.jobType,
    userId,
  });

  return Response.json(
    { jobId, status: 'pending', statusUrl: `/jobs/${jobId}` },
    { status: 202 },
  );
}
```

---

## Consumer Worker: Process the Queue Batch

```typescript
// src/consumer.ts
import type { Env } from './env';
import { processJob } from './job-processors';

export default {
  async queue(
    batch: MessageBatch<{ jobId: string; jobType: string; userId: string }>,
    env: Env,
  ): Promise<void> {
    await Promise.allSettled(
      batch.messages.map(msg => handleMessage(msg, env))
    );
  },
};

async function handleMessage(
  msg: Message<{ jobId: string; jobType: string; userId: string }>,
  env: Env,
): Promise<void> {
  const { jobId, jobType, userId } = msg.body;
  const stub = env.JOB_STATE.get(env.JOB_STATE.idFromName(jobId));

  // Claim the job: only one consumer wins (DO serializes concurrent calls)
  const claimed = await stub.startRunning();
  if (!claimed) {
    // Another consumer already claimed this message — ack and move on
    msg.ack();
    return;
  }

  try {
    // Delegate to job-type-specific processor
    const result = await processJob(jobType, jobId, await stub.getState(), env, stub);

    // Mark complete in DO and D1
    await stub.complete(result);
    await env.DB.prepare(`
      UPDATE jobs SET status = 'completed', finished_at = ? WHERE id = ?
    `).bind(new Date().toISOString(), jobId).run();

    msg.ack();
  } catch (err) {
    const error   = (err as Error).message;
    const state   = await stub.getState();
    const isDead  = state.attempts + 1 >= 5;  // matches max_retries in wrangler.toml

    await stub.fail(error, isDead);
    await env.DB.prepare(`
      UPDATE jobs SET status = ?, error = ?, finished_at = ?
      WHERE id = ?
    `).bind(isDead ? 'dead' : 'failed', error, new Date().toISOString(), jobId).run();

    if (isDead) {
      // Exhaust retries — ack to prevent further delivery (message already in DLQ)
      msg.ack();
    } else {
      // NACK: return to queue for retry after visibility timeout
      msg.retry({ delaySeconds: Math.min(30 * 2 ** state.attempts, 3600) });
    }
  }
}
```

---

## Job Processor Example: CSV Import with Progress Updates

```typescript
// src/job-processors/csv-import.ts
import type { JobState } from '../job-state-do';
import type { JobStateDO } from '../job-state-do';
import type { Env } from '../env';

export async function processCsvImport(
  jobId: string,
  state: JobState,
  env: Env,
  doStub: DurableObjectStub<JobStateDO>,
): Promise<{ rowsImported: number }> {
  const { fileKey, userId } = state.payload as { fileKey: string; userId: string };

  // Fetch CSV from R2
  const object = await env.UPLOADS_BUCKET.get(fileKey);
  if (!object) throw new Error(`R2 object not found: ${fileKey}`);

  const text  = await object.text();
  const lines = text.split('\n').filter(Boolean);
  const total = lines.length - 1;  // Exclude header row
  let imported = 0;

  // Process in chunks to avoid CPU time limits
  const CHUNK_SIZE = 500;
  for (let i = 1; i < lines.length; i += CHUNK_SIZE) {
    const chunk = lines.slice(i, i + CHUNK_SIZE);
    const stmts = chunk.map(line => {
      const [name, email, amount] = line.split(',');
      return env.DB.prepare(`
        INSERT INTO contacts (user_id, name, email, amount_cents, imported_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id, email) DO UPDATE SET
          name = excluded.name,
          amount_cents = excluded.amount_cents
      `).bind(userId, name.trim(), email.trim(), parseInt(amount.trim(), 10), new Date().toISOString());
    });

    await env.DB.batch(stmts);
    imported += chunk.length;

    // Report progress back to DO
    const pct = Math.round((imported / total) * 100);
    await doStub.updateProgress(pct, { rowsImported: imported });
  }

  return { rowsImported: imported };
}
```

---

## Job Status API

```typescript
// src/handlers/job-status.ts
export async function getJobStatus(
  env: Env,
  jobId: string,
  userId: string,
): Promise<Response> {
  // Verify ownership via D1 (fast, avoids hitting the DO for auth)
  const meta = await env.DB.prepare(`
    SELECT id, user_id, job_type, status, enqueued_at
    FROM jobs WHERE id = ?
  `).bind(jobId).first<{ id: string; user_id: string; job_type: string; status: string; enqueued_at: string }>();

  if (!meta || meta.user_id !== userId) {
    return Response.json({ error: 'Not found' }, { status: 404 });
  }

  // Fetch live state from DO for in-progress jobs
  if (meta.status === 'pending' || meta.status === 'running') {
    const stub  = env.JOB_STATE.get(env.JOB_STATE.idFromName(jobId));
    const state = await stub.getState();
    return Response.json(state);
  }

  // For terminal states, D1 metadata is sufficient
  return Response.json(meta);
}
```

---

## D1 Schema for Job List Queries

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  job_type    TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  error       TEXT,
  enqueued_at TEXT NOT NULL,
  finished_at TEXT,

  CHECK (status IN ('pending','running','completed','failed','dead'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_status
  ON jobs (user_id, status, enqueued_at DESC);
```

---

## Anti-patterns

- **Storing large job payloads in the Queue message**: Queue messages are limited to 128 KB. For CSV files or large input blobs, store in R2 and put only the R2 object key in the message.
- **Not using a DO for status tracking**: Querying D1 for job progress on every poll creates unnecessary read load. The DO holds live in-memory state for running jobs; D1 is updated only at terminal state transitions.
- **Acking before processing is confirmed**: Acknowledging the message before the job is complete means a Worker crash between ack and completion leaves the job in a ghost state. Ack only after the work is persisted.
- **Tight infinite loops inside a single invocation**: A Consumer Worker is subject to the 15-minute wall-clock limit (Workers Unbound). For jobs that take longer, split work into smaller chunks, persist progress, and re-enqueue continuation messages.
- **Sharing one DO for all jobs**: Each job must have its own DO instance (keyed by `jobId`). A single DO is single-threaded and would serialise all job status updates, destroying concurrency.
- **Ignoring the dead-letter queue**: Messages in the DLQ are invisible by default. Set up a separate consumer for `job-dlq` to alert, inspect, or requeue dead jobs.

---

## Gotchas

- **Queue at-least-once delivery**: The same message can be delivered more than once (e.g. after a Worker crash before ack). The `stub.startRunning()` returning `false` guards against duplicate processing — ensure this check is the first thing the consumer does.
- **DO `idFromName` stability**: `env.JOB_STATE.idFromName(jobId)` is deterministic given the same `jobId` string and the same binding namespace. Never change the binding name in `wrangler.toml` after deploy, as it shifts all DO IDs.
- **Consumer batch partial failure**: If one message in a batch fails, it is retried independently. `Promise.allSettled` ensures a single failing job does not abort processing of the rest of the batch.
- **Message retry delay is approximate**: `msg.retry({ delaySeconds: N })` sets the minimum delay before re-delivery. Actual re-delivery may be longer depending on queue depth and consumer availability.
- **DO eviction does not lose state**: The DO is evicted from memory when idle, but its durable storage persists. The next call to `env.JOB_STATE.get(...)` transparently re-hydrates it.

---

## Verification

```bash
# 1. Enqueue a test job
JOB=$(curl -s -X POST https://myapp.workers.dev/jobs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"jobType":"csv-import","payload":{"fileKey":"uploads/test.csv","userId":"u1"}}')
echo $JOB   # {"jobId":"...","status":"pending","statusUrl":"/jobs/..."}

JOB_ID=$(echo $JOB | jq -r .jobId)

# 2. Poll status
curl https://myapp.workers.dev/jobs/$JOB_ID \
  -H "Authorization: Bearer <token>"
# Eventually: {"status":"running","progress":42,...}
# Then:       {"status":"completed","result":{"rowsImported":50000},...}

# 3. Check D1 job record
wrangler d1 execute MY_DB --command "SELECT * FROM jobs WHERE id = '$JOB_ID';"

# 4. Simulate failure: use a broken R2 key, verify status becomes 'failed'
# After max_retries: verify status becomes 'dead' and message appears in DLQ

# 5. Inspect DLQ
wrangler queues consumer worker job-dlq --name=dlq-inspector
```

---

## Related

- `workers-queue-fanout-architecture.md` — fan-out patterns with Cloudflare Queues
- `competing-consumers-durable-objects.md` — DO concurrency for competing consumers
- `at-least-once-delivery.md` — at-least-once guarantees and deduplication
- `dead-letter-queue-architecture.md` — DLQ handling and requeue strategies
- `durable-object-alarm-api-scheduled-retry.md` — alarm-based retry as an alternative to Queue NACK
- `batch-processing-architecture.md` — batch processing patterns for large data sets
- `idempotency-keys-workers-api.md` — idempotency for the job creation endpoint

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare Queues consumer configuration — https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Cloudflare R2 documentation — https://developers.cloudflare.com/r2/
- Queue message retry API — https://developers.cloudflare.com/queues/reference/message-acknowledge-retry/
