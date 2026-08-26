# KV Chunked Namespace Translation Loading in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers handler that loads all translations for a locale from a single KV key begins hitting the 25 MB value-size limit as the product grows. Cold-start latency spikes because the full bundle is fetched even when only one namespace (e.g., `checkout`) is needed for the current route. You need a way to split translations across multiple KV keys by namespace and load only what the request actually uses.

## Context

Cloudflare KV values are capped at **25 MB** per key and reads are billed per operation. A monolithic `translations:en` key that holds every string for every page cannot scale past a few hundred locales × namespaces. The solution is namespace sharding: one KV key per locale + namespace (`translations:en:checkout`, `translations:en:nav`, …). Workers cache KV reads automatically in the local colocation cache (default TTL 60 s), so repeated sub-namespace reads within a datacenter are nearly free after the first request.

---

## Namespace Key Convention

```typescript
// Convention: translations:{locale}:{namespace}
// e.g.  translations:en-US:checkout
//        translations:ar:nav

function kvTranslationKey(locale: string, namespace: string): string {
  // Normalise locale to BCP 47 base tag to avoid key explosion
  const base = new Intl.Locale(locale).baseName; // "en-US" → "en-US"
  return `translations:${base}:${namespace}`;
}
```

---

## Writing Chunked Bundles at Build Time

```typescript
// build/upload-translations.ts  (run via wrangler or CI)
import { readFileSync, readdirSync } from "fs";

interface Env {
  TRANSLATIONS: KVNamespace;
}

async function upload(kv: KVNamespace, dir: string) {
  // dir layout: ./locales/en-US/checkout.json, ./locales/ar/nav.json …
  for (const locale of readdirSync(dir)) {
    const nsDir = `${dir}/${locale}`;
    for (const file of readdirSync(nsDir)) {
      const ns = file.replace(/\.json$/, "");
      const value = readFileSync(`${nsDir}/${file}`, "utf8");
      const key = `translations:${locale}:${ns}`;
      await kv.put(key, value, { metadata: { updatedAt: Date.now() } });
      console.log(`Uploaded ${key} (${value.length} bytes)`);
    }
  }
}
```

---

## Lazy Namespace Loader in Workers

```typescript
interface TranslationCache {
 string>;
}

// Module-level in-process cache (lives for the Worker isolate lifetime)
const inProcessCache: TranslationCache = {};

export async function loadNamespace(
  kv: KVNamespace,
  locale: string,
  namespace: string
): Promise<Record<string, string>> {
  const cacheKey = `${locale}:${namespace}`;
  if (inProcessCache[cacheKey]) return inProcessCache[cacheKey];

  const kvKey = kvTranslationKey(locale, namespace);
  const raw = await kv.get(kvKey, { type: "json", cacheTtl: 300 });

  if (!raw) {
    // Fallback: strip region subtag (en-US → en)
    const fallbackLocale = locale.split("-")[0];
    if (fallbackLocale !== locale) {
      return loadNamespace(kv, fallbackLocale, namespace);
    }
    return {}; // ultimate fallback: empty (render keys as-is)
  }

  inProcessCache[cacheKey] = raw as Record<string, string>;
  return inProcessCache[cacheKey];
}

// Helper: resolve a key across multiple namespaces in priority order
export async function t(
  kv: KVNamespace,
  locale: string,
  namespaces: string[],
  key: string,
  vars: Record<string, string> = {}
): Promise<string> {
  for (const ns of namespaces) {
    const bundle = await loadNamespace(kv, locale, ns);
    if (bundle[key]) {
      return bundle[key].replace(/\{\{(\w+)\}\}/g, (_, k) => vars[k] ?? `{{${k}}}`);
    }
  }
  return key; // fallback to raw key
}
```

---

## Route-Scoped Namespace Loading

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locale = request.headers.get("x-locale") ?? "en";

    // Determine which namespaces this route needs
    const routeNs = routeToNamespaces(url.pathname);

    // Load in parallel — KV colocation cache makes repeated reads cheap
    const bundles = await Promise.all(
      routeNs.map((ns) => loadNamespace(env.TRANSLATIONS, locale, ns))
    );
    const merged = Object.assign({}, ...bundles);

    return Response.json({ translations: merged });
  },
};

function routeToNamespaces(pathname: string): string[] {
  if (pathname.startsWith("/checkout")) return ["checkout", "common"];
  if (pathname.startsWith("/account")) return ["account", "common"];
  return ["common"];
}
```

---

## Namespace Manifest for Discovery

Store a small manifest so clients know which namespaces exist for a locale:

```typescript
// Key: translations:{locale}:__manifest
// Value: ["common","checkout","nav","account","errors"]

async function getManifest(kv: KVNamespace, locale: string): Promise<string[]> {
  const key = `translations:${locale}:__manifest`;
  return (await kv.get(key, { type: "json", cacheTtl: 600 })) ?? [];
}
```

---

## Anti-patterns

- **Single monolithic key per locale**: hits the 25 MB limit, fetches unused strings on every request.
- **No in-process cache**: every request pays a KV round-trip even for the same namespace within the same isolate lifetime.
- **Loading all namespaces eagerly**: defeats the purpose; load only what the current route needs.
- **Using the full BCP 47 tag including extensions as the KV key**: `en-US-u-nu-arab` creates phantom keys; normalise to `baseName` before keying.

## Gotchas

- KV `cacheTtl` applies to the **edge cache**, not the in-process `Map`. Both layers are necessary; in-process removes repeated KV API calls within a single isolate.
- KV lists (`kv.list({ prefix: "translations:en:" })`) are eventually consistent — do not rely on them for live manifest generation in the hot path; write an explicit manifest key instead.
- Wrangler's `--local` KV emulation does not replicate the 300 ms eventual-consistency window; test propagation delays in a staging namespace.
- The `cacheTtl` minimum for KV `get` is **60 seconds**; passing a lower value silently floors to 60 s.

## Verification

```bash
# Check key sizes
wrangler kv:key list --namespace-id=<ID> --prefix="translations:en:"

# Confirm chunk fetch latency in production
wrangler tail --format=json | jq '.logs[] | select(.message | contains("kv-get"))'

# Integration test: ensure fallback chain resolves
npx vitest run tests/kv-translation-loader.test.ts
```

## Related

- `i18n-content-fallback-chain-kv-workers.md`
- `translation-kv-caching-ttl-strategy.md`
- `i18n-namespace-organization-lazy-loading.md`
- `react-i18next-lazy-loading.md`
- `locale-fallback-chain.md`

## Sources

- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
- KV `cacheTtl` docs: https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- BCP 47 `baseName`: https://tc39.es/ecma402/#sec-intl.locale-intro
