# Using Intl.DisplayNames in Workers to Render Locale Labels in the User's Language

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your UI needs to render a language selector, a currency picker, or a region dropdown where each option is labeled in the _viewer's_ own language — `"Français"` instead of `"French"` for a French-speaking user, `"日本語"` for a Japanese speaker. Hard-coding translation strings for every combination of language × displayed language is intractable; `Intl.DisplayNames` solves this natively.

## Context

- Cloudflare Workers serving an HTML or JSON API response
- User's preferred locale derived from `Accept-Language` header
- `Intl.DisplayNames` available in V8 runtime (no npm package needed)
- KV caching the serialised display-name list per `(type, locale)` pair with a 24-hour TTL to avoid redundant computation on every request

---

## Section 1: Extracting and Normalising the User Locale

```typescript
// src/lib/accept-locale.ts

/**
 * Parse the Accept-Language header and return the best BCP-47 locale tag
 * that Intl.DisplayNames supports, falling back to 'en'.
 *
 * Example: "fr-CH, fr;q=0.9, en;q=0.8" → 'fr-CH'
 */
export function preferredLocale(acceptLanguage: string | null): string {
  if (!acceptLanguage) return 'en';

  const tags = acceptLanguage
    .split(',')
    .map((part) => {
      const [tag, q] = part.trim().split(';q=');
      return { tag: tag.trim(), q: parseFloat(q ?? '1') };
    })
    .sort((a, b) => b.q - a.q)
    .map((e) => e.tag);

  for (const tag of tags) {
    try {
      // Validate: Intl throws on unrecognised tags
      new Intl.DisplayNames([tag], { type: 'language' });
      return tag;
    } catch {
      // Try next
    }
  }
  return 'en';
}
```

---

## Section 2: Building Display-Name Lists with Intl.DisplayNames

```typescript
// src/lib/display-names.ts

export type DisplayNameType = 'language' | 'region' | 'currency' | 'script';

export interface DisplayNameEntry {
  code: string;   // BCP-47 subtag or ISO 4217 currency code
  label: string;  // Localised display name
}

// Canonical lists of codes to label
const LANGUAGE_CODES = [
  'en','fr','de','es','it','pt','ru','zh','ja','ko',
  'ar','hi','bn','tr','pl','nl','sv','da','fi','no',
  'cs','hu','ro','uk','id','ms','th','vi','el','he',
];

const REGION_CODES = [
  'US','GB','FR','DE','ES','IT','JP','CN','KR','BR',
  'AU','CA','IN','MX','RU','ZA','NG','EG','SA','AE',
  'TR','PL','NL','SE','NO','DK','FI','PT','AR','CL',
];

const CURRENCY_CODES = [
  'USD','EUR','GBP','JPY','CNY','KRW','INR','BRL','CAD','AUD',
  'CHF','SEK','NOK','DKK','MXN','SGD','HKD','NZD','ZAR','RUB',
  'TRY','PLN','THB','IDR','HUF','CZK','ILS','AED','SAR','NGN',
];

const CODE_LISTS: Record<DisplayNameType, string[]> = {
  language: LANGUAGE_CODES,
  region:   REGION_CODES,
  currency: CURRENCY_CODES,
  script:   ['Latn','Cyrl','Arab','Hans','Hant','Deva','Hang','Jpan','Grek','Hebr'],
};

/**
 * Build an array of {code, label} entries for the given type and locale.
 * Entries where the runtime returns `undefined` (unknown code) are omitted.
 */
export function buildDisplayNames(
  type: DisplayNameType,
  locale: string,
): DisplayNameEntry[] {
  const dn = new Intl.DisplayNames([locale], {
    type,
    fallback: 'none',   // return undefined instead of the code itself for unknowns
  });

  return CODE_LISTS[type]
    .map((code) => {
      try {
        const label = dn.of(code);
        if (!label) return null;
        return { code, label };
      } catch {
        return null;
      }
    })
    .filter((e): e is DisplayNameEntry => e !== null);
}
```

---

## Section 3: KV-Cached Edge Rendering in a Worker

```typescript
// src/handlers/display-names.ts
import type { Env } from '../types';
import { preferredLocale } from '../lib/accept-locale';
import { buildDisplayNames, type DisplayNameType } from '../lib/display-names';

const KV_TTL = 60 * 60 * 24; // 24 hours
const ALLOWED_TYPES: DisplayNameType[] = ['language', 'region', 'currency', 'script'];

export async function handleDisplayNames(
  request: Request,
  env: Env,
): Promise<Response> {
  const url  = new URL(request.url);
  const type = (url.searchParams.get('type') ?? 'language') as DisplayNameType;

  if (!ALLOWED_TYPES.includes(type)) {
    return Response.json({ error: `type must be one of: ${ALLOWED_TYPES.join(', ')}` }, { status: 400 });
  }

  const locale = preferredLocale(request.headers.get('Accept-Language'));
  const kvKey  = `display-names:${type}:${locale}`;

  // 1. KV cache hit?
  const cached = await env.KV.get(kvKey, 'json') as { locale: string; type: string; entries: unknown[] } | null;
  if (cached) {
    return Response.json(cached, {
      headers: { 'X-Cache': 'HIT', 'Cache-Control': 'public, max-age=3600' },
    });
  }

  // 2. Compute
  const entries = buildDisplayNames(type, locale);
  const payload = { locale, type, entries };

  // 3. Store in KV (fire-and-forget — don't block response)
  const ctx = (globalThis as { ctx?: ExecutionContext }).ctx;
  const store = env.KV.put(kvKey, JSON.stringify(payload), { expirationTtl: KV_TTL });
  if (ctx) {
    ctx.waitUntil(store);
  } else {
    await store;
  }

  return Response.json(payload, {
    headers: { 'X-Cache': 'MISS', 'Cache-Control': 'public, max-age=3600' },
  });
}

// src/workers/api.ts — wire up the handler
import { handleDisplayNames } from '../handlers/display-names';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Make ctx available to handler (simple approach)
    (globalThis as { ctx?: ExecutionContext }).ctx = ctx;

    const url = new URL(request.url);
    if (url.pathname === '/i18n/display-names') return handleDisplayNames(request, env);
    return new Response('Not Found', { status: 404 });
  },
};
```

Wrangler config:

```toml
name = "i18n-worker"
main = "src/workers/api.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "KV"
id = "<your-kv-namespace-id>"
preview_id = "<your-preview-kv-id>"
```

---

## Anti-patterns

- **Hard-coding localised strings in source code** — unmaintainable across 30+ languages; `Intl.DisplayNames` covers them all natively.
- **Caching per `Accept-Language` header verbatim** — `fr-CH, fr;q=0.9` and `fr;q=1.0, fr-CH;q=0.8` resolve to the same locale but produce different KV keys. Always normalise to the resolved BCP-47 tag first.
- **Calling `Intl.DisplayNames` inside a hot render loop** — instantiate once per request (or once per cache miss), not once per list item.
- **Not handling `fallback: 'none'`** — without it, unknown codes return the code itself (`'XYZ'`) masquerading as a valid label.

## Gotchas

- `Intl.DisplayNames` for `type: 'currency'` uses ISO 4217 codes (`'USD'`), not symbols (`'$'`). To get the symbol use `Intl.NumberFormat` with `style: 'currency'` and extract the symbol part.
- Some locales (`ar`, `he`) return display names in RTL scripts; ensure your UI wraps each label with `dir="auto"` or an explicit `dir` attribute.
- `fallback: 'none'` is a newer option; older V8 versions may ignore it and fall back to the code string. Test with `wrangler dev` using the target `compatibility_date`.
- KV `get` returns `null` for missing keys and for keys whose TTL has expired — both are cache misses and trigger recomputation.
- `ctx.waitUntil` keeps the Worker alive after the response is sent; without it (e.g. in tests), `await store` is necessary to avoid losing the KV write.

---

## Verification

```bash
# Create KV namespace
npx wrangler kv namespace create I18N_KV
# Copy the id into wrangler.toml

# Start dev
npx wrangler dev

# Language names in French
curl -s -H 'Accept-Language: fr' \
  'http://localhost:8787/i18n/display-names?type=language' | jq '.entries[:5]'
# Expected: [{"code":"en","label":"anglais"},{"code":"fr","label":"français"},...]

# Currency names in Japanese
curl -s -H 'Accept-Language: ja' \
  'http://localhost:8787/i18n/display-names?type=currency' | jq '.entries[:3]'
# Expected: [{"code":"USD","label":"米ドル"},{"code":"EUR","label":"ユーロ"},...]

# Second request should be a cache hit
curl -s -H 'Accept-Language: fr' \
  'http://localhost:8787/i18n/display-names?type=language' -I | grep X-Cache
# Expected: X-Cache: HIT
```

---

## Related

- `documentation/categories/i18n/workers-timezone-aware-scheduling-intl.md`
- `documentation/categories/i18n/workers-collator-locale-sort-d1-sqlite.md`
- `documentation/categories/i18n/workers-locale-aware-url-slug-generation.md`
- `documentation/categories/i18n/workers-script-detection-unicode-block.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DisplayNames
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
