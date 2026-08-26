# Cloudflare Queues Consumer Throughput Mismatch and Backpressure Failure

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A sustained viral event on the example project platform caused the moderation event queue (`example project-moderation-queue`) to accumulate a backlog exceeding 180,000 messages over 3 hours. The consumer Worker processing moderation events was configured with a batch size and concurrency ceiling that could not drain messages faster than they were enqueued. The dead-letter queue (DLQ) began filling silently after messages exceeded the maximum delivery retry limit. Approximately 11,400 moderation events were permanently dropped before the incident was contained. Posts that should have been reviewed by the automated moderation pipeline went live unreviewed for the duration.

## Context

example project's content moderation pipeline works as follows: every new post triggers a `ModerationProducer` that enqueues a `ModerationEvent` message to `example project-moderation-queue`. A `ModerationConsumer` Worker pulls batches, calls an external AI moderation API (rate-limited to 300 req/min per account), writes verdicts to D1, and updates the post's `verdict` field. Under normal load, approximately 40–80 posts per minute are created, well within the moderation pipeline's throughput.

The viral event began at 11:40 UTC when a post went widely reshared externally, driving 8,000 new anonymous posts in 90 minutes — roughly 89 posts/minute. The `ModerationConsumer` had a `max_batch_size` of 10 and a `max_concurrency` of 5 (Cloudflare's default), yielding a theoretical throughput of 50 messages/minute against the external API's 300 req/min ceiling — a severe throughput mismatch that was never stress-tested.

The DLQ (`example project-moderation-dlq`) was configured but had no alerts attached. Messages were landing in the DLQ silently. The only monitoring in place was a Grafana dashboard that no one checked during the incident.

## Timeline

- **11:40 UTC** — Viral post triggers spike. New post creation rate climbs from 60/min to 89/min.
- **11:42 UTC** — Queue depth begins growing. `ModerationConsumer` processing 50 events/min vs 89/min inbound.
- **12:00 UTC** — Queue depth: ~1,080 messages. No alerts. No human awareness.
- **12:30 UTC** — Queue depth: ~3,240 messages. Messages that have been retried 3 times begin landing in DLQ.
- **12:47 UTC** — Engineer notices DLQ depth in passing while checking an unrelated Cloudflare dashboard. Raises informally in Slack: "is our moderation queue supposed to have 4,200 messages in the DLQ?"
- **12:50 UTC** — Incident declared. On-call begins investigation.
- **12:55 UTC** — Root cause identified: `max_batch_size` and `max_concurrency` were set at project creation and never revisited.
- **13:02 UTC** — Emergency config change: `max_batch_size` raised to 100, `max_concurrency` raised to 20 in `wrangler.toml`. Deployed.
- **13:05 UTC** — Consumer throughput increases to ~400 events/min. Queue begins draining. DLQ stops growing.
- **13:08 UTC** — Moderation API returns `429 Too Many Requests`. New per-batch rate limiter added with exponential backoff.
- **13:15 UTC** — Throughput stabilized at 280 events/min (just under API rate limit). Queue draining at 191 events/min net.
- **14:33 UTC** — Live queue drained. Total drain time from intervention: 88 minutes.
- **14:35 UTC** — DLQ replay initiated for recoverable messages. 11,400 messages confirmed unrecoverable (exceeded DLQ retention window).
- **15:00 UTC** — Post-mortem scheduled.

## Root Cause

Three compounding failures:

1. **`max_batch_size` and `max_concurrency` set at project creation and never load-tested.** The default values were appropriate for the initial launch traffic profile (40–80 posts/min) but created a fixed throughput ceiling of ~50 events/min. No capacity headroom was modeled against the external API rate limit or against traffic spike scenarios.

2. **No back-pressure signal from consumer to producer.** When the consumer fell behind, the producer had no mechanism to know. Posts continued to be accepted, enqueued, and confirmed to users as "under review" — even when the review pipeline was hours behind. There was no circuit breaker or queue-depth-based admission control.

3. **DLQ had no alerting.** Cloudflare Queues routes messages to the DLQ silently when all retries are exhausted. The team had configured the DLQ at setup but never attached a monitor or alert to it. The DLQ was effectively a black hole that masked the scope of data loss until it was noticed by chance.

## Fix / Resolution: Concurrency Tuning, Rate Limiting, and DLQ Alerting

The immediate config fix and the structural prevention changes:

```typescript
// workers/moderation-consumer.ts
// After the incident: tuned batch size, built-in rate limiting, and DLQ awareness

import type { Queue, MessageBatch, Message } from "@cloudflare/workers-types";

export interface Env {
  MODERATION_DLQ: Queue;
  MODERATION_DB: D1Database;
  MODERATION_API_KEY: string;
  MODERATION_RATE_LIMITER: RateLimiter; // Cloudflare Rate Limiting API binding
}

interface ModerationEvent {
  postId: string;
  body: string;
  authorHash: string;
  enqueuedAt: number;
}

export default {
  async queue(
    batch: MessageBatch<ModerationEvent>,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    // Process messages in sub-batches to avoid overwhelming the moderation API
    // max_batch_size=100 in wrangler.toml; process 10 at a time with delay
    const SUB_BATCH_SIZE = 10;
    const INTER_BATCH_DELAY_MS = 2200; // ~270 req/min, safely under 300/min limit

    const messages = batch.messages;
    const failed: Message<ModerationEvent>[] = [];

    for (let i = 0; i < messages.length; i += SUB_BATCH_SIZE) {
      const subBatch = messages.slice(i, i + SUB_BATCH_SIZE);

      await Promise.allSettled(
        subBatch.map(async (msg) => {
          try {
            const verdict = await callModerationApi(msg.body, env);
            await writeVerdict(msg.body.postId, verdict, env);
            msg.ack();
          } catch (err) {
            if (isRateLimitError(err)) {
              // Retry — do not ack, Queues will re-deliver
              msg.retry({ delaySeconds: 30 });
            } else {
              // Non-retryable: ack to remove from queue, but log to DLQ manually
              console.error("Non-retryable moderation failure", {
                postId: msg.body.postId,
                error: String(err),
              });
              failed.push(msg);
              msg.ack();
            }
          }
        }),
      );

      // Rate-limit delay between sub-batches (skip after last sub-batch)
      if (i + SUB_BATCH_SIZE < messages.length) {
        await new Promise((r) => setTimeout(r, INTER_BATCH_DELAY_MS));
      }
    }

    // Re-enqueue non-retryable failures to DLQ for human review
    if (failed.length > 0) {
      await env.MODERATION_DLQ.sendBatch(
        failed.map((msg) => ({
          body: {
            ...msg.body,
            failedAt: Date.now(),
            reason: "non-retryable-moderation-error",
          },
        })),
      );
    }
  },
};

async function callModerationApi(
  event: ModerationEvent,
  env: Env,
): Promise<"approved" | "rejected" | "review"> {
  const res = await fetch("https://moderation-api.example.com/v1/check", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.MODERATION_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text: event.body }),
    signal: AbortSignal.timeout(8000),
  });

  if (res.status === 429) {
    throw new Error("RATE_LIMIT_EXCEEDED");
  }
  if (!res.ok) {
    throw new Error(`Moderation API error: ${res.status}`);
  }

  const data = await res.json<{ verdict: "approved" | "rejected" | "review" }>();
  return data.verdict;
}

async function writeVerdict(
  postId: string,
  verdict: string,
  env: Env,
): Promise<void> {
  await env.MODERATION_DB.prepare(
    "UPDATE posts SET verdict = ?, verdict_at = ? WHERE id = ?",
  )
    .bind(verdict, Date.now(), postId)
    .run();
}

function isRateLimitError(err: unknown): boolean {
  return String(err).includes("RATE_LIMIT_EXCEEDED");
}
```

The `wrangler.toml` consumer config after the fix:

```toml
[[queues.consumers]]
queue = "example project-moderation-queue"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "example project-moderation-dlq"
max_concurrency = 20
retry_delay = "30s"
```

A Durable Object (`ModerationCoordinator`) was added to track queue depth and signal back-pressure to the producer:

```typescript
// durable-objects/moderation-coordinator.ts
// Tracks queue depth estimate; ModerationProducer checks before enqueuing

export class ModerationCoordinator implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/depth") {
      const depth = (await this.state.storage.get<number>("queueDepth")) ?? 0;
      // Signal back-pressure if depth exceeds threshold
      const backPressure = depth > 50_000;
      return Response.json({ depth, backPressure });
    }

    if (url.pathname === "/increment" && request.method === "POST") {
      const current = (await this.state.storage.get<number>("queueDepth")) ?? 0;
      await this.state.storage.put("queueDepth", current + 1);
      return new Response("ok");
    }

    if (url.pathname === "/decrement" && request.method === "POST") {
      const current = (await this.state.storage.get<number>("queueDepth")) ?? 0;
      await this.state.storage.put("queueDepth", Math.max(0, current - 1));
      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  }
}
```

## Prevention Checklist

- [ ] Load-test the consumer pipeline at 5x expected peak traffic before any launch; document the calculated throughput ceiling and the external API rate limit that constrains it
- [ ] Set a Cloudflare alert on DLQ depth exceeding 100 messages; treat any DLQ growth as an active incident
- [ ] Instrument queue depth via Workers Analytics Engine on every consumer batch invocation; alert on depth > 10,000
- [ ] Add a back-pressure check to the producer: if `ModerationCoordinator` signals back-pressure, return a `202 Accepted` with a `Retry-After` header rather than silently enqueuing
- [ ] Document `max_batch_size` and `max_concurrency` as required fields with a comment in `wrangler.toml` explaining the throughput calculation: `(max_concurrency × max_batch_size) / avg_processing_time_seconds`
- [ ] Schedule a quarterly review of consumer config values against current traffic P99 — config set at launch does not self-update as traffic grows

## Monitoring Gaps Identified

- DLQ depth was not alarmed; the DLQ was treated as a passive archive rather than an active signal of data loss in progress
- No metric tracked the ratio of enqueue rate to dequeue rate; a persistent enqueue > dequeue condition was undetectable without manually inspecting the Cloudflare dashboard

## Anti-patterns

- Setting `max_batch_size` and `max_concurrency` once at project creation and treating them as permanent — consumer throughput capacity must be modeled and periodically re-evaluated against actual and projected traffic
- Relying on the DLQ as implicit error handling without attaching alerts — the DLQ absorbs failures silently by design; silence is not success

## Gotchas

- Cloudflare Queues `max_concurrency` caps the number of concurrent consumer invocations across the whole queue, not per-region; raising it beyond the external API rate limit will trigger cascading `429`s that cause retry storms, which makes the backlog worse, not better
- Messages in the DLQ are retained for the same duration as the source queue (default 4 days); after that window passes, they are silently dropped with no notification — once a message expires from the DLQ it is permanently unrecoverable

## Verification

```bash
# Check live queue and DLQ depths via Cloudflare API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name:.name, consumers_total:.consumers_total, messages_total:.messages_total}'

# Replay DLQ messages back to the main queue (manual recovery)
wrangler queues consumer replay example project-moderation-dlq example project-moderation-queue

# Validate consumer throughput under load (local simulation)
bun run scripts/load-test-moderation-queue.ts --rate 200 --duration 60s

# Check moderation coordinator back-pressure state
curl https://example project.workers.dev/internal/moderation/depth \
  -H "Authorization: Bearer $INTERNAL_TOKEN" | jq .
```

## Related

- `lessons/queue-backlog-death-spirals.md`
- `lessons/queue-consumers-must-be-idempotent.md`
- `lessons/retry-storm-queue-poison-message.md`
- `lessons/durable-object-alarm-silent-failure-payment-reminders.md`
- `monitoring/dlq-depth-alert-runbook.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/queues/reference/consumer-concurrency/
- https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- https://developers.cloudflare.com/durable-objects/
