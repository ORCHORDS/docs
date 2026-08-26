# Translation Fallback Chain with KV-Backed Message Store in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your product ships in 15 locales but translations are incomplete — copywriters have finished British English but not American English, Spanish (Mexico) but not Spanish (Spain). You need a runtime fallback chain so that missing translations degrade gracefully to a parent locale rather than showing raw keys. You also want to update translations without a full Worker redeploy.

---

## Context

KV (Cloudflare Workers KV) is a globally distributed key-value store with strong read performance (sub-millisecond at edge after first fetch). It is ideal for storing locale bundles — JSON objects mapping message keys to translated strings — because:

- Reads are eventually consistent and propagate globally within ~60 seconds
- Large values (up to 25 MB) accommodate complete locale bundles
- TTL-based expiry enables hot-reload without code changes
- KV `list()` lets you enumerate available locales for discovery

The fallback chain pattern mirrors what browsers do with `Accept-Language`: try the most specific locale first, then strip the region, then use the configured fallback language.

---

## Solution

### 1. KV Key Structure

```
messages:{locale}         → Full locale bundle JSON (e.g., messages:en-GB)
messages:{language}       → Language-only bundle (e.g., messages:en)
messages:__index          → JSON array of available locale keys
messages:__version        → Monotonic version counter for cache-busting
```

Bundle format:

```json
{
  "version": 42,
  "locale": "en-GB",
  "messages": {
    "nav.home": "Home",
    "nav.about": "About us",
    "cart.items": "{count, plural, one {# item} other {# items}}",
    "checkout.cta": "Proceed to checkout"
  }
}
```

### 2. Locale Fallback Chain Builder

```typescript
// src/i18n/fallback.ts

/**
 * Build the BCP 47 locale fallback chain.
 *
 * Examples:
 *   'en-GB'  → ['en-GB', 'en', 'en-US']
 *   'zh-Hant-TW' → ['zh-Hant-TW', 'zh-Hant', 'zh', 'en-US']
 *   'pt-BR'  → ['pt-BR', 'pt', 'en-US']
 *   'en-US'  → ['en-US', 'en', 'en-US'] (deduped to ['en-US', 'en'])
 */
export function buildFallbackChain(
  locale: string,
  ultimateFallback = 'en-US',
): string[] {
  const chain: string[] = [];
  const seen = new Set<string>();

  const add = (tag: string): void => {
    if (!seen.has(tag)) { seen.add(tag); chain.push(tag); }
  };

  add(locale);

  const parts = locale.split('-');
  // Walk up the tag hierarchy: 'zh-Hant-TW' → 'zh-Hant' → 'zh'
  for (let i = parts.length - 1; i > 0; i--) {
    add(parts.slice(0, i).join('-'));
  }

  add(ultimateFallback);
  return chain;
}
```

### 3. KV Bundle Loader with Batch Prefetch

```typescript
// src/i18n/bundle-loader.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface MessageBundle {
  version: number;
  locale: string;
  messages: Record<string, string>;
}

/**
 * Load locale bundles for a fallback chain in parallel.
 * Returns an array ordered from most-specific to least-specific;
 * absent locales return null (gaps in the chain are skipped).
 */
export async function loadBundleChain(
  chain: string[],
  kv: KVNamespace,
): Promise<MessageBundle[]> {
  const fetches = chain.map((locale) =>
    kv.get<MessageBundle>(`messages:${locale}`, 'json'),
  );
  const results = await Promise.all(fetches);
  return results.filter((b): b is MessageBundle => b !== null);
}

/**
 * Merge bundles from least-specific to most-specific.
 * Most-specific locale's keys win when there is a conflict.
 */
export function mergeBundles(bundles: MessageBundle[]): Record<string, string> {
  const merged: Record<string, string> = {};
  // Apply in reverse so most-specific overwrites
  for (const bundle of [...bundles].reverse()) {
    Object.assign(merged, bundle.messages);
  }
  return merged;
}

/**
 * High-level helper: load the effective translation map for a locale.
 */
export async function getTranslations(
  locale: string,
  kv: KVNamespace,
  ultimateFallback = 'en-US',
): Promise<{
  messages: Record<string, string>;
  resolvedChain: string[];
}> {
  const { buildFallbackChain } = await import('./fallback');
  const chain = buildFallbackChain(locale, ultimateFallback);
  const bundles = await loadBundleChain(chain, kv);
  const resolvedChain = bundles.map((b) => b.locale);
  return { messages: mergeBundles(bundles), resolvedChain };
}
```

### 4. Message Lookup with Missing Key Logging

```typescript
// src/i18n/translate.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface TranslateOptions {
  /** Substitution params: {name} → value */
  params?: Record<string, string | number>;
  /** Return this string instead of the key when translation is missing */
  fallback?: string;
}

/**
 * Look up a translation key and substitute parameters.
 * Logs missing keys to Analytics Engine for monitoring.
 */
export function translate(
  key: string,
  messages: Record<string, string>,
  locale: string,
  analytics: AnalyticsEngineDataset | null,
  opts: TranslateOptions = {},
): string {
  const pattern = messages[key];

  if (!pattern) {
    // Log to Analytics Engine for visibility (non-blocking)
    analytics?.writeDataPoint({
      blobs: [key, locale],
      indexes: ['missing_translation'],
    });
    return opts.fallback ?? key;
  }

  if (!opts.params) return pattern;

  // Simple variable substitution: {variableName}
  return pattern.replace(
    /\{(\w+)\}/g,
    (_, name) => {
      const val = opts.params?.[name];
      return val !== undefined ? String(val) : `{${name}}`;
    },
  );
}
```

### 5. Hot-Reload Without Redeploy

KV writes propagate globally in ~60 seconds. To update translations:

```typescript
// scripts/publish-bundle.ts  (runs in CI/CD, not in Worker)
import { execSync } from 'child_process';
import * as fs from 'fs';

const locale = process.argv[2]; // e.g., 'en-GB'
const filePath = `locales/${locale}.json`;
const bundle = JSON.parse(fs.readFileSync(filePath, 'utf8'));

bundle.version = Date.now();
bundle.locale = locale;

execSync(
  `npx wrangler kv key put messages:${locale} '${JSON.stringify(bundle)}' \
  --namespace-id $KV_NAMESPACE_ID`,
);

console.log(`Published ${locale} bundle version ${bundle.version}`);
```

The Worker does not need to be redeployed. KV reads in Workers respect a per-isolate in-memory cache that expires every ~60 seconds, so new translations are live within 1–2 minutes globally.

For immediate propagation without waiting for KV propagation delay, use the Cache API to bust cached HTML:

```typescript
// src/cache-bust.ts
export async function bustTranslationCache(
  locale: string,
  caches: CacheStorage,
): Promise<void> {
  const cache = await caches.open('i18n-v1');
  // Delete all cached pages for this locale
  // In practice, maintain a list of URLs or use a version token in keys
  console.log(`Cache bust triggered for locale: ${locale}`);
}
```

### 6. Worker Entry Point

```typescript
// src/index.ts
import type { KVNamespace, AnalyticsEngineDataset } from '@cloudflare/workers-types';
import { parseAcceptLanguage } from './i18n/detect';
import { getTranslations } from './i18n/bundle-loader';
import { translate } from './i18n/translate';

export interface Env {
  MESSAGES: KVNamespace;
  I18N_ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = parseAcceptLanguage(
      request.headers.get('accept-language'),
    );

    const { messages, resolvedChain } = await getTranslations(
      locale,
      env.MESSAGES,
    );

    // Render a JSON payload of translated strings for an SPA
    const payload = {
      locale,
      resolvedChain,
      strings: {
        navHome: translate('nav.home', messages, locale, env.I18N_ANALYTICS),
        navAbout: translate('nav.about', messages, locale, env.I18N_ANALYTICS),
        cartItems: translate(
          'cart.items',
          messages,
          locale,
          env.I18N_ANALYTICS,
          { params: { count: 3 } },
        ),
      },
    };

    return Response.json(payload, {
      headers: { 'vary': 'Accept-Language' },
    });
  },
} satisfies ExportedHandler<Env>;
```

### 7. wrangler.toml

```toml
name = "edge-i18n"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "MESSAGES"
id = "<YOUR_KV_NAMESPACE_ID>"

[[analytics_engine_datasets]]
binding = "I18N_ANALYTICS"
dataset = "i18n_events"
```

---

## Implementation Details

### KV Read Consistency

KV is eventually consistent. After a `kv.put()`, reads from the same region reflect the new value immediately; other regions lag by up to 60 seconds. For most translation updates this is acceptable. If you need instant global propagation, combine KV write with a Cache API purge and a Durable Object broadcast.

### Bundle Size Considerations

KV values can be up to 25 MB. A typical locale bundle with 500 message keys at 50 bytes each is 25 KB — well within limits. For very large applications (5,000+ keys), split bundles by page namespace: `messages:en-US:checkout`, `messages:en-US:product-detail`.

### In-Memory Module Cache

Within a single Worker isolate lifetime, cache the loaded bundle in a module-level variable to avoid repeated KV reads for the same locale across multiple requests served by the same isolate:

```typescript
const bundleCache = new Map<string, Record<string, string>>();

export async function getCachedTranslations(
  locale: string,
  kv: KVNamespace,
): Promise<Record<string, string>> {
  if (bundleCache.has(locale)) return bundleCache.get(locale)!;
  const { messages } = await getTranslations(locale, kv);
  bundleCache.set(locale, messages);
  return messages;
}
```

Note: this cache is cleared when the isolate is evicted (typically after a few minutes of inactivity or on redeploy).

---

## Anti-patterns

- **Do not fetch KV per message key.** Each `kv.get()` call has network latency. Fetch the entire bundle once per request.
- **Do not store one KV key per translation string.** This hits the KV operations limit quickly and creates management overhead. Always bundle by locale.
- **Do not expose missing key names in user-facing responses.** Return a graceful fallback string or the English equivalent — raw keys like `cart.items.count` are confusing and potentially a source of information leakage.
- **Avoid synchronous filesystem reads for locale bundles.** Workers do not have a filesystem. All locale data must come from KV, D1, R2, or be bundled at build time as a `const`.

---

## Gotchas

- KV `get()` with `'json'` type returns `null` when the key does not exist — not an empty object. Always null-check before accessing `.messages`.
- `Promise.all()` on KV fetches runs them concurrently; this is safe and correct. Do not `await` each fetch sequentially in a loop.
- `Analytics Engine` `writeDataPoint()` is fire-and-forget and non-blocking. It does not throw on failure. You do not need a try/catch around it.
- KV `list()` is paginated (default 1,000 keys). For an index of more than 1,000 locales, paginate using the `cursor` field in the response.
- Locale bundle updates to KV while a Worker isolate is alive: the isolate's in-memory module cache (if you implement it) holds the old bundle. Design the TTL to be shorter than your expected isolate lifetime, or bust the cache explicitly.

---

## Verification

```bash
# Publish a test bundle
npx wrangler kv key put messages:en-US \
  '{"version":1,"locale":"en-US","messages":{"nav.home":"Home","cart.items":"{count, plural, one {# item} other {# items}}"}}' \
  --namespace-id $KV_NAMESPACE_ID

npx wrangler kv key put messages:en-GB \
  '{"version":1,"locale":"en-GB","messages":{"checkout.cta":"Proceed to checkout"}}' \
  --namespace-id $KV_NAMESPACE_ID

# Start local dev
npx wrangler dev --local

# en-GB should fall back to en-US for nav.home
curl 'http://localhost:8787/' -H 'Accept-Language: en-GB'
# Expected: resolvedChain includes ["en-GB", "en-US"], nav.home: "Home"

# Missing key should return key string and log to analytics
curl 'http://localhost:8787/' -H 'Accept-Language: fr'
# Expected: nav.home returns "nav.home" (key), resolvedChain: ["en-US"]

# Update bundle without redeploy
npx wrangler kv key put messages:en-US \
  '{"version":2,"locale":"en-US","messages":{"nav.home":"Start"}}' \
  --namespace-id $KV_NAMESPACE_ID
# Within ~60 seconds, subsequent requests return nav.home: "Start"
```

---

## Related

- `workers-plural-rules-intl-messageformat.md` — ICU MessageFormat in D1
- `workers-geo-redirect-locale-detection.md` — locale resolution pipeline
- `workers-currency-formatting-intl-edge.md` — currency with KV prefs
- Cloudflare Workers KV documentation
- Analytics Engine documentation

---

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://www.rfc-editor.org/rfc/rfc5646 (BCP 47 locale hierarchy)
- https://developers.cloudflare.com/workers/runtime-apis/cache/
