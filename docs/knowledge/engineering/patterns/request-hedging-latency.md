# Request Hedging Pattern for Latency Tail Reduction

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

P99 API latency is 3–10× the P50 because a small percentage of requests hit slow
upstream origins: an overloaded DB replica, a cold-started container, a network
path with transient congestion. The slow tail injures user-perceived performance even
though median latency is fine. Increasing retries helps failed requests but not slow
ones that are still in flight.

**Request hedging** (also called "backup requests" or "speculative retry") solves this
by sending a duplicate request to a second upstream after a delay `Δ`, then using
whichever response arrives first and cancelling the other. The delay is tuned to the
P95 baseline latency so most requests complete before the hedge fires, keeping
upstream load increase small (typically < 5%).

## Context

Workers are ideal for hedging because:

- `Promise.race` with `AbortController` lets you cancel the losing request.
- Workers sit at the edge, close to both users and Cloudflare's private network to
  origins, making the hedge's round-trip cheap.
- Hedging is most valuable for read operations (GET, search, ML inference). Never
  hedge non-idempotent writes.

The hedge delay `Δ` should equal roughly the P95 latency of the upstream. A good
initial value is 1.5× the rolling P50. Collect real latency distributions in
production (via `cf.responseTime` or manual timestamps) before tuning `Δ`.

## Core Hedging Primitive

```typescript
// hedge.ts
export interface HedgeOptions {
  /** How long to wait before firing the backup request (ms). */
  delayMs: number;
  /** Optional second URL; defaults to the same URL as the primary. */
  hedgeUrl?: string | URL;
  /** Extra signal to cancel both requests from the outside. */
  signal?: AbortSignal;
}

/**
 * Fetch `url` and, after `delayMs`, concurrently fetch it again.
 * Returns the first response that arrives, cancelling the other.
 */
export async function hedgedFetch(
  url: string | URL,
  init: RequestInit,
  opts: HedgeOptions
): Promise<Response> {
  const outerController = new AbortController();

  // Propagate any external cancellation
  opts.signal?.addEventListener("abort", () =>
    outerController.abort(opts.signal!.reason)
  );

  async function attempt(label: "primary" | "hedge"): Promise<Response> {
    const ac  = new AbortController();
    const sig = ac.signal;

    // Let the outer controller cancel individual attempts
    outerController.signal.addEventListener("abort", () => ac.abort());

    const target = label === "hedge" && opts.hedgeUrl ? opts.hedgeUrl : url;

    try {
      const res = await fetch(target, { ...init, signal: sig });
      // Cancel the sibling once we have a winner
      outerController.abort("winner");
      return res;
    } catch (err) {
      if ((err as DOMException).name === "AbortError") {
        throw err; // propagate cancellation
      }
      throw err;   // propagate real errors
    }
  }

  const primary = attempt("primary");

  // Delay before firing the hedge
  const hedge = (async (): Promise<Response> => {
    await new Promise<void>(resolve => {
      const timer = setTimeout(resolve, opts.delayMs);
      outerController.signal.addEventListener("abort", () => clearTimeout(timer));
    });
    // If primary already won, the outer controller aborted us — throw immediately
    if (outerController.signal.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    return attempt("hedge");
  })();

  try {
    return await Promise.race([primary, hedge]);
  } catch (err) {
    // If race throws because both were aborted (winner chosen), the resolved
    // promise already unwound — this path is for genuine errors.
    throw err;
  }
}
```

## Applying Hedging to Origin Requests

```typescript
// origin-client.ts
import { hedgedFetch } from "./hedge";

const ORIGIN_PRIMARY  = "https://api-primary.internal";
const ORIGIN_SECONDARY = "https://api-secondary.internal"; // replica or second AZ
const HEDGE_DELAY_MS   = 150; // tune to ~P95 of observed origin latency

export async function fetchProduct(
  productId: string,
  env: Env,
  ctx: ExecutionContext
): Promise<ProductData> {
  const url   = `${ORIGIN_PRIMARY}/products/${productId}`;
  const start = Date.now();

  let hedgeUsed = false;
  const res = await hedgedFetch(
    url,
    {
      headers: {
        Authorization: `Bearer ${env.ORIGIN_TOKEN}`,
        "X-Request-Id": crypto.randomUUID(),
      },
    },
    {
      delayMs:  HEDGE_DELAY_MS,
      hedgeUrl: `${ORIGIN_SECONDARY}/products/${productId}`,
    }
  );

  const latency = Date.now() - start;

  // Log hedge outcome for tuning
  ctx.waitUntil(
    (async () => {
      const usedHedge = latency > HEDGE_DELAY_MS;
      await logLatency(env, { productId, latency, usedHedge });
    })()
  );

  if (!res.ok) {
    throw new Error(`Origin returned ${res.status} for product ${productId}`);
  }

  return res.json<ProductData>();
}
```

## Adaptive Hedge Delay from Observed Latency

```typescript
// adaptive-hedge.ts — uses KV to persist rolling P95 estimate
const KV_KEY = "hedge:p95:origin";

export async function getHedgeDelay(kv: KVNamespace): Promise<number> {
  const stored = await kv.get<number>(KV_KEY, "json");
  // Default 200 ms until we have real data
  return stored ?? 200;
}

export async function updateHedgeDelay(
  kv:       KVNamespace,
  latencyMs: number
): Promise<void> {
  const current = (await kv.get<number>(KV_KEY, "json")) ?? 200;

  // Exponential moving average: weight new observation at 10%
  const alpha   = 0.10;
  const updated = Math.round(current * (1 - alpha) + latencyMs * alpha * 1.5);

  // Clamp: don't hedge more aggressively than 50 ms or more conservatively than 1 s
  const clamped = Math.min(1000, Math.max(50, updated));
  await kv.put(KV_KEY, JSON.stringify(clamped), { expirationTtl: 86400 });
}

// In your Worker handler:
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const delay = await getHedgeDelay(env.HEDGE_KV);
    const start = Date.now();

    const res = await hedgedFetch(
      "https://slow-origin.internal/data",
      { headers: { "X-Api-Key": env.API_KEY } },
      { delayMs: delay }
    );

    const elapsed = Date.now() - start;
    ctx.waitUntil(updateHedgeDelay(env.HEDGE_KV, elapsed));

    return res;
  },
};
```

## Anti-patterns

- **Hedging non-idempotent requests**: never hedge POST/PUT/DELETE. A duplicated
  write creates duplicate records or charges. Hedge only safe, idempotent operations.
- **Setting `delayMs` to zero**: this doubles upstream load on every request.
  The hedge is meant to fire only for slow outliers; `delayMs` must be > P50.
- **Ignoring the losing response body**: the cancelled request's response body is
  dropped by the AbortController. Do not attempt to `res.json()` the losing branch
  after the race resolves — it will throw or return garbage.
- **Hedging to the same replica that is already slow**: if latency is caused by that
  specific instance being overloaded, a hedge to the same address just adds load.
  Route the hedge to a different replica or zone.
- **Not logging hedge activation rate**: without metrics you cannot tune `delayMs`.
  Track the percentage of requests where the hedge fired and won.

## Gotchas

- **Workers subrequest limit**: Workers on the Paid plan can open up to 1,000
  concurrent subrequests, but hedging doubles subrequest count for the tail. Monitor
  usage to stay within limits.
- **`Promise.race` does not cancel the loser**: in plain JS, the losing promise
  continues executing in the background. You _must_ use `AbortController` to signal
  the losing fetch to stop; otherwise both requests complete and you pay twice.
- **TCP connection reuse**: if both the primary and hedge hit the same Cloudflare
  PoP cache or connection pool, the hedge may share the same slow TCP connection.
  Ensure the hedge URL resolves differently (different hostname, region, or replica).
- **Response body streaming**: once `Promise.race` resolves, only the winning
  response's body can be consumed. The losing branch must be cleanly aborted before
  its body is read, or you'll get "body used" errors.
- **Cloudflare cache interaction**: requests that are served from the Cloudflare
  cache return in microseconds — hedging adds no value and wastes subrequest budget.
  Check `cf.cacheStatus` and skip hedging for cached responses.

## Verification

```bash
# Simulate slow origin: add 500 ms artificial delay at origin
# then configure HEDGE_DELAY_MS=150 and call the endpoint 100 times

for i in $(seq 1 100); do
  curl -o /dev/null -s -w "%{time_total}\n" \
    "https://your-worker.dev/product/123"
done | awk '{sum+=$1; if($1>max)max=$1} END {print "avg="sum/NR"s max="max"s"}'

# Without hedging: avg ~ 0.5 s, P99 ~ 0.5 s (all slow)
# With hedging:    avg ~ 0.15 s, P99 ~ 0.3 s (tail significantly reduced)

# Verify hedge activation rate in logs (should be ~5-10% for well-tuned Δ)
# Look for usedHedge: true in your structured log output
```

## Related

- `scatter-gather-parallel-workers.md` — fan-out to multiple backends, pick best
- `circuit-breaker-workers-d1-fetch.md` — stop sending to a consistently slow origin
- `retry-with-exponential-backoff.md` — handle outright failures (different from slowness)
- `bulkhead-pattern-workers-subrequests.md` — isolate upstream pools

## Sources

- Google SRE Book — "The Tail at Scale" (Jeff Dean & Luiz André Barroso)
  https://research.google/pubs/the-tail-at-scale/
- Backup Requests pattern — Brewer, E., "Spanner, TrueTime, and the CAP theorem"
- Cloudflare Workers fetch API and AbortController
  https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Hedged Requests at Netflix — Netflix TechBlog latency percentile reduction
