# Finnish Estonian Agglutinative Morphology i18n Workers
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker serving Finnish (`fi-FI`) or Estonian (`et-EE`) users
produces translation strings that look grammatically broken because both
languages are **agglutinative** — they attach meaning through suffixes rather
than prepositions. A naïve translation like `"Signed in as {name}"` becomes
`"Kirjautunut sisään nimellä {name}"`, but possessive and case-suffix forms
(`{name}n`, `{name}lla`) must be handled without exposing case-suffix logic to
translators.

## Context

Finnish and Estonian belong to the Finno-Ugric family. Key i18n challenges:

| Challenge | Detail |
|-----------|--------|
| **15 grammatical cases (Finnish)** | Each noun suffix varies by case: genitive (-n), partitive (-a/-ä), elative (-sta/-stä)… |
| **Vowel harmony** | Suffixes alternate between back (a, o, u) and front (ä, ö, y) forms |
| **Consonant gradation** | Root consonants mutate at morpheme boundaries (k→∅, p→v, t→d) |
| **Plural forms** | Finnish has two CLDR plural categories: `one` (1) and `other` |
| **Estonian cases** | 14 cases; similar vowel alternation but no vowel harmony |

The recommended approach is to **design message keys that avoid mid-string
interpolation of inflected nouns**, and to **provide pre-inflected variants** via
ICU `select` or lookup tables.

## ICU MessageFormat with Finnish Select

Avoid exposing suffix logic to runtime code by using `select` categories that
map to pre-translated strings.

```typescript
// src/lib/fi-messages.ts

/**
 * Instead of "{name}lla on {count} viestiä", provide keys per case.
 * Translators write the grammatically correct Finnish form.
 */
export const fiMessages = {
  // Nominative: "Tervetuloa, {name}!"
  welcome: 'Tervetuloa, {name}!',

  // Adessive (on) + possessive impossible to generate programmatically
  // → use a pre-inflected wrapper select
  inboxHeading: '{gender, select, male {{name}lla on {count} {count, plural, one {viesti} other {viestiä}}} female {{name}lla on {count} {count, plural, one {viesti} other {viestiä}}} other {{name}lla on {count} {count, plural, one {viesti} other {viestiä}}}}',

  // Genitive: {name}n kalenteri — expose as a select
  calendarOf: `{nameCase, select,
    {nameValue}n kalenteri
    other {{nameValue}n kalenteri}
  }`,
};

/**
 * Compute the Finnish genitive suffix.
 * This covers the most common suffix rules; full morphology requires a
 * proper morphological analyser.
 */
export function finnishGenitive(word: string): string {
  if (!word) return word;
  const last = word[word.length - 1].toLowerCase();
  const vowels = 'aeiouäöy';
  if (vowels.includes(last)) {
    // Ends in vowel: append -n
    return word + 'n';
  }
  // Ends in consonant: double last vowel + n (simplified)
  for (let i = word.length - 2; i >= 0; i--) {
    if (vowels.includes(word[i].toLowerCase())) {
      return word + word[i] + 'n';
    }
  }
  return word + 'in'; // fallback
}

// finnishGenitive('Timo') → 'Timon'
// finnishGenitive('Matti') → 'Matin'  (simplified; real: Matin)
// finnishGenitive('Kari') → 'Karin'
```

## Plural Rules: Finnish and Estonian

Finnish: `one` → exactly 1; `other` → all else.
Estonian: same two categories (`üks` = 1 is `one`; everything else is `other`).

```typescript
// src/lib/fi-et-plural.ts

const fiPlural = new Intl.PluralRules('fi-FI');
const etPlural = new Intl.PluralRules('et-EE');

interface PluralMessages {
  one: string;
  other: string;
}

const fiItemMessages: PluralMessages = {
  one: '1 kohde',     // 1 item
  other: '{n} kohdetta', // n items (partitive)
};

const etItemMessages: PluralMessages = {
  one: '1 üksus',
  other: '{n} üksust',
};

export function formatCount(
  n: number,
  locale: 'fi-FI' | 'et-EE',
): string {
  const pr = locale === 'fi-FI' ? fiPlural : etPlural;
  const msgs = locale === 'fi-FI' ? fiItemMessages : etItemMessages;
  const cat = pr.select(n) as 'one' | 'other';
  const numFmt = new Intl.NumberFormat(locale).format(n);
  return msgs[cat].replace('{n}', numFmt);
}

// formatCount(1, 'fi-FI') → '1 kohde'
// formatCount(5, 'fi-FI') → '5 kohdetta'
// formatCount(1, 'et-EE') → '1 üksus'
// formatCount(42, 'et-EE') → '42 üksust'
```

## Intl Formatting: fi-FI and et-EE

```typescript
// src/lib/fi-et-format.ts

/** Finnish date: sunnuntai 23. elokuuta 2026 */
export const fiDateLong = new Intl.DateTimeFormat('fi-FI', {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

/** Finnish number: 1 234 567,89 (space as thousands separator, comma decimal) */
export const fiNumber = new Intl.NumberFormat('fi-FI', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Finnish currency: 1 234,50 € */
export const fiCurrency = new Intl.NumberFormat('fi-FI', {
  style: 'currency',
  currency: 'EUR',
});

/** Estonian date: pühapäev, 23. august 2026 */
export const etDateLong = new Intl.DateTimeFormat('et-EE', {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

/** Estonian currency: 1 234,50 € */
export const etCurrency = new Intl.NumberFormat('et-EE', {
  style: 'currency',
  currency: 'EUR',
});

// fiDateLong.format(new Date('2026-08-23')) → 'sunnuntai 23. elokuuta 2026'
// fiCurrency.format(1234.5) → '1 234,50 €'
// etDateLong.format(new Date('2026-08-23')) → 'pühapäev, 23. august 2026'
```

## Workers Handler: Locale-Driven Response

```typescript
// src/index.ts
import { formatCount } from './lib/fi-et-plural';
import { fiCurrency, etCurrency, fiDateLong, etDateLong } from './lib/fi-et-format';

type SupportedLocale = 'fi-FI' | 'et-EE';

function detectLocale(request: Request): SupportedLocale {
  const accept = request.headers.get('Accept-Language') ?? '';
  if (/\bet\b/i.test(accept)) return 'et-EE';
  if (/\bfi\b/i.test(accept)) return 'fi-FI';
  return 'fi-FI'; // default
}

export default {
  async fetch(request: Request): Promise<Response> {
    const locale = detectLocale(request);
    const now = new Date();
    const n = parseInt(new URL(request.url).searchParams.get('n') ?? '5', 10);

    const dateFmt = locale === 'fi-FI' ? fiDateLong : etDateLong;
    const currFmt = locale === 'fi-FI' ? fiCurrency : etCurrency;

    return new Response(
      JSON.stringify({
        locale,
        date: dateFmt.format(now),
        amount: currFmt.format(n * 9.99),
        items: formatCount(n, locale),
      }),
      {
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Language': locale,
          'Vary': 'Accept-Language',
        },
      }
    );
  },
};
```

## KV Translation Storage with Case Variants

For small apps, store pre-inflected strings directly in KV, keyed by locale and
grammatical case.

```typescript
// src/lib/fi-kv-translations.ts

export type FinnishCase =
  | 'nominative'
  | 'genitive'
  | 'partitive'
  | 'illative'
  | 'adessive';

export async function getTranslation(
  kv: KVNamespace,
  key: string,
  locale: string,
  grammaticalCase: FinnishCase = 'nominative',
): Promise<string | null> {
  // Key structure: "fi-FI:button.save:nominative"
  const kvKey = `${locale}:${key}:${grammaticalCase}`;
  return kv.get(kvKey);
}

export async function putTranslation(
  kv: KVNamespace,
  key: string,
  locale: string,
  translations: Partial<Record<FinnishCase, string>>,
): Promise<void> {
  const puts = Object.entries(translations).map(([cas, val]) =>
    kv.put(`${locale}:${key}:${cas}`, val as string)
  );
  await Promise.all(puts);
}

// Store: { nominative: 'viesti', genitive: 'viestin', partitive: 'viestiä' }
// Retrieve nominative: kv.get('fi-FI:noun.message:nominative') → 'viesti'
```

## Anti-patterns

- **Constructing Finnish/Estonian word forms at runtime** — full morphological
  generation requires a language-specific library (e.g. voikko for Finnish).
  The helper `finnishGenitive` above handles common names but will fail on
  loanwords and irregular nouns.
- **Using `{name}'s` English possessive patterns in Finnish/Estonian ICU
  messages** — Finnish does not use apostrophes; possessive is expressed via
  genitive suffix, which must be pre-computed.
- **Treating Finnish as having many plural categories** — Finnish has only
  `one`/`other` in CLDR despite having grammatical partitive; the _translation_
  handles partitive, not the plural rule.
- **Hardcoding space as thousands separator** — `fi-FI` uses a non-breaking
  thin space (U+202F) or regular space depending on ICU version; always use
  `Intl.NumberFormat`.
- **Ignoring vowel harmony in suffix tables** — a single suffix table (`-lla`)
  without harmony produces `koiralla` (correct) and `pöytälla` (wrong;
  should be `pöydällä`).

## Gotchas

- Finnish special characters `ä` (U+00E4) and `ö` (U+00F6) must sort **after**
  `z` in Finnish collation. `Intl.Collator('fi-FI')` handles this correctly;
  ASCII byte order does not.
- Estonian `õ` (U+00F5) is distinct from `ö`; they are separate letters in the
  Estonian alphabet and must be treated as such.
- `fi-FI` date formats write the month name in the **genitive** case in long
  formats ("elokuuta" is genitive of "elokuu"); `Intl.DateTimeFormat` handles
  this automatically.
- `Intl.RelativeTimeFormat('fi-FI', { numeric: 'auto' })` returns "eilen"
  (yesterday) and "huomenna" (tomorrow) — test this for exact output on the
  Workers v8 ICU version.
- Estonian and Finnish share many loanwords but their morphological rules
  differ. Do not share a single suffix table between the two locales.

## Verification

```typescript
// test/fi-et.spec.ts
import { formatCount } from '../src/lib/fi-et-plural';
import { finnishGenitive } from '../src/lib/fi-messages';
import { fiCurrency, etCurrency } from '../src/lib/fi-et-format';

// Plural
console.assert(formatCount(1, 'fi-FI') === '1 kohde',      'fi one');
console.assert(formatCount(5, 'fi-FI') === '5 kohdetta',   'fi other');
console.assert(formatCount(1, 'et-EE') === '1 üksus',      'et one');
console.assert(formatCount(3, 'et-EE') === '3 üksust',     'et other');

// Genitive (simplified)
console.assert(finnishGenitive('Kari') === 'Karin', 'genitive Kari');
console.assert(finnishGenitive('Timo') === 'Timon', 'genitive Timo');

// Currency formatting
const fiAmt = fiCurrency.format(1234.5);
console.assert(fiAmt.includes('€'), `fi currency missing €: ${fiAmt}`);
console.assert(fiAmt.includes('1'), `fi currency: ${fiAmt}`);

// Collation: ä sorts after z
const sorted = ['zebra', 'äiti', 'auto'].sort(
  new Intl.Collator('fi-FI').compare
);
console.assert(sorted[2] === 'äiti', `ä not last: ${sorted}`);

console.log('Finnish/Estonian i18n tests passed');
```

## Related

- `icu-messageformat-pluralization-complex-languages.md`
- `locale-negotiation-accept-language.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `welsh-maltese-pluralization-workers.md`

## Sources

- CLDR Finnish plural rules — https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
- Finnish grammar overview (University of Helsinki) — https://www.cs.tut.fi/~jkorpela/finnish-grammar.html
- Estonian Language Institute morphological data — https://www.eki.ee/
- MDN `Intl.PluralRules` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- Voikko Finnish morphological analyser — https://voikko.puimula.org/
