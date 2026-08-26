# Stale-While-Revalidate: Background KV Refresh with waitUntil

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your KV cache TTL expires, and suddenly thousands of requests all hit D1
simultaneously — the cache stampede. Alternatively you lower the TTL to reduce
staleness but the burst traffic on expiry is unacceptable. You need responses
to remain fast even as data grows stale, while a background job silently refreshes
the cache for the *next* request without the caller waiting.

The stale-while-revalidate (SWR) pattern solves this: serve the stale cached value
immediately, then asynchronously refresh KV in `ctx.waitUntil()` — outside the
response latency path.

---

## Context

Standard KV TTL creates a hard cliff: the entry expires, all concurrent misses
race to D1, one wins and repopulates, the rest either wait or also hit D1. SWR
softens the cliff with a two-window strategy:

```
Time ──────────────────────────────────────────────────────►
     │◄──── fresh window ────►│◄──── stale window ────►│ expired
     │   serve from KV,       │  serve stale KV,        │ force miss,
     │   no revalidation      │  trigger async refresh  │ must hit D1
```

On Cloudflare Workers the async work runs in `ctx.waitUntil()`, which keeps the
Worker alive after `response` is returned. The caller receives a stale-but-fast
response; D1 is queried once in the background; KV is updated before the *next*
request's stale window opens.

---

## Section 1 — SWR Metadata Envelope

KV stores a JSON envelope that carries both the value and the window timestamps:

```typescript
// lib/swr-cache.ts

interface SWREnvelope<T> {
  value:         T;
  freshUntil:    number;   // epoch ms — serve without revalidation before this
  staleUntil:    number;   // epoch ms — serve stale and revalidate before this
}

export interface SWROptions {
  freshSeconds:  number;   // seconds data is considered fresh (no revalidation)
  staleSeconds:  number;   // additional seconds to serve stale while refreshing
  namespace:     string;
}

export class SWRCache<T> {
  constructor(
    private readonly kv:      KVNamespace,
    private readonly loader:  (key: string) => Promise<T | null>,
    private readonly options: SWROptions,
  ) {}

  async get(key: string, ctx: ExecutionContext): Promise<T | null> {
    const kvKey  = this.key(key);
    const now    = Date.now();
    const raw    = await this.kv.get<SWREnvelope<T>>(kvKey, 'json');

    if (raw !== null) {
      if (now < raw.freshUntil) {
        // Fresh — serve directly, no revalidation
        return raw.value;
      }

      if (now < raw.staleUntil) {
        // Stale but within the revalidation window — serve stale, refresh in background
        ctx.waitUntil(this.revalidate(key, kvKey));
        return raw.value;
      }

      // Beyond stale window — synchronous refresh required
    }

    // Cache miss or hard expiry — must load synchronously
    return this.loadAndStore(key, kvKey);
  }

  async invalidate(key: string): Promise<void> {
    await this.kv.delete(this.key(key));
  }

  private async revalidate(key: string, kvKey: string): Promise<void> {
    try {
      await this.loadAndStore(key, kvKey);
    } catch (err) {
      console.error(JSON.stringify({ event: 'swr_revalidation_error', key, error: String(err) }));
    }
  }

  private async loadAndStore(key: string, kvKey: string): Promise<T | null> {
    const value = await this.loader(key);
    if (value === null) return null;

    const now = Date.now();
    const envelope: SWREnvelope<T> = {
      value,
      freshUntil: now + this.options.freshSeconds  * 1000,
      staleUntil: now + (this.options.freshSeconds + this.options.staleSeconds) * 1000,
    };

    // KV TTL must cover the entire stale window so the envelope survives for background reads
    const totalTtlSeconds = this.options.freshSeconds + this.options.staleSeconds + 60;

    await this.kv.put(kvKey, JSON.stringify(envelope), {
      expirationTtl: totalTtlSeconds,
    });

    return value;
  }

  private key(k: string): string {
    return `${this.options.namespace}:${k}`;
  }
}
```

---

## Section 2 — Usage in a Worker Handler

```typescript
// worker.ts
import { SWRCache } from './lib/swr-cache';

export interface Env {
  KV_CACHE: KVNamespace;
  DB:       D1Database;
}

interface Config {
  featureFlags: Record<string, boolean>;
  thresholds:   Record<string, number>;
  updatedAt:    string;
}

function makeConfigCache(env: Env): SWRCache<Config> {
  return new SWRCache<Config>(
    env.KV_CACHE,
    async (_key) => {
      const row = await env.DB
        .prepare('SELECT feature_flags, thresholds, updated_at FROM app_config WHERE id = 1')
        .first<{ feature_flags: string; thresholds: string; updated_at: string }>();

      if (!row) return null;

      return {
        featureFlags: JSON.parse(row.feature_flags),
        thresholds:   JSON.parse(row.thresholds),
        updatedAt:    row.updated_at,
      };
    },
    {
      freshSeconds:  30,    // serve from KV for 30 s without revalidation
      staleSeconds:  120,   // serve stale for up to 2 more minutes while refreshing
      namespace:     'config',
    },
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache  = makeConfigCache(env);
    const config = await cache.get('global', ctx);   // ctx passed for waitUntil

    if (!config) {
      return Response.json({ error: 'Config unavailable' }, { status: 503 });
    }

    return Response.json(config);
  },
};
```

---

## Section 3 — Window Tuning Guide

| Use-case                     | freshSeconds | staleSeconds | Rationale                                     |
|------------------------------|:------------:|:------------:|-----------------------------------------------|
| Feature flags                | 30           | 120          | Near-real-time but background refresh is fine |
| Exchange rates               | 60           | 300          | Stale rate acceptable for seconds, not minutes |
| Product catalogue            | 300          | 900          | Stable; stale window hides peak traffic       |
| User subscription tier       | 60           | 60           | Short stale window for billing sensitivity    |
| App-wide config              | 30           | 180          | Control-plane changes should propagate fast   |

The KV TTL stored on the envelope must be `freshSeconds + staleSeconds + grace`
(the `+60` above). If the KV TTL is shorter than the stale window, the envelope
disappears before the background refresh has a chance to update it.

---

## Section 4 — Observability: Logging Cache State

```typescript
// Extend get() to log hit/stale/miss for dashboard visibility
async getWithLog(key: string, ctx: ExecutionContext): Promise<{ value: T | null; state: 'fresh' | 'stale' | 'miss' }> {
  const kvKey = this.key(key);
  const now   = Date.now();
  const raw   = await this.kv.get<SWREnvelope<T>>(kvKey, 'json');

  if (raw !== null) {
    if (now < raw.freshUntil)  return { value: raw.value, state: 'fresh' };
    if (now < raw.staleUntil) {
      ctx.waitUntil(this.revalidate(key, kvKey));
      return { value: raw.value, state: 'stale' };
    }
  }

  const value = await this.loadAndStore(key, kvKey);
  return { value, state: 'miss' };
}
```

Emit `state` into structured logs and track the ratio of `stale` to `miss` hits.
A healthy SWR deployment has few `miss` events — most requests land in `fresh` or
`stale`. A spike in `miss` means the stale window is too short for the traffic rate.

---

## Anti-patterns

**Setting `staleSeconds` to 0** — this degenerates to a standard TTL cache with
no background refresh. You lose the stampede protection the SWR pattern provides.

**Not passing `ctx` to `get()`** — if `waitUntil` is never called, the Worker
runtime terminates background work mid-flight after the response is sent. Always
thread `ExecutionContext` to the cache call site.

**Using SWR for security-sensitive data** — serving a stale auth token validation
result or a revoked permission set is a security regression. SWR is for read-heavy,
eventually-consistent data. Use synchronous reads for auth.

**Storing the envelope with a TTL shorter than `freshSeconds + staleSeconds`** —
the envelope expires before the stale window closes; subsequent requests see a hard
miss instead of stale service and must hit D1 synchronously. Add a grace margin.

---

## Gotchas

- **`ctx.waitUntil()` failures are silent.** Errors in the background revalidation
  do not propagate to the caller. Wrap revalidation in try/catch and log explicitly.
- **Multiple concurrent stale readers each trigger `waitUntil()`** — you get
  multiple simultaneous D1 reads during the revalidation window. Use a Durable
  Object lock or add `request-coalescing-cache-stampede.md` on top to deduplicate.
- **KV `expirationTtl` minimum is 60 seconds.** If `freshSeconds + staleSeconds < 60`,
  the put call throws. Enforce a minimum total TTL of 60 s.
- **The `staleUntil` timestamp is set at write time, not at read time.** Each write
  resets both windows. A hot key that is revalidated frequently will always appear
  fresh; a cold key that is rarely revalidated may skip past its stale window on
  the next read, forcing a synchronous miss.

---

## Verification

```bash
# 1. Cold read — synchronous D1 call, KV populated
curl https://api.example.com/config | jq .updatedAt

# 2. Inspect the SWR envelope
wrangler kv:key get --namespace-id=<NS> "config:global"
# Look for freshUntil and staleUntil timestamps

# 3. Wait past freshSeconds (e.g., 35 s), re-request — should return stale, trigger background refresh
sleep 35
curl https://api.example.com/config | jq .updatedAt   # same value, stale

# 4. Immediately re-request — background refresh completed; should now be fresh again
curl https://api.example.com/config | jq .updatedAt
```

---

## Related

- `read-through-cache-workers-kv-d1.md` — transparent read-through without SWR
- `cache-aside-kv-d1-fallback.md` — caller-driven cache population
- `request-coalescing-cache-stampede.md` — deduplicate simultaneous D1 calls on miss
- `multi-layer-cache-workers-cache-api-kv-d1.md` — add Cache API as L1 before KV
- `graceful-degradation.md` — serving degraded data during D1 outage

---

## Sources

- RFC 5861 — HTTP Cache-Control Extensions for Stale Content (stale-while-revalidate directive)
- Cloudflare Workers ExecutionContext.waitUntil — developers.cloudflare.com/workers/runtime-apis/context/
- Cloudflare Workers KV — developers.cloudflare.com/kv/
- "Stale-While-Revalidate", web.dev — web.dev/stale-while-revalidate/
