# Workers Memory Allocation Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Worker is hitting the 128 MB memory limit, triggering isolate recycling and cold-start latency spikes. Workers processing large JSON payloads, image buffers, or accumulating data across many subrequests exhibit gradual memory growth that is not reclaimed within a single request. The Cloudflare dashboard shows elevated `isolate_memory_exceeded` errors.

## Context

The Workers runtime allocates one V8 isolate per Worker script per edge node. An isolate is reused across sequential requests (within the same isolate lifetime) but has a hard 128 MB heap cap. Unlike Node.js, Workers has no `--max-old-space-size` escape hatch. Memory pressure comes from two sources: per-request heap (live during the microtask queue drain) and module-scope state that persists across requests (caches, connection pools, accumulated telemetry). V8's generational GC runs opportunistically; a long-lived isolate that accumulates module-scope data is the most common source of memory growth.

## Auditing Module-Scope State

```typescript
// DANGEROUS: module-scope collections that grow without bound
const requestLog: Array<{ url: string; ts: number }> = [];  // never pruned
const responseCache = new Map<string, Response>();           // Response objects hold body streams

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Every request appends to the module-scope array — leaks indefinitely
    requestLog.push({ url: request.url, ts: Date.now() });

    // Caching Response objects keeps their body ReadableStream alive in the heap
    const cached = responseCache.get(request.url);
    if (cached) return cached.clone();

    const res = await fetch(request);
    responseCache.set(request.url, res.clone()); // body is now pinned
    return res;
  },
};

// SAFE ALTERNATIVE: cap the collection size and cache serialised data, not live objects
const MAX_LOG = 500;
const safeRequestLog: Array<{ url: string; ts: number }> = [];
const safeCache = new Map<string, { body: Uint8Array; headers: Record<string, string>; status: number }>();

export const safeDefault = {
  async fetch(request: Request, env: Env): Promise<Response> {
    safeRequestLog.push({ url: request.url, ts: Date.now() });
    if (safeRequestLog.length > MAX_LOG) safeRequestLog.shift(); // bounded

    const cached = safeCache.get(request.url);
    if (cached) {
      return new Response(cached.body, { status: cached.status, headers: cached.headers });
    }

    const res = await fetch(request);
    const body = new Uint8Array(await res.arrayBuffer()); // serialise — no live stream
    safeCache.set(request.url, {
      body,
      status: res.status,
      headers: Object.fromEntries(res.headers),
    });
    if (safeCache.size > 200) {
      // Evict oldest entry (Map preserves insertion order)
      const oldest = safeCache.keys().next().value;
      if (oldest) safeCache.delete(oldest);
    }

    return new Response(body, { status: res.status, headers: Object.fromEntries(res.headers) });
  },
};
```

## Per-Request Allocation Patterns

```typescript
// Pattern 1: Avoid intermediate ArrayBuffers for large payloads
// BAD: three copies of the payload exist simultaneously (origin body, arrayBuffer, JSON parse)
async function parseLargePayloadBad(request: Request): Promise<unknown> {
  const buf = await request.arrayBuffer();          // copy 1: raw bytes
  const text = new TextDecoder().decode(buf);       // copy 2: string
  return JSON.parse(text);                          // copy 3: object tree
}

// BETTER: use request.json() which lets V8 stream-parse where possible
async function parseLargePayloadGood(request: Request): Promise<unknown> {
  return request.json(); // single parse path, fewer intermediate allocations
}

// Pattern 2: Process large binary responses in chunks to cap peak heap usage
async function processLargeR2Object(stream: ReadableStream): Promise<string> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let totalSize = 0;
  const LIMIT = 10 * 1024 * 1024; // 10 MB guard

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    totalSize += value.byteLength;
    if (totalSize > LIMIT) {
      reader.cancel();
      throw new Error(`Response too large: ${totalSize} bytes`);
    }
    chunks.push(value);
  }

  // Combine only after size is known — avoids repeatedly growing a single buffer
  const combined = new Uint8Array(totalSize);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(combined);
}

// Pattern 3: Release large buffers explicitly before awaiting slow I/O
async function processAndForward(request: Request, env: Env): Promise<Response> {
  let processed: Uint8Array | null = new Uint8Array(await request.arrayBuffer());
  // ... transform processed ...
  const result = processed.slice(0, 100); // extract what we need
  processed = null; // allow GC before the slow subrequest below

  const upstream = await fetch("https://slow-origin.example.com", { body: result, method: "POST" });
  return upstream;
}
```

## Measuring Heap Usage from Inside the Worker

```typescript
// Workers exposes memory diagnostics via the non-standard performance API
// This is best used in wrangler dev; values are approximate in production.

function logMemoryStats(label: string): void {
  // @ts-ignore — non-standard V8 extension available in Workers runtime
  const mem = (performance as any).memory;
  if (!mem) return;
  console.log(`[${label}] heap used: ${(mem.usedJSHeapSize / 1e6).toFixed(1)} MB` +
              ` / limit: ${(mem.jsHeapSizeLimit / 1e6).toFixed(1)} MB`);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    logMemoryStats("request-start");

    const body = await request.arrayBuffer();
    logMemoryStats("after-body-read");

    // ... heavy processing ...

    logMemoryStats("after-processing");
    return new Response("OK");
  },
};
```

## LRU Cache Implementation for Module-Scope Data

```typescript
class LRUCache<K, V> {
  private readonly map = new Map<K, V>();
  constructor(private readonly maxSize: number) {}

  get(key: K): V | undefined {
    if (!this.map.has(key)) return undefined;
    // Move to end (most recently used)
    const value = this.map.get(key)!;
    this.map.delete(key);
    this.map.set(key, value);
    return value;
  }

  set(key: K, value: V): void {
    if (this.map.has(key)) this.map.delete(key);
    else if (this.map.size >= this.maxSize) {
      // Evict least recently used (first entry)
      this.map.delete(this.map.keys().next().value!);
    }
    this.map.set(key, value);
  }

  get size(): number { return this.map.size; }
}

// Usage: bounded in-memory cache for serialised API responses
const apiCache = new LRUCache<string, { data: string; expiresAt: number }>(100);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = new URL(request.url).pathname;
    const cached = apiCache.get(key);
    if (cached && cached.expiresAt > Date.now()) {
      return new Response(cached.data, { headers: { "Content-Type": "application/json" } });
    }

    const res = await fetch(`https://api.example.com${key}`);
    const data = await res.text(); // store as string, not as a live Response
    apiCache.set(key, { data, expiresAt: Date.now() + 60_000 });
    return new Response(data, { headers: { "Content-Type": "application/json" } });
  },
};
```

## Anti-patterns

- Storing live `Response` or `ReadableStream` objects in module-scope Maps — the body stream keeps the underlying byte buffer alive indefinitely until it is consumed or the isolate is recycled.
- Using `Array.push()` without a cap for logging or telemetry in module scope — arrays grow without bound across requests in the same isolate lifetime.
- Calling `await res.arrayBuffer()` on a large response and then `await res.json()` — the body can only be consumed once; the second call throws and the buffer is already held.

## Gotchas

- Workers does not expose `--expose-gc` or `global.gc()` — you cannot trigger garbage collection manually; release references and let V8 GC at its own pace.
- Module-scope state is NOT shared between isolates on different edge nodes or between the main Worker and a Durable Object — each isolate has its own heap.

## Verification

```bash
# Monitor memory-related errors in production
wrangler tail --format pretty | grep -i "memory\|exceeded\|isolate"

# Local heap audit during development
wrangler dev --inspect
# Open chrome://inspect in Chrome, attach to the Workers devtools session,
# then take a heap snapshot from the Memory panel

# Check isolate recycle rate in Cloudflare Analytics
# Dashboard > Workers > Metrics > Errors > filter by "isolate_memory_exceeded"
```

## Related

- `performance/durable-objects-memory-optimization.md`
- `performance/closure-memory-leaks.md`
- `performance/garbage-collection-optimization.md`
- `performance/webassembly-simd-workers-performance.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#memory
- https://v8.dev/blog/trash-talk
- https://developers.cloudflare.com/workers/observability/logs/logpush/
