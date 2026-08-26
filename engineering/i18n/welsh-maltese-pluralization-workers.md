# Welsh and Maltese Pluralization Edge Cases in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your translation system has three or four plural forms in the message catalog for Welsh (`cy`) and Maltese (`mt`) and the wrong form is selected at runtime. Messages like "3 eitem" appear instead of "3 eitem" or "4 o eitemau". ICU `PluralRules` returns an unexpected key, or your Workers-based i18n helper only handles `one` and `other`.

---

## Context

Welsh and Maltese have among the most complex plural systems of any European language:

**Welsh (`cy`)** has **six plural forms** according to CLDR:
| Form | Rule |
|------|------|
| `zero` | n = 0 |
| `one` | n = 1 |
| `two` | n = 2 |
| `few` | n = 3 |
| `many` | n = 6 |
| `other` | everything else |

**Maltese (`mt`)** has **four plural forms**:
| Form | Rule |
|------|------|
| `one` | n = 1 |
| `few` | n = 2..10 |
| `many` | n = 11..19 or n ends in 00, 01..10 |
| `other` | everything else (0, 20–99 excluding 11–19) |

Both languages are EU official languages (Maltese) or regional official languages (Welsh in Wales), making them common targets for localization of government and public-sector platforms. A naive `one` / `other` split silently produces wrong output for the majority of counts.

---

## 1. Verifying ICU Plural Rules in Workers

```typescript
// src/verify-plural-rules.ts

/**
 * Dump plural categories for Welsh and Maltese.
 * Run once during development to confirm ICU data is correct.
 */
export function verifyPluralData(): Record<string, string> {
  const locales = ['cy', 'mt'];
  const testValues = [0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 19, 20, 21, 100, 101];
  const out: Record<string, string> = {};

  for (const locale of locales) {
    const pr = new Intl.PluralRules(locale);
    const row = testValues.map(n => `${n}→${pr.select(n)}`).join(', ');
    out[locale] = row;
  }

  return out;
  /*
    Expected cy: 0→zero, 1→one, 2→two, 3→few, 4→other, 5→other,
                 6→many, 7→other, 10→other, ...
    Expected mt: 0→other, 1→one, 2→few, 3→few, ..., 10→few,
                 11→many, 12→many, ..., 19→many, 20→other, 21→other,
                 100→other, 101→few
  */
}
```

---

## 2. Message Catalog Schema for Six-Form Languages

```typescript
// src/types.ts

/** Full CLDR plural category set */
export type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/** A message with per-locale plural forms. The `other` key is required as fallback. */
export type PluralMessage = Partial<Record<PluralCategory, string>> & { other: string };

export interface TranslationCatalog {
 | PluralMessage;
}
```

```json
// translations/cy.json (Welsh — 6 forms required)
{
  "item_count": {
    "zero":  "Dim eitemau",
    "one":   "1 eitem",
    "two":   "2 eitem",
    "few":   "{{n}} eitem",
    "many":  "{{n}} eitem",
    "other": "{{n}} o eitemau"
  },
  "file_count": {
    "zero":  "Dim ffeiliau",
    "one":   "1 ffeil",
    "two":   "2 ffeil",
    "few":   "{{n}} ffeil",
    "many":  "{{n}} ffeil",
    "other": "{{n}} o ffeiliau"
  }
}
```

```json
// translations/mt.json (Maltese — 4 forms required)
{
  "item_count": {
    "one":   "1 oġġett",
    "few":   "{{n}} oġġetti",
    "many":  "{{n}} oġġetti",
    "other": "{{n}} oġġetti"
  },
  "result_count": {
    "one":   "Riżultat wieħed",
    "few":   "{{n}} riżultati",
    "many":  "{{n}} riżultati",
    "other": "{{n}} riżultati"
  }
}
```

---

## 3. Plural Resolution Helper in Workers

```typescript
// src/plural.ts
import type { PluralMessage, TranslationCatalog } from './types';

const pluralRulesCache = new Map<string, Intl.PluralRules>();

function getPluralRules(locale: string): Intl.PluralRules {
  if (!pluralRulesCache.has(locale)) {
    pluralRulesCache.set(locale, new Intl.PluralRules(locale));
  }
  return pluralRulesCache.get(locale)!;
}

export function t(
  catalog: TranslationCatalog,
  key: string,
  locale: string,
  count?: number,
  vars?: Record<string, string | number>,
): string {
  const entry = catalog[key];
  if (!entry) return key;

  let template: string;

  if (typeof entry === 'string') {
    template = entry;
  } else {
    // Plural message
    if (count === undefined) {
      // No count provided — use the 'other' form as fallback
      template = entry.other;
    } else {
      const category = getPluralRules(locale).select(count);
      template = entry[category] ?? entry.other;
    }
  }

  // Variable substitution
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) => {
    if (name === 'n' && count !== undefined) return String(count);
    return vars?.[name] !== undefined ? String(vars[name]) : `{{${name}}}`;
  });
}
```

---

## 4. Workers KV Translation Loader

```typescript
// src/kv-loader.ts
import type { TranslationCatalog } from './types';

const catalogCache = new Map<string, TranslationCatalog>();

export async function loadCatalog(
  locale: string,
  kv: KVNamespace,
): Promise<TranslationCatalog> {
  if (catalogCache.has(locale)) return catalogCache.get(locale)!;

  const raw = await kv.get(`catalog:${locale}`, { type: 'json' });
  if (!raw) {
    // Fall back to English if locale not found
    const fallback = await kv.get('catalog:en', { type: 'json' });
    catalogCache.set(locale, (fallback ?? {}) as TranslationCatalog);
    return catalogCache.get(locale)!;
  }

  catalogCache.set(locale, raw as TranslationCatalog);
  return raw as TranslationCatalog;
}
```

---

## 5. End-to-End Worker Handler

```typescript
// src/index.ts
import { t } from './plural';
import { loadCatalog } from './kv-loader';

interface Env {
  TRANSLATIONS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locale = url.searchParams.get('locale') ?? 'en';
    const count = Number(url.searchParams.get('n') ?? '1');

    const catalog = await loadCatalog(locale, env.TRANSLATIONS);
    const message = t(catalog, 'item_count', locale, count);

    return Response.json({ locale, count, message });
  },
};

/*
  GET /?locale=cy&n=0  => { message: "Dim eitemau" }
  GET /?locale=cy&n=2  => { message: "2 eitem" }
  GET /?locale=cy&n=6  => { message: "6 eitem" }   (many form)
  GET /?locale=cy&n=7  => { message: "7 o eitemau" } (other form)
  GET /?locale=mt&n=1  => { message: "1 oġġett" }
  GET /?locale=mt&n=5  => { message: "5 oġġetti" }  (few)
  GET /?locale=mt&n=11 => { message: "11 oġġetti" } (many)
  GET /?locale=mt&n=20 => { message: "20 oġġetti" } (other)
*/
```

---

## 6. Ordinal Plurals for Welsh and Maltese

Welsh and Maltese also have ordinal plural rules (for "1st", "2nd", etc.). Welsh ordinals are complex and do not simply map to the same six categories.

```typescript
// src/ordinals.ts

const cyOrdinalRules = new Intl.PluralRules('cy', { type: 'ordinal' });
const mtOrdinalRules = new Intl.PluralRules('mt', { type: 'ordinal' });

// Welsh ordinals: the mutation pattern means ordinal forms differ from cardinals
const CY_ORDINAL: Record<string, string> = {
  zero: '{{n}}fed',
  one: '{{n}}af',
  two: '{{n}}il',
  few: '{{n}}ydd',
  many: '{{n}}ed',
  other: '{{n}}ain',
};

export function formatOrdinal(n: number, locale: string): string {
  if (locale.startsWith('cy')) {
    const cat = cyOrdinalRules.select(n);
    const template = CY_ORDINAL[cat] ?? CY_ORDINAL.other;
    return template.replace('{{n}}', String(n));
  }
  if (locale.startsWith('mt')) {
    // Maltese ordinals: typically handled with the cardinal form + "l-" prefix
    // ICU returns 'other' for most Maltese ordinals
    return `${n}`;
  }
  return `${n}.`;
}
```

---

## Anti-patterns

- **Using only `one` / `other` for Welsh or Maltese** — Welsh has six forms; omitting `zero`, `two`, `few`, `many` silently falls back to `other` for all of them. Users will see "0 o eitemau" instead of "Dim eitemau".
- **Hardcoding plural logic with `n === 1 ? singular : plural`** — This breaks for both languages. Always delegate to `Intl.PluralRules`.
- **Sharing plural cache across request lifecycles without isolation** — `Intl.PluralRules` instances are safe to cache per locale in module scope in Workers (the module is per-isolate), but do not cache per-request state in module scope.
- **Omitting ordinal rules** — Welsh and Maltese ordinals are distinct from cardinals; if your product shows rankings or step numbers, test both rule types.
- **Testing only with `n = 0, 1, 2`** — For Maltese, test `n = 11, 12, 19, 20` specifically; the `many` form covers 11–19 which is the most commonly missed range.

---

## Gotchas

- **Welsh `many` = 6 only**: In CLDR, Welsh `many` applies only to `n = 6`. It is often identical in wording to `few` (`n = 3`) but is grammatically distinct. If your copywriter produces the same string for `few` and `many`, that is likely correct — but both keys must be present in the catalog.
- **Maltese `other` includes 0**: Zero in Maltese falls into `other`, not `zero`. There is no `zero` plural category in Maltese. If you need a special zero message, handle it with a conditional before calling `PluralRules`.
- **ICU version drift**: Plural rules have changed between CLDR versions. CF Workers uses the V8 bundled ICU. Verify your expected outputs against the actual Worker runtime, not a local Node.js install, as ICU data versions may differ.
- **Welsh mutated forms**: The actual Welsh plural strings involve consonant mutations (soft, nasal, aspirate). These are linguistic changes that belong in the translation string, not in code. Do not attempt to automate Welsh mutations in JavaScript.
- **Maltese gender**: Maltese nouns are gendered (masculine/feminine), and this affects adjective agreement in count phrases. Handle gender in the translation string, not in `PluralRules` output.

---

## Verification

```typescript
// verify/plural.test.ts
// Run with: wrangler dev and call /verify

const CY_EXPECTATIONS: [number, string][] = [
  [0, 'zero'], [1, 'one'], [2, 'two'], [3, 'few'],
  [4, 'other'], [5, 'other'], [6, 'many'], [7, 'other'],
  [10, 'other'], [100, 'other'],
];

const MT_EXPECTATIONS: [number, string][] = [
  [0, 'other'], [1, 'one'], [2, 'few'], [3, 'few'],
  [10, 'few'], [11, 'many'], [12, 'many'], [19, 'many'],
  [20, 'other'], [21, 'other'], [100, 'other'], [101, 'few'],
  [111, 'many'], [200, 'other'],
];

function verify(locale: string, expectations: [number, string][]): void {
  const pr = new Intl.PluralRules(locale);
  let pass = 0; let fail = 0;
  for (const [n, expected] of expectations) {
    const got = pr.select(n);
    if (got === expected) pass++;
    else { fail++; console.error(`[${locale}] n=${n}: got ${got}, expected ${expected}`); }
  }
  console.log(`[${locale}] ${pass}/${pass + fail} passed`);
}

verify('cy', CY_EXPECTATIONS);
verify('mt', MT_EXPECTATIONS);
```

---

## Related

- `pluralization-edge-cases-arabic-slavic.md`
- `icu-messageformat-pluralization-complex-languages.md`
- `icu-plural-rules-20-locales.md`
- `Intl-PluralRules-2026.md`
- `intl-pluralrules-range-message-selection.md`
- `translation-kv-caching-ttl-strategy.md`

---

## Sources

- CLDR Welsh plural rules: https://github.com/unicode-org/cldr/blob/main/common/supplemental/plurals.xml
- CLDR Maltese plural rules: https://github.com/unicode-org/cldr/blob/main/common/supplemental/plurals.xml
- Unicode Language Plural Rules chart: https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
- ICU PluralRules docs: https://unicode-org.github.io/icu/userguide/format_parse/numbers/plural-rules.html
- Intl.PluralRules MDN: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- Welsh language mutations reference: https://www.bbc.co.uk/wales/learnwelsh/grammar/mutations/
