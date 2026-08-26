# Priority Queue Pattern with Cloudflare Queues

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Not all background jobs are equal — a payment webhook must not wait behind a bulk CSV export. Cloudflare Queues are strictly FIFO within a single queue, but you need high-priority work to jump ahead of low-priority work.

## Context
Cloudflare Queues does not have native message priorities. The standard workaround is to provision multiple queues — one per priority tier — and let the consumer drain higher-priority queues first using sequential polling. Producer workers route messages to the correct queue based on business rules. Dead-letter handling and retry budgets apply per-queue, giving you independent tuning of each tier. This pattern adds minimal operational overhead because all queues share the same consumer Worker.

## Queue Bindings Setup
Declare three queues in `wrangler.toml`. The consumer Worker pulls from all three; the producer only sends to one.

```toml
# wrangler.toml (producer and consumer share this file or use separate deployments)
[[queues.producers]]
queue = "jobs-high"
binding = "Q_HIGH"

[[queues.producers]]
queue = "jobs-normal"
binding = "Q_NORMAL"

[[queues.producers]]
queue = "jobs-low"
binding = "Q_LOW"

[[queues.consumers]]
queue = "jobs-high"
max_batch_size = 10
max_batch_timeout = 2
max_retries = 3
dead_letter_queue = "jobs-dlq"

[[queues.consumers]]
queue = "jobs-normal"
max_batch_size = 20
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "jobs-dlq"

[[queues.consumers]]
queue = "jobs-low"
max_batch_size = 50
max_batch_timeout = 10
max_retries = 2
dead_letter_queue = "jobs-dlq"
```

## Producer — Routing by Priority
The producer inspects the message payload and routes to the matching queue binding.

```typescript
type Priority = 'high' | 'normal' | 'low';

interface Job {
  type: string;
  priority: Priority;
  payload: Record<string, unknown>;
  traceId: string;
}

interface ProducerEnv {
  Q_HIGH: Queue<Job>;
  Q_NORMAL: Queue<Job>;
  Q_LOW: Queue<Job>;
}

function queueForPriority(env: ProducerEnv, priority: Priority): Queue<Job> {
  switch (priority) {
    case 'high':   return env.Q_HIGH;
    case 'normal': return env.Q_NORMAL;
    default:       return env.Q_LOW;
  }
}

function derivePriority(jobType: string): Priority {
  const HIGH_TYPES = new Set(['payment_webhook', 'fraud_alert', 'user_verification']);
  const LOW_TYPES  = new Set(['report_export', 'bulk_import', 'notification_digest']);
  if (HIGH_TYPES.has(jobType)) return 'high';
  if (LOW_TYPES.has(jobType))  return 'low';
  return 'normal';
}

export const producer = {
  async fetch(request: Request, env: ProducerEnv): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{ type: string; payload: Record<string, unknown> }>();
    const priority = derivePriority(body.type);
    const job: Job = {
      type: body.type,
      priority,
      payload: body.payload,
      traceId: request.headers.get('x-trace-id') ?? crypto.randomUUID(),
    };

    await queueForPriority(env, priority).send(job);
    return Response.json({ queued: true, priority, traceId: job.traceId }, { status: 202 });
  },
};
```

## Consumer — Processing in Priority Order
The consumer receives batches from each queue independently. Workers Queues invokes the `queue` handler once per batch. To emulate draining-high-first within a consumer invocation, ensure high-priority batches have shorter timeouts so they flush more frequently.

```typescript
interface ConsumerEnv {
  DB: D1Database;
}

type JobResult = { success: boolean; error?: string };

async function processJob(job: Job, env: ConsumerEnv): Promise<JobResult> {
  try {
    await env.DB.prepare(
      'INSERT INTO job_log (trace_id, type, priority, processed_at) VALUES (?, ?, ?, ?)',
    ).bind(job.traceId, job.type, job.priority, new Date().toISOString()).run();

    // Dispatch to actual handler
    switch (job.type) {
      case 'payment_webhook':
        await handlePaymentWebhook(job.payload);
        break;
      case 'report_export':
        await handleReportExport(job.payload);
        break;
      default:
        console.warn('unknown job type', job.type);
    }
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
}

export const consumer = {
  async queue(batch: MessageBatch<Job>, env: ConsumerEnv): Promise<void> {
    const failures: string[] = [];

    for (const msg of batch.messages) {
      const result = await processJob(msg.body, env);
      if (result.success) {
        msg.ack();
      } else {
        msg.retry({ delaySeconds: exponentialDelay(msg.attempts) });
        failures.push(msg.body.traceId);
      }
    }

    if (failures.length) {
      console.error(`batch had ${failures.length} failures`, { failures, queue: batch.queue });
    }
  },
};

function exponentialDelay(attempts: number): number {
  return Math.min(2 ** attempts, 60); // caps at 60 s
}

async function handlePaymentWebhook(_payload: Record<string, unknown>): Promise<void> { /* ... */ }
async function handleReportExport(_payload: Record<string, unknown>): Promise<void> { /* ... */ }
```

## Dead-Letter Queue Monitoring
Route DLQ messages to an alert queue and page on-call when messages accumulate.

```typescript
interface DlqEnv {
  PAGERDUTY_KEY: string;
}

export const dlqConsumer = {
  async queue(batch: MessageBatch<Job>, env: DlqEnv): Promise<void> {
    const summaries = batch.messages.map(m => ({
      traceId: m.body.traceId,
      type: m.body.type,
      priority: m.body.priority,
    }));

    console.error('DLQ messages received', { count: batch.messages.length, summaries });

    // Fire PagerDuty alert
    await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        routing_key: env.PAGERDUTY_KEY,
        event_action: 'trigger',
        payload: {
          summary: `${batch.messages.length} jobs exhausted retries on ${batch.queue}`,
          severity: batch.queue.includes('high') ? 'critical' : 'warning',
          source: 'cloudflare-workers',
          custom_details: summaries,
        },
      }),
    }).then(r => r.body?.cancel()).catch(e => console.error('alert failed', e));

    // Ack all DLQ messages to prevent re-delivery loop
    batch.ackAll();
  },
};
```

## Anti-patterns
- Using a single queue with a priority field in the payload — Queues are FIFO; a low-priority message ahead of a high-priority one will be processed first regardless of the field.
- Setting the same `max_batch_timeout` across all queues — high-priority queues should flush faster; use a shorter timeout (1–2 s) for the high tier.
- Retrying indefinitely on the high-priority queue — unbounded retries block new high-priority messages behind stuck ones; set a tight `max_retries` and DLQ.
- Calling `batch.retryAll()` on partial failures — it redelivers already-successful messages; ack/retry individually per message.
- Sending large payloads directly in the queue message — Queues messages max at 128 KB; store large payloads in R2 and include only the object key in the message.

## Gotchas
- Each queue consumer binding creates a separate poll loop; billing counts each delivery attempt and each batch-timeout flush independently.
- `msg.attempts` starts at 1 on the first delivery; your exponential-delay formula must handle `attempts = 1` gracefully.
- Cloudflare Queues guarantees at-least-once delivery; your `processJob` handler must be idempotent — use `traceId` as an idempotency key in D1.
- `max_batch_size` on Queues caps at 100 messages; do not set it higher.
- Workers Queues does not support scheduled delivery (delay on send) beyond the 30-day visibility window; use Durable Objects alarms for precise future scheduling.

## Verification
1. Send 10 low-priority and 10 high-priority messages simultaneously; verify the high-priority D1 log rows have earlier `processed_at` timestamps.
2. Force a job failure (throw in handler) and confirm the message appears in the DLQ after `max_retries` attempts using `wrangler queues list-messages`.
3. Check Cloudflare dashboard Queues metrics for per-queue backlog depth and delivery latency histograms.
4. Unit-test `derivePriority` with all known job types to ensure correct routing.

## Related
- `/documentation/docs/policies/patterns/dead-letter-queue-pattern.md`
- `/documentation/docs/policies/patterns/fan-out-queues-workers.md`
- `/documentation/docs/policies/patterns/idempotency-key-pattern-workers-d1.md`
- `/documentation/docs/policies/patterns/exponential-backoff-jitter-workers.md`

## Sources
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/configuration/
- https://developers.cloudflare.com/queues/reference/javascript-apis/
