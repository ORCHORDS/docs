# Workers Subrequest Fan-out and Parallelism Optimization

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker must aggregate data from multiple upstream APIs — product catalogue,
inventory service, pricing engine, and personalisation backend — before it can return a
response. Executed sequentially the total latency equals the sum of every round-trip.
The wall-clock time balloons to 400–900 ms even when each individual upstream responds in
100–200 ms. The fix is concurrent fan-out with `Promise.all` or structured concurrency
patterns, but naive implementations hit the subrequest budget, create memory pressure, or
silently suppress errors.

## Context

Workers can issue up to **50 simultaneous subrequests** per invocation (1 000 in total).
Each call to `fetch()` inside a Worker returns a Promise that begins network resolution
immediately — there is no thread-pool queue to back up behind. The CPU timer only ticks
when JavaScript is running, so waiting on I/O is free from a CPU-time perspective.
Fan-out therefore costs nothing extra in billing while cutting wall-clock time from
sequential-sum to max-of-parallels. The challenge is error handling, partial failure
strategy, and staying inside the subrequest concurrency limit.

## Parallel Fan-out with Promise.all

The simplest pattern: fire all requests at once, await them together.

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const [catalogRes, inventoryRes, priceRes, personRes] = await Promise.all([
      fetch("https://catalog.internal/products", { headers: authHeader(env) }),
      fetch("https://inventory.internal/stock", { headers: authHeader(env) }),
      fetch("https://pricing.internal/rates", { headers: authHeader(env) }),
      fetch("https://personalization.internal/recs", { headers: authHeader(env) }),
    ]);

    if (!catalogRes.ok) {
      return new Response("Upstream error", { status: 502 });
    }

    const [catalog, inventory, prices, recs] = await Promise.all([
      catalogRes.json(),
      inventoryRes.json(),
      priceRes.json(),
      personRes.json(),
    ]);

    return Response.json({ catalog, inventory, prices, recs });
  },
};
```

Both the network round-trips AND the response-body parsing are parallelised.
Separating the two `Promise.all` calls is intentional: the first awaits headers
(status + content-type), then you can abort early on error before spending CPU parsing
bodies.

## Partial-Failure Strategy with Promise.allSettled

When some upstreams are optional — personalisation can degrade gracefully but catalogue
cannot — use `Promise.allSettled` and promote errors to nullable fields.

```typescript
async function fanOut(env: Env) {
  const results = await Promise.allSettled([
    fetch("https://catalog.internal/products").then((r) => r.json()),
    fetch("https://inventory.internal/stock").then((r) => r.json()),
    fetch("https://pricing.internal/rates").then((r) => r.json()),
    fetch("https://personalization.internal/recs").then((r) => r.json()),
  ]);

  const [catalog, inventory, prices, recs] = results.map((r, i) => {
    if (r.status === "fulfilled") return r.value;
    console.error(`upstream[${i}] failed:`, r.reason);
    return null; // caller decides if null is acceptable
  });

  if (catalog === null) {
    throw new Error("catalog is mandatory; cannot serve response");
  }

  return { catalog, inventory, prices, recs };
}
```

Log the rejection reason so you can track upstream error rates in Workers Logs or
Analytics Engine without surfacing the failure to the end user.

## Bounded Concurrency for Large Fan-outs

When the number of targets is dynamic — e.g. fetching details for N product IDs from
a per-item endpoint — unlimited `Promise.all` can exhaust the 50-concurrent-subrequest
window and cause the excess fetches to queue inside V8, producing stalls.
A concurrency pool keeps the in-flight count bounded.

```typescript
async function pooledFetch<T>(
  urls: string[],
  maxConcurrent: number,
  transform: (r: Response) => Promise<T>
): Promise<T[]> {
  const results: T[] = new Array(urls.length);
  const queue = urls.map((url, index) => ({ url, index }));
  let cursor = 0;

  async function worker(): Promise<void> {
    while (cursor < queue.length) {
      const { url, index } = queue[cursor++];
      const res = await fetch(url);
      results[index] = await transform(res);
    }
  }

  // Spawn exactly `maxConcurrent` workers; each drains the shared queue
  await Promise.all(Array.from({ length: maxConcurrent }, () => worker()));
  return results;
}

// Usage: fetch up to 40 product detail pages concurrently
export default {
  async fetch(req: Request): Promise<Response> {
    const productIds = ["p1", "p2", /* … up to hundreds */];
    const urls = productIds.map((id) => `https://products.internal/item/${id}`);
    const items = await pooledFetch(urls, 40, (r) => r.json());
    return Response.json(items);
  },
};
```

Setting `maxConcurrent` to 40–45 leaves headroom for the Workers runtime's own internal
requests and stays safely below the 50-concurrent cap.

## Structured Fan-out with AbortController Timeouts

Upstream services without SLOs can block the entire response indefinitely. Attach an
`AbortSignal` with a per-request deadline to every subrequest.

```typescript
function fetchWithTimeout(url: string, ms: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return fetch(url, { signal: controller.signal }).finally(() =>
    clearTimeout(timer)
  );
}

export default {
  async fetch(req: Request): Promise<Response> {
    const deadline = 200; // ms per upstream

    const [a, b, c] = await Promise.allSettled([
      fetchWithTimeout("https://svc-a.internal/data", deadline).then((r) => r.json()),
      fetchWithTimeout("https://svc-b.internal/data", deadline).then((r) => r.json()),
      fetchWithTimeout("https://svc-c.internal/data", deadline).then((r) => r.json()),
    ]);

    return Response.json({
      a: a.status === "fulfilled" ? a.value : null,
      b: b.status === "fulfilled" ? b.value : null,
      c: c.status === "fulfilled" ? c.value : null,
    });
  },
};
```

The overall p99 latency becomes `max(upstreamP99) + overhead` instead of
`sum(upstreamP99) + overhead`.

## Anti-patterns

**Sequential await in a loop** — the most common mistake. Each iteration waits for
the previous to complete before starting the next.

```typescript
// BAD: 5 × 150 ms = 750 ms wall-clock
for (const id of ids) {
  const item = await fetch(`/item/${id}`).then((r) => r.json());
  results.push(item);
}
```

**Unbounded Promise.all on dynamic arrays** — submitting 200 fetches simultaneously
causes the runtime to queue the overflow; the first 50 proceed, the rest wait in V8
memory for a slot, consuming heap while adding invisible latency.

**Calling `.json()` inside the first Promise.all** — parsing the body before checking
status means you spend CPU deserialising a 502 HTML error page.

**Ignoring AbortSignal propagation** — if the client disconnects, subrequests continue
consuming CPU and count against billing. Propagate `req.signal` where appropriate.

## Gotchas

- The 50-concurrent limit is **per Worker invocation**, not per account. Each incoming
  request gets a fresh budget.
- Subrequests to the same zone are counted the same as cross-zone. Workers-to-Workers
  calls via `SERVICE_BINDING` do **not** count against the subrequest budget and have
  lower latency than external `fetch()`.
- `waitUntil()` subrequests execute after the response is sent but still count against
  the total 1 000 subrequest budget and the CPU wall-clock limit.
- `Promise.race` is rarely the right tool for fan-out; if the winning response succeeds
  but slower responses fail silently, you lose observability.

## Verification

```bash
# Measure wall-clock time of sequential vs parallel using wrangler tail
wrangler tail --format pretty | grep "duration"

# Synthetic test: compare sequential and parallel variants under load
wrk -t4 -c50 -d30s https://worker.example.com/parallel
wrk -t4 -c50 -d30s https://worker.example.com/sequential
```

Add `server-timing` headers to expose individual upstream latencies to RUM tooling:

```typescript
const t0 = Date.now();
const data = await fanOut(env);
const elapsed = Date.now() - t0;
headers.set("server-timing", `fanout;dur=${elapsed}`);
```

## Related

- `workers-cpu-time-optimization.md`
- `workers-queues-background-offload.md`
- `durable-objects-low-latency-stateful.md`
- `latency-budget-allocation.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
