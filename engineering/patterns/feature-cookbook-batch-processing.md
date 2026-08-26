# feature-cookbook-batch-processing

**Issue:** Batch processing — large datasets, queues, progress
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to process 1M users (e.g. a "find friends"
computation). You loop through them in a Worker. The
Worker times out at 30s. Half the users are processed.
The other half are missed. The user reports "I didn't
get the email."

## Root cause
**Bulk processing in a single Worker doesn't scale.**
Use a queue + multiple workers.

**Source:** CF Queues docs.

## The "queue + worker" pattern

For bulk processing, use a queue:
```ts
// 1. Enqueue
async function processAllUsers(env: Env): Promise<void> {
  const users = await env.DB!.prepare(`SELECT id FROM users WHERE active = 1`).all<{ id: string }>();

  for (const user of users.results) {
    await env.QUEUE.send({ type: 'process_user', userId: user.id });
  }
}

// 2. Worker
export async function handleQueue(batch: MessageBatch<Job>, env: Env): Promise<void> {
  for (const message of batch.messages) {
    try {
      await processUser(message.body.userId, env);
      message.ack();
    } catch (err) {
      message.retry({ delaySeconds: 60 });
    }
  }
}
```

The work is parallel; the user request is fast.

## The "batch size" pattern

For batch processing, process in chunks:
```ts
const BATCH_SIZE = 100;

async function processAllUsers(env: Env): Promise<void> {
  const totalUsers = await getUserCount(env);

  for (let offset = 0; offset < totalUsers; offset += BATCH_SIZE) {
    await env.QUEUE.send({ type: 'process_chunk', offset, size: BATCH_SIZE });
  }
}

async function processChunk(chunk: Chunk, env: Env): Promise<void> {
  const users = await env.DB!.prepare(
    `SELECT * FROM users WHERE active = 1 LIMIT ? OFFSET ?`
  ).bind(chunk.size, chunk.offset).all();

  for (const user of users.results) {
    await processUser(user, env);
  }
}
```

The work is split; each chunk is a job.

## The "idempotency" pattern

For retried jobs, idempotency is critical:
```ts
async function processUser(userId: string, env: Env): Promise<void> {
  const idempotencyKey = `processed:${userId}:${new Date().toISOString().split('T')[0]}`;

  const processed = await env.KV.get(idempotencyKey);
  if (processed) {
    console.log({ msg: 'process.user.skipped', userId });
    return;
  }

  await doTheWork(userId, env);
  await env.KV.put(idempotencyKey, '1', { expirationTtl: 86400 * 2 });
}
```

The work is done once, even on retry.

## The "rate limit" pattern

For rate-limited APIs, batch with delay:
```ts
async function processWithRateLimit(users: User[], env: Env): Promise<void> {
  const BATCH_SIZE = 100;
  const DELAY_MS = 1000;

  for (let i = 0; i < users.length; i += BATCH_SIZE) {
    const batch = users.slice(i, i + BATCH_SIZE);
    await Promise.all(batch.map(u => processUser(u, env)));

    if (i + BATCH_SIZE < users.length) {
      await sleep(DELAY_MS);
    }
  }
}
```

The work is throttled.

## The "progress" pattern

For long jobs, track progress:
```ts
async function processAllUsers(env: Env, ctx: McContext): Promise<{ totalProcessed: number }> {
  const totalUsers = await getUserCount(env);
  let totalProcessed = 0;

  // Update progress every 1000 users
  for (const batch of batchesOfUsers(1000, env)) {
    for (const user of batch) {
      await processUser(user.id, env);
      totalProcessed++;
    }

    // Update the progress
    await env.KV.put(`progress:${ctx.user.id}`, JSON.stringify({ totalProcessed, total: totalUsers }));
  }

  return { totalProcessed };
}
```

The progress is queryable.

## The "DLQ" pattern

For permanently failed jobs:
```ts
async function processWithDLQ(message: Job, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = await getAttempts(message.id, env);

  try {
    await doTheWork(message.body, env);
    await env.KV.delete(`attempts:${message.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.DLQ.send({ ...message.body, error: String(err) });
      return;  // Ack to remove from queue
    }
    await env.KV.put(`attempts:${message.id}`, String(attempts + 1));
    throw err;
  }
}
```

Failed jobs go to the DLQ.

## The "cancellation" pattern

For long jobs, allow cancellation:
```ts
async function processAllUsers(env: Env, jobId: string, ctx: McContext): Promise<void> {
  for (const batch of batchesOfUsers(1000, env)) {
    // Check if cancelled
    const cancelled = await env.KV.get(`cancelled:${jobId}`);
    if (cancelled) {
      console.log({ msg: 'process.cancelled', jobId });
      return;
    }

    for (const user of batch) {
      await processUser(user.id, env);
    }
  }
}
```

The user can cancel the job.

## The "checkpoint" pattern

For long jobs, save checkpoints:
```ts
async function processAllUsers(env: Env, jobId: string): Promise<void> {
  // Resume from the last checkpoint
  const checkpoint = await env.KV.get<{ lastOffset: number }>(`checkpoint:${jobId}`);
  let offset = checkpoint?.lastOffset ?? 0;

  while (true) {
    const users = await getUsers(offset, 1000, env);
    if (users.length === 0) break;

    for (const user of users) {
      await processUser(user, env);
    }

    offset += users.length;
    await env.KV.put(`checkpoint:${jobId}`, JSON.stringify({ lastOffset: offset }));
  }

  // Clean up
  await env.KV.delete(`checkpoint:${jobId}`);
}
```

The job can be resumed from the checkpoint.

## The "monitoring" pattern

For batch jobs, monitor:
```ts
metrics.increment('batch.processed_total', { type: 'user' });
metrics.histogram('batch.duration_ms', duration, { type: 'user' });
metrics.gauge('batch.remaining', remaining);
```

The metrics show progress + health.

## The "bulk update" pattern

For batch updates, use SQL:
```ts
// ❌ Slow: N round-trips
for (const user of users) {
  await env.DB!.prepare(`UPDATE users SET status = ? WHERE id = ?`).bind('verified', user.id).run();
}

// ✅ Fast: 1 round-trip
const placeholders = users.map(() => '(?, ?)').join(',');
const values = users.flatMap(u => ['verified', u.id]);
await env.DB!.prepare(
  `UPDATE users SET status = ? WHERE id IN (${placeholders})`
).bind('verified', ...values).run();
```

Bulk SQL is much faster.

## Verification
- **Test:** All users are processed
- **Test:** Failed jobs go to the DLQ
- **Test:** Idempotency works
- **Live:** Batch is monitored
- **Audit:** Quarterly review of batch jobs

## Gotchas
- **The "process in a single Worker" anti-pattern.** The
  Worker times out; use a queue.
- **The "no idempotency" anti-pattern.** A retried job
  does the work twice.
- **The "no rate limit" anti-pattern.** A vendor may
  rate-limit; throttle.
- **The "no progress" anti-pattern.** A 1M-row job with
  no progress looks stuck.
- **The "no checkpoint" anti-pattern.** A failed job
  starts from scratch.

## Related
- `feature-cookbook-background-jobs.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `cron-scheduling.md`
- `database-migration-strategy.md`
