# Scatter-Gather Pattern with Workers Service Bindings

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A single user request requires data from multiple independent downstream services, and the total latency must be bounded to the slowest single service rather than the sum of all services. Aggregating product prices, availability, and shipping estimates in one API call is a canonical example.

## Context
Cloudflare Workers support direct RPC calls to sibling Workers via Service Bindings, giving sub-millisecond invocation overhead within the same datacenter. Combining `Promise.allSettled` with per-shard timeout guards lets a gateway Worker fan out to N leaf Workers, collect partial results when some shards time out, and merge a response before the client's patience runs out. Unlike HTTP fetch, Service Binding RPC avoids the overhead of HTTP framing and DNS lookup entirely.

## Scatter Phase — Fan-Out to Leaf Workers

Each leaf Worker exposes a typed RPC interface. The gateway imports the interface as a binding.

```typescript
// leaf-worker/src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { productId } = await req.json<{ productId: string }>();
    const price = await env.DB.prepare(
      'SELECT price FROM prices WHERE id = ?'
    ).bind(productId).first<{ price: number }>();
    return Response.json({ source: 'pricing', price: price?.price ?? null });
  },
};
```

```typescript
// gateway/wrangler.toml (binding declaration)
// [[services]]
// binding = "PRICING"
// service = "pricing-worker"
// [[services]]
// binding = "INVENTORY"
// service = "inventory-worker"
// [[services]]
// binding = "SHIPPING"
// service = "shipping-worker"
```

## Gather Phase — Fan-In with Deadline

The gateway fans out all requests simultaneously and waits for the first batch of results with a hard ceiling.

```typescript
// gateway/src/index.ts
interface Env {
  PRICING: Fetcher;
  INVENTORY: Fetcher;
  SHIPPING: Fetcher;
}

const SCATTER_TIMEOUT_MS = 800;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ]);
}

async function callShard(
  binding: Fetcher,
  payload: unknown
): Promise<unknown | null> {
  try {
    const resp = await binding.fetch('https://internal/', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { productId } = await req.json<{ productId: string }>();
    const payload = { productId };

    const [pricing, inventory, shipping] = await Promise.all([
      withTimeout(callShard(env.PRICING, payload), SCATTER_TIMEOUT_MS),
      withTimeout(callShard(env.INVENTORY, payload), SCATTER_TIMEOUT_MS),
      withTimeout(callShard(env.SHIPPING, payload), SCATTER_TIMEOUT_MS),
    ]);

    return Response.json({
      productId,
      pricing: pricing ?? { error: 'unavailable' },
      inventory: inventory ?? { error: 'unavailable' },
      shipping: shipping ?? { error: 'unavailable' },
    });
  },
};
```

## Partial Result Handling

When a shard times out the gateway degrades gracefully rather than failing the entire response. Use a `confidence` field so consumers know which fields are stale or missing.

```typescript
function mergeResults(
  results: Array<unknown | null>,
  keys: string[]
): Record<string, unknown> & { confidence: string[] } {
  const merged: Record<string, unknown> = {};
  const confidence: string[] = [];

  for (let i = 0; i < keys.length; i++) {
    if (results[i] !== null) {
      merged[keys[i]] = results[i];
      confidence.push(keys[i]);
    } else {
      merged[keys[i]] = { error: 'timeout' };
    }
  }

  return { ...merged, confidence };
}
```

## Observability — Tracing Scatter Latency

Tag each shard call with a start timestamp so the gateway can emit per-shard latencies to Workers Analytics Engine.

```typescript
async function timedShard(
  binding: Fetcher,
  payload: unknown,
  shardName: string,
  ctx: ExecutionContext
): Promise<{ result: unknown | null; latencyMs: number }> {
  const start = Date.now();
  const result = await withTimeout(callShard(binding, payload), SCATTER_TIMEOUT_MS);
  const latencyMs = Date.now() - start;

  ctx.waitUntil(
    fetch('https://analytics.internal/emit', {
      method: 'POST',
      body: JSON.stringify({ shard: shardName, latencyMs, hit: result !== null }),
    }).catch(() => {})
  );

  return { result, latencyMs };
}
```

## Anti-patterns
- Calling shards sequentially inside a loop — eliminates the latency benefit entirely
- Using a single global timeout instead of per-shard cancellation — one slow shard blocks all results
- Returning a 500 when any shard fails — partial results are more valuable than an all-or-nothing failure
- Treating Service Binding calls as free — each hop still consumes CPU time and counts toward request limits
- Silently swallowing shard errors without emitting metrics — hides degradation from operators

## Gotchas
- Workers Service Bindings do not support streaming response bodies across the RPC boundary; buffer the full JSON payload
- `setTimeout` inside a Worker uses the JavaScript timer, which is only approximate under Cloudflare's CPU-time scheduling
- A Worker can be invoked by up to 6 chained service bindings before Cloudflare terminates the chain
- Cold-start latency of leaf Workers can spike the first scatter after a period of inactivity in a region

## Verification
```bash
# Deploy all workers then send a test request
curl -X POST https://gateway.example.workers.dev/ \
  -H 'content-type: application/json' \
  -d '{"productId":"prod-123"}' | jq .

# To simulate a shard timeout, add an artificial delay to one leaf:
# Sleep 1200ms in the inventory Worker and confirm the gateway returns
# inventory: { error: "timeout" } with pricing and shipping populated.
```

## Related
- [Aggregator Pattern with Workers Subrequests](aggregator-pattern-workers-subrequests-parallel.md)
- [Worker-to-Worker RPC Service Bindings](worker-to-worker-rpc-service-bindings.md)
- [Retry Storm Prevention with Jitter/Backoff](retry-storm-prevention-workers-jitter-backoff.md)
- [Bulkhead Pattern](bulkhead-pattern.md)

## Sources
- Cloudflare Workers Service Bindings docs: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Enterprise Integration Patterns — Scatter-Gather: https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
