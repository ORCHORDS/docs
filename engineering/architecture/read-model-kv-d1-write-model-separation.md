# Read Model KV Caching in Front of a D1 Write Model

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A example project platform endpoint serves highly-read tenant dashboard data. The write model lives in D1
(normalised tables, transactional updates) and is correct but slow to query under load — dashboard
queries join 4 tables and scan thousands of rows per tenant. Adding read replicas or caching the
full page in CDN is not granular enough: different tenants refresh at different rates, and some data
(live order count) must never be stale by more than 30 seconds. You need a caching layer that is:
fast at the edge (sub-millisecond read), invalidated per-tenant on write events, and served from
the same Worker without a network round-trip to D1 on cache hits.

## Context

Cloudflare KV is globally replicated, eventually consistent (eventual propagation ≤ 60 s globally,
≤ 1 s within a PoP), and optimised for read-heavy workloads. D1 is consistent and transactional but
accessed over the Cloudflare internal network from a Worker (typically 5–30 ms per query). The
pattern: compute denormalised read models from D1 after writes, serialise to JSON, and store in KV
with a TTL matching the acceptable staleness window. On reads, serve from KV; on cache miss, fall
back to D1 and repopulate KV.

---

## KV Namespace Design

```jsonc
// wrangler.jsonc
{
  "name": "example project-dashboard",
  "kv_namespaces": [
    {
      "binding": "READ_CACHE",
      "id": "dashboard-read-cache-prod"
    }
  ],
  "d1_databases": [
    {
      "binding": "DB",
      "database_id": "example project-write-model-prod"
    }
  ]
}
```

KV key convention:
```
read:v1:{tenantId}:{modelName}
```

Examples:
- `read:v1:ten_abc:dashboard_summary`
- `read:v1:ten_abc:order_counts`
- `read:v1:ten_abc:recent_orders:page:1`

The `v1` prefix enables cache-busting on projection schema changes without iterating and deleting
keys (simply increment the version).

---

## Read Model TypeScript Definitions

```typescript
// src/read-models/dashboard-summary.ts

export interface DashboardSummary {
  tenantId:          string;
  totalOrdersCents:  number;
  currency:          string;
  orderCount:        number;
  pendingCount:      number;
  paidCount:         number;
  cancelledCount:    number;
  lastUpdatedAt:     number;  // ms epoch when the model was computed
}

export interface RecentOrder {
  orderId:      string;
  customerName: string;
  totalCents:   number;
  status:       string;
  placedAt:     number;
}

export interface RecentOrdersPage {
  orders:    RecentOrder[];
  total:     number;
  page:      number;
  pageSize:  number;
  computedAt: number;
}
```

---

## Read-Through Cache Layer

```typescript
// src/cache/read-cache.ts
import type { KVNamespace } from '@cloudflare/workers-types';

const CACHE_VERSION = 'v1';

export class ReadCache {
  constructor(
    private readonly kv: KVNamespace,
    private readonly defaultTtlSeconds = 30,
  ) {}

  private key(tenantId: string, model: string, suffix = ''): string {
    return `read:${CACHE_VERSION}:${tenantId}:${model}${suffix ? `:${suffix}` : ''}`;
  }

  async get<T>(tenantId: string, model: string, suffix?: string): Promise<T | null> {
    const raw = await this.kv.get(this.key(tenantId, model, suffix), 'text');
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  async set<T>(
    tenantId: string,
    model: string,
    value: T,
    ttlSeconds = this.defaultTtlSeconds,
    suffix?: string,
  ): Promise<void> {
    await this.kv.put(
      this.key(tenantId, model, suffix),
      JSON.stringify(value),
      { expirationTtl: ttlSeconds },
    );
  }

  async invalidate(tenantId: string, model: string, suffix?: string): Promise<void> {
    await this.kv.delete(this.key(tenantId, model, suffix));
  }

  /** Invalidate all cached models for a tenant — use with care on write events */
  async invalidateTenant(tenantId: string): Promise<void> {
    const prefix = `read:${CACHE_VERSION}:${tenantId}:`;
    const listed = await this.kv.list({ prefix });
    await Promise.all(listed.keys.map((k) => this.kv.delete(k.name)));
  }
}
```

---

## Dashboard Query — Cache-Aside Pattern

```typescript
// src/repositories/dashboard-repository.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { ReadCache } from '../cache/read-cache';
import type { DashboardSummary, RecentOrder, RecentOrdersPage } from '../read-models/dashboard-summary';

export class DashboardRepository {
  constructor(
    private readonly db: D1Database,
    private readonly cache: ReadCache,
  ) {}

  async getSummary(tenantId: string): Promise<DashboardSummary> {
    const cached = await this.cache.get<DashboardSummary>(tenantId, 'dashboard_summary');
    if (cached) return cached;

    // Cache miss — query D1
    const row = await this.db
      .prepare(
        `SELECT
           COUNT(*)                                        AS order_count,
           COALESCE(SUM(total_cents), 0)                  AS total_cents,
           MAX(currency)                                   AS currency,
           SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END) AS pending_count,
           SUM(CASE WHEN status = 'paid'      THEN 1 ELSE 0 END) AS paid_count,
           SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count
         FROM orders
         WHERE tenant_id = ?`,
      )
      .bind(tenantId)
      .first<{
        order_count: number;
        total_cents: number;
        currency: string;
        pending_count: number;
        paid_count: number;
        cancelled_count: number;
      }>();

    const summary: DashboardSummary = {
      tenantId,
      totalOrdersCents:  row?.total_cents  ?? 0,
      currency:          row?.currency     ?? 'USD',
      orderCount:        row?.order_count  ?? 0,
      pendingCount:      row?.pending_count   ?? 0,
      paidCount:         row?.paid_count      ?? 0,
      cancelledCount:    row?.cancelled_count ?? 0,
      lastUpdatedAt:     Date.now(),
    };

    // Populate cache — 30 s TTL
    await this.cache.set(tenantId, 'dashboard_summary', summary, 30);
    return summary;
  }

  async getRecentOrders(
    tenantId: string,
    page = 1,
    pageSize = 20,
  ): Promise<RecentOrdersPage> {
    const cacheKey = `page:${page}:size:${pageSize}`;
    const cached = await this.cache.get<RecentOrdersPage>(tenantId, 'recent_orders', cacheKey);
    if (cached) return cached;

    const offset = (page - 1) * pageSize;
    const [ordersResult, countResult] = await Promise.all([
      this.db
        .prepare(
          `SELECT order_id, customer_name, total_cents, status, placed_at
           FROM orders
           WHERE tenant_id = ?
           ORDER BY placed_at DESC
           LIMIT ? OFFSET ?`,
        )
        .bind(tenantId, pageSize, offset)
        .all<{ order_id: string; customer_name: string; total_cents: number; status: string; placed_at: number }>(),
      this.db
        .prepare('SELECT COUNT(*) AS cnt FROM orders WHERE tenant_id = ?')
        .bind(tenantId)
        .first<{ cnt: number }>(),
    ]);

    const result: RecentOrdersPage = {
      orders: ordersResult.results.map((r) => ({
        orderId:      r.order_id,
        customerName: r.customer_name,
        totalCents:   r.total_cents,
        status:       r.status,
        placedAt:     r.placed_at * 1000,
      })),
      total:      countResult?.cnt ?? 0,
      page,
      pageSize,
      computedAt: Date.now(),
    };

    // Cache paginated results for 60 s — less critical than summary
    await this.cache.set(tenantId, 'recent_orders', result, 60, cacheKey);
    return result;
  }
}
```

---

## Write-Side Invalidation

Invalidate relevant KV keys immediately after a write completes. Do this inside the same Worker
request that mutated D1, using `ctx.waitUntil` to avoid adding latency to the response:

```typescript
// workers/order-api/src/index.ts
import type { D1Database, KVNamespace, ExecutionContext } from '@cloudflare/workers-types';
import { ReadCache } from '../../dashboard/src/cache/read-cache';

interface Env {
  DB:           D1Database;
  READ_CACHE:   KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const body = await request.json<{ tenantId: string; amount: number; customerName: string }>();

    // 1. Write to D1 (write model)
    const orderId = `ord_${crypto.randomUUID().replace(/-/g, '')}`;
    await env.DB
      .prepare(
        `INSERT INTO orders (order_id, tenant_id, customer_name, total_cents, status, placed_at)
         VALUES (?, ?, ?, ?, 'pending', unixepoch())`,
      )
      .bind(orderId, body.tenantId, body.customerName, body.amount)
      .run();

    // 2. Invalidate read cache (fire-and-forget via waitUntil)
    const cache = new ReadCache(env.READ_CACHE);
    ctx.waitUntil(
      Promise.all([
        cache.invalidate(body.tenantId, 'dashboard_summary'),
        cache.invalidate(body.tenantId, 'recent_orders', 'page:1:size:20'),
      ]),
    );

    return Response.json({ orderId }, { status: 201 });
  },
};
```

---

## Proactive Cache Warming After Writes

For high-traffic tenants, invalidation alone causes a thundering herd of D1 queries on the first
post-write request. Warm the cache proactively inside `ctx.waitUntil`:

```typescript
// workers/order-api/src/cache-warmer.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';
import { DashboardRepository } from '../../dashboard/src/repositories/dashboard-repository';
import { ReadCache } from '../../dashboard/src/cache/read-cache';

export async function warmDashboardCache(
  tenantId: string,
  db: D1Database,
  kv: KVNamespace,
): Promise<void> {
  const cache = new ReadCache(kv);
  const repo  = new DashboardRepository(db, cache);

  // Force a D1 read and repopulate cache in one step
  await Promise.all([
    repo.getSummary(tenantId),
    repo.getRecentOrders(tenantId, 1, 20),
  ]);
}
```

```typescript
// In the order create handler:
ctx.waitUntil(warmDashboardCache(body.tenantId, env.DB, env.READ_CACHE));
```

---

## Anti-patterns

- **Caching D1 query result objects with D1 metadata (`.results`, `.meta`)**: Strip the D1
  envelope before serialising to KV. Storing the raw D1 response object leaks internal fields and
  inflates KV value size.
- **Using KV as the source of truth**: KV is eventually consistent. Never use a KV-cached value
  for a decision that must be correct (payment idempotency, inventory decrement). KV is for
  display-only read models.
- **Large TTLs on mutable aggregates**: A 10-minute TTL on `order_count` means users see stale
  counts for 10 minutes after each order. Use the shortest TTL that your acceptable staleness SLA
  permits (typically 15–60 s for dashboards).
- **Invalidating KV synchronously on the critical path**: `kv.delete()` adds ~5–15 ms. Always
  invalidate inside `ctx.waitUntil()` so the response is returned immediately.
- **Calling `kv.list()` in the request path**: `kv.list()` is slow (50–200 ms). Only use
  `invalidateTenant` (which calls `kv.list()`) in background tasks or Queue consumers, never in
  user-facing request handlers.

---

## Gotchas

- KV `expirationTtl` minimum is 60 seconds in production (some accounts have lower limits in
  preview). TTLs below 60 s will be silently rounded up to 60 s. Verify your account limits before
  relying on sub-60 s TTLs.
- KV global propagation can take up to 60 seconds after a `put()`. A user who writes data and then
  reads from a different PoP may see the stale (pre-write) cached value during that window. This is
  a documented trade-off of the cache-aside pattern on a globally distributed KV.
- `ctx.waitUntil()` extends the Worker's lifetime after the response is sent, but not indefinitely.
  D1 queries in a `waitUntil` handler are subject to the same 30 s CPU budget.
- The `v1` version prefix in KV keys means old keys (with `v0:`) are never cleaned up automatically
  when you increment the version. Schedule a periodic Worker to delete stale-versioned keys, or
  set an outer TTL long enough that they expire naturally.
- D1 `SELECT COUNT(*)` on large tables acquires a read lock. Under heavy write load this can cause
  contention. Consider maintaining a separate `order_counts` summary table updated by triggers or
  a Queue consumer instead of running the aggregate on every cache miss.

---

## Verification

```typescript
// test/dashboard-repository.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DashboardRepository } from '../src/repositories/dashboard-repository';
import { ReadCache } from '../src/cache/read-cache';

describe('DashboardRepository', () => {
  it('returns cached summary on cache hit', async () => {
    const mockKv = { get: vi.fn().mockResolvedValue(JSON.stringify({ orderCount: 42 })), put: vi.fn() };
    const cache  = new ReadCache(mockKv as any);
    const db     = { prepare: vi.fn() } as any;
    const repo   = new DashboardRepository(db, cache);

    const result = await repo.getSummary('ten_abc');
    expect(result.orderCount).toBe(42);
    expect(db.prepare).not.toHaveBeenCalled();  // D1 never queried
  });

  it('falls through to D1 on cache miss', async () => {
    const mockKv = { get: vi.fn().mockResolvedValue(null), put: vi.fn() };
    // ... set up D1 mock and verify put() is called with correct TTL
  });
});
```

```bash
# End-to-end: place an order and verify cache is populated
curl -X POST http://localhost:8787/orders \
  -H 'Content-Type: application/json' \
  -d '{"tenantId":"ten_abc","amount":4999,"customerName":"Bob"}'

# Immediately call dashboard — should hit D1 (first request after invalidation)
curl http://localhost:8787/dashboard?tenantId=ten_abc

# Call again — should hit KV (check x-cache header if instrumented)
curl http://localhost:8787/dashboard?tenantId=ten_abc
```

---

## Related

- `/documentation/categories/architecture/cqrs-cloudflare-workers-d1.md`
- `/documentation/categories/architecture/read-model-projection-workers-kv-cqrs.md`
- `/documentation/categories/architecture/cache-aside-pattern.md`
- `/documentation/categories/architecture/kv-replication-lag-compensating-patterns.md`
- `/documentation/categories/architecture/read-your-writes-consistency-workers-kv-d1.md`
- `/documentation/categories/architecture/cache-stampede-prevention-workers-durable-objects.md`

---

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- KV consistency model: https://developers.cloudflare.com/kv/learning/how-kv-works/
- Martin Fowler — "CQRS" pattern: https://martinfowler.com/bliki/CQRS.html
- "Cache-Aside Pattern" — Microsoft Azure Architecture Center: https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside
