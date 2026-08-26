# feature-cookbook-queues

**Issue:** Queues — async, retry, DLQ
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a long-running task. The user submits it.
The Worker times out at 30s. The task is half-done.
The user has no idea what happened.

## Root cause
**Long-running tasks in a single Worker don't work.**
Use a queue.

**Source:** CF Queues docs.

## The "queue" concept

A queue is a buffer between the producer and consumer.
The producer sends a message; the consumer processes
it asynchronously.

**Source:** CF Queues:
https://developers.cloudflare.com/queues/

## The "CF Queues" pattern

For CF Queues, declare in `wrangler.toml`:
```toml
[[queues.producers]]
queue = "tasks"
binding = "TASKS"

[[queues.consumers]]
queue = "tasks"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "tasks-dlq"

[[queues.producers]]
queue = "tasks-dlq"
binding = "TASKS_DLQ"
```

The queue is bound.

## The "send" pattern

For sending a message:
```ts
// Single message
await env.TASKS.send({ type: 'process_user', userId: 'u_123' });

// Batch
await env.TASKS.sendBatch([
  { body: { type: 'process_user', userId: 'u_1' } },
  { body: { type: 'process_user', userId: 'u_2' } },
]);
```

The message is sent.

## The "consume" pattern

For consuming:
```ts
export default {
  async queue(batch: MessageBatch<Job>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processJob(message.body, env);
        message.ack();
      } catch (err) {
        if (err instanceof NonRetryableError) {
          message.ack();  // Don't retry
          await env.KV.put(`failed:${message.id}`, String(err));
        } else {
          message.retry({ delaySeconds: 60 });  // Retry
        }
      }
    }
  },
};
```

The consumer processes the batch.

## The "idempotent" pattern

For idempotency:
```ts
async function processJob(job: Job, env: Env): Promise<void> {
  const processed = await env.KV.get(`processed:${job.id}`);
  if (processed) return;

  await doWork(job, env);
  await env.KV.put(`processed:${job.id}`, '1', { expirationTtl: 86400 * 30 });
}
```

The job is processed once.

## The "DLQ" pattern

For DLQ:
```ts
async function processWithDLQ(job: Job, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = await getAttempts(job.id, env);

  try {
    await doWork(job, env);
    await env.KV.delete(`attempts:${job.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.TASKS_DLQ.send({ ...job, error: String(err) });
      return;
    }
    await env.KV.put(`attempts:${job.id}`, String(attempts + 1));
    throw err;
  }
}
```

Failed jobs go to DLQ.

## The "batch size" pattern

For batch size:
- **Small batches (1-10):** Lower latency, more overhead
- **Large batches (100+):** Higher throughput, higher
  latency

```toml
[[queues.consumers]]
max_batch_size = 100  # Process 100 at a time
max_batch_timeout = 30  # Wait up to 30s for a full batch
```

The batch size is tuned.

## The "priority queue" pattern (limited)

CF Queues doesn't have native priority. Workaround:
- **Separate queues:** high-priority, default, low-priority
- **Worker split:** More consumers on high-priority

```toml
[[queues.producers]]
queue = "tasks-high"

[[queues.producers]]
queue = "tasks-default"

[[queues.producers]]
queue = "tasks-low"
```

The priority is via separate queues.

## The "delay" pattern

For delay (CF Queues doesn't support per-message delay):
- **Schedule:** Use a scheduled Worker
- **Multiple queues:** One per delay bucket

```ts
// Use a scheduled Worker
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const due = await getDueJobs(env);
    for (const job of due) {
      await env.TASKS.send(job);
    }
  },
};
```

The delayed job is sent.

## The "queue observability" pattern

For queue observability:
- **Queue depth:** How many messages waiting?
- **Processing time:** How long per message?
- **Failure rate:** % failed
- **DLQ depth:** How many failed?

```ts
metrics.gauge('queue.depth', depth, { queue: 'tasks' });
metrics.histogram('queue.duration_ms', duration, { queue: 'tasks' });
metrics.increment('queue.failed_total', { queue: 'tasks' });
```

The queue is monitored.

## The "queue backpressure" pattern

For backpressure:
- **Throttle:** Slow the producer
- **Batch:** Send in batches
- **Drop:** Drop low-priority under load

```ts
async function sendIfNotBackedUp(message: any, env: Env): Promise<boolean> {
  const depth = await getQueueDepth(env);
  if (depth > 10_000) {
    logEvent('queue.backpressure', 'warn', { depth });
    return false;  // Drop
  }
  await env.TASKS.send(message);
  return true;
}
```

The producer respects backpressure.

## The "queue anti-pattern" anti-patterns

### 1. Long-running task in a Worker
- **Issue:** Worker times out
- **Fix:** Use a queue

### 2. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** Idempotency keys

### 3. No DLQ
- **Issue:** Failed messages are lost
- **Fix:** Use a DLQ

### 4. No monitoring
- **Issue:** Queue depth grows silently
- **Fix:** Monitor depth + failure rate

### 5. Synchronous wait
- **Issue:** The request waits for the queue
- **Fix:** Return a job ID; poll

### 6. Tight coupling
- **Issue:** The producer and consumer are coupled
- **Fix:** Loose coupling via events

## Verification
- **Test:** Messages are processed
- **Test:** Retries work
- **Test:** DLQ captures failures
- **Test:** Idempotency works
- **Live:** Queue depth is monitored
- **Audit:** Quarterly queue review

## Gotchas
- **The "no idempotency" anti-pattern.** Idempotency
  keys.
- **The "no DLQ" anti-pattern.** Capture failed
  messages.
- **The "synchronous wait" anti-pattern.** Return a job
  ID.

## Related
- `cloudflare/workers-workers-queues-patterns.md`
- `feature-cookbook-event-driven.md`
- `feature-cookbook-batch-processing.md`
- `feature-cookbook-error-recovery.md`
- `idempotency-keys.md`
- `event-sourcing.md`
- CF Queues: https://developers.cloudflare.com/queues/
