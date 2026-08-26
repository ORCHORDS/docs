# queues-dlq-patterns

**Issue:** Configuring Dead-Letter Queues (DLQ) for failed Cloudflare Queues messages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a Queue consumer repeatedly fails to process a message (after retries), the message is dropped by default. A Dead-Letter Queue (DLQ) captures these failed messages so they can be inspected, replayed, or alerted on.

## Pattern / Solution

```toml
# wrangler.toml
[[queues.producers]]
queue = "main-jobs"
binding = "MAIN_QUEUE"

[[queues.consumers]]
queue = "main-jobs"
dead_letter_queue = "main-jobs-dlq"    # DLQ name
max_retries = 3                         # retry up to 3 times before DLQ
retry_delay = 30                        # wait 30s between retries (seconds)
max_batch_size = 10
max_batch_timeout = 5

[[queues.consumers]]
queue = "main-jobs-dlq"                 # DLQ consumer
binding = "DLQ_QUEUE"
max_batch_size = 50
max_batch_timeout = 60
```

```typescript
// Main consumer
export default {
  async queue(batch: MessageBatch<JobPayload>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processJob(message.body, env);
        message.ack();
      } catch (err) {
        console.error(`Job failed: ${err}`, message.body);
        // message.retry() sends back to queue with retry delay
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};
```

```typescript
// DLQ consumer — receives messages that exhausted all retries
export const dlqWorker = {
  async queue(batch: MessageBatch<JobPayload>, env: Env): Promise<void> {
    const failed: Array<{ body: JobPayload; id: string }> = [];

    for (const message of batch.messages) {
      failed.push({ body: message.body, id: message.id });
      message.ack(); // ack to remove from DLQ
    }

    // Alert via Slack
    await fetch(env.SLACK_WEBHOOK, {
      method: 'POST',
      body: JSON.stringify({
        text: `${failed.length} jobs permanently failed`,
        blocks: failed.map(f => ({
          type: 'section',
          text: { type: 'mrkdwn', text: `*${f.id}*: \`${JSON.stringify(f.body)}\`` },
        })),
      }),
      headers: { 'Content-Type': 'application/json' },
    });

    // Store in D1 for manual replay
    await env.DB.batch(
      failed.map(f =>
        env.DB.prepare(`INSERT INTO failed_jobs (id, payload, failed_at) VALUES (?, ?, ?)`)
          .bind(f.id, JSON.stringify(f.body), Date.now())
      )
    );
  },
};
```

**Replaying DLQ messages:**
```typescript
// Re-enqueue from the failed_jobs table
async function replayFailedJobs(env: Env, jobIds: string[]): Promise<void> {
  const jobs = await env.DB.prepare(
    `SELECT payload FROM failed_jobs WHERE id IN (${jobIds.map(() => '?').join(',')})`
  ).bind(...jobIds).all<{ payload: string }>();

  await env.MAIN_QUEUE.sendBatch(
    jobs.results.map(j => ({ body: JSON.parse(j.payload) }))
  );
}
```

## Gotchas
- The DLQ **must** be a different queue from the main queue (no self-referential DLQs).
- If the DLQ consumer also fails, messages are dropped — the DLQ has no DLQ.
- `max_retries` counts **consumer failures**, not network errors. If the Worker never responds (timeout), it uses the queue's delivery timeout setting.
- `retry_delay` adds a minimum delay before redelivery — actual delay may be longer due to batching.
- DLQ consumers still count toward your Queue message billing.
- Always `ack()` in the DLQ consumer; if you don't, messages re-enter the DLQ queue indefinitely.

## Related
- `workers-workers-queues-patterns.md`
- `queues-batch-processing.md`
- `workers-tail-workers.md`
