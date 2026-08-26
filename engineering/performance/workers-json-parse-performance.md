# Workers JSON Parse Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
JSON serialization and deserialization in a hot Workers path adds measurable CPU time, especially for large payloads or high-request-volume endpoints. Naive `JSON.parse` / `JSON.stringify` on every request creates unnecessary allocations and contention against the 10 ms CPU budget.

## Context
Cloudflare Workers run in V8 isolates where CPU time — not wall-clock time — is billed and capped. `JSON.parse` is implemented natively in V8 and is generally fast, but large payloads, repeated schema-less parsing, and unnecessary re-serialization of the same object tree are common performance sinks. Workers have no shared memory between isolates, so caching parsed results across requests requires KV or Durable Objects; within a single request, module-scope memoization is the primary tool.

## Module-scope Object Caching
Parse once at cold-start and reuse across all requests in the same isolate lifetime.

```typescript
// src/config.ts
// Executed once per isolate warm-up; subsequent requests reuse the parsed object.
const RAW_CONFIG = `{"featureFlags":{"newCheckout":true},"limits":{"maxItems":50}}`;
export const CONFIG: AppConfig = JSON.parse(RAW_CONFIG) as AppConfig;

interface AppConfig {
  featureFlags: Record<string, boolean>;
  limits: Record<string, number>;
}

// src/worker.ts
import { CONFIG } from "./config";

export default {
  async fetch(request: Request): Promise<Response> {
    // Zero parse cost — CONFIG is already a live JS object.
    if (CONFIG.featureFlags.newCheckout) {
      return handleNewCheckout(request);
    }
    return handleLegacyCheckout(request);
  },
};
```

This pattern applies to any static JSON embedded at build time (feature flags, route manifests, rate-limit tables).

## Lazy Parsing with a Module-scope Cache Map
For JSON fetched from KV or R2, parse lazily and cache the result in a `Map` keyed by cache-busting ETag or version token.

```typescript
// src/schema-cache.ts
const parsedCache = new Map<string, unknown>();

export async function getCachedJson<T>(
  env: Env,
  kvKey: string
): Promise<T> {
  const { value, metadata } = await env.CONFIG_KV.getWithMetadata<{ etag: string }>(
    kvKey,
    { type: "text" }
  );
  if (!value) throw new Error(`KV key not found: ${kvKey}`);

  const etag = metadata?.etag ?? kvKey;
  if (parsedCache.has(etag)) {
    return parsedCache.get(etag) as T;
  }

  const parsed = JSON.parse(value) as T;
  parsedCache.set(etag, parsed);
  // Evict stale entries so the Map does not grow unbounded across warm requests.
  if (parsedCache.size > 50) {
    const firstKey = parsedCache.keys().next().value;
    if (firstKey !== undefined) parsedCache.delete(firstKey);
  }
  return parsed;
}
```

Because the `Map` lives in module scope it persists across requests in the same isolate, but V8 may spin up new isolates under load — always treat the cache as a best-effort warm-path optimisation.

## Streaming Serialization for Large Response Bodies
Avoid buffering a large object into a string before writing the response. Build the JSON incrementally with a `TransformStream` and the native `TextEncoderStream`.

```typescript
// src/streaming-json.ts
export function streamJsonArray(items: Iterable<unknown>): Response {
  const { readable, writable } = new TransformStream<string, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  (async () => {
    await writer.write(encoder.encode("["));
    let first = true;
    for (const item of items) {
      const chunk = (first ? "" : ",") + JSON.stringify(item);
      first = false;
      await writer.write(encoder.encode(chunk));
    }
    await writer.write(encoder.encode("]"));
    await writer.close();
  })();

  return new Response(readable, {
    headers: {
      "Content-Type": "application/json",
      "Transfer-Encoding": "chunked",
    },
  });
}
```

This keeps peak memory flat regardless of dataset size and lets the browser start parsing before the final `]` arrives.

## Anti-patterns
- Calling `JSON.parse(JSON.stringify(obj))` to deep-clone objects — use `structuredClone()` instead, which is faster in V8.
- Parsing the same KV value on every request without module-scope caching.
- Stringifying response bodies to inspect them for logging, then re-stringifying — clone the object reference or use `Response.clone()` instead.
- Using `JSON.stringify` with a replacer function for large payloads — replacers add function-call overhead per key; pre-shape the object before serializing.
- Assuming `JSON.parse` is safe for untrusted input without size guards — enforce a byte limit before parsing.

## Gotchas
- Module-scope caches are per-isolate, not per-Worker. Under high concurrency Cloudflare spawns multiple isolates; the cache may be cold in each one independently.
- `structuredClone()` does not handle `undefined` values in object properties the same way `JSON.parse(JSON.stringify(...))` does — test before replacing.
- V8's JSON.parse has a practical limit around 512 MB strings; Workers' 128 MB memory ceiling will bite first.
- `JSON.stringify` of objects with circular references throws; wrap in try/catch in catch-all middleware.
- `BigInt` values are not JSON-serializable by default — convert to `string` or `number` before stringifying.

## Verification
```bash
# Measure CPU time for a JSON-heavy endpoint with Wrangler local mode
wrangler dev --local

# Tail real CPU time from production
wrangler tail --format=json | jq '.outcome, .cpuTime'

# Benchmark parse cost in isolation (run in Node, same V8 engine)
node -e "
const payload = JSON.stringify(Array.from({length: 10000}, (_, i) => ({ id: i, name: 'item-' + i })));
console.time('parse');
for (let i = 0; i < 1000; i++) JSON.parse(payload);
console.timeEnd('parse');
"
```

## Related
- [`workers-module-scope-memoization.md`](workers-module-scope-memoization.md)
- [`workers-cpu-time-optimization.md`](workers-cpu-time-optimization.md)
- [`streaming-json-parsing.md`](streaming-json-parsing.md)
- [`kv-metadata-only-reads-optimization.md`](kv-metadata-only-reads-optimization.md)
- [`workers-readable-stream-transform.md`](workers-readable-stream-transform.md)

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/#json
- https://v8.dev/blog/cost-of-javascript-2019
- https://developers.cloudflare.com/workers/observability/logs/workers-tail-worker/
- https://developer.mozilla.org/en-US/docs/Web/API/structuredClone
- https://developers.cloudflare.com/workers/platform/limits/#cpu-time
