# Durable Objects: Distributed Rate Limiter Pattern

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A multi-tenant API served by Cloudflare Workers needs per-tenant rate limiting that is accurate across the entire Cloudflare network, not just per-PoP, without introducing an external Redis dependency.

## Context
Workers run across hundreds of PoPs, so in-memory counters are local to each isolate and cannot enforce global rate limits. Durable Objects solve this by colocating a single authoritative counter instance per tenant, addressable by a deterministic ID derived from the tenant key. Requests from any PoP are forwarded to that single DO instance via the RPC binding, and the DO increments and checks the counter atomically using SQLite storage (available in the `new_sqlite_storage` compatibility flag). Latency is low when smart placement colocates the DO near the requesting region.

## Durable Object: SQLite-backed Sliding Window Counter

The DO stores a rolling window of request timestamps in SQLite, counting only those within the last N seconds.

```typescript
// rate-limiter.ts
import { DurableObject } from "cloudflare:workers";

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number; // Unix ms
}

export class RateLimiter extends DurableObject {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS hits (
        ts INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_ts ON hits (ts);
    `);
  }

  async check(
    windowMs: number,
    maxRequests: number
  ): Promise<RateLimitResult> {
    const now = Date.now();
    const windowStart = now - windowMs;

    // Atomic: delete expired + insert + count in one transaction
    this.sql.exec("BEGIN");
    try {
      this.sql.exec("DELETE FROM hits WHERE ts < ?", windowStart);
      this.sql.exec("INSERT INTO hits (ts) VALUES (?)", now);
      const [row] = [...this.sql.exec("SELECT COUNT(*) AS cnt FROM hits")];
      this.sql.exec("COMMIT");

      const count = (row as { cnt: number }).cnt;
      const allowed = count <= maxRequests;
      const remaining = Math.max(0, maxRequests - count);

      // Oldest hit defines when the window resets
      const [oldest] = [...this.sql.exec("SELECT MIN(ts) AS minTs FROM hits")];
      const resetAt = oldest
        ? (oldest as { minTs: number }).minTs + windowMs
        : now + windowMs;

      return { allowed, remaining, resetAt };
    } catch (e) {
      this.sql.exec("ROLLBACK");
      throw e;
    }
  }

  async reset(): Promise<void> {
    this.sql.exec("DELETE FROM hits");
  }
}
```

## Worker: Routing to the Per-Tenant DO via RPC

Derive a deterministic DO ID from the tenant key and call `check()` via the Workers RPC binding.

```typescript
// worker.ts
import { RateLimiter } from "./rate-limiter";

export interface Env {
  RATE_LIMITER: DurableObjectNamespace<RateLimiter>;
}

const WINDOW_MS = 60_000; // 1-minute sliding window
const MAX_REQUESTS = 100;

function getTenantId(request: Request): string | null {
  // Extract from JWT sub, API key header, or subdomain
  return request.headers.get("X-Tenant-ID");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = getTenantId(request);
    if (!tenantId) {
      return new Response("Missing X-Tenant-ID", { status: 400 });
    }

    // One DO instance per tenant, globally unique by name
    const doId = env.RATE_LIMITER.idFromName(`tenant:${tenantId}`);
    const limiter = env.RATE_LIMITER.get(doId);

    const { allowed, remaining, resetAt } = await limiter.check(
      WINDOW_MS,
      MAX_REQUESTS
    );

    const headers = {
      "X-RateLimit-Limit": String(MAX_REQUESTS),
      "X-RateLimit-Remaining": String(remaining),
      "X-RateLimit-Reset": String(Math.ceil(resetAt / 1000)),
    };

    if (!allowed) {
      return new Response("Too Many Requests", {
        status: 429,
        headers: {
          ...headers,
          "Retry-After": String(Math.ceil((resetAt - Date.now()) / 1000)),
        },
      });
    }

    // Forward to origin or service binding
    return new Response(JSON.stringify({ ok: true, remaining }), {
      status: 200,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  },
};

export { RateLimiter };
```

## Hierarchical Limits: Per-Tenant + Per-Endpoint

For more granular control, use a composite key that combines the tenant and the route.

```typescript
// Per-endpoint limiter: different quotas per route
const LIMITS: Record<string, { windowMs: number; max: number }> = {
  "/api/export": { windowMs: 3_600_000, max: 10 },   // 10/hour
  "/api/ingest": { windowMs: 60_000, max: 1_000 },    // 1 000/min
  default:        { windowMs: 60_000, max: 100 },
};

async function checkHierarchical(
  env: Env,
  tenantId: string,
  pathname: string
): Promise<RateLimitResult> {
  const { windowMs, max } = LIMITS[pathname] ?? LIMITS.default;

  // Composite key: one DO per (tenant, route bucket)
  const routeKey = LIMITS[pathname] ? pathname : "default";
  const doId = env.RATE_LIMITER.idFromName(`${tenantId}:${routeKey}`);
  const limiter = env.RATE_LIMITER.get(doId);

  return limiter.check(windowMs, max);
}
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "rate-limiter-worker"
compatibility_date = "2025-10-01"
compatibility_flags = ["nodejs_compat"]

[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiter"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["RateLimiter"]
```

## Alarm-based Counter Expiry (Optional)

For very high cardinality tenants, set a DO alarm to self-destruct stale instances and free storage.

```typescript
// Inside RateLimiter class
async alarm(): Promise<void> {
  const [row] = [...this.sql.exec("SELECT COUNT(*) AS cnt FROM hits")];
  const count = (row as { cnt: number }).cnt;
  if (count === 0) {
    // No recent hits — let this DO hibernate
    return;
  }
  // Reschedule to clean up again in 1 hour
  await this.ctx.storage.setAlarm(Date.now() + 3_600_000);
}

async check(windowMs: number, maxRequests: number): Promise<RateLimitResult> {
  // Ensure alarm is set to eventually clean up
  const alarm = await this.ctx.storage.getAlarm();
  if (alarm === null) {
    await this.ctx.storage.setAlarm(Date.now() + 3_600_000);
  }
  // ... rest of check logic
  return { allowed: true, remaining: maxRequests, resetAt: Date.now() + windowMs };
}
```

## Anti-patterns
- Using `idFromName()` with unbounded user-supplied strings — sanitize and hash tenant IDs to prevent key injection
- Running rate limit checks inside a Durable Object alarm handler — alarms are for housekeeping, not the critical path
- Storing one row per request indefinitely without deleting expired rows — leads to unbounded SQLite growth
- Using `new_class` instead of `new_sqlite_classes` in migrations — legacy KV storage is slower and limited to 128 KB values

## Gotchas
- Each `RATE_LIMITER.get(id)` call over RPC adds ~5-15 ms of network latency from non-colocated PoPs; enable smart placement on the Worker to minimize this
- The `new_sqlite_storage` flag and `new_sqlite_classes` migration tag are required together; one without the other leaves the DO on legacy storage
- SQLite transactions in Durable Objects are synchronous and blocking on the event loop; avoid large result sets inside transactions
- `idFromName()` with the same string always resolves to the same DO worldwide, but the DO is physically located in a single Cloudflare region — choose naming keys that distribute tenants across geographies if needed

## Verification
1. Deploy the Worker and send 101 requests with the same `X-Tenant-ID` header within 60 seconds
2. Confirm the 101st request returns HTTP 429 with correct `X-RateLimit-Remaining: 0`
3. Wait for the window to expire and confirm the next request returns HTTP 200
4. Call `limiter.reset()` via a secured admin endpoint and verify the counter zeroes out immediately
5. Use `wrangler tail` to inspect DO RPC round-trip times and confirm they are under 20 ms for same-region requests

## Related
- `durable-objects-sqlite-storage.md`
- `durable-objects-best-practices.md`
- `durable-object-new-sqlite-namespace-migration.md`
- `workers-rpc-service-binding-patterns.md`
- `rate-limiting-v2-vs-workers-side.md`

## Sources
- https://developers.cloudflare.com/durable-objects/api/storage-api/
- https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/
- https://developers.cloudflare.com/workers/runtime-apis/rpc/
