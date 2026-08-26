# Workers Subrequest Fan-out Hitting the 1000-Subrequest Limit

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers-based notification service that sent webhook pings to 1,200 registered partner integrations per release event started silently dropping notifications for the last ~200 partners after the 1000th. No errors appeared in `wrangler tail` for the dropped requests — the Worker completed with HTTP 200, but downstream partners reported missing events. The issue was invisible without explicitly counting outbound requests per Worker invocation.

---

## Context

Cloudflare Workers enforce a hard limit of 1000 subrequests per isolate request (on the paid tier; 50 on the free tier). A "subrequest" is any outbound `fetch()` call made from within a Worker, including calls to external APIs, calls to other Workers via Service Bindings, and calls to Durable Object stubs. When the limit is reached, further `fetch()` calls throw a `TypeError: Network connection lost` — but only in some runtime versions; in others the Promise resolves with a synthetic error response, making silent failures possible. The notifications team discovered the issue only when partners began filing tickets about missing webhook events.

---

## What Went Wrong

```typescript
// notifications/fanout.ts — broken: one fetch() per partner, no limit guard
interface Partner {
  id: string;
  webhookUrl: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { eventType, payload } = await request.json();

    // Fetch all registered partners from D1
    const { results: partners } = await env.DB.prepare(
      'SELECT id, webhook_url FROM partners WHERE active = 1'
    ).all() as { results: Partner[] };

    // BAD: fan-out with one fetch() per partner
    // At 1200 partners, the 1001st fetch() silently fails or throws
    const results = await Promise.all(
      partners.map(partner =>
        fetch(partner.webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ eventType, payload }),
          // No timeout — a slow partner ties up the subrequest slot
          signal: AbortSignal.timeout(5000),
        }).catch(err => ({ ok: false, partner: partner.id, error: String(err) }))
      )
    );

    // This count is wrong: some results may be synthetic error objects
    // from the subrequest limit, not real network failures
    const failed = results.filter(r => !('ok' in r) || !r.ok);
    return Response.json({ sent: results.length, failed: failed.length });
  },
};
```

## Root Cause

The Cloudflare Workers runtime counts every outbound `fetch()` call against the isolate's 1000-subrequest budget. This budget is per-request, not per-Worker or per-isolate-lifetime. When the budget is exhausted, the runtime either throws `TypeError: Network connection lost` or returns a synthetic failed Response — the behavior depends on the runtime version and is not guaranteed to surface as a thrown error in all cases. Because the team used `.catch()` on each individual `fetch()`, the subrequest-limit failures were swallowed as ordinary network errors, and the final response reported success. Additionally, all 1200 `fetch()` calls were in-flight simultaneously via `Promise.all`, offering no opportunity to detect and stop when the limit was approached.

## The Fix

```typescript
// notifications/fanout.ts — fixed: batched fan-out with Queues for large sets
import type { Queue } from '@cloudflare/workers-types';

const SUBREQUEST_BATCH_SIZE = 50; // Safe margin under the 1000 limit
const SUBREQUEST_WARN_THRESHOLD = 800; // Emit warning before hitting the cap

interface WebhookJob {
  partnerId: string;
  webhookUrl: string;
  eventType: string;
  payload: unknown;
  attempt: number;
}

async function sendWebhook(
  job: WebhookJob,
  subrequestCount: { n: number }
): Promise<{ partnerId: string; ok: boolean; status?: number; error?: string }> {
  subrequestCount.n++;
  if (subrequestCount.n > SUBREQUEST_WARN_THRESHOLD) {
    console.warn(`Subrequest count approaching limit: ${subrequestCount.n}`);
  }

  try {
    const res = await fetch(job.webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Orchords-Event': job.eventType,
      },
      body: JSON.stringify(job.payload),
      signal: AbortSignal.timeout(5000),
    });
    return { partnerId: job.partnerId, ok: res.ok, status: res.status };
  } catch (err) {
    return { partnerId: job.partnerId, ok: false, error: String(err) };
  }
}

export default {
  async fetch(
    request: Request,
    env: Env & { WEBHOOK_QUEUE: Queue<WebhookJob> }
  ): Promise<Response> {
    const { eventType, payload } = await request.json();

    const { results: partners } = await env.DB.prepare(
      'SELECT id, webhook_url FROM partners WHERE active = 1'
    ).all() as { results: { id: string; webhook_url: string }[] };

    const subrequestCount = { n: 0 };
    const directResults: Awaited<ReturnType<typeof sendWebhook>>[] = [];
    const queuedCount = { n: 0 };

    // Handle partners in batches; offload overflow to Queues
    for (let i = 0; i < partners.length; i += SUBREQUEST_BATCH_SIZE) {
      const batch = partners.slice(i, i + SUBREQUEST_BATCH_SIZE);

      // If we're approaching the subrequest limit, enqueue the rest
      if (subrequestCount.n + batch.length > SUBREQUEST_WARN_THRESHOLD) {
        for (const partner of batch) {
          await env.WEBHOOK_QUEUE.send({
            partnerId: partner.id,
            webhookUrl: partner.webhook_url,
            eventType,
            payload,
            attempt: 1,
          });
          queuedCount.n++;
        }
        continue;
      }

      // Send this batch concurrently (safe: 50 at a time)
      const batchResults = await Promise.all(
        batch.map(partner =>
          sendWebhook(
            {
              partnerId: partner.id,
              webhookUrl: partner.webhook_url,
              eventType,
              payload,
              attempt: 1,
            },
            subrequestCount
          )
        )
      );
      directResults.push(...batchResults);
    }

    const failed = directResults.filter(r => !r.ok);

    return Response.json({
      sentDirect: directResults.length,
      sentViaQueue: queuedCount.n,
      failed: failed.length,
      failedPartners: failed.map(r => r.partnerId),
    });
  },

  // Queue consumer: process offloaded webhook jobs with retry
  async queue(
    batch: MessageBatch<WebhookJob>,
    env: Env & { WEBHOOK_QUEUE: Queue<WebhookJob> }
  ): Promise<void> {
    for (const message of batch.messages) {
      const job = message.body;
      const subrequestCount = { n: 0 };
      const result = await sendWebhook(job, subrequestCount);

      if (!result.ok && job.attempt < 3) {
        // Re-enqueue with backoff (Queues supports delayed delivery)
        await env.WEBHOOK_QUEUE.send(
          { ...job, attempt: job.attempt + 1 },
          { delaySeconds: job.attempt * 30 }
        );
        message.ack();
      } else {
        message.ack();
      }
    }
  },
};
```

## Prevention

```typescript
// Test: assert subrequest count never exceeds safe threshold
import { describe, it, expect, vi } from 'vitest';

describe('webhook fan-out', () => {
  it('does not exceed 800 direct subrequests for any batch size', async () => {
    let fetchCallCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      fetchCallCount++;
      return new Response('ok', { status: 200 });
    });

    // Simulate 1200 partners
    const partners = Array.from({ length: 1200 }, (_, i) => ({
      id: `partner-${i}`,
      webhook_url: `https://partner-${i}.example.com/webhook`,
    }));

    // Run the fan-out handler
    // (inject mock DB and Queue into env)
    // ... test setup ...

    expect(fetchCallCount).toBeLessThanOrEqual(800);
  });
});
```

```bash
# Detection via wrangler tail: parse subrequest exhaustion errors
wrangler tail --format json 2>&1 | jq 'select(.exceptions[]?.message | test("Network connection lost|subrequest"; "i"))'

# Add to wrangler.toml for queue binding:
# [[queues.producers]]
# binding = "WEBHOOK_QUEUE"
# queue = "webhook-fanout"
#
# [[queues.consumers]]
# queue = "webhook-fanout"
# max_batch_size = 10
# max_retries = 3
```

---

## Anti-patterns

- **`Promise.all()` over an unbounded array of `fetch()` calls** — No concurrency limit, no subrequest budget tracking; any list longer than 1000 will silently drop requests.
- **Catching subrequest-limit errors as ordinary network failures** — `.catch()` on individual fetches swallows the limit error, making it look like a flaky network rather than a platform limit.
- **Fan-out architecture entirely within a single Worker request** — For large fan-outs, Workers Queues or Durable Objects are the correct pattern; a single Worker request is not designed for 1000+ outbound calls.
- **No subrequest counter in monitoring** — Without explicitly counting subrequests, the limit is invisible until it causes silent drops in production.
- **Relying on the Worker to complete all sends synchronously** — For non-latency-critical fan-outs (notifications, webhooks), fire-and-forget via Queues is more reliable and observable than synchronous fan-out.

---

## Gotchas

- The 1000 subrequest limit applies per isolate request, not per Worker instance or per isolate lifetime. A new request always starts with a fresh budget of 1000.
- Service Bindings (`env.OTHER_WORKER.fetch()`) count toward the 1000-subrequest limit just like external `fetch()` calls.
- Durable Object `stub.fetch()` calls also count as subrequests.
- On the Workers free tier, the subrequest limit is 50 (not 1000) — tests in free-tier environments may pass under the limit that production (paid) traffic would also hit at 1000.
- `AbortSignal.timeout()` is the correct pattern for per-request timeouts; do NOT use `setTimeout` + `AbortController` in Workers (unreliable timer behavior during I/O suspension).
- Cloudflare Queues `send()` also consumes 1 subrequest per message sent from a Worker — factor this in when mixing direct sends and queue sends.

---

## Verification

```bash
# Count subrequests in a tail session by parsing structured logs
wrangler tail --format json 2>&1 | \
  jq -r 'select(.outcome == "ok") | "subrequests: \(.subrequest_count // "unknown")"'

# Test with exactly 1001 partners to trigger the limit (staging only)
curl -X POST https://notifications-worker.example.workers.dev/trigger \
  -H 'Content-Type: application/json' \
  -d '{"eventType":"release","payload":{"version":"1.0.0"},"testPartnerCount":1001}'

# Check Queue for enqueued overflow jobs
wrangler queues info webhook-fanout

# Verify Queue consumer processed all overflow jobs
wrangler tail --format json 2>&1 | \
  jq 'select(.scriptName == "webhook-consumer") | .logs[]'
```

---

## Related

- `lessons-workers-wasm-memory-limit.md`
- `circuit-breaker-prevents-cascade-failure.md`
- `retry-storm-queue-poison-message.md`

---

## Sources

- Cloudflare Workers Limits (subrequests) — https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- AbortSignal.timeout() — https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
