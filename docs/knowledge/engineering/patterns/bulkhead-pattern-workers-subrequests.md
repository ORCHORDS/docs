# bulkhead-pattern-workers-subrequests

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project hosts multiple tenants on a shared Workers deployment.
A single enterprise tenant kicks off a bulk export: 500 concurrent
subrequests to an external API within one Worker invocation.
Cloudflare enforces a 1000 subrequest limit per Worker; the bulk
export hits 980 and leaves only 20 for all other in-flight Workers
sharing the isolate pool. Small mobile clients start seeing 429s
and timeout errors that have nothing to do with their own usage.

Separately: a CPU-heavy media transcoding tenant burns through
its CPU budget, starving background Workers for other tenants.

## Context

Cloudflare Workers run in shared isolate pools per colo. Subrequests
(`fetch` calls made from within a Worker) share a per-request
limit (1000 as of 2026) and count against the account's overall
fetch budget. CPU time is billed per request but burst-able.

The Bulkhead pattern — borrowed from ship-hull design — isolates
failure domains so that one compartment flooding does not sink the
whole vessel. In Workers, "compartments" are Durable Objects (one
per tenant or resource class) with bounded concurrency queues.

## Per-Tenant Bulkhead via Durable Objects

Each tenant gets a dedicated DO that acts as a concurrency gate.
The DO holds an in-memory counter of active subrequests and
enforces a ceiling before forwarding work.

```ts
export class TenantBulkhead implements DurableObject {
  private active = 0;

  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env,
  ) {}

  async fetch(req: Request): Promise<Response> {
    const body = await req.json<BulkheadRequest>();

    switch (body.action) {
      case 'acquire': return this.acquire(body.tenantId, body.limit);
      case 'release': return this.release();
      case 'status':  return Response.json({ active: this.active });
      default:        return Response.json({ error: 'unknown' }, { status: 400 });
    }
  }

  private async acquire(tenantId: string, limit: number): Promise<Response> {
    if (this.active >= limit) {
      return Response.json(
        { acquired: false, active: this.active, limit, tenantId },
        { status: 429 },
      );
    }
    this.active++;
    return Response.json({ acquired: true, active: this.active, limit });
  }

  private async release(): Promise<Response> {
    if (this.active > 0) this.active--;
    return Response.json({ active: this.active });
  }
}
```

The DO counter is in-memory — it resets on eviction (DO hibernation
after ~10s idle). This is intentional: a cold bulkhead starts at
zero, which is safe. Persistent storage would add latency and is
unnecessary for a concurrency gate.

## Worker-Side Bulkhead Helper

```ts
const TENANT_SUBREQUEST_LIMIT = 50;   // max concurrent subrequests per tenant
const DESKTOP_LIMIT           = 50;
const MOBILE_LIMIT            = 15;   // mobile gets a smaller pool

function getLimit(req: Request): number {
  // CF-Device-Type is set by Cloudflare Bot Management / Device Detection
  const device = req.headers.get('CF-Device-Type') ?? 'desktop';
  return device === 'mobile' ? MOBILE_LIMIT : DESKTOP_LIMIT;
}

async function acquireBulkhead(
  env: Env,
  tenantId: string,
  limit: number,
): Promise<boolean> {
  const id = env.TENANT_BULKHEAD.idFromName(tenantId);
  const gate = env.TENANT_BULKHEAD.get(id);
  const res = await gate.fetch(new Request('https://do/bulkhead', {
    method: 'POST',
    body: JSON.stringify({ action: 'acquire', tenantId, limit }),
  }));
  const body = await res.json<{ acquired: boolean }>();
  return body.acquired;
}

async function releaseBulkhead(env: Env, tenantId: string): Promise<void> {
  const id = env.TENANT_BULKHEAD.idFromName(tenantId);
  const gate = env.TENANT_BULKHEAD.get(id);
  await gate.fetch(new Request('https://do/bulkhead', {
    method: 'POST',
    body: JSON.stringify({ action: 'release' }),
  }));
}

export async function withBulkhead<T>(
  env: Env,
  req: Request,
  tenantId: string,
  fn: () => Promise<T>,
): Promise<T> {
  const limit = getLimit(req);
  const acquired = await acquireBulkhead(env, tenantId, limit);

  if (!acquired) {
    throw new BulkheadRejectedError(tenantId, limit);
  }

  try {
    return await fn();
  } finally {
    // Always release — even on error
    await releaseBulkhead(env, tenantId);
  }
}

class BulkheadRejectedError extends Error {
  constructor(tenantId: string, limit: number) {
    super(`Bulkhead full for tenant ${tenantId} (limit ${limit})`);
    this.name = 'BulkheadRejectedError';
  }
}
```

## Fanout Throttle for Bulk Operations

A tenant exporting 500 records must not fire 500 concurrent fetch
calls. Use a semaphore-style fanout:

```ts
async function fanoutWithLimit<T>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<unknown>,
): Promise<void> {
  const queue = [...items];
  const workers = Array.from({ length: limit }, async () => {
    while (queue.length > 0) {
      const item = queue.shift()!;
      await fn(item);
    }
  });
  await Promise.all(workers);
}

// In a bulk export handler, after bulkhead acquire:
export async function handleBulkExport(req: Request, env: Env, ctx: McContext): Promise<Response> {
  return withBulkhead(env, req, ctx.tenant.id, async () => {
    const { trackIds } = await req.json<{ trackIds: string[] }>();
    const results: unknown[] = [];

    // Max 10 concurrent subrequests per bulk export, regardless of list size
    await fanoutWithLimit(trackIds, 10, async (trackId) => {
      const data = await fetchTrackMetadata(env, trackId);
      results.push(data);
    });

    return Response.json({ count: results.length, results });
  });
}
```

## Mobile vs Desktop Load Shedding

Different client types get different bulkhead pools. Mobile clients
are latency-sensitive but typically issue fewer parallel requests;
desktop/API clients may be scripted and need tighter caps.

```
┌─────────────────────────────────────────────────────┐
│                  TENANT BULKHEAD DO                  │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │  mobile pool     │  │  desktop / API pool       │ │
│  │  limit: 15       │  │  limit: 50                │ │
│  │  active: 8       │  │  active: 43               │ │
│  └──────────────────┘  └──────────────────────────┘ │
│                                                      │
│  global ceiling: 50 (shared)                         │
└─────────────────────────────────────────────────────┘
```

When the global ceiling is hit, new mobile requests receive a
`503` with a small `Retry-After` (2-5s, suitable for auto-retry).
Desktop API clients receive `429` with a longer `Retry-After`
(30-60s, enforcing backoff).

```ts
function buildRejectionResponse(req: Request): Response {
  const device = req.headers.get('CF-Device-Type') ?? 'desktop';
  const isMobile = device === 'mobile';
  return Response.json(
    { error: 'bulkhead_full', message: 'Too many concurrent requests for this tenant' },
    {
      status: isMobile ? 503 : 429,
      headers: {
        'Retry-After': isMobile ? '3' : '30',
        'X-Bulkhead-Device': device,
      },
    },
  );
}
```

## Per-Tenant CPU Budget

Workers CPU time is billed in ms. Enforce a per-tenant CPU soft
limit via a KV counter refreshed every minute:

```ts
const CPU_BUDGET_MS_PER_MIN = 10_000; // 10s CPU per tenant per minute

async function checkCpuBudget(env: Env, tenantId: string): Promise<boolean> {
  const key = `cpu:${tenantId}:${Math.floor(Date.now() / 60_000)}`;
  const raw = await env.RATE_LIMIT.get(key);
  const used = raw ? parseInt(raw, 10) : 0;
  return used < CPU_BUDGET_MS_PER_MIN;
}

async function recordCpuUsage(env: Env, tenantId: string, cpuMs: number): Promise<void> {
  const key = `cpu:${tenantId}:${Math.floor(Date.now() / 60_000)}`;
  const raw = await env.RATE_LIMIT.get(key);
  const used = raw ? parseInt(raw, 10) : 0;
  await env.RATE_LIMIT.put(key, String(used + cpuMs), { expirationTtl: 120 });
}
```

## Isolation Levels Comparison

| Mechanism               | Isolation granularity | Persistence | Latency overhead |
|-------------------------|-----------------------|-------------|-----------------|
| KV counter              | Per-minute bucket     | Edge-global | ~10ms           |
| Durable Object counter  | Per-tenant isolate    | In-memory   | ~1ms DO→Worker  |
| Cloudflare WAF rules    | Per-IP / per-header   | Edge-global | 0 (pre-Worker)  |
| Fanout semaphore        | Per-request in-flight | In-memory   | 0               |

Use all four in combination: WAF rules catch floods before they hit
Workers; DO bulkheads enforce per-tenant concurrency; KV counters
track CPU budgets; fanout semaphores limit subrequest parallelism.

## Anti-patterns

- **One bulkhead for the whole platform.** A single global DO
  becomes a bottleneck. Name bulkheads by `tenantId`.
- **Bulkhead limit equal to the Cloudflare subrequest limit.**
  Leave headroom — set the tenant limit to 50 so the platform
  never approaches the 1000 system limit even with 20 concurrent
  tenants.
- **Not releasing on error.** A `try/finally` is mandatory.
  A leaked `active` counter will fill the bulkhead permanently
  until the DO is evicted.
- **Same limit for mobile and desktop.** Mobile retries are
  automatic and fast. A strict 50-request mobile limit causes
  rapid cascade retries. Use a smaller pool with a shorter
  Retry-After.
- **Persisting the active counter to DO storage.** This adds
  ~1ms per acquire/release and the counter should always start
  at zero on cold start. In-memory is correct here.

## Gotchas

- DO hibernation resets the in-memory `active` counter to zero.
  If the DO goes cold while requests are in-flight, the counter
  will undercount on the next wake. Accept this: it unblocks
  the bulkhead, which is the safe failure mode.
- `CF-Device-Type` is set by Cloudflare's device detection, not
  by the client. It can be absent in local dev (`wrangler dev`).
  Default to `'desktop'` when absent.
- A subrequest that hangs (e.g. waiting for an external API with
  no timeout) holds the bulkhead slot indefinitely. Always set
  a `signal: AbortSignal.timeout(ms)` on every fetch call inside
  a bulkhead.
- Cloudflare's 1000-subrequest limit is per Worker invocation,
  not per second. A DO that makes subrequests on behalf of the
  Worker inherits this limit from the root invocation.

## Verification

```bash
# Hammer a tenant's endpoint beyond the bulkhead limit
for i in $(seq 1 60); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "CF-Device-Type: mobile" \
    https://api.example.com/v1/export/tracks &
done | sort | uniq -c
# Expect: mix of 200 (first 15) and 503 (remaining 45)

# Check bulkhead status
curl -s -X POST https://api.example.com/internal/bulkhead-status \
  -d '{"tenantId":"tenant_abc"}' | jq .active
```

## Related

- `kv-rate-limiting.md` — KV-based rate limiting (different scope)
- `per-tenant-durable-object.md` — DO patterns for example project
- `circuit-breaker-workers-d1-fetch.md` — bulkhead composes with circuit breaker
- `scaling-cf-workers.md` — overall Workers scaling reference

## Sources

- Release It! — Michael T. Nygard (Chapter 4: Bulkheads)
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare Workers Limits: https://developers.cloudflare.com/workers/platform/limits/
