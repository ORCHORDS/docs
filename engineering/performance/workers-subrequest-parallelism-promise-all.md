# Maximising Workers Subrequest Parallelism with Promise.all

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker that fans out to many downstream APIs executes subrequests sequentially, producing total latency that is the *sum* of all round-trips instead of the *maximum*. As the number of subrequests grows toward the platform limit of 1 000 per invocation, sequential execution also risks timeout errors.

---

## Context
Cloudflare Workers allow up to 1 000 subrequests per invocation (including `fetch`, KV, D1, and R2 calls). Sequential execution means each await blocks until the previous request completes, compounding latency linearly. `Promise.all` fires all requests concurrently and resolves when the slowest one finishes — dramatically reducing wall-clock time. For fan-outs exceeding 50 concurrent subrequests, batching into groups of 50 prevents TCP connection saturation at the origin. When total subrequests exceed 1 000, switch to sequential batch execution. Fire-and-forget analytics or logging calls should use `ctx.waitUntil` so they do not contribute to response latency.

---

## Section 1 — Worker Config

```toml
name = "parallel-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
# Max concurrent subrequests per batch before origin saturation
MAX_CONCURRENCY = "50"
# Workers subrequest hard limit
SUBREQUEST_LIMIT = "1000"
```

## Section 2 — Implementation

```typescript
import { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  MAX_CONCURRENCY: string;
  ANALYTICS_URL: string;
}

/** Split an array into chunks of at most `size` elements. */
function chunk<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

/** Fetch a single resource, returning null on failure. */
async function safeFetch(url: string): Promise<{ url: string; data: unknown } | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return { url, data: await res.json() };
  } catch {
    return null;
  }
}

/**
 * Execute subrequests in parallel batches.
 * - Up to `concurrency` requests fire at once.
 * - Batches execute sequentially to stay within the 1 000-subrequest cap.
 */
async function parallelBatchFetch(
  urls: string[],
  concurrency = 50
): Promise<Array<{ url: string; data: unknown } | null>> {
  // Guard against platform limit
  const safeUrls = urls.slice(0, 1000);
  const batches = chunk(safeUrls, concurrency);
  const results: Array<{ url: string; data: unknown } | null> = [];

  for (const batch of batches) {
    // All requests in one batch fire simultaneously
    const batchResults = await Promise.all(batch.map(safeFetch));
    results.push(...batchResults);
  }

  return results;
}

/** Timing helper — compare sequential vs parallel. */
async function timedSequentialFetch(
  urls: string[]
): Promise<{ results: Array<unknown>; elapsedMs: number }> {
  const start = Date.now();
  const results: unknown[] = [];
  for (const url of urls) {
    results.push(await safeFetch(url));
  }
  return { results, elapsedMs: Date.now() - start };
}

async function timedParallelFetch(
  urls: string[],
  concurrency: number
): Promise<{ results: Array<unknown>; elapsedMs: number }> {
  const start = Date.now();
  const results = await parallelBatchFetch(urls, concurrency);
  return { results, elapsedMs: Date.now() - start };
}

/** Fire-and-forget analytics via ctx.waitUntil — zero response latency impact. */
function sendAnalytics(
  ctx: ExecutionContext,
  analyticsUrl: string,
  payload: Record<string, unknown>
): void {
  ctx.waitUntil(
    fetch(analyticsUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {
      // Swallow errors — analytics must never impact the main response
    })
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const concurrency = parseInt(env.MAX_CONCURRENCY ?? '50', 10);

    if (url.pathname === '/aggregate') {
      // Example: fan-out to 200 product APIs
      const productIds: string[] = Array.from({ length: 200 }, (_, i) => String(i + 1));
      const apiUrls = productIds.map(
        (id) => `https://api.example.com/products/${id}`
      );

      const startTs = Date.now();
      const results = await parallelBatchFetch(apiUrls, concurrency);
      const elapsedMs = Date.now() - startTs;

      const successful = results.filter(Boolean);

      // Analytics are non-blocking
      sendAnalytics(ctx, env.ANALYTICS_URL, {
        event: 'aggregate_request',
        total: results.length,
        successful: successful.length,
        elapsedMs,
      });

      return Response.json({
        count: successful.length,
        elapsedMs,
        results: successful,
      });
    }

    if (url.pathname === '/benchmark') {
      const testUrls = Array.from(
        { length: 10 },
        (_, i) => `https://httpbin.org/delay/${(i % 3) + 1}`
      );

      const [seq, par] = await Promise.all([
        timedSequentialFetch(testUrls.slice(0, 5)),
        timedParallelFetch(testUrls.slice(0, 5), 5),
      ]);

      return Response.json({
        sequentialMs: seq.elapsedMs,
        parallelMs: par.elapsedMs,
        speedupFactor: (seq.elapsedMs / par.elapsedMs).toFixed(2),
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Section 3 — Integration Test

```typescript
// test/parallel.test.ts (using Vitest + @cloudflare/vitest-pool-workers)
import { describe, it, expect } from 'vitest';
import worker from '../src/index';

// Mock fetch to simulate 100 ms per subrequest
const originalFetch = globalThis.fetch;
beforeEach(() => {
  let callCount = 0;
  globalThis.fetch = async (input: RequestInfo) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('api.example.com')) {
      callCount++;
      await new Promise((r) => setTimeout(r, 100)); // simulate 100 ms latency
      return new Response(JSON.stringify({ id: callCount }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return originalFetch(input);
  };
});

afterEach(() => { globalThis.fetch = originalFetch; });

describe('parallel batch fetch', () => {
  it('completes 10 requests faster than sequential would', async () => {
    const urls = Array.from({ length: 10 }, (_, i) =>
      `https://api.example.com/products/${i}`
    );

    const start = Date.now();
    // chunk size 10 — all fire at once
    const results = await (worker as any).parallelBatchFetch(urls, 10);
    const elapsed = Date.now() - start;

    expect(results.filter(Boolean)).toHaveLength(10);
    // Parallel: ~100 ms; sequential would be ~1000 ms
    expect(elapsed).toBeLessThan(300);
  });
});
```

---

## Anti-patterns
- **`Promise.all` on 1 000+ URLs at once** — exhausts the Workers subrequest limit in a single batch; always chunk first.
- **Awaiting analytics inside the response path** — makes users wait for non-critical logging; use `ctx.waitUntil` instead.
- **Ignoring `Promise.all` rejections** — one failed subrequest rejects the entire `Promise.all`; wrap individual fetches in `safeFetch` to isolate failures.
- **Unbounded concurrency to a single origin** — hammering one upstream with 50+ simultaneous connections can trigger rate limits; tune `MAX_CONCURRENCY` per downstream capacity.

---

## Gotchas
- The 1 000-subrequest limit is per *Worker invocation*, not per `fetch` call — KV reads, D1 queries, R2 operations, and service bindings all count toward it.
- `ctx.waitUntil` calls also count as subrequests; budget them when calculating total usage.
- `Promise.allSettled` is safer than `Promise.all` when you want results even if some requests fail — use it if partial success is acceptable.
- Workers do not have a configurable connection pool; the runtime manages TCP reuse automatically.
- `fetch` inside Workers does not follow browser CORS rules — you can fan out to any origin without preflight.

---

## Verification

```bash
# Measure aggregate endpoint latency
curl -w "Total: %{time_total}s\n" -o /dev/null -s \
  https://my-worker.example.com/aggregate

# Run the built-in benchmark comparing sequential vs parallel
curl -s https://my-worker.example.com/benchmark | jq .
# Expected output:
# {
#   "sequentialMs": 1523,
#   "parallelMs": 312,
#   "speedupFactor": "4.88"
# }

# Check subrequest count in Cloudflare dashboard
# Workers > your-worker > Metrics > Subrequests per invocation
```

---

## Related
- `workers-cache-api-stale-while-revalidate.md`
- `workers-kv-bulk-read-cache-warming.md`
- `workers-streaming-large-d1-result-set.md`

---

## Sources
- Cloudflare Workers limits — https://developers.cloudflare.com/workers/platform/limits/
- MDN Promise.all — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all
- Cloudflare ctx.waitUntil — https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/#contextwaituntil
