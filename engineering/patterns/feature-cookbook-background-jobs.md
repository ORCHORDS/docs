# feature-cookbook-background-jobs

**Issue:** Background jobs — cron, queues, retries
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to send a daily digest email to 100k users.
You put the logic in a Worker. The Worker times out.
Half the emails are sent. The user complains.

## Root cause
**Long-running tasks in a single Worker don't work.**
Use a queue.

**Source:** CF Cron + Queues.

## The "cron" pattern

For scheduled jobs, CF Cron Triggers:
```toml
[triggers]
crons = ["0 9 * * *"]  # 9am UTC daily
```

```ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Run the job
    await sendDailyDigest(env, ctx);
  },
};
```

The cron is scheduled.

## The "queue" pattern

For background jobs, use a queue:
```ts
// 1. Enqueue
await env.QUEUE.send({ type: 'send_email', userId, template: 'daily-digest' });

// 2. Process
export default {
  async queue(batch: MessageBatch<Job>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processJob(message.body, env);
        message.ack();
      } catch (err) {
        message.retry();
      }
    }
  },
};
```

The queue is async.

## The "batch processing" pattern

For bulk operations:
```ts
async function processAllUsers(env: Env, ctx: ExecutionContext): Promise<void> {
  // 1. Get all users
  const users = await env.DB!.prepare(`SELECT id FROM users WHERE active = 1`).all<{ id: string }>();

  // 2. Chunk + enqueue
  const BATCH_SIZE = 100;
  for (let i = 0; i < users.results.length; i += BATCH_SIZE) {
    const batch = users.results.slice(i, i + BATCH_SIZE);
    await env.QUEUE.send({
      type: 'process_batch',
      userIds: batch.map(u => u.id),
    });
  }
}
```

The work is parallelized.

## The "idempotent job" pattern

For idempotency:
```ts
async function processJob(job: Job, env: Env): Promise<void> {
  const key = `job:${job.id}`;
  const processed = await env.KV!.get(key);
  if (processed) return;

  await doWork(job, env);
  await env.KV!.put(key, '1', { expirationTtl: 86400 * 30 });
}
```

The job is processed once.

## The "retry" pattern

For retries:
```ts
async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxAttempts - 1) throw err;
      if (!isRetryable(err)) throw err;
      await sleep(Math.min(2 ** attempt * 1000, 30_000));
    }
  }
  throw new Error('unreachable');
}
```

The retry is exponential.

## The "DLQ" pattern

For failed jobs:
```ts
async function processWithDLQ(job: Job, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = await getAttempts(job.id, env);

  try {
    await doWork(job, env);
    await env.KV!.delete(`attempts:${job.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.DLQ.send({ ...job, error: String(err) });
      return;
    }
    await env.KV!.put(`attempts:${job.id}`, String(attempts + 1));
    throw err;
  }
}
```

Failed jobs go to DLQ.

## The "long-running" pattern

For long-running, use ctx.waitUntil:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Start a background task
    ctx.waitUntil(doLongRunningWork(env));

    // Return immediately
    return new Response('OK');
  },
};
```

The request returns immediately.

## The "cron expression" pattern

For cron:
```
* * * * *
| | | | |
| | | | +-- day of week (0-6, 0=Sunday)
| | | +---- month (1-12)
| | +------ day of month (1-31)
| +-------- hour (0-23)
+---------- minute (0-59)
```

Common expressions:
- `0 9 * * *` — daily at 9am
- `0 */2 * * *` — every 2 hours
- `0 0 * * 0` — weekly on Sunday midnight
- `0 0 1 * *` — monthly on the 1st

## The "job observability" pattern

For observability:
- **Total jobs:** How many?
- **Failed jobs:** How many failed?
- **Average duration:** How long?
- **DLQ depth:** How many failed permanently?

```ts
metrics.increment('jobs.processed_total', { type: 'send_email' });
metrics.histogram('jobs.duration_ms', duration, { type: 'send_email' });
```

The jobs are monitored.

## The "job priority" pattern

For priority, separate queues:
```toml
[[queues.producers]]
queue = "high-priority"
binding = "HIGH_PRIORITY"

[[queues.producers]]
queue = "default"
binding = "DEFAULT"

[[queues.producers]]
queue = "low-priority"
binding = "LOW_PRIORITY"
```

The priority is via separate queues.

## The "job scheduling" pattern

For delayed jobs, scheduled Worker:
```ts
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const due = await env.KV!.get<Job[]>(`due:${event.cron}`, 'json') ?? [];
    for (const job of due) {
      await env.QUEUE.send(job);
    }
  },
};
```

The delayed job is sent.

## The "job test" pattern

For testing:
```ts
test('sendEmail processes correctly', async () => {
  const job = { type: 'send_email', userId: 'u_1', template: 'welcome' };
  await processJob(job, mockEnv);

  expect(mockEmail.send).toHaveBeenCalledWith({
    to: 'alice@example.com',
    subject: 'Welcome!',
  });
});
```

The job is tested.

## The "job anti-pattern" anti-patterns

### 1. Long-running in Worker
- **Issue:** Worker times out
- **Fix:** Use a queue

### 2. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** Idempotency keys

### 3. No retry
- **Issue:** Transient failure = permanent failure
- **Fix:** Retry with backoff

### 4. No DLQ
- **Issue:** Failed jobs are lost
- **Fix:** Use DLQ

### 5. No monitoring
- **Issue:** Job health is unknown
- **Fix:** Metrics

## Verification
- **Test:** Cron fires
- **Test:** Jobs are processed
- **Test:** Idempotency works
- **Live:** Job health is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "long-running in Worker" anti-pattern.** Use
  queue.
- **The "no idempotency" anti-pattern.** Idempotency
  keys.
- **The "no DLQ" anti-pattern.** Capture failures.

## Related
- `cloudflare/workers-workers-queues-patterns.md`
- `feature-cookbook-batch-processing.md`
- `feature-cookbook-queues.md`
- `feature-cookbook-error-recovery.md`
- `cron-scheduling.md`
- `idempotency-keys.md`
- CF Cron: https://developers.cloudflare.com/workers/configuration/cron-triggers/
