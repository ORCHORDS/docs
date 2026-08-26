# Pluralisation with `Intl.PluralRules` in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves UI copy in multiple languages and counts like "1 item" vs "2 items" break in Arabic or Russian because those languages have more than two plural forms. You need a reliable, runtime-correct way to select the right string without shipping a third-party i18n library that bloats the Worker bundle.

---

## Context

Cloudflare Workers expose the full `Intl` API including `Intl.PluralRules`, which implements the CLDR plural rules for every BCP 47 locale. Russian uses four forms (`one`, `few`, `many`, `other`) and Arabic uses six (`zero`, `one`, `two`, `few`, `many`, `other`). Translation strings for each plural category are stored as a JSON object in KV under a key like `translations:<locale>`. The `t()` helper hydrates the correct string and interpolates variables at the point of use. Because `Intl.PluralRules` is synchronous and CPU-cheap, it does not add measurable latency to a Worker response.

---

## Section 1 — KV translation shape

Store translations as a nested JSON blob. Plural entries live under a `_plural` sub-key.

```json
// KV key: translations:ar
{
  "item_count": {
    "_plural": true,
    "zero":  "لا عناصر",
    "one":   "عنصر واحد",
    "two":   "عنصران",
    "few":   "{{count}} عناصر",
    "many":  "{{count}} عنصرًا",
    "other": "{{count}} عنصر"
  },
  "item_count_ru": {
    "_plural": true,
    "one":   "{{count}} элемент",
    "few":   "{{count}} элемента",
    "many":  "{{count}} элементов",
    "other": "{{count}} элемента"
  }
}

// KV key: translations:en
{
  "item_count": {
    "_plural": true,
    "one":  "{{count}} item",
    "other": "{{count}} items"
  }
}
```

---

## Section 2 — Worker implementation

```typescript
// src/i18n/plural.ts
export interface Env {
  TRANSLATIONS: KVNamespace;
}

type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

type PluralEntry = {
  _plural: true;
} & Partial<Record<PluralCategory, string>>;

type TranslationMap = Record<string, string | PluralEntry>;

// Module-level cache so repeated requests in the same isolate avoid KV reads.
const translationCache = new Map<string, TranslationMap>();

async function loadTranslations(
  kv: KVNamespace,
  locale: string
): Promise<TranslationMap> {
  if (translationCache.has(locale)) {
    return translationCache.get(locale)!;
  }
  const raw = await kv.get(`translations:${locale}`, { type: 'json' });
  const map: TranslationMap = (raw as TranslationMap) ?? {};
  translationCache.set(locale, map);
  return map;
}

/**
 * Translate a key. If the entry has `_plural: true`, `vars.count` must be
 * provided and will be used to select the correct CLDR plural category.
 */
export async function t(
  kv: KVNamespace,
  locale: string,
  key: string,
  vars: Record<string, string | number> = {}
): Promise<string> {
  // Attempt the requested locale, then fall back to base tag, then 'en'.
  const chain = buildLocaleChain(locale);
  let entry: string | PluralEntry | undefined;
  let resolvedMap: TranslationMap | undefined;

  for (const loc of chain) {
    const map = await loadTranslations(kv, loc);
    if (key in map) {
      entry = map[key];
      resolvedMap = map;
      break;
    }
  }

  if (entry === undefined) {
    // Last resort: return the raw key so the UI degrades gracefully.
    console.warn(`[i18n] missing key "${key}" for locale chain ${chain.join(' → ')}`);
    return key;
  }

  // Scalar string — no plural handling needed.
  if (typeof entry === 'string') {
    return interpolate(entry, vars);
  }

  // Plural entry — resolve the correct category.
  if (entry._plural) {
    const count = Number(vars.count ?? 0);
    const pr = new Intl.PluralRules(locale);
    const category = pr.select(count) as PluralCategory;
    // Fall back through categories if this locale doesn't define the exact one.
    const text =
      entry[category] ??
      entry['other'] ??
      key;
    return interpolate(text, { ...vars, count });
  }

  return key;
}

function interpolate(
  template: string,
  vars: Record<string, string | number>
): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) =>
    name in vars ? String(vars[name]) : `{{${name}}}`
  );
}

function buildLocaleChain(locale: string): string[] {
  const chain: string[] = [locale];
  // e.g. 'pt-BR' → add 'pt'
  const base = locale.split('-')[0];
  if (base !== locale) chain.push(base);
  if (base !== 'en') chain.push('en');
  return chain;
}
```

---

## Section 3 — Request handler

```typescript
// src/index.ts
import { t } from './i18n/plural';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locale = url.searchParams.get('locale') ?? 'en';
    const count = parseInt(url.searchParams.get('count') ?? '1', 10);

    const label = await t(env.TRANSLATIONS, locale, 'item_count', { count });

    return Response.json({ locale, count, label });
  },
};

// Example outputs:
// locale=ar&count=3  → { label: '3 عناصر' }   (few)
// locale=ar&count=11 → { label: '11 عنصرًا' }  (many)
// locale=ru&count=1  → { label: '1 элемент' }  (one)
// locale=ru&count=5  → { label: '5 элементов' } (many)
// locale=en&count=2  → { label: '2 items' }     (other)
```

---

## Anti-patterns

- **Hard-coding plural forms as `if count === 1`** — Breaks for every language with more than two forms; always delegate to `Intl.PluralRules`.
- **Creating a new `Intl.PluralRules` instance per request inside a hot loop** — The constructor is cheap but not free; cache it keyed by locale if called thousands of times in one request.
- **Storing plural strings as an array indexed by position** — Position-indexed arrays have no semantic meaning across locales; use named CLDR categories (`one`, `few`, `many`, etc.) as object keys.
- **Skipping the locale chain fallback** — A missing `pt-BR` translation should silently fall through to `pt` then `en`; throwing an error breaks the entire page for one missing string.

---

## Gotchas

- `Intl.PluralRules.select()` returns the *category name* (`'one'`, `'few'`, …), not an index. Map that string to your object key, not an array position.
- Arabic has a `zero` category but English does not; always provide `other` as the mandatory fallback category in every locale's plural entry.
- The Workers runtime does NOT include `Intl.PluralRules` ordinal support in all older compatibility dates — set `compatibility_date = "2023-03-01"` or later in `wrangler.toml` to guarantee full CLDR data.
- KV `get` with `type: 'json'` returns `null` when the key is absent, not an empty object; guard with `?? {}`.
- Module-level Maps survive across requests in the same isolate; they do not survive a cold start or an isolate eviction. Do not rely on them as a primary cache — treat them as a warm-request optimisation only.

---

## Verification

```bash
# 1. Seed KV in local dev
npx wrangler kv:key put --binding=TRANSLATIONS 'translations:ar' \
  '{"item_count":{"_plural":true,"zero":"لا عناصر","one":"عنصر واحد","two":"عنصران","few":"{{count}} عناصر","many":"{{count}} عنصرًا","other":"{{count}} عنصر"}}' \
  --local

npx wrangler kv:key put --binding=TRANSLATIONS 'translations:en' \
  '{"item_count":{"_plural":true,"one":"{{count}} item","other":"{{count}} items"}}' \
  --local

# 2. Run dev server
npx wrangler dev

# 3. Smoke-test plural categories
curl 'http://localhost:8787/?locale=ar&count=0'   # zero
curl 'http://localhost:8787/?locale=ar&count=1'   # one
curl 'http://localhost:8787/?locale=ar&count=2'   # two
curl 'http://localhost:8787/?locale=ar&count=5'   # few
curl 'http://localhost:8787/?locale=ar&count=11'  # many
curl 'http://localhost:8787/?locale=ru&count=1'   # one
curl 'http://localhost:8787/?locale=ru&count=3'   # few
curl 'http://localhost:8787/?locale=ru&count=11'  # many
curl 'http://localhost:8787/?locale=en&count=1'   # one
curl 'http://localhost:8787/?locale=en&count=2'   # other
```

---

## Related

- `translation-key-missing-fallback-kv-workers.md`
- `locale-negotiation-accept-language-workers.md`

---

## Sources

- MDN Intl.PluralRules — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- CLDR Plural Rules — https://cldr.unicode.org/index/cldr-spec/plural-rules
- Cloudflare Workers Intl support — https://developers.cloudflare.com/workers/runtime-apis/web-standards/
