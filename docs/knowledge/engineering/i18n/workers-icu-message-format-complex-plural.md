# Complex Plural/Select Formatting with ICU MessageFormat in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves localised UI strings that contain gender-sensitive and
count-sensitive text such as:

> "She added 1 photo to her album" / "He added 3 photos to his album"

Simple string interpolation breaks for Slavic, Arabic, or any language with
more than two plural forms. You need ICU MessageFormat with `plural` and
`select` combined, parsed once at deploy time and cached in KV.

## Context

- Runtime: Cloudflare Workers (V8 isolates, no Node built-ins)
- Parser: `@formatjs/icu-messageformat-parser` (pure-JS, edge-safe)
- Formatter: `intl-messageformat` (re-uses the parsed AST)
- Storage: Cloudflare KV for the serialised AST cache
- Languages covered: English, Polish, Arabic (three-form + RTL handled elsewhere)

---

## 1. Installing the Right Packages

Only the parser + formatter are needed; the full `@formatjs` suite is tree-shakeable.

```bash
npm install @formatjs/icu-messageformat-parser intl-messageformat
```

Add to `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "I18N_CACHE"
id      = "<your-kv-namespace-id>"
```

---

## 2. Defining ICU Messages

```typescript
// src/messages.ts
export const MESSAGES: Record<string, Record<string, string>> = {
  en: {
    photoAdded:
      `{gender, select,
         female {{count, plural,
                  one  {She added # photo to her album.}
                  other{She added # photos to her album.}}}
         male   {{count, plural,
                  one  {He added # photo to his album.}
                  other{He added # photos to his album.}}}
         other  {{count, plural,
                  one  {They added # photo to their album.}
                  other{They added # photos to their album.}}}}`
  },
  pl: {
    // Polish has 4 plural forms: one, few, many, other
    photoAdded:
      `{gender, select,
         female {{count, plural,
                  one    {Ona dodała # zdjęcie do swojego albumu.}
                  few    {Ona dodała # zdjęcia do swojego albumu.}
                  many   {Ona dodała # zdjęć do swojego albumu.}
                  other  {Ona dodała # zdjęcia do swojego albumu.}}}
         male   {{count, plural,
                  one    {On dodał # zdjęcie do swojego albumu.}
                  few    {On dodał # zdjęcia do swojego albumu.}
                  many   {On dodał # zdjęć do swojego albumu.}
                  other  {On dodał # zdjęcia do swojego albumu.}}}
         other  {{count, plural,
                  one    {Dodano # zdjęcie do albumu.}
                  few    {Dodano # zdjęcia do albumu.}
                  many   {Dodano # zdjęć do albumu.}
                  other  {Dodano # zdjęć do albumu.}}}}`
  }
};
```

---

## 3. Parsing AST and Caching in KV

Parse once during a cold start; write the serialised AST to KV so subsequent
isolates skip parsing entirely.

```typescript
// src/icu-cache.ts
import { parse, type MessageFormatElement } from '@formatjs/icu-messageformat-parser';

export interface Env {
  I18N_CACHE: KVNamespace;
}

type AstMap = Record<string, MessageFormatElement[]>;

/**
 * Returns parsed AST for every message in `locale`, using KV as a
 * write-through cache. TTL: 1 hour (messages change at deploy time only).
 */
export async function getLocaleAst(
  locale: string,
  rawMessages: Record<string, string>,
  env: Env
): Promise<AstMap> {
  const cacheKey = `icu-ast:${locale}`;

  // 1. Try KV cache first
  const cached = await env.I18N_CACHE.get<AstMap>(cacheKey, 'json');
  if (cached) return cached;

  // 2. Parse all messages for this locale
  const ast: AstMap = {};
  for (const [key, pattern] of Object.entries(rawMessages)) {
    ast[key] = parse(pattern, { captureLocation: false });
  }

  // 3. Write-through to KV (fire-and-forget — don't block the response)
  env.I18N_CACHE.put(cacheKey, JSON.stringify(ast), {
    expirationTtl: 3600
  });

  return ast;
}
```

---

## 4. Formatting Messages at Request Time

```typescript
// src/formatter.ts
import IntlMessageFormat from 'intl-messageformat';
import type { MessageFormatElement } from '@formatjs/icu-messageformat-parser';

type AstMap = Record<string, MessageFormatElement[]>;

/**
 * Format a single ICU message from a pre-parsed AST map.
 * Values can include numbers, strings, and React/HTML elements if needed.
 */
export function formatMessage(
  astMap: AstMap,
  key: string,
  locale: string,
  values: Record<string, string | number>
): string {
  const ast = astMap[key];
  if (!ast) throw new Error(`Missing ICU message key: ${key}`);

  // IntlMessageFormat accepts a pre-parsed AST directly — no re-parsing
  const mf = new IntlMessageFormat(ast, locale);
  return mf.format(values) as string;
}
```

---

## 5. Worker Entry Point

```typescript
// src/index.ts
import { getLocaleAst } from './icu-cache';
import { formatMessage } from './formatter';
import { MESSAGES } from './messages';

export interface Env {
  I18N_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Derive locale from path prefix, e.g. /pl/...
    const localePart = url.pathname.split('/')[1];
    const locale = MESSAGES[localePart] ? localePart : 'en';
    const messages = MESSAGES[locale];

    // Load (or build) the AST for this locale
    const astMap = await getLocaleAst(locale, messages, env);

    // Demo: read gender and count from query params
    const gender = url.searchParams.get('gender') ?? 'other';
    const count  = parseInt(url.searchParams.get('count') ?? '1', 10);

    const text = formatMessage(astMap, 'photoAdded', locale, { gender, count });

    return new Response(JSON.stringify({ locale, text }), {
      headers: { 'Content-Type': 'application/json; charset=utf-8' }
    });
  }
};
```

---

## Anti-patterns

- **Parsing on every request** — `parse()` is CPU-bound; always cache the AST.
- **Using `JSON.stringify` on the raw pattern string** — the parser output is
  an array of typed nodes; always serialise the AST, not the source string.
- **Assuming two plural forms** — English has two but many languages have up to
  six. Always declare all CLDR plural categories your translations cover.
- **Importing full `@formatjs/intl`** — it pulls in React and heavy polyfills.
  Use only `@formatjs/icu-messageformat-parser` + `intl-messageformat`.

## Gotchas

- KV `get` with `'json'` returns `null` on cache miss, not an empty object.
  Always null-check before using the cached value.
- `IntlMessageFormat` uses `Intl.PluralRules` under the hood. Workers runtime
  ships V8's full `Intl` — no polyfill needed.
- The `#` shorthand in plural blocks expands to the numeric value formatted
  with the locale's default number format. Pass a pre-formatted string if you
  need a custom number style.
- KV TTL is per-key; if you push new translations, also delete or overwrite the
  KV entry, or set a short enough TTL (`expirationTtl`).

## Verification

```bash
# Local dev
npx wrangler dev src/index.ts

# English, female, 1 photo
curl 'http://localhost:8787/en/?gender=female&count=1'
# → {"locale":"en","text":"She added 1 photo to her album."}

# Polish, male, 3 photos (few form)
curl 'http://localhost:8787/pl/?gender=male&count=3'
# → {"locale":"pl","text":"On dodał 3 zdjęcia do swojego albumu."}

# Polish, other, 5 photos (many form)
curl 'http://localhost:8787/pl/?gender=other&count=5'
# → {"locale":"pl","text":"Dodano 5 zdjęć do albumu."}

# Confirm KV cache hit on second request (latency drop)
curl -w '%{time_total}\n' 'http://localhost:8787/en/?gender=female&count=2'
```

## Related

- `workers-bidirectional-text-rtl-html-rewriter.md` — RTL handling for Arabic
- `workers-number-system-arabic-indic.md` — non-Latin numeral systems
- `workers-translation-missing-key-alert-d1.md` — detecting missing ICU keys

## Sources

- https://formatjs.io/docs/core-concepts/icu-syntax
- https://unicode-org.github.io/cldr/ldml/tr35-numbers.html#Language_Plural_Rules
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/#v8-built-ins
