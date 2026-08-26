# Eventual Consistency Patterns: Cloudflare KV Replication Lag and Compensating Strategies

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You write a feature flag to Cloudflare KV, then immediately serve traffic — some edge nodes still read the old value for up to 60 seconds. You update a user's subscription tier; for a brief window the user sees stale permissions. You delete a revoked API key from KV; the key remains valid on some PoPs. These are symptoms of KV's eventual consistency model colliding with correctness requirements that implicitly assumed strong consistency.

---

## Context

Cloudflare KV is a globally replicated key-value store. Writes go to a single authoritative region (currently in the US or EU depending on account), then propagate outward to ~300 PoPs via an async replication pipeline. The documented propagation SLA is **up to 60 seconds** to all PoPs after a write returns 200. Reads from any PoP are served from that PoP's local cache, so:

- A write made in Frankfurt may be invisible to a reader in Tokyo for up to a minute.
- Reads with `cacheTtl: 0` bypass the in-PoP read cache but still see the most recent locally replicated value — they do not force a read from the authoritative region.
- There is no linearizable read option; KV is explicitly BASE, not ACID.

Understanding this constraint is the prerequisite for every compensating strategy below.

---

## Section 1: Measuring Actual Replication Lag

Before choosing a strategy, measure your real-world lag distribution. Write a canary value with a timestamp, then read it back from a Scheduled Worker that runs globally:

```typescript
// lag-probe.ts — runs as a Scheduled Worker in multiple regions
interface Env {
  PROBE_KV: KVNamespace;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const key = 'lag-probe';
    const written = await env.PROBE_KV.get<{ ts: number }>(key, 'json');
    if (!written) return;

    const nowMs  = Date.now();
    const lagMs  = nowMs - written.ts;
    const coloId = (globalThis as any).__CF?.colo ?? 'unknown';

    // Emit to Analytics Engine for percentile analysis
    await fetch('https://api.example.com/internal/lag-metric', {
      method: 'POST',
      body: JSON.stringify({ colo: coloId, lagMs, ts: nowMs }),
    });
  },
};

// Writer Worker — called once per minute from a Durable Object alarm
export async function writeProbe(env: Env): Promise<void> {
  await env.PROBE_KV.put('lag-probe', JSON.stringify({ ts: Date.now() }));
}
```

Collect data for a week. Most production accounts see p50 < 5 s and p99 < 45 s, but spikes to 60 s occur. Design for the p99.

---

## Section 2: Version-Fencing — Reject Stale Reads

Attach a monotonic version number to every KV value. On read, compare the version against the minimum expected version from the initiating context:

```typescript
interface VersionedValue<T> {
  version: number;
  data: T;
  writtenAt: number;
}

async function kvGetVersioned<T>(
  kv: KVNamespace,
  key: string,
  minVersion: number
): Promise<{ value: T; version: number } | { stale: true; currentVersion: number }> {
  const raw = await kv.get<VersionedValue<T>>(key, 'json');
  if (!raw) throw new Error(`Key ${key} not found`);

  if (raw.version < minVersion) {
    return { stale: true, currentVersion: raw.version };
  }
  return { value: raw.data, version: raw.version };
}

// Usage: after writing version 42, pass minVersion=42 in the immediate next request
async function handleRequest(request: Request, env: Env): Promise<Response> {
  const { key, minVersion } = await request.json<{ key: string; minVersion: number }>();
  const result = await kvGetVersioned(env.CONFIG_KV, key, minVersion);

  if ('stale' in result) {
    // Return 202 Accepted — client should retry after propagation delay
    return Response.json(
      { status: 'propagating', currentVersion: result.currentVersion, minVersion },
      { status: 202 }
    );
  }
  return Response.json(result);
}
```

The version number travels with the write context (e.g., in a session cookie or response header) and acts as a fence: any PoP that has not yet replicated to the required version gracefully signals the caller to retry.

---

## Section 3: Read-Your-Writes with Durable Objects

The canonical pattern for read-your-writes consistency on Cloudflare is to route post-write reads through a Durable Object whose storage is strongly consistent:

```typescript
// ConsistentConfigDO.ts
import { DurableObject } from 'cloudflare:workers';

interface Env {
  GLOBAL_KV: KVNamespace;
  CONSISTENT_CONFIG: DurableObjectNamespace;
}

export class ConsistentConfigDO extends DurableObject {
  // DO storage is consistent within a single DO instance
  async put(key: string, value: unknown): Promise<void> {
    await this.ctx.storage.put(key, JSON.stringify(value));
    // Async propagation to KV for eventual global availability
    await (this.env as Env).GLOBAL_KV.put(key, JSON.stringify(value));
  }

  async get(key: string): Promise<unknown> {
    const local = await this.ctx.storage.get<string>(key);
    if (local !== undefined) return JSON.parse(local);
    // Fallback to KV once lag has resolved
    const kv = await (this.env as Env).GLOBAL_KV.get(key);
    return kv ? JSON.parse(kv) : null;
  }
}

// Worker: route writes and immediate reads to DO, background reads to KV
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const isMutation = request.method === 'PUT' || request.method === 'DELETE';

    if (isMutation || url.searchParams.has('consistent')) {
      const stub = env.CONSISTENT_CONFIG.get(env.CONSISTENT_CONFIG.idFromName('global'));
      return stub.fetch(request);
    }

    // Eventual read from KV — fast, globally distributed
    const key   = url.searchParams.get('key') ?? '';
    const value = await env.GLOBAL_KV.get(key);
    return Response.json({ key, value });
  },
};
```

Trade-off: the DO is a single region hot-path. Use this pattern only for the post-write window; switch to direct KV reads once the caller's session has advanced past the write.

---

## Section 4: Stale-While-Revalidate with Local Cache

For high-read, low-write config data (feature flags, rate-limit thresholds), implement a stale-while-revalidate pattern in the Worker itself to mask propagation lag from clients:

```typescript
// local-cache.ts — in-memory cache scoped to a single Worker isolate lifetime
const localCache = new Map<string, { value: string; expiresAt: number }>();

async function getWithSWR(kv: KVNamespace, key: string, ttlMs = 5000): Promise<string | null> {
  const cached = localCache.get(key);
  const now    = Date.now();

  if (cached && cached.expiresAt > now) {
    return cached.value;
  }

  if (cached && cached.expiresAt <= now) {
    // Serve stale immediately, revalidate in background
    const revalidate = kv.get(key).then(fresh => {
      if (fresh !== null) {
        localCache.set(key, { value: fresh, expiresAt: now + ttlMs });
      }
    });
    // ctx.waitUntil would be ideal here — pass it from the caller
    void revalidate;
    return cached.value;
  }

  // Cold path
  const value = await kv.get(key);
  if (value !== null) {
    localCache.set(key, { value, expiresAt: now + ttlMs });
  }
  return value;
}
```

Because Worker isolates are recycled, this cache is warm only within a single request burst on a given PoP. It is most effective for flags read thousands of times per second on a busy PoP, where the lag window is tolerable.

---

## Section 5: Compensating Writes — Idempotent Re-apply

When KV is used for access control (API key revocation, permission grants), the risk of stale reads is a security concern. The compensating strategy is to check a secondary authoritative source for the critical window:

```typescript
// key-auth-middleware.ts
interface Env {
  API_KEYS_KV: KVNamespace;
  AUTH_DO: DurableObjectNamespace;      // authoritative revocation list
}

async function isKeyRevoked(key: string, env: Env): Promise<boolean> {
  // Primary fast path: KV (eventual)
  const kvEntry = await env.API_KEYS_KV.get(`revoked:${key}`);
  if (kvEntry !== null) return true;

  // Secondary authoritative path: only for keys revoked in last 120 s
  const doStub = env.AUTH_DO.get(env.AUTH_DO.idFromName('revocations'));
  const resp   = await doStub.fetch(
    new Request(`https://do/check?key=<redacted-secret>
  );
  const { revoked } = await resp.json<{ revoked: boolean }>();
  return revoked;
}
```

The DO acts as a 120-second cache of recent revocations. After 120 s, KV has propagated and the DO check becomes unnecessary. The DO's in-memory map is rebuilt from KV on cold start:

```typescript
// AuthDO.ts — stores revocations for the KV propagation window only
export class AuthDO extends DurableObject {
  private revoked = new Map<string, number>(); // key → revokedAt ms

  async fetch(request: Request): Promise<Response> {
    await this.evictExpired();
    const url = new URL(request.url);

    if (url.pathname === '/revoke') {
      const { key } = await request.json<{ key: string }>();
      this.revoked.set(key, Date.now());
      return new Response('ok');
    }

    if (url.pathname === '/check') {
      const key = url.searchParams.get('key') ?? '';
      return Response.json({ revoked: this.revoked.has(key) });
    }

    return new Response('Not Found', { status: 404 });
  }

  private async evictExpired(): Promise<void> {
    const cutoff = Date.now() - 120_000;
    for (const [key, ts] of this.revoked) {
      if (ts < cutoff) this.revoked.delete(key);
    }
  }
}
```

---

## Section 6: Observability — Detect Stale Reads in Production

Instrument KV reads to surface stale-read incidents:

```typescript
async function trackedKVGet(
  kv: KVNamespace,
  key: string,
  expectedVersion: number | null,
  ae: AnalyticsEngineDataset
): Promise<string | null> {
  const raw = await kv.get<{ version: number; data: string }>(key, 'json');

  ae.writeDataPoint({
    blobs: [key],
    doubles: [
      raw?.version ?? -1,
      expectedVersion ?? -1,
      raw && expectedVersion && raw.version < expectedVersion ? 1 : 0, // stale flag
    ],
    timestamps: [new Date()],
  });

  return raw?.data ?? null;
}
```

Query the Analytics Engine dataset with Workers Analytics Engine GraphQL API to get per-key stale-read rates over time and tune compensating strategy thresholds accordingly.

---

## Anti-patterns

- **Using KV for strongly consistent counters**: KV has no atomic increment. Use Durable Objects or D1 for counters requiring consistency.
- **Storing session tokens in KV and relying on instant revocation**: The propagation window means a revoked token stays valid on some PoPs. Use the DO-backed revocation window above.
- **Setting `cacheTtl: 0` expecting linearizable reads**: `cacheTtl: 0` bypasses the per-PoP cache but does not route to the authoritative region.
- **Polling KV after a write with tight retry loops**: Polling at 100 ms intervals for up to 60 s burns request budget. Use exponential back-off (1 s → 2 s → 4 s…) capped at 60 s.
- **Writing high-cardinality data to KV**: KV is optimised for low-write, high-read patterns. Metadata-scale data (per-user records mutated frequently) belongs in D1 or Durable Objects.

---

## Gotchas

- **KV list operations reflect eventual state**: `kv.list()` returns keys as they exist in the PoP's replica — deleted keys may still appear for up to 60 s after deletion.
- **Metadata vs value propagation**: KV key metadata and value propagate together in a single replication event. They are never partially applied.
- **Different TTL behaviour for missing keys**: A `null` return from `kv.get()` on a key that was just deleted can be cached at the PoP for up to the key's previously configured `expirationTtl`. Explicitly set `expirationTtl` conservatively for revocable keys.
- **Workers KV limits**: 1,000 writes/second per account across all keys. Write bursts (e.g., bulk feature flag updates) should be throttled or batched.

---

## Verification

```bash
# Write a versioned value
wrangler kv:key put --binding=CONFIG_KV "feature:new-checkout" '{"version":42,"data":true}'

# Immediately read from multiple PoPs via a global probe Worker
for region in ams cdg nrt sfo; do
  curl "https://probe.example.com/kv?key=<redacted-secret>&minVersion=42&region=$region"
done
# 202 responses indicate PoPs still catching up; retry until all return 200

# Measure propagation time (seconds until all PoPs return 200)
# Use Analytics Engine query to chart p50/p95/p99 over a week of probe data
```

---

## Related

- `eventual-consistency-ux-design.md` — UX patterns for masking lag from users
- `consistency-patterns.md` — CAP theorem and consistency level trade-offs
- `feature-flag-cloudflare-workers-kv.md` — feature flag architecture
- `circuit-breaker-kv-state-machine.md` — using DO as circuit breaker state
- `caching-topology-cloudflare-native.md` — KV, Cache API, and R2 cache layers

---

## Sources

- Cloudflare KV consistency model: https://developers.cloudflare.com/kv/reference/consistency/
- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Durable Objects storage: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Werner Vogels, "Eventually Consistent": https://doi.org/10.1145/1435417.1435432
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
