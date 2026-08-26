# Workers KV Eventual Consistency and Stale Data Handling

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A feature flag stored in KV is toggled off in the dashboard, but Workers across 10+ edge PoPs continue serving the old `true` value for up to 60 seconds.  A product price is updated, but some users see the stale price during the propagation window and complete purchases at the wrong amount.  A session token is revoked, but the revocation does not reach all edge nodes before the attacker re-uses it.  These are all expressions of the same root cause: KV is eventually consistent, not strongly consistent, and the default `cacheTtl` can extend staleness far beyond the 60-second global propagation floor.

## Context

**Workers KV** replicates writes to Cloudflare's global network asynchronously.  The write acknowledges from the closest datacenter; other PoPs see it "eventually," which Cloudflare defines as **up to 60 seconds** in normal conditions but which can stretch longer during edge datacenter outages or heavy write load.

Additionally, each PoP has its own **in-memory cache layer** layered on top of the replicated store.  When you call `kv.get(key, { cacheTtl: 3600 })`, you are instructing that PoP's cache to serve the locally cached value for up to 1 hour without re-checking the replicated store.  The total staleness window is therefore:

```
max_staleness = replication_lag + cacheTtl
```

For a value written with `cacheTtl: 3600`, you could see data that is over 60 minutes old.  Omitting `cacheTtl` (the default) falls back to a Cloudflare-controlled TTL, typically around 60 seconds.

Understanding the three layers is critical for reasoning about staleness:

| Layer | Controlled by | Staleness window |
|-------|--------------|-----------------|
| In-PoP memory cache | `cacheTtl` in `kv.get()` | 0 s – many hours |
| Replication across PoPs | Cloudflare internals | ~1 s – 60 s typical |
| Durable write acknowledge | Origin write | 0 s (synchronous) |

For features that need **strong consistency** (session revocation, inventory counters, rate limits), KV is the wrong primitive — use Durable Objects.  This article focuses on correctly designing KV-backed systems to **manage and tolerate** the staleness that is inherent to the technology.

## Section 1 — Staleness Budget and cacheTtl Sizing

Choose `cacheTtl` based on how long the application can tolerate stale data for each key category:

```javascript
// config/kv-ttls.js
export const KV_TTL = {
  // Feature flags: stakeholders accept ~60 s propagation lag
  featureFlag:   60,
  // Product copy / marketing: staleness OK for 5 min
  marketing:     300,
  // Price data: staleness unacceptable — omit cacheTtl to use CF default (~60 s)
  price:         undefined,
  // Session revocation: must never be cached; use Durable Objects instead
  sessionRevoke: null,  // sentinel: do not use KV for this
};
```

```javascript
// src/kv-client.js
export async function kvGet(kv, key, category) {
  const ttl = KV_TTL[category];

  if (ttl === null) {
    throw new Error(`Category "${category}" must not use KV — use Durable Objects`);
  }

  const options = ttl !== undefined ? { cacheTtl: ttl } : {};
  return kv.get(key, { type: 'json', ...options });
}
```

Using a typed wrapper prevents ad-hoc `cacheTtl` values from spreading through the codebase.  Code review can enforce that new KV reads go through `kvGet` with an explicit category.

## Section 2 — Version Stamping and Client-Side Staleness Detection

When the propagation window matters to end-users, embed a version stamp in the KV value and surface it to clients so they can detect when they received a stale response.

```javascript
// Write side — stamp every value with a write timestamp and version
async function kvPut(kv, key, payload) {
  const record = {
    v:         Date.now(),   // monotonic write timestamp (ms)
    schemaVer: 2,
    data:      payload,
  };
  await kv.put(key, JSON.stringify(record), {
    expirationTtl: 86400,   // hard expiry 24 h
  });
}

// Read side — return staleness metadata alongside the value
export async function kvGetVersioned(kv, key, maxAgeMs = 60_000) {
  const raw = await kv.get(key, { type: 'json' });
  if (!raw) return { value: null, stale: false, ageMs: null };

  const ageMs = Date.now() - raw.v;
  const stale = ageMs > maxAgeMs;

  return { value: raw.data, stale, ageMs };
}
```

```javascript
// In a Worker handler
export default {
  async fetch(request, env) {
    const { value, stale, ageMs } = await kvGetVersioned(
      env.CONFIG_KV, 'feature:checkout-v2', 90_000
    );

    const headers = new Headers({ 'Content-Type': 'application/json' });
    if (stale) {
      // Surface staleness to the observability layer
      headers.set('X-Cache-Age-Ms', String(ageMs));
      headers.set('X-Cache-Stale',  'true');
    }

    return new Response(JSON.stringify({ enabled: value?.enabled ?? false }), { headers });
  },
};
```

Clients (mobile apps, dashboards) can consume `X-Cache-Stale: true` and show a "refreshing…" indicator rather than acting on potentially stale data.

## Section 3 — Write-Through Invalidation with a Durable Object Coordinator

For data where staleness of even 60 seconds causes business harm (price, stock level), use a **Durable Object as a coordinator** that holds the authoritative value and writes to KV only as a fan-out cache, not as the source of truth.

```javascript
// src/PriceDO.js
export class PriceDO {
  constructor(state, env) {
    this.state = state;
    this.env   = env;
    this.state.blockConcurrencyWhile(async () => {
      this.price = await this.state.storage.get('price') ?? null;
    });
  }

  async fetch(request) {
    if (request.method === 'GET') {
      // Strongly consistent read from the DO itself
      return Response.json({ price: this.price });
    }

    if (request.method === 'PUT') {
      const { price } = await request.json();
      this.price = price;
      // Write to DO storage (strongly consistent)
      await this.state.storage.put('price', price);
      // Asynchronously fan out to KV for non-critical readers
      // ctx.waitUntil is not available in DO — schedule via alarm
      await this.state.storage.setAlarm(Date.now() + 0); // immediate alarm
      return Response.json({ ok: true });
    }
  }

  // Called when the alarm fires — write authoritative value to KV
  async alarm() {
    if (this.price !== null) {
      await this.env.PRICE_KV.put(
        'price:current',
        JSON.stringify({ price: this.price, ts: Date.now() }),
        { expirationTtl: 3600 }
      );
    }
  }
}
```

```javascript
// src/index.js — read path uses KV for cheap reads, DO for writes
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/price' && request.method === 'GET') {
      // Fast path: serve from KV (eventual, but acceptable for display)
      const cached = await env.PRICE_KV.get('price:current', { type: 'json', cacheTtl: 10 });
      if (cached) {
        return Response.json(cached);
      }
      // Fallback: go to the DO for the authoritative value
      const id  = env.PRICE_DO.idFromName('current-price');
      const obj = env.PRICE_DO.get(id);
      return obj.fetch(request);
    }

    if (url.pathname === '/price' && request.method === 'PUT') {
      // All writes go through the DO
      const id  = env.PRICE_DO.idFromName('current-price');
      const obj = env.PRICE_DO.get(id);
      return obj.fetch(request);
    }
  },
};
```

This pattern gives you O(1) read cost at edge scale (KV read = ~1 ms at cache hit) while keeping writes strongly consistent through the DO.

## Section 4 — KV Cache Warming at Worker Startup

Cold-start KV reads — the first read after a Worker instance spins up — incur a **network hop to the KV replicated store** because the in-process cache is empty.  For high-traffic Workers, this is amortized.  For Workers with low RPS or after a deploy, cold-start KV reads can add 10–80 ms.

Warm the cache proactively using `waitUntil` on the first request:

```javascript
// src/index.js
let cachedConfig = null;
let lastFetch    = 0;
const REFRESH_INTERVAL_MS = 30_000;

export default {
  async fetch(request, env, ctx) {
    const now = Date.now();

    // Serve stale from memory if within refresh interval
    if (cachedConfig && (now - lastFetch) < REFRESH_INTERVAL_MS) {
      return handleRequest(request, cachedConfig);
    }

    // Refresh in-process cache — use waitUntil so it doesn't block response
    const refreshPromise = env.CONFIG_KV
      .get('app-config', { type: 'json', cacheTtl: 30 })
      .then(cfg => {
        if (cfg) {
          cachedConfig = cfg;
          lastFetch    = Date.now();
        }
      });

    if (!cachedConfig) {
      // First request: must await — no cached value yet
      await refreshPromise;
    } else {
      // Subsequent: refresh async, serve existing cache immediately
      ctx.waitUntil(refreshPromise);
    }

    return handleRequest(request, cachedConfig);
  },
};

async function handleRequest(request, config) {
  return Response.json({ ok: true, config });
}
```

This pattern layers a short-lived **in-process (V8 isolate) cache** on top of KV's edge cache.  The two-layer cache means:
- P99 read latency ≈ 0 ms (in-process hit)
- Cache refresh every 30 s via background `waitUntil`
- No additional KV read per request for the 30-second window

## Anti-patterns

- **Using KV for session revocation tokens** — a revoked token in KV may still be considered valid at a PoP that has not received the update yet.  Use Durable Objects with a blocklist for immediate revocation.
- **Setting `cacheTtl` to 3600 on prices** — users will see an hour-old price even after you update it.  Choose `cacheTtl` based on the business tolerance for staleness, not on what reduces KV read costs.
- **Reading your own writes immediately** — a Worker that writes to KV and then reads the same key within 60 s may read the pre-write value.  If you need read-your-own-writes consistency, store the written value in the request context rather than re-reading from KV.
- **Ignoring KV list() in hot paths** — `kv.list()` performs a scan with no edge caching.  Never call it per-request; call it in a cron Worker and cache the result as a single key.
- **Storing mutable counters in KV** — KV has last-writer-wins semantics on concurrent writes.  Two Workers incrementing the same counter concurrently will lose one increment.  Use Durable Objects for counters.

## Gotchas

- Cloudflare's "up to 60 seconds" propagation guarantee assumes normal network conditions.  During incidents, propagation can take several minutes.  Design for worst-case, not best-case.
- `kv.getWithMetadata()` returns a separate `metadata` object alongside the value at no extra cost.  Use metadata for staleness hints (write timestamp, schema version) rather than embedding them in the value body, to keep the value parse clean.
- In Workers running with `compatibility_date` older than 2022-01-31, `cacheTtl` below 60 seconds is silently clamped to 60 seconds.  Verify your `compatibility_date` in `wrangler.toml` before relying on short TTLs.
- KV has a **1 MB value size limit**.  Attempting to `put` a value larger than 1 MB fails silently in some SDK versions.  Always check the return value of `kv.put()`.
- `kv.delete()` is also eventually consistent.  Deleting a key does not guarantee all PoPs stop serving it immediately.

## Verification

1. Write a value to KV, then immediately read it from 5 different edge PoPs using `fetch` requests routed via different `cf-worker-via` headers.  Measure how many PoPs return the new value vs the old within 10, 30, and 60 seconds.
2. Set `cacheTtl: 5` on a KV read.  Update the value.  Confirm the Worker returns the new value within 5–10 seconds at the edge node you are hitting, without redeploying the Worker.
3. Instrument `ageMs` from the version-stamped read pattern above and send it to Analytics Engine.  Plot the P99 staleness over 24 hours.  P99 > 120 s indicates a replication anomaly worth investigating.

## Related

- `kv-read-performance.md` — KV cold-start read latency patterns
- `workers-kv-read-performance-mobile-cold-start.md` — mobile-specific cold start
- `durable-objects-low-latency-stateful.md` — strongly consistent alternative to KV
- `edge-caching-patterns.md` — cache-control strategies at the CDN layer
- `cache-stampede-prevention.md` — preventing concurrent cold-start reads

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- KV consistency model: https://developers.cloudflare.com/kv/reference/how-kv-works/
- Workers KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Durable Objects vs KV comparison: https://developers.cloudflare.com/durable-objects/best-practices/
