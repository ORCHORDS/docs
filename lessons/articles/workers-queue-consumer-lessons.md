# Workers Queue Consumer Lessons

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You wire up a Cloudflare Queue consumer and everything looks fine in staging. In production, messages appear to retry forever, the DLQ never receives anything, two consumer instances process the same message twice on bursts, and increasing batch size makes throughput *worse* rather than better. Separately, a Queue-based ordering guarantee that worked in dev breaks under concurrent load.

---

## Context

Cloudflare Queues deliver messages to a Worker consumer in configurable batches. The consumer has a fixed wall-clock timeout (default 60 s, max 600 s as of 2025). Each message must be explicitly acknowledged with `message.ack()` or batch-acknowledged with `batch.ackAll()`. Unacknowledged messages are retried up to `max_retries` times; after that they are forwarded to a dead-letter queue if one is configured. Multiple consumer instances can run concurrently on the same queue during traffic bursts.

Orchords uses Queues for audio processing jobs, notification fanning, and analytics ingestion. The lessons below reflect real failures across those workloads.

---

## Solution

```typescript
// workers-queue-consumer-lessons.ts

import type { Queue, MessageBatch, Message, ExecutionContext } from '@cloudflare/workers-types';

interface Env {
  AUDIO_QUEUE: Queue;
  DEAD_LETTER_STORE: KVNamespace;
  DB: D1Database;
}

// ─────────────────────────────────────────────────────────────
// LESSON 1: Always ack() explicitly — never rely on implicit ack
// ─────────────────────────────────────────────────────────────
//
// If queue() returns without calling ack() on each message,
// the runtime treats the entire batch as failed and retries.
// This is the most common cause of infinite retry loops.

export default {
  async queue(
    batch: MessageBatch<AudioJob>,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processAudioJob(message.body, env);
        message.ack(); // REQUIRED — missing this = infinite retry
      } catch (err) {
        if (isTransient(err)) {
          message.retry({ delaySeconds: backoffSeconds(message.attempts) });
        } else {
          // Permanent failure: ack to remove from queue,
          // then write to our own DLQ store for debugging
          await env.DEAD_LETTER_STORE.put(
            `dlq:${message.id}`,
            JSON.stringify({ body: message.body, error: String(err), ts: Date.now() }),
            { expirationTtl: 7 * 24 * 3600 }
          );
          message.ack();
        }
      }
    }
  },
};

function backoffSeconds(attempts: number): number {
  // Exponential backoff: 10s, 20s, 40s, 80s, max 300s
  return Math.min(10 * Math.pow(2, attempts - 1), 300);
}

function isTransient(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return (
    err.message.includes('timeout') ||
    err.message.includes('429') ||
    err.message.includes('503')
  );
}

// ─────────────────────────────────────────────────────────────
// LESSON 2: DLQ requires max_retries to be set explicitly
// ─────────────────────────────────────────────────────────────
//
// If max_retries is not set in wrangler.toml, the default is
// 3 retries but the DLQ binding is never consulted — messages
// are silently dropped after max retries, not forwarded.
//
// wrangler.toml:
//
// [[queues.consumers]]
// queue = "audio-jobs"
// max_batch_size = 10
// max_batch_timeout = 5
// max_retries = 3                          # REQUIRED for DLQ
// dead_letter_queue = "audio-jobs-dlq"    # REQUIRED for DLQ
// visibility_timeout_ms = 30000

// ─────────────────────────────────────────────────────────────
// LESSON 3: Batch size tuning — bigger is not always better
// ─────────────────────────────────────────────────────────────
//
// A batch of 100 audio jobs each taking 500 ms exceeds the 60 s
// consumer timeout. The runtime kills the invocation, all 100
// messages retry, and you get amplified load. Tune batch size
// to: batch_size * avg_processing_time_ms < (timeout_ms * 0.7)

const MAX_BATCH_SIZE = 10; // configured in wrangler.toml
const AVG_JOB_MS = 4_000; // measured from production metrics
const TIMEOUT_MS = 60_000; // consumer timeout
const SAFETY_FACTOR = 0.7;
// headroom = TIMEOUT_MS * SAFETY_FACTOR / AVG_JOB_MS = 10.5 → 10

interface AudioJob {
  songId: string;
  format: 'mp3' | 'wav' | 'flac';
  operation: 'transcode' | 'waveform' | 'fingerprint';
}

async function processAudioJob(job: AudioJob, env: Env): Promise<void> {
  // Simulate processing
  const start = Date.now();
  await env.DB.prepare(
    'UPDATE songs SET processing_status = ? WHERE id = ?'
  )
    .bind('processing', job.songId)
    .run();

  // ... actual audio processing ...

  await env.DB.prepare(
    'UPDATE songs SET processing_status = ?, processed_at = ? WHERE id = ?'
  )
    .bind('done', new Date().toISOString(), job.songId)
    .run();

  console.log(`Processed ${job.songId} in ${Date.now() - start}ms`);
}

// ─────────────────────────────────────────────────────────────
// LESSON 4: Duplicate processing under concurrent consumers
// ─────────────────────────────────────────────────────────────
//
// During traffic spikes, Cloudflare may invoke multiple consumer
// instances concurrently on the same queue. If your processing
// is not idempotent, messages can be processed more than once.
//
// Fix: use an idempotency key in D1 or KV before processing.

async function processIdempotent(
  message: Message<AudioJob>,
  env: Env
): Promise<void> {
  const key = `processing:${message.id}`;

  // Attempt to claim this message ID atomically
  const existing = await env.DEAD_LETTER_STORE.get(key);
  if (existing !== null) {
    // Another consumer instance already processed this message
    console.warn(`Duplicate message ${message.id} skipped`);
    message.ack();
    return;
  }

  // Claim the message with a short TTL (longer than max consumer timeout)
  await env.DEAD_LETTER_STORE.put(key, '1', { expirationTtl: 600 });

  await processAudioJob(message.body, env);
  message.ack();
}

// ─────────────────────────────────────────────────────────────
// LESSON 5: Queue vs Durable Object for ordered processing
// ─────────────────────────────────────────────────────────────
//
// Cloudflare Queues deliver messages in roughly FIFO order but
// do NOT guarantee strict ordering across concurrent consumer
// invocations. If you need strict per-entity ordering
// (e.g., process song A's events in creation order), route
// messages to a Durable Object keyed on the entity ID.

interface Env2 extends Env {
  SONG_PROCESSOR: DurableObjectNamespace;
}

export const orderedConsumer = {
  async queue(
    batch: MessageBatch<AudioJob>,
    env: Env2,
    _ctx: ExecutionContext
  ): Promise<void> {
    // Group messages by entity to preserve per-song ordering
    const grouped = new Map<string, Message<AudioJob>[]>();
    for (const msg of batch.messages) {
      const list = grouped.get(msg.body.songId) ?? [];
      list.push(msg);
      grouped.set(msg.body.songId, list);
    }

    // Route each group to the DO for that song (single-threaded per DO)
    await Promise.all(
      Array.from(grouped.entries()).map(async ([songId, messages]) => {
        const id = env.SONG_PROCESSOR.idFromName(songId);
        const stub = env.SONG_PROCESSOR.get(id);
        const body = messages.map((m) => m.body);

        const res = await stub.fetch('https://do/process', {
          method: 'POST',
          body: JSON.stringify(body),
          headers: { 'Content-Type': 'application/json' },
        });

        if (res.ok) {
          messages.forEach((m) => m.ack());
        } else {
          // Let the queue retry the whole group
          messages.forEach((m) => m.retry());
        }
      })
    );
  },
};

// ─────────────────────────────────────────────────────────────
// LESSON 6: Consumer timeout vs message processing time
// ─────────────────────────────────────────────────────────────
//
// The consumer timeout is wall-clock time for the entire batch,
// not per message. Use ctx.waitUntil() for fire-and-forget work
// that can outlive the batch handler, and keep the main handler
// lean. But note: messages are only safe to ack() before
// ctx.waitUntil resolves if you are sure the work will succeed.

export const timedConsumer = {
  async queue(
    batch: MessageBatch<AudioJob>,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    const jobs = batch.messages.map((msg) => ({
      message: msg,
      promise: processAudioJob(msg.body, env).then(() => msg.ack()),
    }));

    // Race all jobs against a per-batch deadline
    const deadline = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('batch deadline')), 50_000)
    );

    const results = await Promise.allSettled(
      jobs.map((j) => Promise.race([j.promise, deadline]))
    );

    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      if (result.status === 'rejected') {
        jobs[i].message.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

---

## Implementation Details

**Explicit `ack()` vs implicit** — the Cloudflare Queues runtime only considers a message successfully delivered if `ack()` or `ackAll()` is called before the consumer handler returns. An unhandled exception, a forgotten `ack()`, or a timeout all cause the entire batch to be retried. There is no way to partially acknowledge a batch without iterating over each message individually.

**DLQ wiring** requires both `max_retries` and `dead_letter_queue` in `wrangler.toml`. Setting only one has no effect. After `max_retries` exhausted, the message is forwarded to the named queue (which must exist and have its own consumer or be a plain queue you read with the REST API).

**Visibility timeout** (`visibility_timeout_ms`) is the window during which a message is invisible to other consumer instances after it has been delivered. Set it to at least 1.5× your average processing time per message to avoid spurious re-delivery under slow processing.

**Idempotency keys** should be scoped to `message.id`, which is stable across retries (same message, same ID). Do not use a composite key derived from message body — body may repeat for naturally duplicate events.

**Queue vs DO ordering** — use Queues when ordering is not critical and you want horizontal scale. Use a Durable Object when per-entity strict ordering is required. Route from the queue consumer to a DO keyed on the entity ID to get the best of both: durable delivery via Queue + ordered execution via DO.

---

## Anti-patterns

- Returning from `queue()` without acking every message (causes infinite retry).
- Setting `max_batch_size` to 100 for workloads with 4-second average processing time (guaranteed timeout).
- Assuming `dead_letter_queue` works without also setting `max_retries`.
- Processing messages in parallel with `Promise.all()` and then calling `batch.ackAll()` — if one job fails, you ack the whole batch and lose the failed message.
- Using a global counter in the Worker as a deduplication store (resets on every invocation).
- Sending non-serialisable objects to the queue — the body must be JSON-serialisable; Dates become strings and are parsed back as strings.

---

## Gotchas

- `message.retry()` does not throw or stop execution — you must `return` or `continue` after calling it, otherwise processing continues and you may call `ack()` later.
- `message.attempts` starts at `1` on the first delivery, so your backoff formula should use `attempts - 1` as the exponent to get 0 delay on the first retry.
- Queues do not guarantee exactly-once delivery even with `max_retries = 0` — at-least-once is the model. Design consumers to be idempotent.
- The consumer timeout is not configurable above 600 s. If a job legitimately takes longer than 600 s, break it into stages and chain them via the queue.
- `batch.retryAll()` retries all messages in the batch, including ones you already called `ack()` on — it overrides individual acks.

---

## Verification

```typescript
// Integration test skeleton using Miniflare or wrangler dev
import { Miniflare } from 'miniflare';

const mf = new Miniflare({
  scriptPath: './dist/index.js',
  queueConsumers: ['audio-jobs'],
});

// Send a message and assert the DB row is updated
await mf.sendQueueMessages('audio-jobs', [
  { songId: 'song-1', format: 'mp3', operation: 'transcode' },
]);

// Allow the consumer a tick to run
await new Promise((r) => setTimeout(r, 100));

const db = await mf.getD1Database('DB');
const row = await db.prepare('SELECT processing_status FROM songs WHERE id = ?').bind('song-1').first();
console.assert(row?.processing_status === 'done', 'song should be processed');
```

---

## Related

- `documentation/categories/lessons/workers-durable-object-pitfalls.md`
- `documentation/categories/lessons/subrequest-limit-patterns.md`
- Cloudflare Queues documentation: Consumer configuration, Retry and DLQ, Batch processing

---

## Sources

- Cloudflare Workers Queues docs (2025)
- Orchords production incident log #QUE-007 (infinite retry), #QUE-012 (DLQ misconfiguration), #QUE-019 (duplicate processing)
- Cloudflare Community: "Queue consumer not sending to DLQ" thread
