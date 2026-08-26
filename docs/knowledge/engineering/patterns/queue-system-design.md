# queue-system-design

**Issue:** When to use a queue (CF Queues, DO, external broker)
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a feature that needs to send an email after a user
action. You do it inline: `await sendEmail(...)`. The email
service is slow. The user waits. The user closes the tab. The
email is partially sent. You have an inconsistent state.

## Root cause
**Synchronous execution of slow operations hurts UX.** The user
should not wait for an email to send. The user should not even
care if the email is sent at all.

**Source:** Martin Fowler — Patterns of Enterprise Application
Architecture: https://martinfowler.com/eaaCatalog/

> "Use a queue to coordinate the work of multiple workers,
> to schedule work for later processing, or to buffer work
> between processes."

## The 3 patterns

### 1. Fire-and-forget
- **What:** Enqueue the work; the user doesn't wait
- **Latency:** User sees instant response; work happens later
- **Failure mode:** If the worker dies, work is lost (unless
  the queue is durable)
- **Example:** Send a "welcome" email after signup

### 2. Async-with-callback
- **What:** Enqueue the work; notify the user when done
- **Latency:** User sees "pending" response; work happens
  later; user gets a webhook / push
- **Failure mode:** Same as fire-and-forget
- **Example:** Process a video upload; notify when ready

### 3. Saga (choreographed)
- **What:** Multiple steps coordinated via a queue
- **Latency:** User sees final state; intermediate steps are
  hidden
- **Failure mode:** Compensating actions needed for partial
  failures
- **Example:** Order processing: charge → reserve → ship

## CF Queues

Cloudflare Queues is a managed message queue:
```toml
# wrangler.toml
[[queues.producers]]
queue = "email-queue"
binding = "EMAIL_QUEUE"

[[queues.consumers]]
queue = "email-queue"
max_batch_size = 10
max_batch_timeout = 30
```

```ts
// Producer (Pages Function)
export async function onRequestPost(context: Context): Promise<Response> {
  const { request, env } = context;
  const userId = await authenticate(request, env);
  const body = await request.json() as { to: string; subject: string; body: string };

  // Enqueue (fire-and-forget)
  await env.EMAIL_QUEUE.send({
    type: 'send-email',
    userId,
    to: body.to,
    subject: body.subject,
    body: body.body,
    timestamp: Date.now(),
  });

  return new Response(JSON.stringify({ ok: true }), { status: 202 });
}

// Consumer (Worker)
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return new Response('OK');
  },
  async queue(batch: MessageBatch<EmailMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendEmail(msg.body, env);
        msg.ack();  // Mark as processed
      } catch (err) {
        msg.retry();  // Retry (up to 3 times by default)
      }
    }
  },
};
```

## DIY queue with Durable Objects

For simple cases, use a DO as a queue:
```ts
class JobQueueDO {
  private jobs: Job[] = [];

  async fetch(req: Request): Promise<Response> {
    if (req.method === 'POST') {
      const job = await req.json() as Job;
      this.jobs.push(job);
      // Optionally: trigger a worker via alarm()
      this.ctx.storage.setAlarm(Date.now() + 1000);
      return new Response('OK', { status: 202 });
    }
    if (req.method === 'GET') {
      // Worker pulls a job
      const job = this.jobs.shift();
      return new Response(JSON.stringify(job));
    }
    return new Response('Method not allowed', { status: 405 });
  }

  async alarm(): Promise<void> {
    // Process pending jobs
    while (this.jobs.length > 0) {
      const job = this.jobs.shift()!;
      try {
        await processJob(job);
      } catch (err) {
        // Log + retry
      }
    }
  }
}
```

✅ Use when: simple queueing, low volume
❌ Drawback: not horizontally scalable (single DO instance)

## When to use a queue

✅ Use a queue when:
- **The work is slow** (> 100ms typically)
- **The user doesn't need the result immediately**
- **You have bursts** (queue absorbs them)
- **You need to retry on failure**
- **You have multiple workers** (queue distributes work)

❌ Don't use a queue when:
- **The work is fast** (< 10ms)
- **The user needs the result now** (do it inline)
- **The work is rare** (a queue is overhead)
- **You have one worker** (no benefit to a queue)

## Common mistakes

### Don't make the user wait for the queue
The user clicked "Send email." They should see "Email sent"
in 50ms, not "Email will be sent in 30 seconds."

### Don't lose messages
A queue that drops messages on worker death is not a queue.
Use a durable queue (CF Queues, Kafka, SQS, etc.).

### Don't forget retries
A worker can fail. The message should be retried. After N
retries, send to a dead-letter queue.

### Don't forget idempotency
A message can be processed twice. The worker should be
idempotent (e.g. check if the job is already done).

## Verification
- **Test:** `test/queue.test.ts > message enqueued, processed,
  marked complete` — passes
- **Test:** `test/queue.test.ts > worker failure triggers
  retry, success after retry` — passes
- **Live:** Queue depth is monitored; alerts on backlog
- **Audit:** Quarterly review of retry + DLQ behavior

## Gotchas
- **A queue is a SPOF for the producer.** If the queue is
  down, the user can't enqueue. Have a fallback (e.g. write
  to a "pending" table in D1, process later).
- **A queue is NOT ordered by default.** CF Queues and most
  others don't guarantee FIFO. If you need ordering, use a
  single-partition queue.
- **A queue has a TTL.** If a message sits too long, it
  expires. Set the TTL based on your use case.
- **A dead-letter queue is essential.** Without it, failures
  pile up silently. After N retries, send to DLQ for manual
  review.
- **The producer and consumer are usually in different
  workers.** Don't put both in the same Pages Function; the
  consumer needs to be a long-running Worker.

## Related
- `idempotency-keys.md` (for the consumer)
- `retry-with-jitter.md` (for the worker's retry behavior)
- `circuit-breaker-pattern.md` (for vendor calls in the worker)
- CF Queues: https://developers.cloudflare.com/queues/
