# ICU MessageFormat Translations Stored in KV with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to serve translated UI strings from a Cloudflare Worker without bundling locale files into the Worker script itself. Locale bundles must be hot-swappable without redeployment, and you need full ICU MessageFormat support for pluralisation, gender, and select rules.

---

## Context
Cloudflare KV is an ideal store for locale JSON bundles because values can be up to 25 MB and reads are eventually consistent with sub-millisecond latency at the edge. `@formatjs/intl-messageformat` can be compiled to a Workers-compatible ES module bundle using esbuild with `platform: 'browser'` and `target: 'es2022'`. A three-level fallback chain (`fr-CA → fr → en`) is implemented by attempting KV lookups in order and merging results. Responses are cached in the Workers Cache API for one hour to avoid KV reads on every request.

---

## Setup / Config

```toml
# wrangler.toml
name = "i18n-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "TRANSLATIONS"
id = "YOUR_KV_NAMESPACE_ID"
preview_id = "YOUR_KV_PREVIEW_ID"
```

```bash
# Upload locale bundles
wrangler kv:key put --binding=TRANSLATIONS "en" "$(cat locales/en.json)"
wrangler kv:key put --binding=TRANSLATIONS "fr" "$(cat locales/fr.json)"
wrangler kv:key put --binding=TRANSLATIONS "fr-CA" "$(cat locales/fr-CA.json)"

# Install deps
npm install @formatjs/intl-messageformat
npm install -D esbuild
```

```json
// locales/en.json
{
  "cart.items": "{count, plural, one {# item} other {# items}}",
  "greeting": "Hello, {name}!",
  "gender": "{gender, select, male {He} female {She} other {They}} liked your post."
}
```

```json
// locales/fr.json
{
  "cart.items": "{count, plural, one {# article} other {# articles}}",
  "greeting": "Bonjour, {name} !",
  "gender": "{gender, select, male {Il} female {Elle} other {Elles}} a aimé votre publication."
}
```

```json
// locales/fr-CA.json
{
  "greeting": "Allo, {name} !"
}
```

---

## Implementation

```typescript
// src/index.ts
import IntlMessageFormat from '@formatjs/intl-messageformat';

export interface Env {
  TRANSLATIONS: KVNamespace;
}

type Messages = Record<string, string>;

/**
 * Build a fallback chain for a locale.
 * fr-CA -> ["fr-CA", "fr", "en"]
 */
function buildFallbackChain(locale: string): string[] {
  const chain: string[] = [locale];
  const hyphen = locale.indexOf('-');
  if (hyphen !== -1) chain.push(locale.slice(0, hyphen));
  if (!chain.includes('en')) chain.push('en');
  return chain;
}

/**
 * Load messages from KV with fallback chain.
 * More specific locales override less specific ones.
 */
async function loadMessages(
  kv: KVNamespace,
  locale: string,
  cache: Cache,
  cacheKey: string,
): Promise<Messages> {
  const cached = await cache.match(new Request(cacheKey));
  if (cached) {
    return cached.json<Messages>();
  }

  const chain = buildFallbackChain(locale);
  // Load from least specific to most specific so overrides work correctly
  const merged: Messages = {};
  for (const lang of [...chain].reverse()) {
    const raw = await kv.get(lang);
    if (raw) {
      try {
        const msgs = JSON.parse(raw) as Messages;
        Object.assign(merged, msgs);
      } catch {
        console.error(`Failed to parse locale bundle for ${lang}`);
      }
    }
  }

  // Cache merged result for 1 hour
  const response = new Response(JSON.stringify(merged), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600',
    },
  });
  await cache.put(new Request(cacheKey), response.clone());

  return merged;
}

/**
 * Format a single ICU message key.
 */
function format(
  messages: Messages,
  key: string,
  values: Record<string, string | number> = {},
  locale: string = 'en',
): string {
  const pattern = messages[key];
  if (!pattern) return key; // graceful degradation
  try {
    const mf = new IntlMessageFormat(pattern, locale);
    return mf.format(values) as string;
  } catch (err) {
    console.error(`ICU format error for key "${key}": ${err}`);
    return key;
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Resolve locale from Accept-Language header
    const acceptLang = request.headers.get('Accept-Language') ?? 'en';
    const locale = acceptLang.split(',')[0].trim().split(';')[0].trim() || 'en';

    const cache = caches.default;
    const cacheKey = `https://i18n-cache.internal/messages/${locale}`;
    const messages = await loadMessages(env.TRANSLATIONS, locale, cache, cacheKey);

    if (url.pathname === '/translate') {
      const key = url.searchParams.get('key') ?? '';
      const valuesParam = url.searchParams.get('values');
      let values: Record<string, string | number> = {};
      if (valuesParam) {
        try {
          values = JSON.parse(valuesParam);
        } catch { /* ignore malformed values */ }
      }

      const result = format(messages, key, values, locale);
      return Response.json({ key, locale, result });
    }

    // Demo endpoint: return all messages for locale
    return Response.json({ locale, messages });
  },
};
```

---

## Integration / Testing

```bash
# Run dev server
npx wrangler dev

# Test plural rule — English
curl 'http://localhost:8787/translate?key=cart.items&values=%7B%22count%22%3A1%7D' \
  -H 'Accept-Language: en'
# {"key":"cart.items","locale":"en","result":"1 item"}

# Test plural rule — French
curl 'http://localhost:8787/translate?key=cart.items&values=%7B%22count%22%3A3%7D' \
  -H 'Accept-Language: fr'
# {"key":"cart.items","locale":"fr","result":"3 articles"}

# Test fallback: fr-CA falls back to fr for missing key
curl 'http://localhost:8787/translate?key=gender&values=%7B%22gender%22%3A%22female%22%7D' \
  -H 'Accept-Language: fr-CA'
# Returns the fr translation (fr-CA bundle doesn't define "gender")

# Test fr-CA override for greeting
curl 'http://localhost:8787/translate?key=greeting&values=%7B%22name%22%3A%22Marie%22%7D' \
  -H 'Accept-Language: fr-CA'
# {"key":"greeting","locale":"fr-CA","result":"Allo, Marie !"}
```

```typescript
// test/i18n.test.ts (Vitest + @cloudflare/vitest-pool-workers)
import { env } from 'cloudflare:test';
import { SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';

beforeAll(async () => {
  await env.TRANSLATIONS.put('en', JSON.stringify({
    'cart.items': '{count, plural, one {# item} other {# items}}',
  }));
  await env.TRANSLATIONS.put('fr', JSON.stringify({
    'cart.items': '{count, plural, one {# article} other {# articles}}',
  }));
});

describe('ICU MessageFormat', () => {
  it('formats singular in English', async () => {
    const res = await SELF.fetch(
      'http://example.com/translate?key=cart.items&values=%7B%22count%22%3A1%7D',
      { headers: { 'Accept-Language': 'en' } },
    );
    const body = await res.json<{ result: string }>();
    expect(body.result).toBe('1 item');
  });

  it('formats plural in French', async () => {
    const res = await SELF.fetch(
      'http://example.com/translate?key=cart.items&values=%7B%22count%22%3A5%7D',
      { headers: { 'Accept-Language': 'fr' } },
    );
    const body = await res.json<{ result: string }>();
    expect(body.result).toBe('5 articles');
  });
});
```

---

## Anti-patterns
- **Bundling locale JSON into Worker script** — inflates script size (1 MB compressed limit) and requires redeployment to update copy.
- **Parsing ICU patterns on every request without caching** — `new IntlMessageFormat(pattern)` compiles the AST; cache compiled instances in a `Map` keyed by `locale:key` in module-level scope.
- **Using `Accept-Language` verbatim as a KV key** — the header can contain quality values (`fr-CA;q=0.9,fr;q=0.8`); always parse and normalise before lookup.
- **Ignoring KV eventual consistency** — a freshly written locale bundle may not be visible at all PoPs for up to 60 seconds; invalidate cached responses after a write via Cache API purge.

---

## Gotchas
- `@formatjs/intl-messageformat` depends on `Intl.PluralRules` which is available in the Workers runtime but **not** in `workerd` local mode prior to compatibility date `2023-03-01`.
- KV `get()` returns `null` for missing keys, not an empty string — always null-check before `JSON.parse`.
- The Workers Cache API requires a `Request` object as the key, not a plain string.
- `buildFallbackChain('zh-Hant-TW')` will only strip one segment; for three-part locales you need a loop, not a single `indexOf('-')`.

---

## Verification

```bash
# Confirm KV namespace has all expected keys
wrangler kv:key list --binding=TRANSLATIONS

# Check cache hit via Cloudflare dashboard Cache Analytics
# or inspect CF-Cache-Status header in staging
curl -I 'https://your-worker.workers.dev/' -H 'Accept-Language: fr'
# Expect: CF-Cache-Status: HIT on second request

# Deploy and run integration test against staging
npx wrangler deploy --env staging
npx vitest run --environment staging
```

---

## Related
- `workers-currency-number-format-cf-country.md`
- `workers-date-time-format-timezone-d1.md`
- `workers-multilingual-sitemap-xml-d1.md`

---

## Sources
- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- FormatJS IntlMessageFormat — https://formatjs.io/docs/intl-messageformat
- ICU Message Syntax — https://unicode-org.github.io/icu/userguide/format_parse/messages/
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
