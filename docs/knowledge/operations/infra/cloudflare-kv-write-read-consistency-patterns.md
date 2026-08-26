# Cloudflare KV Write/Read Consistency and TTL Patterns

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker writes a value to KV and immediately reads it back — the old value is returned. Or a config
key is updated but edge PoPs continue serving stale data for 60+ seconds. Alternatively, a KV-backed
feature flag store is thrashing because expiry semantics are misunderstood, causing cache stampedes.
You need a clear mental model for KV's consistency guarantee and TTL behavior so you can design
reliably around them.

## Context

Cloudflare KV is an **eventually consistent**, globally distributed key-value store. Writes
propagate from the originating data center to all Cloudflare edge PoPs within roughly 60 seconds
under normal conditions. Reads are served from the nearest PoP's in-memory cache; after a cache
miss, values are fetched from the central store and cached locally for up to 60 seconds by default.

Implications:
- A Worker writing a KV key and then reading it in the same request may observe the old value if
  the read is served from a warm edge cache.
- `expirationTtl` sets how long a key lives in the KV store itself (minimum 60 seconds).
- `cacheTtl` (on `get` options) controls how long the edge cache holds the value — this is separate
  from the key's storage expiry.
- There is no compare-and-swap (CAS) or transactions; KV is write-wins with no conflict detection.

## Reading with Controlled Cache TTL

```typescript
// src/lib/kv.ts
export interface KVGetOptions {
  /** Edge cache TTL in seconds. Default: 60. Minimum: 60. */
  cacheTtl?: number;
  /** Force a cache bypass — costs one read unit but returns the freshest value. */
  bypassCache?: boolean;
}

/**
 * Typed KV getter with explicit cache control.
 * Pass cacheTtl=60 (minimum) for near-real-time reads.
 * Pass cacheTtl=3600 for stable config that changes rarely.
 */
export async function kvGet<T>(
  kv: KVNamespace,
  key: string,
  opts: KVGetOptions = {},
): Promise<T | null> {
  const cacheTtl = opts.bypassCache ? undefined : (opts.cacheTtl ?? 60);
  const raw = await kv.get(key, cacheTtl ? { cacheTtl } : undefined);
  if (raw === null) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return raw as unknown as T;
  }
}

/**
 * Write with TTL.  expirationTtl minimum is 60 seconds.
 * Returns the key so callers can build a local read-your-writes cache.
 */
export async function kvPut<T>(
  kv: KVNamespace,
  key: string,
  value: T,
  expirationTtl?: number,
): Promise<string> {
  const body = typeof value === "string" ? value : JSON.stringify(value);
  await kv.put(key, body, expirationTtl ? { expirationTtl } : undefined);
  return key;
}
```

## Read-Your-Writes: In-Request Local Cache

```typescript
// src/lib/kv-local-cache.ts
/**
 * Wraps KVNamespace with an in-memory Map that lives for one request.
 * Writes are reflected immediately within the same Worker invocation.
 * The underlying KV is still eventually consistent across requests/PoPs.
 */
export class LocalKVCache {
  private cache = new Map<string, string | null>();

  constructor(private kv: KVNamespace) {}

  async get(key: string): Promise<string | null> {
    if (this.cache.has(key)) return this.cache.get(key)!;
    const value = await this.kv.get(key, { cacheTtl: 60 });
    this.cache.set(key, value);
    return value;
  }

  async put(key: string, value: string, expirationTtl?: number): Promise<void> {
    await this.kv.put(key, value, expirationTtl ? { expirationTtl } : undefined);
    this.cache.set(key, value);  // reflect write immediately in-request
  }

  async delete(key: string): Promise<void> {
    await this.kv.delete(key);
    this.cache.set(key, null);
  }
}

// Usage in Worker fetch handler:
export default {
  async fetch(req: Request, env: { KV: KVNamespace }): Promise<Response> {
    const kv = new LocalKVCache(env.KV);
    await kv.put("session:abc", "user:123", 3600);
    const val = await kv.get("session:abc");  // returns "user:123" immediately
    return new Response(val);
  },
};
```

## Cache-Aside Pattern for Feature Flags

```typescript
// src/lib/feature-flags.ts
export type FeatureFlags = Record<string, boolean>;

const FLAGS_KEY     = "feature-flags:v1";
const CACHE_TTL_SEC = 120;  // accept up to 2 min staleness for flag reads

let localFlags: FeatureFlags | null = null;
let localFlagsFetchedAt = 0;

/**
 * Cache flags in module-level scope (survives within one isolate lifetime).
 * Falls back to KV if stale, and to hardcoded defaults on KV miss.
 */
export async function getFlags(kv: KVNamespace): Promise<FeatureFlags> {
  const now = Date.now() / 1000;
  if (localFlags && now - localFlagsFetchedAt < CACHE_TTL_SEC) {
    return localFlags;
  }

  const raw = await kv.get(FLAGS_KEY, { cacheTtl: 60 });
  if (raw) {
    try {
      localFlags = JSON.parse(raw) as FeatureFlags;
      localFlagsFetchedAt = now;
      return localFlags;
    } catch {
      // fall through to defaults
    }
  }

  // Hardcoded safe defaults when KV is unreachable
  return { newCheckout: false, betaDashboard: false };
}

export async function setFlags(kv: KVNamespace, flags: FeatureFlags): Promise<void> {
  await kv.put(FLAGS_KEY, JSON.stringify(flags), { expirationTtl: 86400 * 30 });
  // Invalidate local cache so next read picks up new flags within this isolate
  localFlags = null;
}
```

## TTL Expiry Patterns

```typescript
// src/lib/ttl-patterns.ts

/** Sliding window rate-limit counter using KV TTL */
export async function incrementRateLimit(
  kv: KVNamespace,
  key: string,
  windowSec: number,
  limit: number,
): Promise<{ allowed: boolean; count: number }> {
  const raw   = await kv.get(key);
  const count = raw ? parseInt(raw, 10) + 1 : 1;

  if (count === 1) {
    // First request in window — set TTL to window duration
    await kv.put(key, "1", { expirationTtl: Math.max(windowSec, 60) });
  } else {
    // Subsequent requests — KV has no atomic increment; race is acceptable for rate limiting
    await kv.put(key, String(count), { expirationTtl: Math.max(windowSec, 60) });
  }

  return { allowed: count <= limit, count };
}

/** Soft-expiry: store data with explicit expiry field, TTL is 2× for grace period */
export interface SoftExpiryEntry<T> {
  data: T;
  expiresAt: number;  // Unix seconds
}

export async function putWithSoftExpiry<T>(
  kv: KVNamespace,
  key: string,
  data: T,
  ttlSec: number,
): Promise<void> {
  const entry: SoftExpiryEntry<T> = {
    data,
    expiresAt: Math.floor(Date.now() / 1000) + ttlSec,
  };
  // KV TTL = 2× logical TTL; stale data is still readable during refresh
  await kv.put(key, JSON.stringify(entry), { expirationTtl: ttlSec * 2 });
}

export async function getWithSoftExpiry<T>(
  kv: KVNamespace,
  key: string,
): Promise<{ data: T; stale: boolean } | null> {
  const raw = await kv.get(key, { cacheTtl: 60 });
  if (!raw) return null;
  const entry = JSON.parse(raw) as SoftExpiryEntry<T>;
  const stale = Math.floor(Date.now() / 1000) > entry.expiresAt;
  return { data: entry.data, stale };
}
```

## Terraform KV Provisioning with Separate Namespaces per Purpose

```hcl
# terraform/cloudflare-kv.tf
locals {
  kv_namespaces = {
    sessions      = { title = "orchords-sessions-${var.environment}" }
    feature_flags = { title = "orchords-flags-${var.environment}" }
    rate_limits   = { title = "orchords-ratelimits-${var.environment}" }
    cache         = { title = "orchords-cache-${var.environment}" }
  }
}

resource "cloudflare_workers_kv_namespace" "namespaces" {
  for_each   = local.kv_namespaces
  account_id = var.cloudflare_account_id
  title      = each.value.title
}

output "kv_namespace_ids" {
  value = { for k, v in cloudflare_workers_kv_namespace.namespaces : k => v.id }
}
```

## Anti-patterns

- **Treating KV as a synchronous database**: KV's eventual consistency makes it unsuitable for
  inventory counts, financial ledgers, or any coordination requiring linearizability. Use Durable
  Objects or D1 for those.
- **Using expirationTtl < 60**: the API accepts the write but silently enforces a 60-second minimum.
  Designing logic that assumes shorter TTLs will behave unexpectedly.
- **Sharing one KV namespace for unrelated workloads**: key collisions and quota exhaustion are hard
  to diagnose; partition by purpose (sessions, flags, cache, rate-limits).
- **Polling KV in a tight loop**: each `kv.get` consumes a read unit; use module-level caching with
  a staleness budget instead of fetching on every sub-request.

## Gotchas

- `kv.list()` has a maximum of 1000 keys per call and does not guarantee ordering across pages;
  use `cursor` pagination for large namespaces.
- Deleting a key does not propagate instantly; edge caches may serve the deleted value for up to
  60 seconds even after `kv.delete()` returns.
- KV values have a 25 MiB size limit. Values over 1 MiB add noticeable latency; consider R2 for
  large blobs.
- Free plan Workers have 100,000 KV reads/day; paid plan Workers have 10 million reads/day. Rate
  limits apply per account, not per namespace.

## Verification

```bash
# Write a test key with 120-second TTL
npx wrangler kv key put "test:consistency" "hello-$(date +%s)" \
  --namespace-id "$KV_NS_ID" --ttl 120

# Read it back and observe propagation delay
for i in 1 2 3; do
  sleep 5
  npx wrangler kv key get "test:consistency" --namespace-id "$KV_NS_ID"
done

# List all keys in a namespace (first page)
npx wrangler kv key list --namespace-id "$KV_NS_ID" --limit 20 | jq '.[].name'

# Check expiry metadata
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$KV_NS_ID/metadata/test:consistency" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result'
```

## Related

- `cloudflare-workers-kv-namespace-terraform.md` — namespace provisioning via Terraform
- `cloudflare-durable-objects-stateful-edge.md` — strongly consistent alternative
- `cloudflare-workers-cost-optimization-scale.md` — read unit cost management
- `cache-invalidation-strategies.md` — general cache invalidation patterns
- `redis-eviction-policies.md` — comparison with Redis TTL semantics

## Sources

- https://developers.cloudflare.com/kv/concepts/how-kv-works/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/kv/platform/limits/
- https://developers.cloudflare.com/kv/reference/consistency/
