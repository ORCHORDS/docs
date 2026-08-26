# Translation File Caching Strategy with Cloudflare KV and Cache TTLs

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Worker fetches translation JSON from an origin or R2 bucket on every request. Under moderate load (>500 req/s) this produces:

- Cold-start latency spikes of 150–400 ms per locale
- R2/origin egress cost growing linearly with traffic
- Workers CPU time wasted on repeated JSON parsing of identical bundles
- Translation updates taking effect inconsistently across edge locations

You need a deterministic, multi-layer caching strategy that keeps translation bundles fast, fresh, and cheap.

---

## Context

Cloudflare Workers has three relevant caching layers, each with different trade-offs:

| Layer | Scope | Max size | TTL control | Invalidation |
|---|---|---|---|---|
| **In-memory module cache** | Single isolate | ~10 MB total | Process lifetime | Worker redeploy |
| **Workers KV** | Global | 25 MB/value | `expirationTtl` | `kv.delete()` or overwrite |
| **Cache API** | Edge PoP | Unlimited | `Cache-Control` header | `cache.delete()` |

Translation bundles (JSON per locale per namespace) are typically 20–200 KB each and change only during deployments or TMS pushes. They are ideal for aggressive KV caching because:

- Content is fully public (no PII)
- Same bundle is served to all users of a locale
- Stale-while-revalidate is acceptable for most products

---

## Architecture: Three-Layer Cache Waterfall

```
Request
  │
  ▼
[1] In-process Map (module-scoped, isolate lifetime)
  │  miss?
  ▼
[2] Workers KV (global, TTL-controlled)
  │  miss?
  ▼
[3] Cache API (PoP-local, HTTP semantics)
  │  miss?
  ▼
[4] R2 / Origin (authoritative source)
  │  store upstream
  ◀──────────────────────────────────────
```

### Why four layers instead of one?

KV reads have ~5 ms p50 latency from the nearest PoP. An in-memory Map removes even that for hot locales within a warm isolate. The Cache API layer is a safety net for large bundles that exceed module memory or when the isolate is cold.

---

## Layer 1: In-Process Module Cache

```typescript
// src/translation-cache.ts

// Module-level Map: lives for the duration of the isolate.
// Each Worker isolate runs in a single V8 context; the Map
// persists across requests within that isolate.
const PROCESS_CACHE = new Map<string, { bundle: Record<string, string>; fetchedAt: number }>();

// Maximum age for the in-process cache (ms).
// Short enough that a KV invalidation propagates in ~1 minute.
const PROCESS_TTL_MS = 60_000;

export function getFromProcessCache(
  locale: string,
  namespace: string
): Record<string, string> | null {
  const key = `${locale}:${namespace}`;
  const entry = PROCESS_CACHE.get(key);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > PROCESS_TTL_MS) {
    PROCESS_CACHE.delete(key);
    return null;
  }
  return entry.bundle;
}

export function setInProcessCache(
  locale: string,
  namespace: string,
  bundle: Record<string, string>
): void {
  const key = `${locale}:${namespace}`;
  PROCESS_CACHE.set(key, { bundle, fetchedAt: Date.now() });

  // Evict least-recently-set entries if the Map grows too large.
  if (PROCESS_CACHE.size > 100) {
    const oldest = PROCESS_CACHE.keys().next().value;
    if (oldest) PROCESS_CACHE.delete(oldest);
  }
}
```

**Key property:** `PROCESS_CACHE` is re-created on each Worker redeploy, so stale bundles cannot outlive a deploy.

---

## Layer 2: Workers KV

### Binding definition (wrangler.toml)

```toml
[[kv_namespaces]]
binding = "TRANSLATIONS_KV"
id      = "abc123def456..."   # production namespace
preview_id = "xyz789..."      # preview / staging namespace

[env.production]
[[env.production.kv_namespaces]]
binding = "TRANSLATIONS_KV"
id      = "abc123def456..."
```

### KV key schema

```
translations:{locale}:{namespace}:{version}
```

Examples:
- `translations:en-US:common:v42`
- `translations:ar:checkout:v42`
- `translations:pl:errors:v42`

The `version` segment is set at deploy time (e.g. a build hash or semver). This enables zero-downtime translation updates: old Workers still read the old version key; new Workers read the new version key. Both are valid KV entries simultaneously.

### Reading and writing KV

```typescript
// src/kv-translation-loader.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  TRANSLATIONS_KV: KVNamespace;
  TRANSLATION_VERSION: string; // set via wrangler secret or env var
}

const KV_TTL_SECONDS = 3600; // 1 hour; adjust per deployment cadence

export async function getFromKV(
  env: Env,
  locale: string,
  namespace: string
): Promise<Record<string, string> | null> {
  const key = `translations:${locale}:${namespace}:${env.TRANSLATION_VERSION}`;
  const raw = await env.TRANSLATIONS_KV.get(key, { type: 'json' });
  return raw as Record<string, string> | null;
}

export async function setInKV(
  env: Env,
  locale: string,
  namespace: string,
  bundle: Record<string, string>
): Promise<void> {
  const key = `translations:${locale}:${namespace}:${env.TRANSLATION_VERSION}`;
  await env.TRANSLATIONS_KV.put(key, JSON.stringify(bundle), {
    expirationTtl: KV_TTL_SECONDS,
  });
}
```

### KV metadata for cache headers

KV supports a `metadata` object (up to 1024 bytes) stored alongside the value. Use it to embed cache policy without re-fetching the full bundle:

```typescript
interface TranslationMeta {
  lastModified: string; // ISO-8601
  etag: string;         // content hash
  size: number;         // bytes
}

await env.TRANSLATIONS_KV.put(key, JSON.stringify(bundle), {
  expirationTtl: KV_TTL_SECONDS,
  metadata: {
    lastModified: new Date().toISOString(),
    etag: await computeHash(bundle),
    size: JSON.stringify(bundle).length,
  } satisfies TranslationMeta,
});

// Later, read metadata without fetching the full value:
const { metadata } = await env.TRANSLATIONS_KV.getWithMetadata<TranslationMeta>(key);
```

---

## Layer 3: Cache API (PoP-Level)

The Cache API stores responses, not raw values. Wrap the bundle in a synthetic `Response` before storing:

```typescript
// src/cache-api-layer.ts

const CACHE_URL_BASE = 'https://internal.translations.local/';

function makeCacheUrl(locale: string, namespace: string, version: string): string {
  return `${CACHE_URL_BASE}${version}/${locale}/${namespace}.json`;
}

export async function getFromCacheAPI(
  locale: string,
  namespace: string,
  version: string
): Promise<Record<string, string> | null> {
  const cache = await caches.open('translations-v1');
  const url   = makeCacheUrl(locale, namespace, version);
  const resp  = await cache.match(url);
  if (!resp) return null;
  return resp.json();
}

export async function setInCacheAPI(
  locale: string,
  namespace: string,
  version: string,
  bundle: Record<string, string>
): Promise<void> {
  const cache = await caches.open('translations-v1');
  const url   = makeCacheUrl(locale, namespace, version);

  const resp = new Response(JSON.stringify(bundle), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      // 5-minute max-age; stale-while-revalidate allows serving stale
      // for another 60 seconds while revalidation happens in background.
      'Cache-Control': 'public, max-age=300, stale-while-revalidate=60',
      'ETag': `"${version}"`,
    },
  });

  await cache.put(url, resp);
}
```

---

## Layer 4: Origin Loader (R2 or Fetch)

```typescript
// src/origin-loader.ts
import type { R2Bucket } from '@cloudflare/workers-types';

export interface Env {
  TRANSLATION_ASSETS: R2Bucket;
}

export async function loadFromR2(
  env: Env,
  locale: string,
  namespace: string
): Promise<Record<string, string>> {
  const key    = `i18n/${locale}/${namespace}.json`;
  const object = await env.TRANSLATION_ASSETS.get(key);

  if (!object) {
    // Fallback: try the base language (strip region tag)
    const baseLang = locale.split('-')[0];
    const fallback = await env.TRANSLATION_ASSETS.get(`i18n/${baseLang}/${namespace}.json`);
    if (!fallback) throw new Error(`Missing translation: ${key}`);
    return fallback.json();
  }

  return object.json();
}
```

---

## Assembling the Waterfall

```typescript
// src/translation-loader.ts
import { getFromProcessCache, setInProcessCache } from './translation-cache';
import { getFromKV, setInKV }                      from './kv-translation-loader';
import { getFromCacheAPI, setInCacheAPI }          from './cache-api-layer';
import { loadFromR2 }                              from './origin-loader';
import type { Env }                                from './types';

export async function loadTranslations(
  env: Env,
  locale: string,
  namespace: string
): Promise<Record<string, string>> {
  // Layer 1: in-process
  const fromProcess = getFromProcessCache(locale, namespace);
  if (fromProcess) return fromProcess;

  // Layer 2: KV
  const fromKV = await getFromKV(env, locale, namespace);
  if (fromKV) {
    setInProcessCache(locale, namespace, fromKV);
    return fromKV;
  }

  // Layer 3: Cache API
  const fromCacheAPI = await getFromCacheAPI(locale, namespace, env.TRANSLATION_VERSION);
  if (fromCacheAPI) {
    // Backfill KV so the next isolate benefits
    await setInKV(env, locale, namespace, fromCacheAPI);
    setInProcessCache(locale, namespace, fromCacheAPI);
    return fromCacheAPI;
  }

  // Layer 4: R2
  const fromR2 = await loadFromR2(env, locale, namespace);

  // Populate all upstream layers
  await Promise.all([
    setInKV(env, locale, namespace, fromR2),
    setInCacheAPI(locale, namespace, env.TRANSLATION_VERSION, fromR2),
  ]);
  setInProcessCache(locale, namespace, fromR2);

  return fromR2;
}
```

---

## Cache Invalidation on Translation Updates

When the TMS pushes new translation files, you need to purge stale KV entries. Use a Cloudflare Worker scheduled via a Durable Object or Cron Trigger:

```typescript
// src/invalidate.ts – called from a Cron Trigger or CI pipeline

export async function invalidateLocale(
  env: Env,
  locale: string,
  namespaces: string[]
): Promise<void> {
  const oldVersion = env.TRANSLATION_VERSION; // version being superseded

  const deletes = namespaces.map((ns) => {
    const key = `translations:${locale}:${ns}:${oldVersion}`;
    return env.TRANSLATIONS_KV.delete(key);
  });

  await Promise.all(deletes);

  // Cache API entries expire naturally via max-age; force-purge if needed:
  const cache = await caches.open('translations-v1');
  const cachePurges = namespaces.map((ns) => {
    const url = `https://internal.translations.local/${oldVersion}/${locale}/${ns}.json`;
    return cache.delete(url);
  });

  await Promise.all(cachePurges);
}
```

**CI integration:** After uploading new translation files to R2, call `invalidateLocale()` for each changed locale from a Worker triggered by a `wrangler publish` post-hook or a GitHub Actions step that hits a `/_internal/invalidate` endpoint.

---

## TTL Matrix: Recommended Values

| Layer | TTL | Rationale |
|---|---|---|
| In-process Map | 60 s | Short enough that a KV invalidation propagates quickly |
| Workers KV `expirationTtl` | 3 600 s | Translations change at most on each deploy |
| Cache API `max-age` | 300 s | PoP-level; allows fast purge via `cache.delete()` |
| Cache API `stale-while-revalidate` | 60 s | Zero-latency serving during background revalidation |
| R2 signed URL (if used) | 900 s | Pre-signed URL lifespan for direct client access |

---

## Anti-Patterns

- **Storing all locales in one KV value.** A 2 MB JSON blob for 50 locales means every namespace update invalidates the whole blob. Shard by `locale:namespace`.
- **Using KV as the only cache layer.** KV reads cost ~$0.50 per million ops. With 10 M req/day and 3 namespaces per request, that is $15/day just in KV reads. The in-process layer eliminates most of that.
- **Forgetting `expirationTtl` on KV writes.** Without it, KV entries live forever. After 100 deploys you accumulate thousands of stale version-keyed entries, incurring KV storage fees.
- **Parsing JSON inside every `fetch()` event.** JSON.parse on a 200 KB bundle inside the hot path adds 2–5 ms. Parse once and store the object in the in-process Map.
- **Invalidating by deleting all KV keys.** Iterating `list()` and deleting is eventually consistent (KV is not strongly consistent). Use versioned keys and let the old version expire instead.

---

## Gotchas

- **KV is eventually consistent globally.** After a `put()`, other edge locations may serve stale data for up to 60 seconds. For critical translation fixes, bump `TRANSLATION_VERSION` instead of relying on invalidation.
- **KV `get` with `type: 'json'` still counts as a full read.** The value is deserialized server-side but you pay the same read unit cost.
- **Cache API is PoP-local.** A cache.put() in Frankfurt does not populate London. Each PoP warms independently on the first cache miss.
- **Module-level Map does not persist across isolate restarts.** Cloudflare may restart isolates after idle timeouts or resource pressure. Always treat the process cache as a best-effort optimization.
- **R2 `get()` returns `null` for missing objects** (not a 404 error), so explicit null checks are required.

---

## Verification

```typescript
// Smoke-test the cache waterfall in a test Worker

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== '/__cache-test') {
      return new Response('not found', { status: 404 });
    }

    const results: Record<string, unknown> = {};
    const start = Date.now();

    // First load – should hit R2
    const bundle1 = await loadTranslations(env, 'en-US', 'common');
    results.firstLoad = { ms: Date.now() - start, keys: Object.keys(bundle1).length };

    // Second load – should hit in-process Map
    const t2 = Date.now();
    const bundle2 = await loadTranslations(env, 'en-US', 'common');
    results.secondLoad = { ms: Date.now() - t2, keys: Object.keys(bundle2).length };

    return Response.json(results);
  },
};
```

Expect: `firstLoad.ms` 50–200 ms (R2 round-trip), `secondLoad.ms` < 1 ms (in-process Map).

---

## Related

- `d1-schema-locale-preferences-content-translations-2026.md`
- `locale-negotiation-accept-language.md`
- `i18n-namespace-organization-lazy-loading.md`
- `i18n-bundle-size-tree-shaking-2026.md`
- `i18n-deployment-2026.md`

---

## Sources

- [Cloudflare KV documentation](https://developers.cloudflare.com/kv/)
- [Cache API in Workers](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [KV pricing](https://developers.cloudflare.com/kv/platform/pricing/)
- [Workers limits: memory](https://developers.cloudflare.com/workers/platform/limits/#memory)
