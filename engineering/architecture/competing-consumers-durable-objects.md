# Competing Consumers Pattern with Durable Objects for Distributed Task Processing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Workers application needs to process a shared work queue where multiple
concurrent processors race to claim and execute tasks without double-processing the same
item. Classic serverless architectures handle this with brokered queues (SQS + Lambda),
but Cloudflare's Queues consumer model delivers to a single Worker instance per batch,
losing the elasticity benefit when tasks vary dramatically in duration. The competing
consumers pattern replaces the broker-side lock with a Durable Object that acts as a
stateful task registry: Workers race to claim a task, the DO atomically assigns ownership,
and the winner processes while losers immediately retry the next available task.

Concrete triggers:
- Audio/video transcoding jobs in the example project React Native app that fan out per track
- Bulk chord-diagram generation where each chord is independent
- Batch notification dispatch where each recipient is idempotent but slow
- Scheduled data-sync pipelines where concurrency must not exceed a capacity ceiling

---

## Context

Cloudflare Queues (as of 2025) pull-delivers batches to a single consumer Worker
invocation. Within that invocation parallelism is achievable with `Promise.all`, but
the batch size cap (currently 100 messages) limits throughput for long-running per-message
work. Durable Objects provide the missing piece: a strongly-consistent, single-threaded
execution context that serialises concurrent requests, making them ideal atomic task
registries.

The pattern layers three primitives:
1. **Cloudflare Queue** — durable buffer, fan-in from producers, delivers to a coordinator Worker
2. **Coordinator Worker** — receives queue batches, splits items, dispatches to a pool of processing Workers
3. **Task Registry Durable Object** — atomically claims and releases tasks, tracks state, enforces capacity

This is fundamentally the same as the "competing consumers" enterprise integration pattern
(Hohpe & Woolf, 2003) but implemented without a traditional message broker lock.

---

## Architecture Overview

```
Producer(s)
    │  enqueue(task)
    ▼
Cloudflare Queue
    │  batch delivery (≤100 msgs)
    ▼
Coordinator Worker (queue consumer)
    │  for each message:
    │    POST /task/claim  ──────────────────────────────────▶ TaskRegistry DO
    │                      ◀── { taskId, claimToken } ───────        │
    │                                                                 │ serialised
    │    process(task, claimToken)                                    │ claim logic
    │    POST /task/complete { claimToken }  ────────────────▶ TaskRegistry DO
    │    POST /task/fail { claimToken, retry } ──────────────▶ TaskRegistry DO
    ▼
    ack or nack back to Queue
```

Multiple Coordinator Worker invocations run concurrently (Cloudflare auto-scales). Each
invocation races to claim tasks from the same DO, which serialises claims atomically.

---

## Task Registry Durable Object

```typescript
// src/do/task-registry.ts
import { DurableObject } from 'cloudflare:workers';

interface TaskRecord {
  id: string;
  payload: unknown;
  status: 'pending' | 'claimed' | 'done' | 'failed';
  claimToken?: string;
  claimedAt?: number;
  attempts: number;
  maxAttempts: number;
}

interface Env {
  TASK_REGISTRY: DurableObjectNamespace;
}

export class TaskRegistry extends DurableObject {
  private tasks: Map<string, TaskRecord> = new Map();
  private readonly CLAIM_TIMEOUT_MS = 30_000; // 30 s lease

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    // Rehydrate from storage on cold start
    this.ctx.blockConcurrencyWhile(async () => {
      const stored = await this.ctx.storage.get<Map<string, TaskRecord>>('tasks');
      if (stored) this.tasks = stored;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    switch (url.pathname) {
      case '/enqueue':
        return this.handleEnqueue(request);
      case '/claim':
        return this.handleClaim();
      case '/complete':
        return this.handleComplete(request);
      case '/fail':
        return this.handleFail(request);
      case '/status':
        return this.handleStatus();
      default:
        return new Response('Not found', { status: 404 });
    }
  }

  private async handleEnqueue(request: Request): Promise<Response> {
    const { id, payload, maxAttempts = 3 } = await request.json<{
      id: string;
      payload: unknown;
      maxAttempts?: number;
    }>();

    if (this.tasks.has(id)) {
      return Response.json({ ok: false, reason: 'duplicate' });
    }

    const record: TaskRecord = {
      id, payload, status: 'pending',
      attempts: 0, maxAttempts,
    };
    this.tasks.set(id, record);
    await this.persist();
    return Response.json({ ok: true, id });
  }

  private async handleClaim(): Promise<Response> {
    const now = Date.now();

    // Expire stale claims before trying to claim a new task
    for (const [, task] of this.tasks) {
      if (
        task.status === 'claimed' &&
        task.claimedAt !== undefined &&
        now - task.claimedAt > this.CLAIM_TIMEOUT_MS
      ) {
        task.status = task.attempts >= task.maxAttempts ? 'failed' : 'pending';
        task.claimToken = undefined;
        task.claimedAt = undefined;
      }
    }

    // Find first pending task
    const task = [...this.tasks.values()].find(t => t.status === 'pending');
    if (!task) {
      return Response.json({ ok: false, reason: 'empty' }, { status: 204 });
    }

    const claimToken = crypto.randomUUID();
    task.status = 'claimed';
    task.claimToken = claimToken;
    task.claimedAt = now;
    task.attempts += 1;

    await this.persist();
    return Response.json({ ok: true, taskId: task.id, claimToken, payload: task.payload });
  }

  private async handleComplete(request: Request): Promise<Response> {
    const { claimToken } = await request.json<{ claimToken: string }>();
    const task = this.findByToken(claimToken);
    if (!task) return Response.json({ ok: false, reason: 'invalid_token' }, { status: 400 });

    task.status = 'done';
    task.claimToken = undefined;
    await this.persist();
    return Response.json({ ok: true });
  }

  private async handleFail(request: Request): Promise<Response> {
    const { claimToken, retry = true } = await request.json<{
      claimToken: string;
      retry?: boolean;
    }>();
    const task = this.findByToken(claimToken);
    if (!task) return Response.json({ ok: false, reason: 'invalid_token' }, { status: 400 });

    if (retry && task.attempts < task.maxAttempts) {
      task.status = 'pending';
    } else {
      task.status = 'failed';
    }
    task.claimToken = undefined;
    task.claimedAt = undefined;
    await this.persist();
    return Response.json({ ok: true, status: task.status });
  }

  private async handleStatus(): Promise<Response> {
    const counts = { pending: 0, claimed: 0, done: 0, failed: 0 };
    for (const t of this.tasks.values()) counts[t.status]++;
    return Response.json(counts);
  }

  private findByToken(token: string): TaskRecord | undefined {
    return [...this.tasks.values()].find(t => t.claimToken === token);
  }

  private async persist(): Promise<void> {
    await this.ctx.storage.put('tasks', this.tasks);
  }
}
```

---

## Coordinator Worker (Queue Consumer)

```typescript
// src/workers/coordinator.ts
import type { Env } from '../types';

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    // Use a stable DO name per logical job type to shard if needed
    const registryId = env.TASK_REGISTRY.idFromName('chord-generation');
    const registry = env.TASK_REGISTRY.get(registryId);

    // Enqueue all incoming messages into the DO
    await Promise.all(
      batch.messages.map(msg =>
        registry.fetch('https://do/enqueue', {
          method: 'POST',
          body: JSON.stringify({ id: msg.id, payload: msg.body, maxAttempts: 3 }),
        })
      )
    );

    // Competing claim loop — run N concurrent processors
    const CONCURRENCY = 10;
    await Promise.all(Array.from({ length: CONCURRENCY }, () => this.runWorker(registry, env)));

    // Ack the whole batch once processors are done (DO tracks per-task state)
    batch.ackAll();
  },

  async runWorker(registry: DurableObjectStub, env: Env): Promise<void> {
    while (true) {
      const claimRes = await registry.fetch('https://do/claim', { method: 'POST' });
      if (claimRes.status === 204) break; // No more tasks

      const { taskId, claimToken, payload } = await claimRes.json<{
        taskId: string;
        claimToken: string;
        payload: unknown;
      }>();

      try {
        await processTask(payload, env);
        await registry.fetch('https://do/complete', {
          method: 'POST',
          body: JSON.stringify({ claimToken }),
        });
      } catch (err) {
        await registry.fetch('https://do/fail', {
          method: 'POST',
          body: JSON.stringify({ claimToken, retry: true }),
        });
      }
    }
  },
};

async function processTask(payload: unknown, env: Env): Promise<void> {
  // Domain-specific work: generate chord diagram, transcode audio, etc.
  // Keep under the DO's 30s lease (CLAIM_TIMEOUT_MS above)
}
```

---

## wrangler.toml Configuration

```toml
[[durable_objects.bindings]]
name = "TASK_REGISTRY"
class_name = "TaskRegistry"

[[migrations]]
tag = "v1"
new_classes = ["TaskRegistry"]

[[queues.consumers]]
queue = "chord-jobs"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 0         # DO tracks retries; disable queue-level retry
```

---

## Capacity Sharding

When a single DO becomes a throughput bottleneck (all writes serialised), shard by a
partition key:

```typescript
// Shard by first char of task ID — 16 shards
const shard = taskId.charCodeAt(0) % 16;
const registryId = env.TASK_REGISTRY.idFromName(`tasks-shard-${shard}`);
```

Each shard is an independent DO instance with its own claim queue. Producers and
consumers must agree on the sharding function.

---

## Mobile API Consumer Considerations (example project React Native)

The React Native client should not poll the DO directly. Instead:

1. **Submit** a job via a REST Worker endpoint that enqueues to Cloudflare Queues.
2. **Poll** a lightweight `/job-status/:jobId` Worker endpoint that queries D1 for the
   final outcome written by the processor.
3. **Push** (preferred): the processor Worker POSTs a result to a push-notification
   Worker (Web Push / FCM gateway) when a task completes, avoiding polling entirely.

```
React Native App
    │  POST /jobs  { payload }
    ▼
Ingress Worker ─── enqueue ──▶ Cloudflare Queue
                                     │
                                     ▼
                               Coordinator Worker + DO
                                     │ done
                                     ▼
                               Write result to D1
                               + POST /push/:deviceToken ──▶ FCM/APNs
```

---

## Anti-patterns

- **Claiming inside the queue consumer without a DO**: Workers are stateless; two
  simultaneous invocations will double-process without external coordination.
- **Long leases**: Setting `CLAIM_TIMEOUT_MS` too high means a crashed Worker holds a
  task hostage until the lease expires. Keep it to 1.5× the p99 task duration.
- **Unbounded task map in the DO**: The DO's 128 MB memory limit means the in-memory
  `Map` must be bounded. Prune `done` and `failed` records after a TTL or move them to D1.
- **Using queue-level retries with DO retry logic**: They fight each other. Disable
  queue retries (`max_retries = 0`) and let the DO own the retry policy.
- **Single DO for high-volume workloads**: A single DO handles ~1000 req/s. For bulk
  workloads exceeding that, use sharding (see Capacity Sharding above).

---

## Gotchas

- DO storage writes are durable but add ~1 ms overhead per call. Batching storage
  writes (`put` once per request rather than per field) is critical.
- `blockConcurrencyWhile` in the constructor is the only safe way to rehydrate state.
  Skipping it causes races on the first request after a cold start.
- The DO's single-threaded model means only one `claim` runs at a time — this is the
  feature, not a bug. Shard when you need more parallelism.
- Cloudflare enforces a 30-second CPU time limit per Worker invocation. Ensure the
  coordinator loop's total wall time fits within 30 s (or use streaming responses to
  keep the connection alive for `waitUntil`-backed work).
- DO storage has a 2 GB per-namespace limit across all keys.

---

## Verification

```bash
# 1. Enqueue 50 synthetic tasks
for i in $(seq 1 50); do
  curl -X POST https://api.example.com/queue \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"task-$i\",\"payload\":{\"chord\":\"Cmaj7\"}}"
done

# 2. Check DO status
curl https://api.example.com/registry/status
# Expected: { pending: 0, claimed: 0, done: 50, failed: 0 }

# 3. Inject a failure scenario
curl -X POST https://api.example.com/queue \
  -d '{"id":"fail-1","payload":{"chord":"INVALID"}}'
# After max retries: { failed: 1 }

# 4. Verify no double-processing (check D1 result table for duplicate task IDs)
wrangler d1 execute DB --command \
  "SELECT task_id, COUNT(*) c FROM task_results GROUP BY task_id HAVING c > 1;"
```

---

## Related

- `workers-queue-fanout-architecture.md` — fan-out from a single queue event
- `at-least-once-delivery.md` — queue delivery guarantees
- `message-deduplication.md` — idempotency at the consumer
- `workers-do-websocket-architecture.md` — Durable Objects for real-time state
- `distributed-lock-design.md` — alternative locking primitives
- `dead-letter-queue-architecture.md` — handling exhausted retries

---

## Sources

- Cloudflare Durable Objects documentation (developers.cloudflare.com/durable-objects)
- Cloudflare Queues documentation (developers.cloudflare.com/queues)
- Enterprise Integration Patterns — Hohpe & Woolf (2003), "Competing Consumers" pattern
- Cloudflare Workers runtime limits (CPU time, memory, DO storage)
