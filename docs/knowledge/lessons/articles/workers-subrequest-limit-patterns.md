# Workers Subrequest Limit Patterns

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers endpoint that fans out to 60 upstream microservices returns `Error: Too many subrequests` for a subset of requests. A background sync Worker that iterates over a list of resources and calls the upstream API for each one fails silently once it exceeds 50 calls. An API aggregation layer works fine in staging (where it calls fewer services) but breaks in production where the full integration surface is active.

## Context

Cloudflare Workers enforce a **50 subrequest limit per request invocation** on the free plan, and **1000 subrequests on the paid plan** (Workers Standard). A "subrequest" is any outbound network call made from a Worker: `fetch()`, Service Binding calls that cross a Worker boundary, KV `get`/`put`/`delete` (each counts), Durable Object `fetch()`, R2 `get`/`put`, and some D1 operations. The limit exists to prevent runaway Workers from consuming disproportionate network resources. Calls that do NOT count as subrequests: Service Bindings called to the same Worker script (same-worker invocation), Durable Object storage operations (these are local to the DO), and in-process CPU work.

## Solution

```typescript
import { Env } from './types';

// ─── Pattern 1: Subrequest budget tracking ────────────────────────────────────
// Instrument every subrequest to stay aware of consumption.

class SubrequestBudget {
  private used = 0;
  private readonly limit: number;

  constructor(limit = 50) {
    this.limit = limit;
  }

  consume(count = 1): void {
    this.used += count;
    if (this.used > this.limit) {
      throw new Error(`Subrequest budget exceeded: ${this.used}/${this.limit}`);
    }
  }

  remaining(): number {
    return Math.max(0, this.limit - this.used);
  }

  toHeader(): string {
    return `used=${this.used}, limit=${this.limit}`;
  }
}

// ─── Pattern 2: Batching multiple fetches into one ───────────────────────────
// Instead of N individual API calls, aggregate into a single batch request
// if the upstream supports it.

export async function batchFetchUsers(
  userIds: string[],
  env: Env,
  budget: SubrequestBudget
): Promise<Record<string, unknown>> {
  // ❌ BAD: one subrequest per userId (costs N subrequests)
  // const users = await Promise.all(
  //   userIds.map(id => fetch(`https://api.example.com/users/${id}`))
  // );

  // ✅ GOOD: single batch request (costs 1 subrequest)
  budget.consume(1);
  const response = await fetch('https://api.example.com/users/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${env.API_TOKEN}` },
    body: JSON.stringify({ ids: userIds }),
  });

  if (!response.ok) throw new Error(`Batch fetch failed: ${response.status}`);
  const data = await response.json() as { users: Array<{ id: string }> };
  return Object.fromEntries(data.users.map(u => [u.id, u]));
}

// ─── Pattern 3: Service Bindings vs fetch subrequest cost ────────────────────
// Calling another Worker via a Service Binding is FREE when the callee
// is in the same Cloudflare account and the call stays within the same
// request context. Calling an external URL with fetch() costs 1 subrequest.

export async function callInternalService(
  env: Env & { INTERNAL_API: Fetcher },
  budget: SubrequestBudget,
  path: string
): Promise<unknown> {
  // ✅ Service Binding call: does NOT consume a subrequest budget slot
  // (it does consume CPU time in the callee, which is billed separately)
  const response = await env.INTERNAL_API.fetch(`https://internal${path}`);
  // Note: even though this doesn't cost a subrequest budget slot, it still
  // counts against the callee's CPU time limit.
  return response.json();
}

export async function callExternalService(
  env: Env,
  budget: SubrequestBudget,
  url: string
): Promise<unknown> {
  // ❌ External fetch: costs 1 subrequest
  budget.consume(1);
  const response = await fetch(url, {
    headers: { 'Authorization': `Bearer ${env.API_TOKEN}` },
  });
  return response.json();
}

// ─── Pattern 4: KV bulk reads ────────────────────────────────────────────────
// Each kv.get() costs 1 subrequest. Use kv.getWithMetadata() or restructure
// data to reduce the number of KV reads per request.

export async function bulkKVRead(
  env: Env,
  budget: SubrequestBudget,
  keys: string[]
): Promise<Map<string, unknown>> {
  const result = new Map<string, unknown>();

  // ❌ BAD: N subrequests for N keys
  // for (const key of keys) {
  //   budget.consume(1);
  //   const value = await env.MY_KV.get(key, { type: 'json' });
  //   result.set(key, value);
  // }

  // ✅ GOOD: Restructure data so one KV get returns all needed data.
  // Store a compound value under a single aggregated key:
  const BULK_KEY = `bulk:${keys.sort().join(',')}`;
  budget.consume(1);
  const cached = await env.MY_KV.get(BULK_KEY, { type: 'json' }) as Record<string, unknown> | null;
  if (cached) {
    for (const [k, v] of Object.entries(cached)) result.set(k, v);
    return result;
  }

  // Cache miss: fetch individually (spend the budget), then cache the aggregate.
  const fetched: Record<string, unknown> = {};
  const batchSize = Math.min(keys.length, budget.remaining() - 1); // reserve 1 for the write
  for (const key of keys.slice(0, batchSize)) {
    budget.consume(1);
    const value = await env.MY_KV.get(key, { type: 'json' });
    if (value !== null) fetched[key] = value;
    result.set(key, value);
  }

  // Write aggregate cache — TTL 60 s to limit stale window
  budget.consume(1);
  await env.MY_KV.put(BULK_KEY, JSON.stringify(fetched), { expirationTtl: 60 });
  return result;
}

// ─── Pattern 5: D1 batch queries ─────────────────────────────────────────────
// D1 batch() sends multiple SQL statements in a single subrequest.

export async function d1BatchExample(
  env: Env,
  budget: SubrequestBudget,
  userIds: string[]
): Promise<unknown[]> {
  // ❌ BAD: N subrequests for N D1 queries
  // const results = await Promise.all(
  //   userIds.map(id => env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(id).all())
  // );

  // ✅ GOOD: batch() sends all statements in 1 subrequest
  budget.consume(1);
  const statements = userIds.map(id =>
    env.DB.prepare('SELECT id, email, name FROM users WHERE id = ?1').bind(id)
  );
  const results = await env.DB.batch(statements);
  return results.flatMap(r => r.results);
}

// ─── Pattern 6: Cache API for upstream response caching ──────────────────────
// Cache upstream responses in the Workers Cache API to avoid repeated
// subrequests for the same resource within the cache TTL.

export async function cachedUpstreamFetch(
  budget: SubrequestBudget,
  url: string,
  cacheTtlSeconds = 30
): Promise<unknown> {
  const cache = caches.default;
  const cacheKey = new Request(url, { method: 'GET' });

  // Cache lookup — does NOT consume a subrequest slot
  const cached = await cache.match(cacheKey);
  if (cached) return cached.json();

  // Cache miss — consume 1 subrequest for the upstream call
  budget.consume(1);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Upstream error: ${response.status}`);

  // Clone and cache the response
  const toCache = new Response(response.clone().body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      'Cache-Control': `public, max-age=${cacheTtlSeconds}`,
    },
  });
  // cache.put does NOT consume a subrequest slot
  await cache.put(cacheKey, toCache);

  return response.json();
}

// ─── Pattern 7: Request fan-out architecture ─────────────────────────────────
// For workflows that genuinely need to call many upstreams, restructure so
// the orchestration Worker enqueues work and consumers handle individual calls.

export async function fansOutSafely(
  request: Request,
  env: Env
): Promise<Response> {
  const { resourceIds } = await request.json() as { resourceIds: string[] };

  if (resourceIds.length > 40) {
    // Too many to fan out directly — enqueue for background processing
    for (const chunk of chunkArray(resourceIds, 40)) {
      await env.SYNC_QUEUE.send({ resourceIds: chunk });
    }
    return Response.json({ status: 'enqueued', count: resourceIds.length }, { status: 202 });
  }

  // Small enough to process inline
  const budget = new SubrequestBudget(50);
  const results = await Promise.all(
    resourceIds.map(id => {
      budget.consume(1);
      return fetch(`https://upstream.example.com/resource/${id}`);
    })
  );
  return Response.json({ results: results.length });
}

function chunkArray<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) chunks.push(arr.slice(i, i + size));
  return chunks;
}
```

## Implementation Details

**Subrequest accounting.** The following operations each consume one subrequest: `fetch()`, KV `get`, KV `put`, KV `delete`, KV `list`, R2 `get`, R2 `put`, R2 `delete`, Durable Object `fetch()`, and D1 `run`/`all`/`first` (but not `batch` — that counts as one regardless of how many statements). Service Binding calls to the same-origin Worker do NOT consume a subrequest slot.

**`Promise.all` does not reduce subrequest count.** Parallel subrequests still consume the same number of slots; they simply execute concurrently. Use `Promise.all` for latency reduction, not budget reduction.

**Cache API reads are free.** `cache.match()` does not consume a subrequest slot. Only `fetch()` and binding operations do. This makes the Cache API an excellent buffer for frequently accessed upstream resources.

**D1 `batch()` is the key optimisation.** Ten D1 queries in a `batch()` call count as 1 subrequest. This is the single highest-leverage optimisation for D1-heavy Workers.

## Anti-patterns

- **`Promise.all` over a large array of `fetch()` calls.** This parallelises the I/O wait but still consumes one subrequest per call. Batch the upstream calls instead.
- **KV `list()` followed by individual `get()` for each key.** One `list` + N `get`s = N+1 subrequests. Structure data to avoid key enumeration at request time.
- **Calling downstream Workers via `fetch()` instead of Service Bindings.** Any `fetch()` to a `*.workers.dev` URL counts as a subrequest. Use Service Bindings (zero subrequest cost) for internal Worker-to-Worker calls.
- **Not tracking subrequest consumption in code.** Without explicit tracking, it is easy for incremental feature additions to push a handler over the limit in production.

## Gotchas

- **The limit applies per request invocation, not per isolate.** Each incoming request starts with a fresh budget. A Worker serving 100 concurrent requests can make 100 × 50 = 5000 subrequests across the fleet — the per-request limit is the binding constraint.
- **`wrangler dev` may not enforce the subrequest limit.** The local Miniflare environment does not reproduce the runtime's subrequest counter. Always test fan-out Workers with `--remote` or in a staging environment.
- **Redirects count.** If a `fetch()` follows a redirect, each hop counts as a separate subrequest. Disable redirect following if the upstream redirects frequently: `fetch(url, { redirect: 'manual' })`.
- **Service Binding calls still consume CPU budget of the callee.** Free subrequest slots does not mean free execution — the callee's CPU time is billed to the callee's account.

## Verification

```typescript
// In staging, instrument the handler with a SubrequestBudget and log
// the final consumption before returning:

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const budget = new SubrequestBudget(50);
    try {
      const result = await mainHandler(request, env, budget);
      console.log(`Subrequests used: ${budget.toHeader()}`);
      return result;
    } catch (err) {
      if (err instanceof Error && err.message.includes('budget exceeded')) {
        return new Response('Service Unavailable — subrequest limit', { status: 503 });
      }
      throw err;
    }
  },
};

async function mainHandler(request: Request, env: Env, budget: SubrequestBudget): Promise<Response> {
  // ... implementation ...
  return new Response('ok');
}
```

## Related

- `workers-subrequest-limit-fan-out-exceeded-incident.md`
- `lessons-workers-subrequest-fan-out-limit.md`
- `cloudflare-storage-primitive-selection.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `kv-read-costs-capacity-planning-retrospective.md`

## Sources

- Cloudflare Workers — Limits (subrequests): https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare D1 — Batch Statements: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
