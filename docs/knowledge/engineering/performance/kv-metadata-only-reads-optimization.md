# KV Metadata-Only Reads Performance Optimization
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers application checks whether a feature flag, rate-limit counter, or session token exists in
KV on every inbound request. The KV value bodies are often large (serialised JSON, JWT payloads
>2 KB) but the check only needs existence confirmation or a handful of scalar fields. Full-value
reads waste bandwidth on the Workers ↔ KV data plane and inflate KV read unit costs when values
are billed by size tier.

## Context

Cloudflare KV's `getWithMetadata()` API returns both the value and an arbitrary metadata object
(up to 1,024 bytes) that is set at write time. Crucially, **metadata is returned with near-zero
marginal cost** regardless of value size: the metadata blob travels with the key index, not with
the value body. When metadata alone is sufficient to answer a question, skipping the value read
avoids the value-fetch round-trip from the KV storage tier to the Worker.

As of 2026, KV reads are priced per-operation (not per-byte at the Workers tier), so the
optimisation matters most for latency, not billing. However, for values stored in cold regional
tiers, the value-fetch adds 10–50 ms of data-plane latency that metadata reads avoid entirely.

The tradeoff: metadata is capped at 1,024 bytes and must be set explicitly at write time. You
must design your write path to embed the fields workers will check read-only.

## Designing Metadata for Fast Reads

```typescript
// src/types.ts
export interface SessionMetadata {
  userId: string;
  role: 'admin' | 'user' | 'readonly';
  expiresAt: number;   // Unix timestamp (ms)
  version: number;     // for cache-busting logic
}

// Full value stored separately — large, not read on hot path
export interface SessionValue {
  permissions: string[];
  preferences: Record<string, unknown>;
  auditTrail: Array<{ action: string; ts: number }>;
}
```

```typescript
// src/session-write.ts
export async function writeSession(
  kv: KVNamespace,
  sessionId: string,
  meta: SessionMetadata,
  value: SessionValue,
  ttlSeconds: number,
): Promise<void> {
  await kv.put(
    `session:${sessionId}`,
    JSON.stringify(value),
    {
      expirationTtl: ttlSeconds,
      metadata: meta,   // max 1,024 bytes — keep scalar
    },
  );
}
```

## Metadata-Only Read on Hot Path

```typescript
// src/session-check.ts
export interface AuthResult {
  valid: boolean;
  userId?: string;
  role?: SessionMetadata['role'];
}

export async function checkSession(
  kv: KVNamespace,
  sessionId: string,
): Promise<AuthResult> {
  // getWithMetadata with type=null fetches ONLY metadata, not the value body
  const { metadata } = await kv.getWithMetadata<SessionMetadata>(
    `session:${sessionId}`,
    { type: 'json', cacheTtl: 60 },
  );

  if (!metadata) return { valid: false };

  if (metadata.expiresAt < Date.now()) {
    // Expired — do not touch value; metadata check is sufficient
    return { valid: false };
  }

  return {
    valid: true,
    userId: metadata.userId,
    role: metadata.role,
  };
}
```

> **Note**: `kv.getWithMetadata(key, { type: 'json' })` still fetches the value when the value is
> non-null. To skip the value body entirely use `type: 'stream'` and never consume the body, or
> structure the key so the value is stored under a separate key only read when needed (see below).

## Value-Deferred Pattern (True Metadata-Only)

When `getWithMetadata` always returns the value regardless of `type`, use a two-key pattern:

```typescript
// Write: index key (metadata) + data key (value)
export async function writeSessionV2(
  kv: KVNamespace,
  sessionId: string,
  meta: SessionMetadata,
  value: SessionValue,
  ttlSeconds: number,
): Promise<void> {
  // Metadata key — tiny value, only used for existence + metadata reads
  await kv.put(
    `session-idx:${sessionId}`,
    '',   // empty body — metadata carries all fast-path fields
    { expirationTtl: ttlSeconds, metadata: meta },
  );

  // Data key — large body, only fetched on demand
  await kv.put(
    `session-data:${sessionId}`,
    JSON.stringify(value),
    { expirationTtl: ttlSeconds },
  );
}

export async function getSessionFull(
  kv: KVNamespace,
  sessionId: string,
): Promise<{ meta: SessionMetadata; value: SessionValue } | null> {
  const [metaResult, dataResult] = await Promise.all([
    kv.getWithMetadata<SessionMetadata>(`session-idx:${sessionId}`, 'json'),
    kv.get<SessionValue>(`session-data:${sessionId}`, 'json'),
  ]);

  if (!metaResult.metadata || !dataResult) return null;
  return { meta: metaResult.metadata, value: dataResult };
}
```

## Batch Metadata Reads with list()

KV `list()` returns all keys and their metadata in a single operation, enabling bulk existence
checks without N individual reads:

```typescript
// src/feature-flags.ts
export interface FlagMeta {
  enabled: boolean;
  rollout: number;   // 0–100 percentage
  cohort?: string;
}

export async function loadAllFlags(
  kv: KVNamespace,
): Promise<Map<string, FlagMeta>> {
  const flags = new Map<string, FlagMeta>();
  let cursor: string | undefined;

  do {
    const page = await kv.list<FlagMeta>({
      prefix: 'flag:',
      cursor,
      limit: 1000,
    });

    for (const key of page.keys) {
      if (key.metadata) {
        const name = key.name.replace('flag:', '');
        flags.set(name, key.metadata);
      }
    }

    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  return flags;
}
```

Cache the result in a Worker-level `Map` (module-level variable) with a TTL check to avoid
repeated KV `list()` calls within the same isolate lifetime:

```typescript
// src/flag-cache.ts
let flagCache: Map<string, FlagMeta> | null = null;
let flagCacheTs = 0;
const FLAG_CACHE_TTL_MS = 30_000;

export async function getFlags(kv: KVNamespace): Promise<Map<string, FlagMeta>> {
  if (flagCache && Date.now() - flagCacheTs < FLAG_CACHE_TTL_MS) {
    return flagCache;
  }
  flagCache = await loadAllFlags(kv);
  flagCacheTs = Date.now();
  return flagCache;
}
```

## Anti-patterns

- **Storing large objects in metadata**: metadata is capped at 1,024 bytes. Exceeding it silently
  truncates or throws a 400 error. Keep metadata to scalar primitives.
- **Re-reading the full value to check expiry**: if `expiresAt` is in metadata, the value read is
  never needed for auth checks. Avoid the extra read.
- **Using `kv.list()` on hot per-request paths without isolate caching**: `list()` is slower than
  `get()`; cache the result in-memory for the isolate lifetime.
- **Forgetting to set metadata on update**: if you update the value via `kv.put()` without
  re-passing `metadata`, the metadata is reset to `null`. Always include metadata on every write.
- **Relying on metadata freshness for strong consistency**: KV is eventually consistent. Metadata
  can lag by up to 60 s in the global tier. Use for low-sensitivity fast paths only.

## Gotchas

- `kv.getWithMetadata()` with `cacheTtl` applies the Workers KV read cache (within the PoP). Set
  `cacheTtl: 60` on auth-check paths to cut global KV reads by 10–50× under steady load.
- Metadata from `list()` is returned per-key without a separate read; it is the cheapest way to
  bulk-check existence + scalar fields across many keys.
- Deleting a key via `kv.delete()` removes both the value and metadata atomically.
- KV `list()` is paginated at 1,000 keys per page. For namespaces with >10,000 keys, consider
  storing a manifest in a single large KV value instead of relying on `list()`.
- The metadata size limit is per-key, not per-namespace. A 1,024-byte limit is generous for
  scalar fields (userId, role, ts, version) but tight for arrays or embedded objects.

## Verification

```typescript
// Benchmark: metadata-only vs full-value read
async function benchmarkReads(kv: KVNamespace, sessionId: string) {
  const iterations = 100;

  // Warm-up
  await kv.getWithMetadata(`session-idx:${sessionId}`, 'json');

  const metaStart = Date.now();
  for (let i = 0; i < iterations; i++) {
    await kv.getWithMetadata<SessionMetadata>(`session-idx:${sessionId}`, 'json');
  }
  const metaAvg = (Date.now() - metaStart) / iterations;

  const fullStart = Date.now();
  for (let i = 0; i < iterations; i++) {
    await kv.get<SessionValue>(`session-data:${sessionId}`, 'json');
  }
  const fullAvg = (Date.now() - fullStart) / iterations;

  return { metaAvgMs: metaAvg, fullAvgMs: fullAvg, savedMs: fullAvg - metaAvg };
}
```

Emit the result to Analytics Engine. In production, metadata reads should be 20–40% faster than
full-value reads for values >1 KB under cold conditions.

## Related

- `kv-bulk-get-batching.md`
- `kv-read-performance.md`
- `workers-kv-read-performance-mobile-cold-start.md`
- `kv-eventual-consistency-stale-data.md`
- `workers-middleware-chain-performance.md`

## Sources

- Cloudflare Docs: KV API — getWithMetadata — https://developers.cloudflare.com/kv/api/read-key-value-pairs/#getWithMetadata
- Cloudflare Docs: KV Metadata — https://developers.cloudflare.com/kv/api/write-key-value-pairs/#metadata
- Cloudflare Docs: KV list() — https://developers.cloudflare.com/kv/api/list-keys/
- Cloudflare Docs: KV Limits — https://developers.cloudflare.com/kv/platform/limits/
