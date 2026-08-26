# KV Locale Key Sharding for High-Traffic Multilingual Apps

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A multilingual Cloudflare Workers application serving translations from KV runs into
hot-key throttling at scale. A single key like `translations:en` is read on every
request and hits KV's per-key read rate limits (~1 000 reads/s/key on the free tier,
~unlimited on paid but still subject to edge-cache TTL contention). You need a sharding
strategy that spreads reads across multiple KV keys while remaining transparent to the
application layer.

## Context

Cloudflare KV is an eventually-consistent, globally-distributed store. Individual keys
are cached at the edge per PoP with a configurable TTL (minimum 60 s). Under extreme
read load a single hot key forces the edge node to re-validate more often than the TTL
suggests, and write bursts propagate to all PoPs within ~60 s. Sharding locale
translation bundles across N sibling keys reduces per-key pressure and allows
namespace-isolated cache invalidation.

Applicable stack: Workers, KV namespaces, D1 (version manifest), optional R2 (large
bundles).

---

## 1. Sharding Strategy Overview

Translation keys are split into **namespace shards** (one KV key per logical group):

```
translations:{locale}:{namespace}:{shard_index}
```

Example for `en` locale, `ui` namespace, 4 shards:
```
translations:en:ui:0
translations:en:ui:1
translations:en:ui:2
translations:en:ui:3
```

Each shard contains a flat JSON object of ~250-500 translation keys. The shard index for
a given translation key is determined by a stable hash:

```typescript
// src/lib/kv-sharding.ts

export function shardIndex(key: string, shardCount: number): number {
  // FNV-1a 32-bit — fast, no crypto overhead, deterministic
  let hash = 2166136261;
  for (let i = 0; i < key.length; i++) {
    hash ^= key.charCodeAt(i);
    hash = (hash * 16777619) >>> 0;
  }
  return hash % shardCount;
}
```

---

## 2. Writing Sharded Bundles at Build Time

The shard-write script runs during CI after translation files are updated.

```typescript
// scripts/publish-translations.ts
import type { KVNamespace } from '@cloudflare/workers-types';

interface ShardConfig {
  locale: string;
  namespace: string;
  shardCount: number;
  ttl: number; // seconds
}

async function publishShards(
  kv: KVNamespace,
  translations: Record<string, string>,
  config: ShardConfig,
): Promise<void> {
  const { locale, namespace, shardCount, ttl } = config;

  // Initialise empty shard buckets
  const shards: Record<string, Record<string, string>> = {};
  for (let i = 0; i < shardCount; i++) {
    shards[`${i}`] = {};
  }

  // Distribute keys deterministically
  for (const [msgKey, value] of Object.entries(translations)) {
    const idx = shardIndex(msgKey, shardCount);
    shards[`${idx}`][msgKey] = value;
  }

  // Write each shard
  const writes = Object.entries(shards).map(([idx, payload]) =>
    kv.put(
      `translations:${locale}:${namespace}:${idx}`,
      JSON.stringify(payload),
      { expirationTtl: ttl },
    ),
  );

  await Promise.all(writes);
}
```

---

## 3. Reading with Lazy Shard Hydration

On the Worker, load only the shard that contains the requested key. Cache the parsed
shard in the Worker's in-memory module scope (lives for the lifetime of the isolate —
typically minutes).

```typescript
// src/lib/t.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { shardIndex } from './kv-sharding';

const SHARD_COUNT = 4;
const kvCache = new Map<string, Record<string, string>>();

async function getShard(
  kv: KVNamespace,
  locale: string,
  ns: string,
  idx: number,
): Promise<Record<string, string>> {
  const cacheKey = `${locale}:${ns}:${idx}`;
  if (kvCache.has(cacheKey)) return kvCache.get(cacheKey)!;

  const raw = await kv.get(`translations:${locale}:${ns}:${idx}`);
  const parsed = raw ? (JSON.parse(raw) as Record<string, string>) : {};
  kvCache.set(cacheKey, parsed);
  return parsed;
}

export async function t(
  kv: KVNamespace,
  locale: string,
  ns: string,
  key: string,
  fallbackLocale = 'en',
): Promise<string> {
  const idx = shardIndex(key, SHARD_COUNT);
  let shard = await getShard(kv, locale, ns, idx);
  let value = shard[key];

  if (!value && locale !== fallbackLocale) {
    shard = await getShard(kv, fallbackLocale, ns, idx);
    value = shard[key];
  }

  return value ?? key; // return key as last-resort
}
```

---

## 4. Cache Invalidation via Version Manifest in D1

When a translation bundle is republished, increment a version number in D1 and let
Workers compare it against their in-memory copy to decide whether to clear `kvCache`.

```typescript
// src/lib/version-check.ts
import type { D1Database } from '@cloudflare/workers-types';

let cachedVersion: number | null = null;

export async function checkAndInvalidate(
  db: D1Database,
  locale: string,
  ns: string,
): Promise<boolean> {
  const row = await db
    .prepare(
      'SELECT version FROM translation_versions WHERE locale = ? AND namespace = ? LIMIT 1',
    )
    .bind(locale, ns)
    .first<{ version: number }>();

  const remoteVersion = row?.version ?? 0;
  if (cachedVersion !== remoteVersion) {
    cachedVersion = remoteVersion;
    // Evict all shard cache entries for this locale+namespace
    for (const key of kvCache.keys()) {
      if (key.startsWith(`${locale}:${ns}:`)) kvCache.delete(key);
    }
    return true; // invalidated
  }
  return false;
}
```

D1 schema:

```sql
CREATE TABLE translation_versions (
  locale    TEXT NOT NULL,
  namespace TEXT NOT NULL,
  version   INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (locale, namespace)
);
```

---

## 5. Shard-Aware Prefetching for Critical Paths

For SSR pages that render above-the-fold content, prefetch all shards in parallel rather
than waiting for each lookup to trigger a shard load:

```typescript
// src/middleware/prefetch-shards.ts
export async function prefetchAllShards(
  kv: KVNamespace,
  locale: string,
  ns: string,
): Promise<void> {
  await Promise.all(
    Array.from({ length: SHARD_COUNT }, (_, i) => getShard(kv, locale, ns, i)),
  );
}
```

Call this once per request in the middleware layer before rendering begins.

---

## 6. Monitoring Shard Distribution Balance

Log shard sizes at build time to detect skewed distributions that could re-introduce hot
keys:

```typescript
// scripts/check-shard-balance.ts
export function reportShardBalance(
  translations: Record<string, string>,
  shardCount: number,
): void {
  const counts = new Array<number>(shardCount).fill(0);
  for (const key of Object.keys(translations)) {
    counts[shardIndex(key, shardCount)]++;
  }
  const avg = counts.reduce((a, b) => a + b, 0) / shardCount;
  const maxDeviation = Math.max(...counts.map((c) => Math.abs(c - avg)));
  console.log('Shard sizes:', counts);
  console.log(`Avg: ${avg.toFixed(1)}, max deviation: ${maxDeviation}`);
  if (maxDeviation / avg > 0.25) {
    console.warn('WARNING: shard imbalance >25% — consider increasing shard count');
  }
}
```

---

## Anti-patterns

- **Single monolithic KV key per locale** — defeats the purpose of edge caching and
  creates a hot-key bottleneck at scale.
- **Sharding by first letter of key** — produces wildly uneven shards (many keys start
  with 'a', 'b'; few with 'x', 'z').
- **Too many shards** — each shard is a separate KV read; >16 shards means potentially
  16 parallel KV fetches on cold start. 4–8 shards is the sweet spot for most apps.
- **Clearing the entire in-memory cache on any KV write** — triggers a thundering-herd
  of KV reads. Scope cache invalidation to the changed locale+namespace.
- **Storing full ICU MessageFormat patterns per key** — inflates shard payload. Store
  pre-compiled string templates and resolve plurals/gender in the Worker.

## Gotchas

- KV `get()` returns `null` for missing keys, not an empty string. Always handle `null`
  explicitly before `JSON.parse`.
- The module-scoped `kvCache` is **per isolate**, not shared across Workers instances.
  Different PoPs will have independent caches; version check via D1 is the only reliable
  cross-PoP invalidation mechanism.
- KV `expirationTtl` must be ≥60 seconds. Setting a lower TTL causes a 400 error at
  write time.
- FNV-1a is not cryptographically secure. Do not use shard assignment to control access
  permissions.
- `kvCache` grows unbounded in long-lived isolates. Bound it with an LRU if you serve
  hundreds of locale/namespace combinations.

## Verification

```typescript
// test/kv-sharding.test.ts
import { shardIndex } from '../src/lib/kv-sharding';

describe('shardIndex', () => {
  it('is deterministic', () => {
    expect(shardIndex('button.submit', 4)).toBe(shardIndex('button.submit', 4));
  });

  it('stays within bounds', () => {
    const keys = ['a', 'button.cancel', 'nav.home', 'error.network', 'x'.repeat(100)];
    for (const k of keys) {
      const idx = shardIndex(k, 8);
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(8);
    }
  });
});
```

Check KV key distribution after publishing:

```bash
wrangler kv:key list --namespace-id=<ID> --prefix="translations:en:ui:" | jq 'length'
```

## Related

- `translation-kv-caching-ttl-strategy.md`
- `i18n-content-fallback-chain-kv-workers.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `workers-durable-objects-locale-session-state.md`

## Sources

- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
- FNV hash reference: http://www.isthe.com/chongo/tech/comp/fnv/
- Cloudflare Workers isolate lifecycle: https://developers.cloudflare.com/workers/reference/security-model/
