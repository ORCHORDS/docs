# Retry Storm Prevention with Jitter and Backoff in Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

An upstream service becomes temporarily unavailable. All Workers retrying failed requests simultaneously hit the recovered service with a thundering-herd burst, causing it to fail again immediately. The retry loop amplifies the original incident into a prolonged outage affecting far more requests than the initial failure window would have.

## Context

Retry storms occur when many independent clients share the same deterministic retry schedule—typically a fixed delay or a naive exponential backoff without randomisation. When all clients back off for exactly 2 s, 4 s, and 8 s, they synchronise into bursts that arrive simultaneously. Full jitter breaks the synchronisation by randomising the wait within the backoff window, spreading load across the interval. Decorrelated jitter goes further by making each attempt's delay independent of the previous one, producing a more uniform distribution. In a Cloudflare Workers context, both Queues retries and manual subrequest retries must apply jitter; Queues supports delay configuration but not jitter natively, so the consumer must re-enqueue with a randomised delay when needed.

## Full Jitter Retry for Subrequests

Replace fixed-delay exponential backoff with `sleep(random(0, min(cap, base * 2^attempt)))`. The cap prevents unbounded delays on very deep retry stacks.

```typescript
// src/lib/retry.ts
export interface RetryOptions {
  maxAttempts: number;
  baseDelayMs: number;
  capMs: number;
  retryableStatuses?: number[];
}

const DEFAULT_OPTIONS: RetryOptions = {
  maxAttempts: 5,
  baseDelayMs: 200,
  capMs: 10_000,
  retryableStatuses: [429, 502, 503, 504],
};

function fullJitterDelay(attempt: number, base: number, cap: number): number {
  const ceiling = Math.min(cap, base * Math.pow(2, attempt));
  return Math.random() * ceiling;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchWithRetry(
  url: string,
  init: RequestInit,
  options: Partial<RetryOptions> = {}
): Promise<Response> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  let lastError: unknown;

  for (let attempt = 0; attempt < opts.maxAttempts; attempt++) {
    if (attempt > 0) {
      const delay = fullJitterDelay(attempt - 1, opts.baseDelayMs, opts.capMs);
      await sleep(delay);
    }

    try {
      const res = await fetch(url, init);
      if (!opts.retryableStatuses!.includes(res.status)) {
        return res; // success or non-retryable error
      }
      lastError = new Error(`HTTP ${res.status}`);
    } catch (err) {
      // Network-level failure (DNS, TCP reset, abort)
      lastError = err;
    }
  }

  throw lastError;
}
```

## Decorrelated Jitter for Queue Re-enqueue

When a Queue consumer needs to defer re-processing, it cannot sleep—it must re-enqueue the message with a delay. Use decorrelated jitter: `delay = min(cap, random(base, prev * 3))` to avoid correlated bursts.

```typescript
// src/queue-consumer.ts
interface RetryEnvelope {
  payload: unknown;
  attempt: number;
  prevDelayMs: number;
}

interface Env {
  WORK_QUEUE: Queue<RetryEnvelope>;
}

const BASE_MS = 500;
const CAP_MS = 30_000;

function decorrelatedDelay(prevDelayMs: number): number {
  const next = Math.random() * (prevDelayMs * 3 - BASE_MS) + BASE_MS;
  return Math.min(CAP_MS, next);
}

export default {
  async queue(batch: MessageBatch<RetryEnvelope>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const envelope = msg.body;

      try {
        await processWork(envelope.payload);
        msg.ack();
      } catch (err) {
        const MAX_ATTEMPTS = 8;
        if (envelope.attempt >= MAX_ATTEMPTS) {
          // Exhaust retries — send to DLQ or alert
          console.error("Max retries exceeded", { envelope, err });
          msg.ack(); // ack to prevent infinite Queues retry loop
          await sendToDlq(envelope, env);
          continue;
        }

        const delayMs = decorrelatedDelay(envelope.prevDelayMs || BASE_MS);
        const delaySecs = Math.ceil(delayMs / 1000);

        await env.WORK_QUEUE.send(
          {
            payload: envelope.payload,
            attempt: envelope.attempt + 1,
            prevDelayMs: delayMs,
          },
          { delaySeconds: delaySecs }
        );

        msg.ack(); // ack original; re-enqueued copy carries retry state
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function processWork(_payload: unknown): Promise<void> {
  // business logic
}

async function sendToDlq(_envelope: RetryEnvelope, _env: Env): Promise<void> {
  // write to D1 dead letter table or send to monitoring
}
```

## Circuit Breaker Integration

Combine jitter backoff with a circuit breaker stored in KV or a Durable Object. When the breaker is open, skip the retry entirely—returning a synthetic failure—to avoid hammering a known-broken service.

```typescript
// src/lib/circuit-breaker.ts
type BreakerState = "closed" | "open" | "half-open";

interface BreakerRecord {
  state: BreakerState;
  failures: number;
  openedAt: number;
}

const FAILURE_THRESHOLD = 5;
const RECOVERY_WINDOW_MS = 15_000;

export async function guardedFetch(
  url: string,
  init: RequestInit,
  kv: KVNamespace,
  key: string
): Promise<Response> {
  const raw = await kv.get<BreakerRecord>(key, "json");
  const breaker: BreakerRecord = raw ?? { state: "closed", failures: 0, openedAt: 0 };

  if (breaker.state === "open") {
    if (Date.now() - breaker.openedAt < RECOVERY_WINDOW_MS) {
      return new Response("Service unavailable (circuit open)", { status: 503 });
    }
    breaker.state = "half-open";
  }

  try {
    const { fetchWithRetry } = await import("./retry");
    const res = await fetchWithRetry(url, init, { maxAttempts: 3 });

    if (res.ok || !([502, 503, 504].includes(res.status))) {
      // Reset on success
      await kv.put(key, JSON.stringify({ state: "closed", failures: 0, openedAt: 0 }), {
        expirationTtl: 300,
      });
    }
    return res;
  } catch (err) {
    breaker.failures += 1;
    if (breaker.failures >= FAILURE_THRESHOLD || breaker.state === "half-open") {
      breaker.state = "open";
      breaker.openedAt = Date.now();
    }
    await kv.put(key, JSON.stringify(breaker), { expirationTtl: 300 });
    throw err;
  }
}
```

## Anti-patterns

- Fixed-interval retries with no jitter—every caller backs off identically and produces synchronised bursts on recovery.
- Retrying non-idempotent requests (e.g., payment submissions) without an idempotency key—each retry may create duplicate side effects.
- Catching all errors uniformly and retrying; network timeouts and 400 Bad Request both trigger retries, wasting quota on non-transient failures.

## Gotchas

- Cloudflare Queues `delaySeconds` has a minimum of 0 and a maximum of 43 200 (12 hours); values outside this range throw at enqueue time.
- Workers CPU time does not include `setTimeout` sleep—sleeping does not consume CPU quota, but it does consume wall-clock time against the request timeout.

## Verification

```bash
# Simulate upstream failure and confirm jitter distribution
wrangler tail --format json | jq 'select(.logs[].message | contains("delay")) | .logs[].message'

# Check circuit breaker state in KV
wrangler kv key get --binding=CACHE "breaker:upstream-api"
```

## Related

- `architecture/circuit-breaker.md`
- `architecture/circuit-breaker-kv-state-machine.md`
- `architecture/dead-letter-queue-architecture.md`
- `architecture/retry-pattern.md`

## Sources

- https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- https://developers.cloudflare.com/queues/configuration/configure-queues/#delay-messages
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
