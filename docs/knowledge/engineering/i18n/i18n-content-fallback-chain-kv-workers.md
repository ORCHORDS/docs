# i18n Content Fallback Chains in Cloudflare KV

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Workers app serves translations from Cloudflare KV and encounters missing keys for regional locales like `pt-BR` or `zh-TW`. Rather than surfacing an empty string or a raw key name, you need an automatic fallback chain — `pt-BR → pt → en` — that resolves at the edge without extra round-trips or a full translation bundle download. You also need to invalidate stale cached translations when the content team pushes updates to KV.

## Context

Cloudflare KV is a globally distributed key-value store well-suited to storing translation catalogues. Each key encodes the locale and the message ID, e.g. `i18n:pt-BR:checkout.cta`. When a translation is missing for a specific locale, CLDR defines a parent-locale hierarchy (`pt-BR → pt → und → en`). Implementing this chain in Workers avoids client-side fallback waterfalls while keeping the per-request logic simple. Bulk loading via KV `list` and `getWithMetadata` operations allows a Worker to prefetch an entire namespace into memory for the duration of an isolate's lifetime, caching formatted translation maps and only re-fetching when a version token stored in KV changes.

## KV Namespace Layout and Locale-Keyed Namespacing

Store translations under predictable key patterns so both lookup and list operations are efficient. Use a prefix hierarchy of `i18n:{locale}:{messageId}` or, for bulk loading, store one JSON blob per locale under `i18n:catalog:{locale}`.

```typescript
// src/i18n/kv-schema.ts

// Single-message key pattern:
//   i18n:en:checkout.cta           → "Buy now"
//   i18n:pt-BR:checkout.cta        → "Comprar agora"
//   i18n:pt:checkout.cta           → "Comprar"   (regional fallback target)
//   i18n:en:checkout.cta           → "Buy now"   (root fallback)

// Bulk-catalog key pattern (preferred for apps with >50 keys):
//   i18n:catalog:en                → '{"checkout.cta":"Buy now", ...}'
//   i18n:catalog:pt-BR             → '{"checkout.cta":"Comprar agora", ...}'

// Version token (cache-busting):
//   i18n:version                   → "2026-08-22T14:30:00Z"

export const KV_PREFIX = "i18n";
export const CATALOG_KEY = (locale: string) => `${KV_PREFIX}:catalog:${locale}`;
export const MSG_KEY = (locale: string, id: string) => `${KV_PREFIX}:${locale}:${id}`;
export const VERSION_KEY = `${KV_PREFIX}:version`;
```

## Fallback Chain Resolution Algorithm

Build the chain from the most specific locale to the root. CLDR defines `pt-BR → pt → en` as the canonical path. For locales with no CLDR-defined parent, fall directly to `en`.

```typescript
// src/i18n/fallback.ts

const CLDR_PARENTS: Record<string, string> = {
  "pt-BR": "pt",
  "pt-PT": "pt",
  "zh-TW": "zh-Hant",
  "zh-HK": "zh-Hant",
  "zh-Hant": "zh",
  "zh-Hans": "zh",
  "zh-MO": "zh-Hant",
  "en-GB": "en",
  "en-AU": "en",
  "es-419": "es",
  "fr-CA": "fr",
  "de-AT": "de",
  "de-CH": "de",
};

const ROOT_LOCALE = "en";

/**
 * Returns the ordered fallback chain for a given locale tag.
 * e.g. buildFallbackChain("pt-BR") → ["pt-BR", "pt", "en"]
 *      buildFallbackChain("fr-CA") → ["fr-CA", "fr", "en"]
 *      buildFallbackChain("ja")    → ["ja", "en"]
 */
export function buildFallbackChain(locale: string): string[] {
  const chain: string[] = [];
  let current: string | undefined = locale;

  while (current && !chain.includes(current)) {
    chain.push(current);
    const explicit = CLDR_PARENTS[current];
    if (explicit) {
      current = explicit;
      continue;
    }
    // Implicit subtag truncation: "fr-CA" → "fr" if not in CLDR_PARENTS
    const parts = current.split("-");
    if (parts.length > 1) {
      current = parts.slice(0, -1).join("-");
    } else {
      break;
    }
  }

  if (!chain.includes(ROOT_LOCALE)) {
    chain.push(ROOT_LOCALE);
  }
  return chain;
}

/**
 * Resolves a single message key against KV using the fallback chain.
 * Returns the first non-null value found, or null if all chain members miss.
 */
export async function resolveMessage(
  kv: KVNamespace,
  locale: string,
  messageId: string
): Promise<string | null> {
  const chain = buildFallbackChain(locale);
  for (const chainLocale of chain) {
    const value = await kv.get(MSG_KEY(chainLocale, messageId));
    if (value !== null) return value;
  }
  return null;
}
```

## Bulk Translation Loading with KV List Operations

For apps with many messages, issuing one `kv.get` per message key per request is too expensive. Instead, load the full catalog for each locale in the fallback chain once at isolate startup (or on version change), merge them in chain order (most specific locale wins), and cache the merged map in a module-level `Map`.

```typescript
// src/i18n/catalog.ts
import { buildFallbackChain, CATALOG_KEY, VERSION_KEY } from "./fallback";

type TranslationMap = Map<string, string>;

interface CatalogCache {
  version: string;
  locales: Map<string, TranslationMap>;
  merged: Map<string, TranslationMap>; // locale → merged fallback map
}

let catalogCache: CatalogCache | null = null;

async function loadLocaleCatalog(
  kv: KVNamespace,
  locale: string
): Promise<TranslationMap> {
  const raw = await kv.get(CATALOG_KEY(locale));
  if (!raw) return new Map();
  try {
    const obj = JSON.parse(raw) as Record<string, string>;
    return new Map(Object.entries(obj));
  } catch {
    console.error(`Failed to parse catalog for locale ${locale}`);
    return new Map();
  }
}

/**
 * Builds a merged translation map for `locale` by walking its fallback chain.
 * More-specific locales win over less-specific ones.
 */
function mergeCatalogChain(
  chain: string[],
  rawCatalogs: Map<string, TranslationMap>
): TranslationMap {
  // Iterate chain in reverse (root first) so specific locales overwrite
  const merged: TranslationMap = new Map();
  for (const chainLocale of [...chain].reverse()) {
    const catalog = rawCatalogs.get(chainLocale);
    if (catalog) {
      for (const [k, v] of catalog) {
        merged.set(k, v);
      }
    }
  }
  return merged;
}

export async function getTranslations(
  kv: KVNamespace,
  locale: string
): Promise<TranslationMap> {
  const currentVersion = (await kv.get(VERSION_KEY)) ?? "unknown";

  // Invalidate in-memory cache when KV version token changes
  if (catalogCache && catalogCache.version !== currentVersion) {
    catalogCache = null;
  }

  if (!catalogCache) {
    catalogCache = {
      version: currentVersion,
      locales: new Map(),
      merged: new Map(),
    };
  }

  if (catalogCache.merged.has(locale)) {
    return catalogCache.merged.get(locale)!;
  }

  const chain = buildFallbackChain(locale);

  // Fetch any chain members not yet in the raw catalog cache
  await Promise.all(
    chain.map(async (chainLocale) => {
      if (!catalogCache!.locales.has(chainLocale)) {
        const catalog = await loadLocaleCatalog(kv, chainLocale);
        catalogCache!.locales.set(chainLocale, catalog);
      }
    })
  );

  const merged = mergeCatalogChain(chain, catalogCache.locales);
  catalogCache.merged.set(locale, merged);
  return merged;
}

// Worker usage:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = new URL(request.url).searchParams.get("locale") ?? "en";
    const t = await getTranslations(env.I18N_KV, locale);
    const cta = t.get("checkout.cta") ?? "Buy";
    return new Response(JSON.stringify({ locale, cta }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Cache-Busting on Translation Updates

When the content team publishes new translations, write all updated catalog blobs to KV first, then atomically bump the version token. The Workers module cache will detect the version change on the next request and reload affected catalogs.

```typescript
// scripts/publish-translations.ts (Node.js deploy script)
// Run via: npx ts-node scripts/publish-translations.ts

import { writeTranslationCatalogs } from "./lib/kv-admin";

async function publishTranslations(
  accountId: string,
  namespaceId: string,
  apiToken: string,
  catalogs: Record<string, Record<string, string>>
): Promise<void> {
  const base = `https://api.cloudflare.com/client/v4/accounts/${accountId}/storage/kv/namespaces/${namespaceId}`;
  const headers = {
    Authorization: `Bearer ${apiToken}`,
    "Content-Type": "application/json",
  };

  // 1. Write all locale catalogs as a bulk operation
  const bulkPairs = Object.entries(catalogs).map(([locale, messages]) => ({
    key: `i18n:catalog:${locale}`,
    value: JSON.stringify(messages),
  }));

  const catalogResp = await fetch(`${base}/bulk`, {
    method: "PUT",
    headers,
    body: JSON.stringify(bulkPairs),
  });
  if (!catalogResp.ok) {
    throw new Error(`Catalog bulk write failed: ${await catalogResp.text()}`);
  }

  // 2. Bump the version token AFTER catalogs are written
  const version = new Date().toISOString();
  const versionResp = await fetch(`${base}/values/i18n:version`, {
    method: "PUT",
    headers,
    body: version,
  });
  if (!versionResp.ok) {
    throw new Error(`Version token write failed: ${await versionResp.text()}`);
  }

  console.log(`Published translations at version ${version}`);
}
```

## Anti-patterns

- Building the fallback chain on every message lookup instead of once per locale per request — chains are pure functions of the locale string and should be memoised.
- Relying on KV TTL alone for cache invalidation — TTL eviction is non-deterministic and can leave stale translations in place for minutes after a content update; always use a version token.
- Listing all KV keys with `kv.list()` on every request to discover locale catalogs — `list` is expensive and not designed for hot-path usage; store catalogs as pre-aggregated JSON blobs under known keys.
- Storing translations as individual KV keys per message in the hot path — 200 messages per locale × 4 locales in the chain = up to 800 KV reads per page render; always pre-aggregate into per-locale catalog blobs.

## Gotchas

- KV is eventually consistent: after writing updated catalog blobs and bumping the version token, Workers in distant data centres may still read the old version token for up to 60 seconds. Accept this staleness window or use a Durable Object as a strong-consistency version register if freshness is critical.
- Module-level caches (`catalogCache`) survive across requests within the same isolate instance but are not shared between isolate instances on different machines. A version-token check per request is the correct cross-instance invalidation mechanism.
- `kv.get()` returns `null` (not `undefined` or an empty string) for missing keys — guard every lookup with a strict `!== null` check to avoid treating a legitimately empty translation value as a cache miss.

## Verification

```bash
# Write test catalogs to KV via wrangler
echo '{"checkout.cta":"Buy now"}' | wrangler kv key put \
  --binding I18N_KV "i18n:catalog:en" --stdin

echo '{"checkout.cta":"Comprar"}' | wrangler kv key put \
  --binding I18N_KV "i18n:catalog:pt" --stdin

# pt-BR catalog intentionally missing to test fallback to "pt"
wrangler kv key put --binding I18N_KV "i18n:version" "2026-08-22T00:00:00Z"

# Should return "Comprar" via pt-BR → pt fallback
curl -s "https://your-worker.workers.dev/?locale=pt-BR" | jq '.cta'

# Should return "Buy now" via zh-TW → zh-Hant → zh → en fallback
curl -s "https://your-worker.workers.dev/?locale=zh-TW" | jq '.cta'

# Bump version and confirm stale cache is invalidated on next request
wrangler kv key put --binding I18N_KV "i18n:version" "2026-08-22T01:00:00Z"
curl -s "https://your-worker.workers.dev/?locale=pt-BR" | jq '.cta'
```

## Related

- `i18n/locale-fallback-chain.md`
- `i18n/locale-fallback-strategies-2026.md`
- `i18n/translation-kv-caching-ttl-strategy.md`
- `i18n/locale-negotiation-cloudflare-pages-accept-language.md`
- `i18n/workers-durable-objects-locale-session-state.md`

## Sources

- https://developers.cloudflare.com/kv/api/
- https://unicode.org/reports/tr35/#Locale_Inheritance
- https://www.unicode.org/cldr/charts/latest/supplemental/likely_subtags.html
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#write-multiple-key-value-pairs
