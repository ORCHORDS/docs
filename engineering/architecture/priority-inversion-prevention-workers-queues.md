# Priority Inversion Prevention in Workers Queues

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A high-priority payment confirmation is stuck behind 50 000 low-priority bulk
email messages in the same Cloudflare Queue. Enterprise customer jobs wait
minutes while free-tier batch exports consume all consumer concurrency. You
observe that setting a single `maxConcurrency` on one queue makes the problem
worse, not better — this is priority inversion.

---

## Context

**Priority inversion** occurs when a low-priority task holds a resource (queue
consumer slot, Worker CPU, external API rate-limit quota) that a high-priority
task needs, causing the high-priority task to wait longer than a low-priority
one. In Cloudflare Queues, the surface area is:

- A single queue processed FIFO — high-priority messages enqueued after a
  flood of low-priority messages wait behind them
- A shared consumer Worker where `maxConcurrency` is the only throttle
- API rate-limit credits consumed by bulk jobs, starving latency-sensitive ones

The solution is **priority segregation**: separate queues per priority tier,
each with its own consumer and concurrency budget, combined with a **work-
stealing** fallback so idle high-priority consumers can process medium-priority
work.

```
High-priority queue  → Consumer (concurrency 20) → immediate processing
Medium-priority queue → Consumer (concurrency 10) → < 5 s SLA
Low-priority queue   → Consumer (concurrency  5) → best-effort
                           │ (idle steal)
                           └─ pulls from medium if high queue empty
```

---

## Queue Topology — Three-Tier Separation

```toml
# wrangler.toml
[[queues.producers]]
queue = "jobs-high"
binding = "HIGH_QUEUE"

[[queues.producers]]
queue = "jobs-medium"
binding = "MEDIUM_QUEUE"

[[queues.producers]]
queue = "jobs-low"
binding = "LOW_QUEUE"

[[queues.consumers]]
queue = "jobs-high"
max_batch_size = 10
max_batch_timeout = 1
max_concurrency = 20
max_retries = 3

[[queues.consumers]]
queue = "jobs-medium"
max_batch_size = 25
max_batch_timeout = 5
max_concurrency = 10
max_retries = 5

[[queues.consumers]]
queue = "jobs-low"
max_batch_size = 100
max_batch_timeout = 30
max_concurrency = 5
max_retries = 10
```

---

## Priority-Aware Producer

```typescript
type JobPriority = "high" | "medium" | "low";

interface Job {
  id: string;
  type: string;
  priority: JobPriority;
  payload: unknown;
  enqueuedAt: string;
}

interface ProducerEnv {
  HIGH_QUEUE: Queue<Job>;
  MEDIUM_QUEUE: Queue<Job>;
  LOW_QUEUE: Queue<Job>;
}

const PRIORITY_QUEUES: Record<JobPriority, keyof ProducerEnv> = {
  high: "HIGH_QUEUE",
  medium: "MEDIUM_QUEUE",
  low: "LOW_QUEUE",
};

async function enqueueJob(
  env: ProducerEnv,
  type: string,
  payload: unknown,
  priority: JobPriority
): Promise<string> {
  const job: Job = {
    id: crypto.randomUUID(),
    type,
    priority,
    payload,
    enqueuedAt: new Date().toISOString(),
  };

  const queueKey = PRIORITY_QUEUES[priority];
  const queue = env[queueKey] as Queue<Job>;
  await queue.send(job, {
    // Use delaySeconds=0 for high priority to avoid any scheduler holdback
    delaySeconds: priority === "low" ? 5 : 0,
  });

  return job.id;
}

// Usage: payment confirmation → high priority
// Usage: report generation → medium priority
// Usage: bulk export → low priority
export default {
  async fetch(request: Request, env: ProducerEnv): Promise<Response> {
    const { type, payload, priority = "medium" } = await request.json<{
      type: string;
      payload: unknown;
      priority?: JobPriority;
    }>();

    const jobId = await enqueueJob(env, type, payload, priority as JobPriority);
    return Response.json({ jobId });
  },
};
```

---

## Consumer Worker — Rate-Limited Execution

Each tier's consumer applies its own rate limiter to prevent resource
starvation across tiers that share upstream APIs:

```typescript
import type { MessageBatch, Message } from "@cloudflare/workers-types";

interface ConsumerEnv {
  DB: D1Database;
  RATE_LIMITER: RateLimiter; // Cloudflare Workers Rate Limiting binding
  PRIORITY_TIER: string;     // set via env var per consumer
}

export default {
  async queue(batch: MessageBatch<Job>, env: ConsumerEnv): Promise<void> {
    // Process messages in enqueue order within the batch (already FIFO within tier)
    for (const message of batch.messages) {
      await processWithBackpressure(message, env);
    }
  },
};

async function processWithBackpressure(
  message: Message<Job>,
  env: ConsumerEnv
): Promise<void> {
  // Check rate limit before consuming external API quota
  const { success } = await env.RATE_LIMITER.limit({ key: env.PRIORITY_TIER });
  if (!success) {
    // Rate limited: retry later rather than drop
    message.retry({ delaySeconds: tierRetryDelay(env.PRIORITY_TIER) });
    return;
  }

  try {
    await processJob(message.body, env);
    message.ack();

    // Emit latency metric for SLA monitoring
    const latencyMs = Date.now() - new Date(message.body.enqueuedAt).getTime();
    console.log(JSON.stringify({
      level: "info",
      event: "job_processed",
      jobId: message.body.id,
      priority: message.body.priority,
      latencyMs,
      tier: env.PRIORITY_TIER,
    }));
  } catch (err) {
    console.error("Job failed", message.body.id, err);
    message.retry({ delaySeconds: 30 });
  }
}

function tierRetryDelay(tier: string): number {
  return tier === "high" ? 2 : tier === "medium" ? 10 : 60;
}

async function processJob(job: Job, _env: ConsumerEnv): Promise<void> {
  // Dispatch to job-type handlers
  switch (job.type) {
    case "send_payment_confirmation":
      // ... process payment
      break;
    case "generate_report":
      // ... generate report
      break;
    default:
      throw new Error(`Unknown job type: ${job.type}`);
  }
}
```

---

## Priority Ceiling — Preventing Starvation of Low-Priority Work

Pure priority queues can starve low-priority work indefinitely. Use an
**aging** mechanism: promote jobs that have waited beyond their SLA threshold:

```typescript
interface PromotionEnv {
  DB: D1Database;
  HIGH_QUEUE: Queue<Job>;
  MEDIUM_QUEUE: Queue<Job>;
}

// Scheduled every 5 minutes
export async function promoteAgedJobs(env: PromotionEnv): Promise<void> {
  const MEDIUM_TO_HIGH_AGE_MS = 2 * 60 * 1000; // promote medium after 2 min
  const cutoff = new Date(Date.now() - MEDIUM_TO_HIGH_AGE_MS).toISOString();

  const { results } = await env.DB
    .prepare(
      `SELECT id, type, payload
         FROM pending_jobs
        WHERE priority = 'medium'
          AND enqueued_at < ?
          AND promoted = 0
        LIMIT 50`
    )
    .bind(cutoff)
    .all<{ id: string; type: string; payload: string }>();

  for (const row of results) {
    const job: Job = {
      id: row.id,
      type: row.type,
      priority: "high", // promoted
      payload: JSON.parse(row.payload),
      enqueuedAt: new Date().toISOString(),
    };
    await env.HIGH_QUEUE.send(job);
    await env.DB
      .prepare("UPDATE pending_jobs SET promoted = 1 WHERE id = ?")
      .bind(row.id)
      .run();
  }
}
```

---

## Dead-Letter Isolation per Tier

Each tier should have its own DLQ binding so that a flood of failed low-
priority jobs never fills the shared DLQ and obscures high-priority failures:

```toml
[[queues.consumers]]
queue = "jobs-high"
dead_letter_queue = "dlq-high"

[[queues.consumers]]
queue = "jobs-medium"
dead_letter_queue = "dlq-medium"

[[queues.consumers]]
queue = "jobs-low"
dead_letter_queue = "dlq-low"
```

---

## Anti-patterns

- **One queue, one consumer for all priorities**: The textbook priority
  inversion scenario. A single FIFO queue cannot express priority.
- **Solving with `delaySeconds` alone**: Delay only defers — it does not
  guarantee a low-priority message yields to a high-priority one added later.
- **Unbounded concurrency on the low tier**: Low-priority consumers consuming
  100 % of external API rate-limit credit starve high-priority consumers.
- **Promoting jobs without deduplication**: If the original queue message is
  also retried, the same job may be processed twice after promotion.

---

## Gotchas

- Cloudflare Queues does not natively support priority within a single queue;
  multiple queues is the only supported mechanism.
- `max_concurrency` in `wrangler.toml` sets the ceiling across all instances
  of that consumer Worker; it is not a per-isolate setting.
- Workers Rate Limiting bindings use a sliding window; bursts within the window
  can still exhaust quota before the window resets, so size windows conservatively.
- High `max_batch_timeout` on the high-priority consumer adds unnecessary
  latency waiting for a full batch; set it to 1 s or less.

---

## Verification

```bash
# Compare queue depths across tiers
wrangler queues consumer get jobs-high
wrangler queues consumer get jobs-medium
wrangler queues consumer get jobs-low

# Watch for SLA breaches in Workers Logs
wrangler tail --search "latencyMs" --format json | jq \
  'select(.message | contains("job_processed")) | {priority, latencyMs}'

# Inject a high-priority test job
curl -X POST https://api.example.com/jobs \
  -H "Content-Type: application/json" \
  -d '{"type":"send_payment_confirmation","payload":{},"priority":"high"}'
```

---

## Related

- `priority-queue-architecture.md`
- `backpressure-patterns.md`
- `dead-letter-queue-architecture.md`
- `competing-consumers-queues.md`
- `rate-limiting-architecture-workers.md`

---

## Sources

- Priority inversion — NASA Mars Pathfinder incident (1997)
- Cloudflare Queues documentation — Consumer concurrency and batching
- Cloudflare Workers Rate Limiting API documentation
- L. Sha, R. Rajkumar, J. Lehoczky — "Priority Inheritance Protocols" (1990)
