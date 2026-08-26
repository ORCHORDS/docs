# Read-Through Cache: Transparent KV Layer over D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to serve frequently-read D1 data at KV latency without scattering cache
logic across every handler. The business logic should call a single `store.get(key)`
and receive a value — it must not know whether the data came from KV or D1. Cache
population should be automatic, not a caller responsibility. This differs from
cache-aside: in cache-aside the caller drives population; in read-through the cache
layer itself owns the fallback logic transparently.

---

## Context

**Read-through** places the cache between the caller and the data source. The caller
interacts only with the cache interface; the cache transparently loads from the
origin on a miss and returns the value:

```
Caller → ReadThroughCache.get(key)
              │
              ├─ KV.get(key) → HIT  → return cached value
              │
              └─ MISS → D1.query(key)
                          │
                          ├─ KV.put(key, value, TTL)
                          └─ return value to caller
```

On write, the cache invalidates (or refreshes) its own entry — the caller still
writes to D1 directly, then calls `cache.invalidate(key)`. This keeps the cache
consistent without coupling write paths to caching concerns.

---

## Section 1 — ReadThroughCache Class

```typescript
// lib/read-through-cache.ts

export type Loader<T> = (key: string) => Promise<T | null>;

export interface ReadThroughOptions {
  ttlSeconds: number;
  namespace:  string;          // key prefix: "product", "config", etc.
  nullTtl?:   number;          // TTL for caching null (not-found) results; 0 = don't cache null
}

export class ReadThroughCache<T> {
  constructor(
    private readonly kv:      KVNamespace,
    private readonly loader:  Loader<T>,
    private readonly options: ReadThroughOptions,
  ) {}

  async get(key: string): Promise<T | null> {
    const kvKey = this.key(key);

    // 1. KV lookup
    const raw = await this.kv.get(kvKey, 'text');
    if (raw !== null) {
      // Distinguish a cached null sentinel from a missing key
      if (raw === '__null__') return null;
      return JSON.parse(raw) as T;
    }

    // 2. Transparent population from origin
    const value = await this.loader(key);

    if (value !== null) {
      await this.kv.put(kvKey, JSON.stringify(value), {
        expirationTtl: this.options.ttlSeconds,
      });
    } else if (this.options.nullTtl && this.options.nullTtl > 0) {
      // Cache the not-found result to prevent repeated D1 lookups for non-existent keys
      await this.kv.put(kvKey, '__null__', {
        expirationTtl: this.options.nullTtl,
      });
    }

    return value;
  }

  async invalidate(key: string): Promise<void> {
    await this.kv.delete(this.key(key));
  }

  async refresh(key: string): Promise<T | null> {
    await this.invalidate(key);
    return this.get(key);
  }

  private key(k: string): string {
    return `${this.options.namespace}:${k}`;
  }
}
```

---

## Section 2 — Wiring to D1: Plan Repository

```typescript
// repos/plan-repo.ts
import { ReadThroughCache } from '../lib/read-through-cache';

export interface Plan {
  id:           string;
  orgId:        string;
  tier:         'free' | 'pro' | 'enterprise';
  seats:        number;
  renewsAt:     string;
}

export interface Env {
  KV_CACHE: KVNamespace;
  DB:       D1Database;
}

export function makePlanCache(env: Env): ReadThroughCache<Plan> {
  return new ReadThroughCache<Plan>(
    env.KV_CACHE,
    async (orgId) => {
      const row = await env.DB
        .prepare('SELECT id, org_id, tier, seats, renews_at FROM plans WHERE org_id = ? LIMIT 1')
        .bind(orgId)
        .first<{ id: string; org_id: string; tier: string; seats: number; renews_at: string }>();

      if (!row) return null;

      return {
        id:       row.id,
        orgId:    row.org_id,
        tier:     row.tier as Plan['tier'],
        seats:    row.seats,
        renewsAt: row.renews_at,
      };
    },
    {
      ttlSeconds: 120,      // tolerate up to 2-minute staleness
      nullTtl:    30,       // cache "not found" for 30 s to protect D1
      namespace:  'plan',
    },
  );
}

export async function getPlan(orgId: string, env: Env): Promise<Plan | null> {
  return makePlanCache(env).get(orgId);
}

export async function upgradePlan(orgId: string, tier: Plan['tier'], env: Env): Promise<void> {
  await env.DB
    .prepare('UPDATE plans SET tier = ?, updated_at = ? WHERE org_id = ?')
    .bind(tier, new Date().toISOString(), orgId)
    .run();

  // Invalidate so next get() re-loads fresh data from D1
  await makePlanCache(env).invalidate(orgId);
}
```

---

## Section 3 — Worker Handler

```typescript
// worker.ts
import { getPlan, upgradePlan } from './repos/plan-repo';

export interface Env {
  KV_CACHE: KVNamespace;
  DB:       D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url   = new URL(request.url);
    const orgId = url.searchParams.get('orgId');

    if (!orgId) return Response.json({ error: 'orgId required' }, { status: 400 });

    if (request.method === 'GET') {
      const plan = await getPlan(orgId, env);
      if (!plan) return Response.json({ error: 'Not found' }, { status: 404 });
      return Response.json(plan);
    }

    if (request.method === 'POST') {
      const { tier } = await request.json<{ tier: 'free' | 'pro' | 'enterprise' }>();
      await upgradePlan(orgId, tier, env);
      return Response.json({ ok: true });
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
```

---

## Section 4 — Null Caching and Stampede Guard

When an unknown `orgId` is queried, without `nullTtl` every miss causes a D1 read.
Under traffic from bots or misconfigured clients this produces a "stampede on null"
that saturates D1.

```typescript
// Set nullTtl to 30–60 s for entities unlikely to be created within the window
const cache = new ReadThroughCache<Plan>(env.KV_CACHE, loader, {
  ttlSeconds: 120,
  nullTtl:    60,   // 60 s protection window for non-existent orgs
  namespace:  'plan',
});
```

The sentinel `__null__` stored in KV is checked explicitly to distinguish a cached
null from a KV miss. An alternative is a wrapper object `{ v: null }` stored as
JSON, which avoids the magic-string sentinel.

---

## Anti-patterns

**Returning a cache object and calling `.get()` with a loader** — that is cache-aside,
not read-through. Read-through binds the loader at construction time so callers
never touch the loader directly. If callers pass loaders at call time, you have
cache-aside and all its caller-coupling.

**Bypassing the cache for admin reads** — if an admin API reads directly from D1 and
then the regular API hits KV, operational staff will see a different view than
customers during the TTL window. Route all reads through the cache.

**Not caching nulls when the entity can be legitimately absent** — repeated 404-class
queries are a common denial-of-service vector against D1. Always set `nullTtl`.

**Using the same namespace for different entity shapes** — key collisions silently
return wrong types. One `ReadThroughCache` instance per entity type; one namespace
string per instance.

---

## Gotchas

- **KV minimum TTL is 60 s.** If `nullTtl` is set to less than 60, the `kv.put()`
  call throws. Clamp to `Math.max(60, nullTtl)` or accept that null protection only
  starts at 60 s.
- **The loader must be pure per key.** If the loader's result depends on context
  other than the key (e.g. the caller's locale), the cache will serve one locale's
  data to all callers. Make the key encode all dimensions that vary.
- **KV read-after-write is eventually consistent.** After `invalidate()`, a Worker
  in another datacenter may still read the old KV value for up to 60 s. This is the
  expected KV propagation window; design for it.
- **`__null__` sentinel is a contract.** If you ever store the literal string
  `"__null__"` as a real value in the same namespace, the cache will misinterpret it.
  Use a wrapper object `{ v: null }` if the domain allows null as a valid value.

---

## Verification

```bash
# Cold read — should call D1 and populate KV
curl "https://api.example.com/plan?orgId=org_123" | jq .tier

# Confirm KV entry was written
wrangler kv:key get --namespace-id=<CACHE_NS> "plan:org_123"

# Write a plan upgrade — should invalidate KV
curl -X POST "https://api.example.com/plan?orgId=org_123" \
  -H "Content-Type: application/json" \
  -d '{"tier":"enterprise"}'

# Next GET should re-populate KV from D1 with new tier
curl "https://api.example.com/plan?orgId=org_123" | jq .tier

# Null caching: query non-existent org, then confirm sentinel in KV
curl "https://api.example.com/plan?orgId=org_unknown"
wrangler kv:key get --namespace-id=<CACHE_NS> "plan:org_unknown"
# expected output: __null__
```

---

## Related

- `cache-aside-kv-d1-fallback.md` — caller-driven population (compare with read-through)
- `stale-while-revalidate-workers-kv.md` — serve stale while refreshing in background
- `write-behind-cache-kv-d1.md` — async flush of KV writes back to D1
- `circuit-breaker-workers-d1-fetch.md` — open circuit when D1 is unreachable
- `request-coalescing-cache-stampede.md` — coalescing concurrent misses to one D1 call

---

## Sources

- Cloudflare Workers KV — developers.cloudflare.com/kv/
- Cloudflare D1 — developers.cloudflare.com/d1/
- "Read-Through Cache Pattern", Microsoft Azure Architecture Center —
  learn.microsoft.com/azure/architecture/patterns/cache-aside
- "Caching Patterns", AWS Prescriptive Guidance —
  docs.aws.amazon.com/prescriptive-guidance/latest/caching-strategies/read-through.html
