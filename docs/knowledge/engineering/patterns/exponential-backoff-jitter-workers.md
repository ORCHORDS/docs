# Exponential Backoff with Jitter in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Worker calls a downstream API that rate-limits or occasionally returns 429/503.
Naively retrying immediately floods the already-struggling upstream, causing a
thundering-herd effect where all retries arrive at the same moment and extend the
outage. Similarly, Cloudflare Queue consumers that fail and re-enqueue at fixed
intervals create synchronized retry storms that overwhelm downstream capacity.

**Exponential backoff with jitter** solves both problems: each successive retry waits
exponentially longer than the last, and random jitter desynchronises concurrent
retriers so they spread load over time rather than all hitting at once.

## Context

Two distinct runtime contexts in Workers require different backoff implementations:

1. **In-request retries**: the Worker retries within a single HTTP request's lifetime
   (< 30 s CPU wall time). Uses `scheduler.wait()` to sleep between attempts without
   blocking the event loop.

2. **Queue consumer retries**: the Worker processes a message, throws, and the Queue
   re-delivers with a delay. Jitter is applied by returning a custom `retryDelay`
   in the `MessageBatch` handler rather than sleeping.

Three jitter strategies exist; **full jitter** is recommended for most cases because
it provides the best throughput distribution under load:

| Strategy | Formula | Use when |
|----------|---------|----------|
| None | `cap * 2^attempt` | Single caller, no thundering herd |
| Equal jitter | `half + rand(half)` | Guaranteed minimum delay needed |
| Full jitter | `rand(cap * 2^attempt)` | **Default — best load spreading** |
| Decorrelated | `rand(base, prev * 3)` | Very high concurrency (> 1000 callers) |

## In-request Retry with Full Jitter

```typescript
// backoff.ts — reusable utility
export interface BackoffOptions {
  /** Base delay in ms (first retry window ceiling). Default: 100 ms. */
  baseMs?: number;
  /** Maximum delay cap in ms. Default: 30_000 ms (30 s). */
  capMs?:  number;
  /** Maximum number of retry attempts. Default: 5. */
  maxAttempts?: number;
  /** HTTP status codes that should trigger a retry. */
  retryOn?: number[];
}

export interface BackoffResult<T> {
  value:    T;
  attempts: number;
}

/**
 * Full-jitter exponential backoff:
 *   delay = random(0, min(cap, base * 2^attempt))
 */
function jitteredDelay(attempt: number, baseMs: number, capMs: number): number {
  const expo = baseMs * Math.pow(2, attempt);
  const ceil = Math.min(capMs, expo);
  return Math.floor(Math.random() * ceil);
}

export async function withRetry<T>(
  fn:   () => Promise<T>,
  opts: BackoffOptions = {}
): Promise<BackoffResult<T>> {
  const {
    baseMs       = 100,
    capMs        = 30_000,
    maxAttempts  = 5,
    retryOn      = [429, 500, 502, 503, 504],
  } = opts;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxAttempts; attempt++) {
    try {
      const value = await fn();

      // If the function returns a Response, check status code
      if (value instanceof Response && retryOn.includes(value.status)) {
        if (attempt === maxAttempts) return { value, attempts: attempt + 1 };

        const delay = jitteredDelay(attempt, baseMs, capMs);
        const retryAfter = value.headers.get("Retry-After");
        const waitMs = retryAfter
          ? parseInt(retryAfter, 10) * 1000  // honour upstream hint
          : delay;

        await scheduler.wait(Math.min(waitMs, capMs));
        continue;
      }

      return { value, attempts: attempt + 1 };
    } catch (err) {
      lastError = err;
      if (attempt === maxAttempts) break;

      const delay = jitteredDelay(attempt, baseMs, capMs);
      await scheduler.wait(delay);
    }
  }

  throw lastError ?? new Error("Max retry attempts reached");
}
```

## Using withRetry for Upstream Fetch Calls

```typescript
// origin-fetch.ts
import { withRetry } from "./backoff";

export async function fetchWithRetry(
  url:     string,
  init:    RequestInit,
  env:     Env
): Promise<Response> {
  const { value: response, attempts } = await withRetry(
    () => fetch(url, init),
    {
      baseMs:      200,
      capMs:       10_000,
      maxAttempts: 4,
      retryOn:     [429, 500, 502, 503, 504],
    }
  );

  if (attempts > 1) {
    // Emit a metric so you can track retry rate in Logpush / Analytics Engine
    console.log(JSON.stringify({
      type:     "retry_summary",
      url,
      attempts,
      status:   response.status,
    }));
  }

  return response;
}

// In your Worker handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const res = await fetchWithRetry(
      "https://upstream.api/data",
      { headers: { Authorization: `Bearer ${env.API_KEY}` } },
      env
    );

    if (!res.ok) {
      return new Response("Upstream unavailable after retries", { status: 502 });
    }

    return new Response(await res.text(), { headers: res.headers });
  },
};
```

## Queue Consumer with Jitter-based Retry Delay

```typescript
// queue-consumer.ts
// Cloudflare Queues allow returning retryDelay (seconds) per message.

interface ProcessingResult {
  success:  boolean;
  attempt:  number;
}

function queueRetryDelay(attempt: number): number {
  // Full-jitter in seconds; Queue max delay is 43_200 s (12 h)
  const baseS = 5;
  const capS  = 3_600; // 1 hour max
  const expo  = baseS * Math.pow(2, attempt);
  const ceil  = Math.min(capS, expo);
  return Math.floor(Math.random() * ceil) + 1; // at least 1 s
}

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const attempt = (msg.attempts ?? 1) - 1; // 0-indexed

      try {
        await processMessage(env, msg.body);
        msg.ack();
      } catch (err) {
        const isTransient =
          err instanceof Error && err.message.includes("upstream");

        if (isTransient && attempt < 5) {
          const delaySec = queueRetryDelay(attempt);
          console.log(JSON.stringify({
            type:    "queue_retry",
            attempt,
            delaySec,
            msgId:   msg.id,
            error:   String(err),
          }));
          msg.retry({ delaySeconds: delaySec });
        } else {
          // Permanent failure or max retries reached — send to DLQ
          console.error(JSON.stringify({
            type:  "queue_dlq",
            msgId: msg.id,
            error: String(err),
          }));
          await env.DLQ.send({ originalMsg: msg.body, error: String(err) });
          msg.ack(); // ack so it's not re-delivered from the main queue
        }
      }
    }
  },
};

async function processMessage(env: Env, body: unknown): Promise<void> {
  // Business logic — throws on transient failure
}
```

## Anti-patterns

- **Retry immediately on every error**: zero-delay retries increase load on an already
  failing upstream and can exhaust the Worker's CPU time limit. Always wait.
- **No jitter (synchronised backoff)**: if 100 Workers all retry at `base * 2^n`
  without jitter, they arrive at the upstream in a synchronized wave. Full jitter
  eliminates this: each Worker waits a uniformly-random fraction of the window.
- **Retrying non-transient errors**: 400 Bad Request, 401 Unauthorized, and 404 Not
  Found will never succeed on retry. Only retry 429, 5xx, and network errors.
- **Ignoring `Retry-After` headers**: when the upstream explicitly says "wait 30 s",
  using your own backoff formula instead may violate the API's terms of service and
  worsen the situation. Respect the header when present.
- **Unbounded retry in a Queue consumer**: without a max-attempts check, messages
  that trigger permanent errors loop forever, consuming Queue throughput and money.
  Always have a DLQ exit path.

## Gotchas

- **`scheduler.wait()` is Workers-only**: this is a Cloudflare-specific extension of
  the Web Platform. It is _not_ `setTimeout` wrapped in a Promise — it yields the
  isolate to other requests and does not count against CPU time while waiting.
- **Queue `msg.attempts`**: the field counts total _deliveries_, starting at 1, not
  retries. Compute `attempt = msg.attempts - 1` for 0-indexed backoff calculations.
- **Wall-clock vs CPU time**: an in-request retry that calls `scheduler.wait(5_000)`
  five times uses 25 s of wall time but minimal CPU time. Stay within the 30 s
  wall-clock request limit on the Free plan (no wall limit on Paid).
- **Decorrelated jitter can produce very long delays**: `rand(base, prev * 3)` can
  grow unboundedly without a cap. Always clamp with `min(cap, ...)`.
- **`Math.random()` is not cryptographically random**: for backoff purposes this is
  fine (you want fast, uniform distribution, not security). Do not use `crypto.subtle`
  here — it is slower and offers no benefit for timing randomisation.

## Verification

```bash
# Run 20 concurrent requests to a staging endpoint that returns 503 on first call
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{time_total}\n" \
    "https://your-worker.dev/retry-demo" &
done
wait

# With full-jitter retries: response times should be spread across ~0-10 s range
# Without jitter: all requests complete at multiples of the base delay (synchronized)

# For Queue testing: send 50 messages that will fail once
npx wrangler d1 execute ... # or use wrangler queues send
# Inspect retry delays in Logpush output — should be uniformly distributed 0..cap
# and not all identical
```

## Related

- `retry-with-exponential-backoff.md` — base exponential backoff without jitter
- `retry-with-jitter.md` — jitter strategies in isolation
- `dead-letter-queue-pattern.md` — what to do when retries are exhausted
- `circuit-breaker-workers-d1-fetch.md` — stop retrying a failing upstream entirely
- `request-hedging-latency.md` — reduce tail latency without retrying failures

## Sources

- AWS Architecture Blog — "Exponential Backoff and Jitter" (Marc Brooker, 2015)
  https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Cloudflare Queues — `retryDelay` / `msg.retry()`
  https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Cloudflare Workers — `scheduler.wait()`
  https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- Google SRE Workbook — Chapter 22: Handling Overload
