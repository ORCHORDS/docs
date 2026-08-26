# Viral Content Cascade: Rate Limiting Notification Fanout with Durable Objects

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Viral Cascade Problem

When a piece of content goes viral, the notification system faces an extreme fanout event: a single post liked by one celebrity can trigger hundreds of thousands of push and email notifications within seconds. Without rate limiting at the content level, this overwhelms downstream delivery services, saturates queue workers, and causes cascading failures that affect unrelated content and users.

The core challenge is that standard per-user or per-IP rate limits do not protect against viral fanout — the storm originates from many legitimate users interacting with the same object simultaneously. What is needed is per-content rate limiting that controls the velocity of outbound notification dispatch for any single piece of content, independent of individual actor velocity.

Cloudflare Durable Objects are ideal here because each content item can own exactly one Durable Object instance — a strongly consistent, single-threaded actor that serialises all fanout requests for that object, applies token-bucket logic, and emits backpressure signals to Queue producers.

## Context

- Runtime: Cloudflare Workers + Durable Objects + Queues
- Storage: D1 for content metadata, KV for rate-limit config per content tier
- Queue: Cloudflare Queues for async notification delivery
- Deployment: single `wrangler.toml`, Workers-native only (no Node runtime)

## Per-Content Durable Object Rate Limiter

Each content item gets a Durable Object identified by its content ID. The DO holds an in-memory token bucket that refills at a configured rate. Callers send fanout requests; the DO either accepts them (consuming tokens) or returns a `429` with a `retryAfter` hint.

```ts
// durable-objects/ContentFanoutLimiter.ts
export interface FanoutRequest {
  contentId: string;
  recipientBatch: string[];
  priority: 'high' | 'normal' | 'low';
}

export class ContentFanoutLimiter implements DurableObject {
  private tokens: number;
  private lastRefill: number;
  private readonly capacity: number;
  private readonly refillRate: number; // tokens per second

  constructor(private state: DurableObjectState, private env: Env) {
    this.capacity = 500;
    this.refillRate = 100; // allow 100 notifications/sec per content item
    this.tokens = this.capacity;
    this.lastRefill = Date.now();
  }

  private refill(): void {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillRate);
    this.lastRefill = now;
  }

  async fetch(request: Request): Promise<Response> {
    const body = await request.json<FanoutRequest>();
    this.refill();

    const needed = body.recipientBatch.length;
    if (this.tokens < needed) {
      const waitSecs = Math.ceil((needed - this.tokens) / this.refillRate);
      return Response.json({ accepted: false, retryAfter: waitSecs }, { status: 429 });
    }

    this.tokens -= needed;
    // Enqueue the accepted batch
    await this.env.NOTIFICATION_QUEUE.send({
      contentId: body.contentId,
      recipients: body.recipientBatch,
      priority: body.priority,
      enqueuedAt: Date.now(),
    });

    return Response.json({ accepted: true, remaining: Math.floor(this.tokens) });
  }
}
```

## Backpressure from Cloudflare Queues

Queue consumers signal overload back to producers by returning non-`ack` responses, letting Cloudflare retry with exponential backoff. The fanout Worker checks DO rejection and splits large recipient lists into smaller chunks, re-enqueuing the overflow with a delay hint.

```ts
// workers/fanout-dispatcher.ts
export default {
  async queue(batch: MessageBatch<FanoutMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { contentId, recipients } = msg.body;
      const id = env.CONTENT_FANOUT.idFromName(contentId);
      const stub = env.CONTENT_FANOUT.get(id);

      // Split into chunks of 50 to stay within DO token budget
      const chunks = chunkArray(recipients, 50);
      for (const chunk of chunks) {
        const res = await stub.fetch('https://do/fanout', {
          method: 'POST',
          body: JSON.stringify({ contentId, recipientBatch: chunk, priority: msg.body.priority }),
        });

        if (res.status === 429) {
          const { retryAfter } = await res.json<{ retryAfter: number }>();
          // Re-enqueue overflow with delay; Queues supports delaySeconds
          await env.NOTIFICATION_QUEUE.send(
            { contentId, recipients: chunk, priority: 'low' },
            { delaySeconds: retryAfter }
          );
        }
      }
      msg.ack();
    }
  },
};

function chunkArray<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
```

## Graceful Degradation for Trending Content

When content exceeds a "trending" threshold (e.g., token exhaustion persists for >30 seconds), the system switches to digest mode: instead of individual notifications, recipients receive a single batched digest after a cooldown window. KV stores the trending flag; downstream delivery Workers check it.

```ts
// workers/trend-detector.ts
export async function markTrendingIfNeeded(
  contentId: string,
  env: Env,
  exhaustedFor: number // seconds
): Promise<void> {
  if (exhaustedFor >= 30) {
    await env.CONTENT_KV.put(
      `trending:${contentId}`,
      JSON.stringify({ since: Date.now(), digestMode: true }),
      { expirationTtl: 3600 }
    );
  }
}

export async function isTrending(contentId: string, env: Env): Promise<boolean> {
  const val = await env.CONTENT_KV.get(`trending:${contentId}`);
  return val !== null;
}

// Delivery worker checks trending flag before sending individual notification
export async function deliverOrBatch(
  contentId: string,
  recipient: string,
  env: Env
): Promise<void> {
  if (await isTrending(contentId, env)) {
    await env.DIGEST_QUEUE.send({ contentId, recipient, queuedAt: Date.now() });
    return;
  }
  await sendPushNotification(recipient, contentId, env);
}
```

## Anti-patterns

- Using a single global rate limiter for all content — hot content starves cold content
- Synchronous fanout inside the request path — always push to a queue first
- Hardcoding token bucket capacity — store limits in KV, keyed by content tier
- Acking queue messages before the DO confirms acceptance — leads to silent drops
- Using Durable Object alarms as the primary dispatch mechanism under viral load — alarm queue backs up

## Gotchas

- Durable Object instances have a 128 MB memory cap; do not accumulate unbounded recipient lists in-memory
- `delaySeconds` on Cloudflare Queues has a max of 43200 (12 h); clamp retry delays
- `idFromName` is deterministic but case-sensitive — normalise `contentId` before hashing
- DO `fetch()` counts against the Worker CPU subrequest budget; monitor `cf-cache-status` on DO responses
- Queue batch size defaults to 5; increase `max_batch_size` in `wrangler.toml` for throughput

## Verification

```ts
// test: verify DO rejects batches that exceed remaining tokens
import { ContentFanoutLimiter } from './durable-objects/ContentFanoutLimiter';

async function testTokenExhaustion() {
  // Simulate a DO with 10 tokens remaining
  const do_ = new MockDO(10);
  const res = await do_.fetch(buildRequest({ recipientBatch: Array(50).fill('u1') }));
  console.assert(res.status === 429, 'Should reject oversized batch');
  const body = await res.json<{ retryAfter: number }>();
  console.assert(body.retryAfter > 0, 'retryAfter must be positive');
}
```

## Related

- `documentation/docs/policies/issues/platform-abuse-rate-velocity-d1-workers.md`
- `documentation/docs/policies/issues/real-time-toxic-content-scoring-workers-ai.md`
- `documentation/docs/policies/issues/kv-metadata-size-limit.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/batching-retries/
