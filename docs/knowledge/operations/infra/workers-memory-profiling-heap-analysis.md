# Cloudflare Workers Memory Profiling and Heap Analysis

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Worker processing large JSON payloads or performing in-memory aggregations begins hitting the 128 MB per-isolate memory limit under sustained load, causing isolate evictions that manifest as sporadic 503 errors and cold start spikes. Standard heap profiling tools (Node.js `--inspect`, Chrome DevTools heap snapshots) do not attach to the Workers runtime. Teams must infer memory behaviour from observable signals: CPU time, isolate recycle rate, and carefully crafted in-Worker heap estimation probes.

## Context

Cloudflare Workers isolates are governed by a 128 MB memory limit (Unbound Workers) or 64 MB (Standard Workers). Unlike Node.js, there is no `process.memoryUsage()` API or V8 heap snapshot capability exposed to Worker scripts at runtime. Memory pressure is observed indirectly: the Workers runtime will terminate an isolate that exceeds its limit mid-request, returning a 1101 error code (`Worker exceeded memory limit`). In practice, most heap growth in Workers stems from three patterns: holding large ArrayBuffers for streaming transforms without releasing them, accumulating global-scope caches that grow unboundedly across requests on the same isolate, and deserialising entire D1 or R2 result sets into memory before processing. Profiling must combine local workerd heap inspection (available in development) with production signals from Tail Workers and Logpush.

## Local Heap Profiling with workerd and Chrome DevTools

The `workerd` runtime (used by `wrangler dev`) supports V8's inspector protocol, enabling heap snapshots locally before deploying.

```bash
# Start wrangler dev with inspector enabled on default port 9229
wrangler dev --inspector-port 9229 src/index.ts

# In a separate terminal, trigger the inspector connection
# Open Chrome and navigate to: chrome://inspect
# Click "Open dedicated DevTools for Node"
# Navigate to Memory tab → Take heap snapshot
# Then exercise the Worker with load to observe heap growth:
for i in $(seq 1 50); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    "http://localhost:8787/api/aggregate?page=$i"
done

# After load, take a second snapshot and compare
# Look for: large ArrayBuffer detached refs, growing Map/Set in module scope,
# accumulated Response objects not garbage collected
```

```typescript
// src/index.ts — instrument with in-Worker heap estimation
// Uses a FinalizationRegistry to detect GC pressure indirectly
const gcPressureRegistry = new FinalizationRegistry((label: string) => {
  console.log(`[GC] Object collected: ${label}`);
});

function trackAllocation<T extends object>(obj: T, label: string): T {
  gcPressureRegistry.register(obj, label);
  return obj;
}

// Measure approximate heap footprint of a value
function estimateBytes(value: unknown): number {
  if (value === null || value === undefined) return 0;
  if (typeof value === "string") return value.length * 2; // UTF-16
  if (value instanceof ArrayBuffer) return value.byteLength;
  if (value instanceof Uint8Array) return value.byteLength;
  if (typeof value === "object") {
    // Rough heuristic: JSON-encode and measure string length
    try {
      return JSON.stringify(value).length * 2;
    } catch {
      return 1024; // Unknown; assume 1 KB for circular refs
    }
  }
  return 8; // Number, boolean, bigint
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.arrayBuffer();
    const bodySizeKB = (body.byteLength / 1024).toFixed(1);

    // Release the ArrayBuffer reference immediately after use
    const parsed = JSON.parse(new TextDecoder().decode(body));
    // body is now eligible for GC — do not hold a reference in outer scope
    (body as unknown as { [key: string]: unknown })["_released"] = undefined;

    const result = processPayload(parsed);
    return Response.json({ result, meta: { inputKB: bodySizeKB } });
  },
} satisfies ExportedHandler<Env>;
```

## Bounding Global Cache Size to Prevent Isolate Heap Growth

In-Worker module-scope Maps grow across requests on the same warm isolate. Implement a bounded LRU cache to cap memory usage.

```typescript
// lib/lru-cache.ts
export class LRUCache<K, V> {
  private readonly cache = new Map<K, V>();
  private readonly maxSize: number;
  private readonly maxBytesEstimate: number;
  private currentBytes = 0;

  constructor(maxSize: number, maxBytesEstimate = 10 * 1024 * 1024) {
    this.maxSize = maxSize;
    this.maxBytesEstimate = maxBytesEstimate;
  }

  get(key: K): V | undefined {
    const value = this.cache.get(key);
    if (value !== undefined) {
      // Move to end (most recently used)
      this.cache.delete(key);
      this.cache.set(key, value);
    }
    return value;
  }

  set(key: K, value: V, estimatedBytes = 0): void {
    if (this.cache.has(key)) {
      this.cache.delete(key);
    } else if (
      this.cache.size >= this.maxSize ||
      this.currentBytes + estimatedBytes > this.maxBytesEstimate
    ) {
      // Evict least recently used entry
      const lruKey = this.cache.keys().next().value;
      if (lruKey !== undefined) this.cache.delete(lruKey);
    }
    this.cache.set(key, value);
    this.currentBytes += estimatedBytes;
  }

  get size(): number {
    return this.cache.size;
  }

  get estimatedBytes(): number {
    return this.currentBytes;
  }
}

// Module-scope cache capped at 200 entries and ~20 MB
const responseCache = new LRUCache<string, object>(200, 20 * 1024 * 1024);
```

## Detecting Memory Pressure via Tail Workers

Production memory pressure is detected by correlating Tail Worker error events and isolate recycle signals.

```typescript
// workers/memory-tail/src/index.ts
export interface Env {
  METRICS_KV: KVNamespace;
  ALERT_WEBHOOK: string;
}

interface TailEvent extends TraceItem {
  cpuTime: number;
  wallTime: number;
  exceptions: Array<{ name: string; message: string }>;
}

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const event of events) {
      const memoryErrors = event.exceptions.filter(
        (e) =>
          e.message.includes("Worker exceeded memory limit") ||
          e.message.includes("memory limit") ||
          e.name === "RangeError" // ArrayBuffer allocation failure
      );

      if (memoryErrors.length > 0) {
        const key = `mem_error:${event.scriptName}:${new Date().toISOString().slice(0, 13)}`;
        const existing = parseInt((await env.METRICS_KV.get(key)) ?? "0", 10);
        await env.METRICS_KV.put(key, String(existing + 1), { expirationTtl: 86400 });

        if (existing + 1 >= 5) {
          // 5+ memory errors in 1 hour — fire alert
          await fetch(env.ALERT_WEBHOOK, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: `Memory pressure alert: ${event.scriptName} hit ${existing + 1} OOM errors in the last hour`,
              errors: memoryErrors,
            }),
          });
        }
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Storing full `Response` objects in a module-scope Map as a response cache — Response bodies are streams; retaining them prevents GC and leaks memory proportional to total response body size.
- Using `JSON.parse(await response.text())` for large payloads instead of streaming — deserialising a 10 MB JSON payload into a single V8 object tree can temporarily consume 3–5× the raw size in heap.
- Relying on `console.log(JSON.stringify(largeObject))` for debugging in production — serialising large objects for logging doubles their heap footprint transiently.
- Setting module-scope arrays as unbounded accumulation buffers across requests — even a 1 KB push per request accumulates to 1 GB after 1 million requests on a warm isolate.

## Gotchas

- The Workers runtime recycles isolates proactively when the PoP is under memory pressure, even below the 128 MB per-isolate limit — memory OOM errors can appear at 60–80 MB usage during high-traffic events.
- `ArrayBuffer.transfer()` (available in Workers) allows zero-copy moves but does NOT reduce heap size; the destination buffer still occupies the same memory.
- `FinalizationRegistry` callbacks are not guaranteed to fire within a given request's execution window; they are hints for GC observation in development, not reliable production instrumentation.
- Wrangler's `--local` mode uses a Node.js V8 heap with different GC heuristics than the production isolate; local heap snapshots reveal allocation patterns but not production eviction timing.

## Verification

```bash
# Check for error code 1101 (memory limit exceeded) in Logpush
wrangler tail my-api-worker --format json \
  | jq 'select(.exceptions[].message | test("memory limit"))'

# Local: trigger heap snapshot comparison via workerd inspector
# Before and after a batch of large-payload requests:
node -e "
const CDP = require('chrome-remote-interface');
CDP(async (client) => {
  const { HeapProfiler } = client;
  await HeapProfiler.enable();
  const { profile } = await HeapProfiler.takeHeapSnapshot();
  require('fs').writeFileSync('heap-before.json', JSON.stringify(profile));
  await client.close();
});
"
```

## Related

- `infra/workers-cold-start-bundle-size-optimization.md`
- `infra/cloudflare-workers-limits-resource-planning.md`
- `infra/workers-opentelemetry-tail-workers.md`
- `infra/workerd-local-dev-setup.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#memory
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://github.com/cloudflare/workerd
