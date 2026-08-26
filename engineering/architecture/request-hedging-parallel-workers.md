# Request Hedging with Parallel Workers Subrequests

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Tail latency is the dominant problem in distributed systems: the 99th percentile response time is often 10–100x the median, driven by slow backends, garbage collection pauses, or transient network congestion. For user-facing APIs where P99 matters more than average cost, waiting for a single slow backend to respond is unacceptable. Retrying after a timeout helps with failures but does nothing for slow-but-successful responses—the client already waited.

Request hedging solves tail latency without increasing error rates: issue a second (or third) identical request to a different backend or instance after a short delay. Use whichever response arrives first; cancel the rest. If the first request was fast, the hedge never fires or is cancelled immediately. If the first request was slow, the hedge wins. The median cost is one request; the P99 cost converges toward the hedge delay rather than the slow-backend tail.

## Context

Cloudflare Workers make hedging natural: a Worker can issue multiple `fetch()` subrequests concurrently using `Promise.race()`. Workers run at the edge, close to backends, which minimizes the base latency and makes the hedge delay a small fraction of end-to-end latency. Workers' cost model charges per subrequest CPU time, so hedge requests that are cancelled early cost proportionally less.

The challenge is idempotency: hedging is safe only for read operations or operations with idempotency keys. Hedging a non-idempotent write (e.g., `POST /charge`) without idempotency keys causes duplicate side effects. This constraint must be enforced at the call site.

## Core Hedging Utility

The hedger fires the primary request immediately, starts a timer, and fires a hedge request after the delay. `Promise.race()` returns whichever resolves first; the other is abandoned.

```typescript
// src/hedging/hedger.ts

export interface HedgeOptions {
  /** Milliseconds to wait before firing the hedge request */
  delayMs: number;
  /** Maximum number of hedge attempts (default 1) */
  maxHedges?: number;
  /** Called before each hedge to allow per-attempt URL variation (e.g., different replicas) */
  replicaSelector?: (attemptIndex: number) => string;
}

/**
 * Execute `requestFactory` with hedging.
 * `requestFactory(url)` must produce an idempotent fetch.
 */
export async function hedgedFetch(
  primaryUrl: string,
  requestInit: RequestInit,
  options: HedgeOptions
): Promise<Response> {
  const { delayMs, maxHedges = 1, replicaSelector } = options;
  const controller = new AbortController();
  const { signal } = controller;

  // Clone init and attach abort signal
  const hedgedInit: RequestInit = { ...requestInit, signal };

  const attempts: Promise<Response>[] = [];
  const timers: ReturnType<typeof setTimeout>[] = [];

  // Primary request — fires immediately
  attempts.push(
    fetch(primaryUrl, hedgedInit).catch(err => {
      if (err instanceof Error && err.name === 'AbortError') {
        return new Promise<never>(() => {});  // Pending forever — race will settle via another branch
      }
      throw err;
    })
  );

  // Schedule hedge requests
  for (let i = 0; i < maxHedges; i++) {
    const hedgeUrl = replicaSelector ? replicaSelector(i + 1) : primaryUrl;
    const hedgeIndex = i;

    const hedgePromise = new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(async () => {
        try {
          const res = await fetch(hedgeUrl, hedgedInit);
          resolve(res);
        } catch (err) {
          if (err instanceof Error && err.name === 'AbortError') return;  // Cancelled — ignore
          reject(err);
        }
      }, delayMs * (hedgeIndex + 1));
      timers.push(timer);
    });

    attempts.push(hedgePromise);
  }

  try {
    const winner = await Promise.race(attempts);
    return winner;
  } finally {
    // Cancel remaining in-flight requests
    controller.abort();
    timers.forEach(t => clearTimeout(t));
  }
}
```

## Usage: Hedging a Read Against Multiple D1 Replicas via Hyperdrive

Hyperdrive exposes a connection string that can target different read replicas. The hedger alternates between replicas using `replicaSelector`:

```typescript
// src/handlers/product-read.ts
import { hedgedFetch } from '../hedging/hedger';
import { Env } from '../types';

const REPLICA_URLS = [
  'https://db-reader-eu.internal/query',
  'https://db-reader-us.internal/query',
];

export async function getProductHedged(
  productId: string,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const body = JSON.stringify({ sql: 'SELECT * FROM products WHERE id = ?', params: [productId] });

  const response = await hedgedFetch(
    REPLICA_URLS[0],
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.DB_API_TOKEN}`,
      },
      body,
    },
    {
      delayMs: 50,       // Fire hedge after 50 ms
      maxHedges: 1,
      replicaSelector: () => REPLICA_URLS[1],
    }
  );

  return new Response(response.body, {
    status: response.status,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Hedging with Idempotency Keys for Writes

Hedging a write is safe only with an idempotency key that the backend uses to deduplicate. The key is included in the request headers; only one of the hedged requests will create the side effect.

```typescript
// src/hedging/idempotent-hedge.ts
import { hedgedFetch } from './hedger';

export async function idempotentPost(
  url: string,
  payload: unknown,
  idempotencyKey: string,
  env: { API_TOKEN: string }
): Promise<Response> {
  return hedgedFetch(
    url,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.API_TOKEN}`,
        'Idempotency-Key': idempotencyKey,  // Backend deduplicates on this key
      },
      body: JSON.stringify(payload),
    },
    { delayMs: 100, maxHedges: 1 }
  );
}
```

The backend must store the idempotency key in D1 and return a cached response for duplicate requests within the key's validity window:

```typescript
// src/backend/idempotency-guard.ts
export async function withIdempotencyGuard<T>(
  db: D1Database,
  key: string,
  ttlSeconds: number,
  handler: () => Promise<{ status: number; body: T }>
): Promise<{ status: number; body: T; duplicate: boolean }> {
  const existing = await db
    .prepare('SELECT status, body FROM idempotency_cache WHERE key = ? AND expires_at > ?')
    .bind(key, new Date().toISOString())
    .first<{ status: number; body: string }>();

  if (existing) {
    return { status: existing.status, body: JSON.parse(existing.body) as T, duplicate: true };
  }

  const result = await handler();

  await db
    .prepare(
      `INSERT OR REPLACE INTO idempotency_cache (key, status, body, expires_at)
       VALUES (?, ?, ?, datetime('now', ? || ' seconds'))`
    )
    .bind(key, result.status, JSON.stringify(result.body), ttlSeconds)
    .run();

  return { ...result, duplicate: false };
}
```

## Adaptive Hedge Delay via P99 Measurement

Rather than a fixed hedge delay, measure P99 of recent requests and set the hedge delay to P50. This self-tunes as backend latency changes:

```typescript
// src/hedging/adaptive-delay.ts
import { Env } from '../types';

export async function getAdaptiveHedgeDelay(
  endpoint: string,
  env: Env
): Promise<number> {
  // Read P50 of last 1000 requests for this endpoint from Analytics Engine
  // (assumes latency data points are written on each request completion)
  const key = `hedge_delay:${btoa(endpoint)}`;
  const cached = await env.HEDGE_CONFIG.get(key);
  if (cached) return Number(cached);

  // Fallback to a conservative default while we gather data
  return 50;
}

export function recordRequestLatency(
  endpoint: string,
  latencyMs: number,
  env: Env
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [endpoint],
    doubles: [latencyMs],
    indexes: ['request_latency'],
  });
}
```

## Anti-patterns

- Hedging non-idempotent writes without idempotency keys—this creates duplicate transactions, charges, or messages.
- Setting `delayMs` to zero—this doubles backend load on every request and eliminates the cost benefit of hedging.
- Hedging in a tight loop without cancellation—if `Promise.race()` is not used, all hedge requests run to completion regardless of which wins, amplifying backend load proportionally to `maxHedges`.
- Using hedging for calls that mutate shared state in the Worker (e.g., a counter in a Durable Object) without considering that both hedged and primary may succeed before cancellation.
- Applying hedging to already-fast endpoints (P99 < 10 ms)—the hedge delay overhead dominates; hedging is for tail latency mitigation, not general performance improvement.

## Gotchas

- `AbortController.abort()` in a Worker cancels the subrequest's connection, but the downstream server may have already started processing. Idempotency keys are still required.
- Workers' subrequest limit (50 subrequests per request on the free plan, unlimited on paid) constrains how many hedges are practical in a single Worker invocation.
- Cancelled `fetch()` calls throw `AbortError`. The hedger above suppresses these to prevent unhandled rejections from racing with the winner. Ensure your error handling distinguishes AbortError from real failures.
- `Promise.race()` resolves with the first settled promise, including rejections. Wrap each attempt in `.catch()` if you want to fall back from a failed primary to a successful hedge rather than propagating the error immediately.
- The hedge delay timer starts when the Worker begins executing the hedging code, not when the primary request leaves the edge. On PoPs with high subrequest queue pressure, the effective delay may be longer.

## Verification

1. Set up two mock backends: one that responds in 200 ms and one that responds in 20 ms. Configure `replicaSelector` to alternate between them and `delayMs = 50`. Confirm the winning response arrives in ~70 ms (20 ms backend + 50 ms delay overhead), not 200 ms.
2. Set both backends to respond in 10 ms. Confirm the hedge timer never fires (response arrives before `delayMs` elapses) and only one backend receives the request.
3. Simulate the primary timing out at 2 s. Confirm the hedge fires at `delayMs = 50` ms and the total response time is ≈ 50 ms + hedge backend latency.
4. Test idempotent write hedging: confirm both requests reach the backend but only one creates a side effect (idempotency cache returns the second).
5. Measure P95 latency before and after applying hedging to a slow endpoint; confirm the P95 converges toward P50 + `delayMs`.

## Related

- `retry-pattern.md` — retry strategies for failures (complementary to hedging, which targets slowness)
- `scatter-gather-workers-service-bindings.md` — fan-out to multiple services and aggregate results
- `circuit-breaker-kv-state-machine.md` — preventing overload on consistently slow backends
- `grpc-retry-hedging-idempotency-budget.md` — gRPC-level hedging policy specification

## Sources

- Google SRE Book — "Tail at Scale" (hedged requests): https://sre.google/sre-book/addressing-cascading-failures/
- Jeff Dean & Luiz André Barroso, "The Tail at Scale" (2013): https://dl.acm.org/doi/10.1145/2408776.2408794
- Cloudflare Workers fetch() and subrequest limits: https://developers.cloudflare.com/workers/platform/limits/#subrequests
