# ICU MessageFormat Pluralization for Complex Languages (Polish, Arabic, Russian) in Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Your Workers-powered application serves users in Polish, Arabic, and Russian. Simple `{count} items` strings work fine in English, but Polish needs six plural forms, Arabic needs six (with different ranges), and Russian needs three — none of which matches the two-form English model. A naive `count === 1 ? singular : plural` branch ships wrong strings to every non-English speaker. You need correct pluralization at the edge, without bundling a full ICU runtime or making per-request calls to an external translation service.

---

## Context

ICU MessageFormat is the industry-standard message syntax used by Android, iOS, Java, and most enterprise l10n toolchains. Its `{count, plural, …}` selector delegates to CLDR plural rules, which classify numbers into categories (`zero`, `one`, `two`, `few`, `many`, `other`) per locale. The mapping from number to category is non-trivial:

- **Polish (pl):** `one` = 1; `few` = 2–4 and 22–24 and … (ends in 2–4, not 12–14); `many` = all other integers; `other` = fractions.
- **Russian (ru):** `one` = ends in 1 but not 11; `few` = ends in 2–4 but not 12–14; `many` = everything else; `other` = fractions.
- **Arabic (ar):** six categories including `zero` (0), `one` (1), `two` (2), `few` (3–10), `many` (11–99), `other` (fractions and 100+).

`@formatjs/intl-messageformat` implements this via `Intl.PluralRules`, which is available in the V8 runtime used by Cloudflare Workers. The challenge is keeping bundle size small, avoiding hot-path compilation overhead, and serializing compiled rules to KV so each isolate does not re-parse message strings on every request.

---

## Section 1 — Installing and Bundling `@formatjs/intl-messageformat`

```bash
npm install @formatjs/intl-messageformat
```

The package tree-shakes to ~30 kB (gzipped ~10 kB) when you import only the core and explicitly list locales. Workers have a 1 MB compressed script limit, so avoid the `intl-messageformat/src/core` mega-import:

```typescript
// worker/src/lib/mf.ts
import IntlMessageFormat from "@formatjs/intl-messageformat";

// Explicitly import only the locale data you need — this prevents
// the full CLDR data set from being bundled.
import "@formatjs/intl-pluralrules/locale-data/ar";
import "@formatjs/intl-pluralrules/locale-data/pl";
import "@formatjs/intl-pluralrules/locale-data/ru";

export { IntlMessageFormat };
```

In `wrangler.toml`, set:

```toml
[build]
  command = "npm run build"

[build.upload]
  format = "modules"
```

Verify the bundle size before deploying:

```bash
npx wrangler deploy --dry-run --outdir dist
du -sh dist/worker.js
```

---

## Section 2 — Authoring ICU Messages for Polish, Arabic, and Russian

ICU MessageFormat requires every CLDR plural category used by a locale to be either explicitly listed or collapsed into `other`. Omitting a category is not an error — the library falls through to `other` — but it produces wrong strings.

```typescript
// messages/pl.ts  — Polish (6 CLDR categories; "other" covers fractions)
export const messages = {
  itemCount: `{count, plural,
    one   {# przedmiot}
    few   {# przedmioty}
    many  {# przedmiotów}
    other {# przedmiotu}
  }`,

  // Ordinal: "1st", "2nd" etc. — Polish uses "other" for all ordinals
  rankLabel: `{rank, selectordinal,
    other {# miejsce}
  }`,
};

// messages/ar.ts  — Arabic (all 6 categories meaningful)
export const messages = {
  itemCount: `{count, plural,
    zero  {لا عناصر}
    one   {عنصر واحد}
    two   {عنصران}
    few   {# عناصر}
    many  {# عنصرًا}
    other {# عنصر}
  }`,
};

// messages/ru.ts  — Russian (3 integer categories + "other" for fractions)
export const messages = {
  itemCount: `{count, plural,
    one   {# товар}
    few   {# товара}
    many  {# товаров}
    other {# товара}
  }`,
};
```

Key rule: always include `other` — it is mandatory in ICU syntax and covers CLDR categories not explicitly listed.

---

## Section 3 — Pre-Compiling Messages and Serializing ASTs to KV

Parsing ICU message strings on every request adds ~0.5–2 ms per message. Instead, compile the AST at build time, serialize it to JSON, and store in Workers KV. Each isolate deserializes the JSON and passes the pre-parsed AST directly to `IntlMessageFormat`, skipping the parser entirely.

```typescript
// scripts/compile-messages.ts  (runs at build time, not in the Worker)
import { parse } from "@formatjs/icu-messageformat-parser";
import { readFileSync, writeFileSync } from "fs";

const locales = ["ar", "pl", "ru"];

for (const locale of locales) {
  const raw = JSON.parse(
    readFileSync(`messages/${locale}.json`, "utf-8")
  ) as Record<string, string>;

  const compiled: Record<string, unknown> = {};
  for (const [key, pattern] of Object.entries(raw)) {
    compiled[key] = parse(pattern, { locale });
  }

  writeFileSync(
    `dist/messages-${locale}.json`,
    JSON.stringify(compiled)
  );
}
```

Upload during deployment:

```bash
for locale in ar pl ru; do
  wrangler kv:key put \
    --binding=TRANSLATIONS \
    "messages:${locale}" \
    --path "dist/messages-${locale}.json"
done
```

In the Worker, consume pre-compiled ASTs:

```typescript
// worker/src/lib/translate.ts
import { IntlMessageFormat } from "./mf";
import type { MessageFormatElement } from "@formatjs/icu-messageformat-parser";

type CompiledCatalog = Record<string, MessageFormatElement[]>;

const catalogCache = new Map<string, CompiledCatalog>();

async function getCatalog(
  kv: KVNamespace,
  locale: string
): Promise<CompiledCatalog> {
  if (catalogCache.has(locale)) return catalogCache.get(locale)!;

  const raw = await kv.get(`messages:${locale}`, "json") as CompiledCatalog | null;
  if (!raw) throw new Error(`No catalog for locale: ${locale}`);

  catalogCache.set(locale, raw);
  return raw;
}

export async function t(
  kv: KVNamespace,
  locale: string,
  key: string,
  values: Record<string, string | number>
): Promise<string> {
  const catalog = await getCatalog(kv, locale);
  const ast = catalog[key];
  if (!ast) return key; // fallback: return the key itself

  // Pass the pre-parsed AST to skip compilation
  const mf = new IntlMessageFormat(ast, locale);
  return mf.format(values) as string;
}
```

The in-process `catalogCache` Map persists for the lifetime of the isolate (typically minutes to hours), so the KV read happens only once per isolate per locale.

---

## Section 4 — Cardinal vs. Ordinal Plurals

ICU distinguishes two plural types:

- **Cardinal** (`{n, plural, …}`) — "3 items", "21 items". This is the default.
- **Ordinal** (`{n, selectordinal, …}`) — "1st place", "3rd floor".

CLDR maintains separate rule sets for cardinal and ordinal. Languages differ significantly:

| Locale | Cardinal categories | Ordinal categories |
|--------|--------------------|--------------------|
| `pl`   | one, few, many, other | other (all ordinals use `other`) |
| `ar`   | zero, one, two, few, many, other | other |
| `ru`   | one, few, many, other | other |
| `en`   | one, other | one, two, few, other |

For Russian and Arabic, ordinal pluralization collapses to `other` for all integers. Do not add `one`/`few` ordinal branches for `ru` or `ar` — `Intl.PluralRules` in ordinal mode returns `other` for them, and those branches would be dead code.

```typescript
// Ordinal example — rank display
const ordinalMessages = {
  en: `{rank, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}`,
  // Russian, Arabic, Polish: ordinal = always "other"
  ru: `{rank, selectordinal, other {#-е место}}`,
  ar: `{rank, selectordinal, other {المركز #}}`,
  pl: `{rank, selectordinal, other {# miejsce}}`,
};
```

Use `Intl.PluralRules` in ordinal mode to verify at build time:

```typescript
// Build-time check: confirm CLDR returns expected category
const pr = new Intl.PluralRules("ru", { type: "ordinal" });
console.assert(pr.select(1) === "other", "Russian ordinal 1 must be 'other'");
console.assert(pr.select(21) === "other", "Russian ordinal 21 must be 'other'");
```

---

## Section 5 — Handling Fractions and Range Plurals

The `other` category in ICU covers fractional counts in most Slavic languages. Russian "1.5 товара" uses `other`, not `one`, because the integer `one` rule (`ends in 1, not 11`) does not apply to fractions.

```typescript
// Correct: fractions fall to "other" in Russian
const pr = new Intl.PluralRules("ru");
pr.select(1);    // "one"   → "товар"
pr.select(1.5);  // "other" → "товара"
pr.select(21);   // "many"  → "товаров"
```

For range plurals ("1–5 items"), use `Intl.PluralRules.selectRange()` which is available in V8 (Node 20 / Workers runtime):

```typescript
// Range plural — "1–5 товаров"
const pr = new Intl.PluralRules("ru");
const category = pr.selectRange(1, 5); // "many" in Russian
const mf = new IntlMessageFormat(
  `{count, plural, one {# товар} few {# товара} many {# товаров} other {# товара}}`,
  "ru"
);
// Pass the end-of-range value; ICU uses selectRange internally when
// both `start` and `end` values are provided.
const result = mf.format({ count: 5 });
```

Note: `IntlMessageFormat.format()` does not yet expose a dedicated range-format API — pass the terminal value and rely on `selectRange` in your own format layer if the display pattern requires "1–5 товаров" rather than "5 товаров".

---

## Section 6 — KV TTL Strategy for Compiled Catalogs

Compiled message catalogs rarely change (only on new deploys). Use a long TTL in KV reads and invalidate on deploy:

```typescript
// worker/src/lib/translate.ts — read with cache-control metadata
const { value, metadata } = await kv.getWithMetadata<
  CompiledCatalog,
  { version: string }
>(`messages:${locale}`, "json");

// Store version in a separate key set by CI/CD
const currentVersion = await kv.get("catalog:version");

if (metadata?.version !== currentVersion) {
  // Evict local cache — stale catalog version
  catalogCache.delete(locale);
  return getCatalog(kv, locale); // re-fetch
}
```

In your deploy pipeline:

```bash
# Write version key AFTER uploading all catalog files
VERSION=$(git rev-parse --short HEAD)
wrangler kv:key put --binding=TRANSLATIONS "catalog:version" "$VERSION"
```

This ensures isolates that have cached an old catalog version detect the mismatch on the next request and refresh without a full isolate restart.

---

## Anti-Patterns

- **Runtime ICU parsing on every request.** Compiling ICU strings costs 0.5–2 ms per message. Pre-compile to AST and cache.
- **Hardcoding `count === 1 ? … : …`.** This is wrong for every language with more than two plural forms. Always delegate to CLDR via `Intl.PluralRules` or ICU `plural`.
- **Omitting the `other` category.** ICU throws `SyntaxError: Expected "other"` at parse time if `other` is missing. Always include it.
- **Using the same messages for cardinal and ordinal.** Ordinal rules are separate in CLDR. A Russian ordinal branch `one {#-й}` is dead code — `selectOrdinal("ru", 1)` returns `other`.
- **Bundling all CLDR locale data.** `import "@formatjs/intl-pluralrules"` without a locale filter adds ~200 kB to your bundle. Import only the locales you serve.
- **Relying on `Intl.PluralRules.selectRange` for message formatting.** `IntlMessageFormat` does not yet wire `selectRange` into the `plural` selector. Use it for display-layer logic only.

---

## Gotchas

1. **Arabic `zero` category.** `Intl.PluralRules("ar").select(0)` returns `"zero"`. If your ICU message omits the `zero` branch, the library falls through to `other`, which may produce grammatically incorrect Arabic ("0 عنصر" instead of "لا عناصر"). Always add `zero` for Arabic.
2. **Polish `many` vs `other`.** Polish integers use `one`/`few`/`many`; `other` is for fractions. `pl.select(1.5)` returns `other`. Failing to distinguish produces "1.5 przedmiotu" correctly but "3.0 przedmiotu" instead of the expected "3.0 przedmiotu" — check your fraction display separately.
3. **V8 `Intl.PluralRules` version parity.** Workers runs V8. Verify the CLDR version bundled in V8 matches your `@formatjs/intl-pluralrules` polyfill. Mismatches can cause different category assignments for edge-case numbers. Pin `@formatjs/intl-pluralrules` and test on a Worker instance, not just Node.
4. **KV serialization of BigInt.** If count values come from a D1 `INTEGER` column and you read them as BigInt in Workers, `JSON.stringify` will throw. Cast to `Number` before passing to `IntlMessageFormat`.
5. **Hot isolate cache invalidation.** The in-process `Map` cache is per-isolate. After a deploy, old isolates may serve stale catalogs for several minutes until they are evicted. Use the version-check pattern in Section 6.

---

## Verification

```typescript
// Test suite — run with `wrangler dev` or a local Jest/Vitest Worker harness
import { IntlMessageFormat } from "@formatjs/intl-messageformat";
import "@formatjs/intl-pluralrules/locale-data/ar";
import "@formatjs/intl-pluralrules/locale-data/pl";
import "@formatjs/intl-pluralrules/locale-data/ru";

const cases = [
  // Polish
  { locale: "pl", msg: `{n, plural, one {# przedmiot} few {# przedmioty} many {# przedmiotów} other {# przedmiotu}}`, n: 1,    expected: "1 przedmiot"    },
  { locale: "pl", msg: `{n, plural, one {# przedmiot} few {# przedmioty} many {# przedmiotów} other {# przedmiotu}}`, n: 3,    expected: "3 przedmioty"   },
  { locale: "pl", msg: `{n, plural, one {# przedmiot} few {# przedmioty} many {# przedmiotów} other {# przedmiotu}}`, n: 5,    expected: "5 przedmiotów"  },
  { locale: "pl", msg: `{n, plural, one {# przedmiot} few {# przedmioty} many {# przedmiotów} other {# przedmiotu}}`, n: 22,   expected: "22 przedmioty"  },
  // Arabic
  { locale: "ar", msg: `{n, plural, zero {لا} one {واحد} two {اثنان} few {# قليلة} many {# كثير} other {# أخرى}}`, n: 0,    expected: "لا"             },
  { locale: "ar", msg: `{n, plural, zero {لا} one {واحد} two {اثنان} few {# قليلة} many {# كثير} other {# أخرى}}`, n: 2,    expected: "اثنان"          },
  { locale: "ar", msg: `{n, plural, zero {لا} one {واحد} two {اثنان} few {# قليلة} many {# كثير} other {# أخرى}}`, n: 5,    expected: "5 قليلة"        },
  { locale: "ar", msg: `{n, plural, zero {لا} one {واحد} two {اثنان} few {# قليلة} many {# كثير} other {# أخرى}}`, n: 15,   expected: "15 كثير"        },
  // Russian
  { locale: "ru", msg: `{n, plural, one {# товар} few {# товара} many {# товаров} other {# товара}}`, n: 1,    expected: "1 товар"        },
  { locale: "ru", msg: `{n, plural, one {# товар} few {# товара} many {# товаров} other {# товара}}`, n: 11,   expected: "11 товаров"     },
  { locale: "ru", msg: `{n, plural, one {# товар} few {# товара} many {# товаров} other {# товара}}`, n: 21,   expected: "21 товар"       },
];

for (const { locale, msg, n, expected } of cases) {
  const result = new IntlMessageFormat(msg, locale).format({ n }) as string;
  console.assert(result === expected, `[${locale}] n=${n}: got "${result}", want "${expected}"`);
}
console.log("All pluralization tests passed");
```

---

## Related Articles

- `documentation/docs/policies/i18n/icu-messageformat-2026.md`
- `documentation/docs/policies/i18n/icu-plural-rules-20-locales.md`
- `documentation/docs/policies/i18n/pluralization-edge-cases-arabic-slavic.md`
- `documentation/docs/policies/i18n/translation-kv-caching-ttl-strategy.md`
- `documentation/docs/policies/i18n/cloudflare-workers-geolocation-locale-routing.md`
- `documentation/docs/policies/i18n/unicode-cldr-plural-rules-locale-data.md`

---

## Sources

- CLDR Plural Rules — https://cldr.unicode.org/index/cldr-spec/plural-rules
- ICU MessageFormat syntax — https://unicode-org.github.io/icu/userguide/format_parse/messages/
- `@formatjs/intl-messageformat` — https://formatjs.io/docs/core-concepts/icu-syntax
- Cloudflare Workers V8 compatibility — https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- `Intl.PluralRules` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- Cloudflare KV — https://developers.cloudflare.com/kv/
