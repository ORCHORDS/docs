# Scatter-Gather with Workers Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your API response must aggregate data from multiple downstream Workers (e.g., inventory, pricing, and reviews services). Calling them sequentially adds their latencies together, while calling them in parallel with bare `Promise.all` means a single service failure aborts the entire request. You need a resilient fan-out that returns partial results, logs failures to D1, and enforces a hard timeout across all downstream calls.

---

## Context

The scatter-gather pattern fans a single request out to N downstream services concurrently and merges the responses. Cloudflare Workers service bindings let you invoke sibling Workers directly — no HTTP round-trip over the public internet — with sub-millisecond cold-start overhead. `Promise.allSettled` is the correct primitive here: unlike `Promise.all`, it does not short-circuit on rejection, so all results (fulfilled or rejected) are available for inspection. An `AbortController` with a 2-second deadline is shared across all fan-out fetches; services that exceed the deadline have their signal aborted and their result is treated as a failure. Failures are written to a D1 `service_failures` table for SLO dashboards, and the merged response includes a `degraded` flag when some services did not contribute.

---

## Service Binding Config

```toml
# wrangler.toml (gateway Worker)
[[services]]
binding = "SERVICE_INVENTORY"
service = "inventory-worker"

[[services]]
binding = "SERVICE_PRICING"
service = "pricing-worker"

[[services]]
binding = "SERVICE_REVIEWS"
service = "reviews-worker"

[vars]
SCATTER_TIMEOUT_MS = "2000"
```

---

## Implementation

```typescript
// src/scatter-gather.ts

export interface Env {
  SERVICE_INVENTORY: Fetcher;
  SERVICE_PRICING:   Fetcher;
  SERVICE_REVIEWS:   Fetcher;
  DB:                D1Database;
  SCATTER_TIMEOUT_MS: string;
}

interface ServiceResult<T> {
  service:  string;
  data:     T | null;
  ok:       boolean;
  latencyMs: number;
  error?:   string;
}

interface AggregatedResponse {
  inventory: unknown | null;
  pricing:   unknown | null;
  reviews:   unknown | null;
  degraded:  boolean;
  failures:  string[];
}

// ── Per-service fetch with timeout and timing ──────────────────────────────

async function fetchService(
  name: string,
  fetcher: Fetcher,
  request: Request,
  signal: AbortSignal
): Promise<ServiceResult<unknown>> {
  const start = Date.now();

  try {
    const res = await fetcher.fetch(
      new Request(request.url, {
        method:  request.method,
        headers: request.headers,
        signal,
      })
    );

    const latencyMs = Date.now() - start;

    if (!res.ok) {
      return {
        service: name,
        data:    null,
        ok:      false,
        latencyMs,
        error:   `HTTP ${res.status}`,
      };
    }

    const data = await res.json();
    return { service: name, data, ok: true, latencyMs };
  } catch (err) {
    const latencyMs = Date.now() - start;
    const isAbort   = err instanceof DOMException && err.name === "AbortError";
    return {
      service:  name,
      data:     null,
      ok:       false,
      latencyMs,
      error:    isAbort ? `timeout after ${latencyMs}ms` : String(err),
    };
  }
}

// ── Log failures to D1 (fire-and-forget via waitUntil) ────────────────────

async function logFailures(
  db: D1Database,
  failures: Array<ServiceResult<unknown>>,
  requestId: string
): Promise<void> {
  if (failures.length === 0) return;

  const stmt = db.prepare(
    `INSERT INTO service_failures (request_id, service, error, latency_ms, failed_at)
     VALUES (?, ?, ?, ?, ?)`
  );

  const now = Date.now();
  const batch = failures.map((f) =>
    stmt.bind(requestId, f.service, f.error ?? "unknown", f.latencyMs, now)
  );

  await db.batch(batch);
}

// ── Scatter-gather orchestrator ────────────────────────────────────────────

export async function scatterGather(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  requestId: string
): Promise<AggregatedResponse> {
  const timeoutMs = parseInt(env.SCATTER_TIMEOUT_MS, 10);
  const controller = new AbortController();
  const timer      = setTimeout(() => controller.abort(), timeoutMs);

  const services: Array<{ name: string; fetcher: Fetcher }> = [
    { name: "inventory", fetcher: env.SERVICE_INVENTORY },
    { name: "pricing",   fetcher: env.SERVICE_PRICING   },
    { name: "reviews",   fetcher: env.SERVICE_REVIEWS   },
  ];

  // ── Scatter: fan out to all services concurrently ─────────────────────────
  const settled = await Promise.allSettled(
    services.map(({ name, fetcher }) =>
      fetchService(name, fetcher, request, controller.signal)
    )
  );

  clearTimeout(timer);

  // ── Gather: separate successes from failures ───────────────────────────────
  const results = settled.map((s) =>
    s.status === "fulfilled" ? s.value : ({ service: "unknown", data: null, ok: false, latencyMs: 0, error: String((s as PromiseRejectedResult).reason) } satisfies ServiceResult<unknown>)
  );

  const successes = results.filter((r) => r.ok);
  const failures  = results.filter((r) => !r.ok);

  // Log failures asynchronously — do not block the response
  if (failures.length > 0) {
    ctx.waitUntil(logFailures(env.DB, failures, requestId));
  }

  // ── Merge results into aggregated response ─────────────────────────────────
  const byName = Object.fromEntries(successes.map((r) => [r.service, r.data]));

  return {
    inventory: byName["inventory"] ?? null,
    pricing:   byName["pricing"]   ?? null,
    reviews:   byName["reviews"]   ?? null,
    degraded:  failures.length > 0,
    failures:  failures.map((f) => `${f.service}: ${f.error}`),
  };
}

// src/index.ts
import { scatterGather, type Env } from "./scatter-gather";
import { randomUUID } from "node:crypto";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const requestId = randomUUID();
    const result    = await scatterGather(request, env, ctx, requestId);

    const status = result.degraded ? 206 : 200; // 206 Partial Content when degraded

    return Response.json(result, {
      status,
      headers: {
        "X-Request-Id":   requestId,
        "X-Degraded":     String(result.degraded),
      },
    });
  },
};
```

---

## Integration / Testing

```typescript
// test/scatter-gather.test.ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { scatterGather, type Env } from "../src/scatter-gather";

function makeFetcher(response: Response): Fetcher {
  return { fetch: vi.fn().mockResolvedValue(response) } as unknown as Fetcher;
}

function makeEnv(overrides: Partial<{ inventory: Response; pricing: Response; reviews: Response }> = {}): Env {
  return {
    SERVICE_INVENTORY: makeFetcher(overrides.inventory ?? Response.json({ stock: 5 })),
    SERVICE_PRICING:   makeFetcher(overrides.pricing   ?? Response.json({ price: 99 })),
    SERVICE_REVIEWS:   makeFetcher(overrides.reviews   ?? Response.json({ rating: 4.5 })),
    DB:                { batch: vi.fn().mockResolvedValue([]) } as unknown as D1Database,
    SCATTER_TIMEOUT_MS: "2000",
  };
}

const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

describe("scatter-gather", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns all data when all services succeed", async () => {
    const req = new Request("https://gateway.example.com/product/123");
    const res = await scatterGather(req, makeEnv(), ctx, "req-1");
    expect(res.degraded).toBe(false);
    expect(res.inventory).toEqual({ stock: 5 });
    expect(res.pricing).toEqual({ price: 99 });
    expect(res.reviews).toEqual({ rating: 4.5 });
  });

  it("returns partial result and sets degraded when one service fails", async () => {
    const env = makeEnv({ reviews: new Response(null, { status: 503 }) });
    const req = new Request("https://gateway.example.com/product/123");
    const res = await scatterGather(req, env, ctx, "req-2");
    expect(res.degraded).toBe(true);
    expect(res.reviews).toBeNull();
    expect(res.pricing).toEqual({ price: 99 });
    expect(res.failures.some((f) => f.includes("reviews"))).toBe(true);
  });
});
```

---

## Anti-patterns

- **Using `Promise.all` instead of `Promise.allSettled`** — a single service failure rejects the entire `Promise.all`, returning a 500 to the client even when two of three services responded successfully.
- **Not aborting the signal on success** — failing to call `clearTimeout(timer)` leaves a dangling timer that may abort follow-up requests in the same isolate.
- **Awaiting `logFailures` in the hot path** — D1 writes should be deferred via `ctx.waitUntil`; awaiting them adds D1 latency to every degraded response.
- **Forwarding the original `request.body` to all services** — the `Request` body is a readable stream and can only be consumed once; clone the request or extract the body before the fan-out.

---

## Gotchas

- Service bindings are only available when the callee Worker is deployed in the same Cloudflare account; `wrangler dev` must run all services locally with `--service` flags or a multi-Worker `wrangler.toml`.
- `AbortSignal` passed via a service binding request is respected by the callee's `fetch()` calls but not by the callee's own compute; long CPU loops in the callee will not be interrupted.
- A `206 Partial Content` response may confuse CDN or client-side caching; add `Cache-Control: no-store` on degraded responses.
- D1 `batch` is transactional per batch; a single failed row rolls back all inserts in that batch — handle the error and retry individual rows if needed.
- `Promise.allSettled` never rejects; a rejected result in `settled` has `status === "rejected"` — always check `.status` before accessing `.value`.

---

## Verification

```bash
# Start all workers locally
npx wrangler dev --service inventory-worker --service pricing-worker --service reviews-worker

# All services healthy
curl -i http://localhost:8787/product/123
# HTTP/1.1 200, X-Degraded: false

# Simulate a service outage by stopping one worker, then:
curl -i http://localhost:8787/product/123
# HTTP/1.1 206, X-Degraded: true
# Body: { ..., degraded: true, failures: ["reviews: timeout after 2000ms"] }

# Check D1 failure log
npx wrangler d1 execute DB --command \
  "SELECT service, error, latency_ms FROM service_failures ORDER BY failed_at DESC LIMIT 10"
```

---

## Related

- `request-coalescing-durable-objects.md`
- `compensating-transaction-workers-d1.md`
- `write-behind-cache-workers-kv-d1.md`

---

## Sources

- Cloudflare Workers service bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Promise.allSettled MDN — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled
- Scatter-gather integration pattern — https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
