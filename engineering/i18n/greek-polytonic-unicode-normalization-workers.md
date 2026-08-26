# Greek Polytonic Unicode Normalization Workers
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker serving a Greek-language audience — particularly one that
handles classical texts, academic publishing, or Greek Orthodox liturgical
content — must correctly normalise, search, and collate text that mixes
**monotonic** (modern Greek, single accent) and **polytonic** (ancient/formal
Greek, three-accent system with breath marks) orthography. Naively comparing
strings across the two systems fails silently.

## Context

Modern Greek uses **monotonic orthography** (official since 1982): a single
acute accent on the stressed syllable. Classical and formal texts use
**polytonic orthography**: acute (`´`), grave (`` ` ``), circumflex (`ˆ`), and
breath marks (smooth `᾿`/rough `῾`). Both systems share the same base Greek
letters; Unicode encodes polytonic combinations in the **Greek Extended** block
(U+1F00–U+1FFF).

Key concerns on Workers:
- NFC for display, NFD for diacritic stripping in search
- NFKC collapses some precomposed Greek chars (e.g. U+03D3 → U+03A5)
- Collation for `el-GR` via `Intl.Collator` respects accent-insensitive sorting
- HTMLRewriter can strip polytonic marks from user-supplied HTML at the edge

## Unicode Block Layout for Greek

| Range | Block | Examples |
|-------|-------|---------|
| U+0370–U+03FF | Greek and Coptic | α β γ Α Ω |
| U+1F00–U+1FFF | Greek Extended | ἀ ἁ ᾀ ᾁ ὰ ά |
| U+0300–U+036F | Combining Diacritical Marks | combining grave, acute, circumflex |

Polytonic text is typically stored as **precomposed NFC** using Greek Extended
codepoints. NFD decomposes them into base letter + combining marks.

## Normalisation Functions

```typescript
// src/lib/el-normalize.ts

/**
 * Normalise Greek text to NFC.
 * Precomposed polytonic characters are preserved.
 */
export function toNFC(input: string): string {
  return input.normalize('NFC');
}

/**
 * Convert polytonic Greek to monotonic by stripping all accents and
 * breath marks, retaining only the final acute accent (tonos).
 * This is an approximation for search — not a linguistically correct
 * monotonic conversion, which requires knowing which syllable to stress.
 */
export function polytonicToStripped(input: string): string {
  return input
    .normalize('NFD')
    // Remove combining: grave (0300), acute (0301), circumflex (0302/0342),
    // smooth breathing (0313), rough breathing (0314), subscript (0345),
    // diaeresis (0308), macron (0304), breve (0306)
    .replace(/[̀-͂̕̚ͅ]/g, '')
    .normalize('NFC');
}

/**
 * Strip ALL diacritics for fully accent-insensitive search.
 */
export function stripGreekDiacritics(input: string): string {
  return input
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // all combining diacritical marks
    .normalize('NFC');
}

// toNFC('ἄνθρωπος') → 'ἄνθρωπος' (Greek Extended precomposed)
// polytonicToStripped('ἄνθρωπος') → 'ανθρωπος'
// stripGreekDiacritics('ἄνθρωπος') → 'ανθρωπος'
// stripGreekDiacritics('Ήλιος') → 'Ηλιος'
```

## Collation with Intl.Collator

`el-GR` collation in V8 ICU supports sensitivity levels. Use `'base'` for
accent-insensitive, case-insensitive search; `'accent'` for accent-sensitive.

```typescript
// src/lib/el-collator.ts

/** Accent-insensitive, case-insensitive sort (for search ranking) */
export const elCollatorBase = new Intl.Collator('el-GR', {
  sensitivity: 'base',
  usage: 'sort',
});

/** Full collation: accent- and case-sensitive (for display sort) */
export const elCollatorFull = new Intl.Collator('el-GR', {
  sensitivity: 'variant',
  usage: 'sort',
});

/** Case-insensitive but accent-sensitive */
export const elCollatorAccent = new Intl.Collator('el-GR', {
  sensitivity: 'accent',
  usage: 'sort',
});

export function sortGreekWords(words: string[], accentInsensitive = false): string[] {
  const collator = accentInsensitive ? elCollatorBase : elCollatorFull;
  return [...words].sort((a, b) => collator.compare(a, b));
}

// sortGreekWords(['ώρα', 'ωρα', 'Ωρα'], true)
// → ['Ωρα', 'ωρα', 'ώρα']  (base treats all as equal, stable order)
// sortGreekWords(['ώρα', 'ωρα', 'Ωρα'], false)
// → ['ωρα', 'Ωρα', 'ώρα']  (accent/case-sensitive)
```

## D1: Storing Polytonic and Stripped Forms

```sql
-- migrations/0001_el_texts.sql
CREATE TABLE texts (
  id          TEXT PRIMARY KEY,
  content     TEXT NOT NULL,        -- NFC original (polytonic preserved)
  content_fold TEXT NOT NULL,       -- stripped for accent-insensitive FTS
  lang        TEXT NOT NULL DEFAULT 'el'
);
CREATE INDEX idx_content_fold ON texts (content_fold);
```

```typescript
// src/lib/el-d1.ts
import { stripGreekDiacritics } from './el-normalize';

export async function insertText(
  db: D1Database,
  id: string,
  content: string,
  lang = 'el',
): Promise<void> {
  const nfc = content.normalize('NFC');
  const fold = stripGreekDiacritics(nfc).toLowerCase();

  await db
    .prepare(`INSERT OR REPLACE INTO texts (id, content, content_fold, lang)
              VALUES (?, ?, ?, ?)`)
    .bind(id, nfc, fold, lang)
    .run();
}

export async function searchTexts(
  db: D1Database,
  query: string,
): Promise<{ id: string; content: string }[]> {
  const fold = stripGreekDiacritics(query.normalize('NFC')).toLowerCase();
  const { results } = await db
    .prepare(`SELECT id, content FROM texts WHERE content_fold LIKE ? LIMIT 20`)
    .bind(`%${fold}%`)
    .all<{ id: string; content: string }>();
  return results;
}
```

## HTMLRewriter: Strip Polytonic Marks from User Content

When serving user-generated polytonic text to a monotonic-only audience, strip
diacritics at the edge without touching stored content.

```typescript
// src/handlers/el-rewrite.ts
import { polytonicToStripped } from '../lib/el-normalize';

class GreekTextRewriter implements HTMLRewriterElementContentHandlers {
  private buffer = '';

  text(chunk: Text): void {
    this.buffer += chunk.text;
    if (chunk.lastInTextNode) {
      chunk.replace(polytonicToStripped(this.buffer));
      this.buffer = '';
    } else {
      chunk.remove();
    }
  }
}

export function applyPolytonicRewriter(response: Response): Response {
  return new HTMLRewriter()
    .on('p, h1, h2, h3, span[lang="grc"]', new GreekTextRewriter())
    .transform(response);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch('https://content.example.com' + new URL(request.url).pathname);
    const acceptLang = request.headers.get('Accept-Language') ?? '';
    // Only strip polytonic for modern Greek clients, not classical scholars
    if (acceptLang.includes('el') && !acceptLang.includes('grc')) {
      return applyPolytonicRewriter(upstream);
    }
    return upstream;
  },
};
```

## Intl Formatting for Modern Greek

```typescript
// src/lib/el-format.ts

export const elDate = new Intl.DateTimeFormat('el-GR', {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

export const elCurrency = new Intl.NumberFormat('el-GR', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
});

export const elRelTime = new Intl.RelativeTimeFormat('el-GR', {
  numeric: 'auto',
  style: 'long',
});

// elDate.format(new Date('2026-08-23')) → 'Κυριακή, 23 Αυγούστου 2026'
// elCurrency.format(1234.5) → '1.234,50 €'
// elRelTime.format(-1, 'day') → 'χθες'
```

## Anti-patterns

- **Using NFKC on Greek polytonic text** — NFKC decomposes the U+03D3 (ϓ) to Υ
  plus combining, and collapses some spacing modifier letters, potentially
  altering meaning in classical texts.
- **Assuming monotonic === stripped** — monotonic Greek still has the tonos
  (´); stripping all marks produces archaic-looking toneless text unsuitable
  for display.
- **`'el'` vs `'el-GR'`** — `Intl.Collator('el')` resolves to `el-GR`; be
  explicit to avoid ICU subtag resolution surprises.
- **Storing NFD polytonic in D1** — the Greek Extended precomposed forms must
  be stored as NFC; NFD expands them into U+1F00 area combining sequences that
  are hard to query.
- **Stripping diacritics for display** — only strip for search/sort indices.
  Users reading classical texts need full polytonic rendering.

## Gotchas

- `'ο'` (Greek omicron, U+03BF) and `'o'` (Latin o, U+006F) are visually
  identical but codepoint-distinct. Collation-aware search handles this;
  naive string comparison does not.
- The iota subscript (ᾳ ῃ ῳ) decomposes as base + combining iota below
  (U+0345). When stripping diacritics for search, U+0345 falls in the
  combining range and is removed — this is usually correct for search.
- `Intl.Collator('el-GR', { sensitivity: 'base' }).compare('α', 'ά')` returns
  `0` (equal) — correct for search but wrong for precise sort.
- Beta code (a transliteration scheme used in TLG databases) is `*A` = Α,
  `a` = α. Users may paste beta code into search boxes; detect via `/[*|/\\\\=]/`
  and reject or convert before normalising.
- HTMLRewriter's `text()` handler receives chunks, not full text nodes. Buffer
  until `chunk.lastInTextNode` before applying regex normalisation.

## Verification

```typescript
// test/el-normalize.spec.ts
import { stripGreekDiacritics, polytonicToStripped } from '../src/lib/el-normalize';

const cases: [string, string, string][] = [
  ['ἄνθρωπος', 'ανθρωπος', 'ανθρωπος'],
  ['Ήλιος',    'Ηλιος',    'Ηλιος'],
  ['ᾄδω',      'αδω',       'αδω'],
  ['Ωρα',      'Ωρα',       'Ωρα'],
];

for (const [input, expectedStrip, expectedFull] of cases) {
  const s = polytonicToStripped(input);
  const f = stripGreekDiacritics(input);
  console.assert(s === expectedStrip, `polytonicToStripped("${input}"): got "${s}"`);
  console.assert(f === expectedFull,  `stripGreekDiacritics("${input}"): got "${f}"`);
}
console.log('Greek normalisation tests passed');
```

## Related

- `unicode-normalization-nfc-nfd.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `rtl-text-detection-workers-htmlrewriter.md`
- `bidi-algorithm-unicode.md`
- `accent-insensitive-search-pipeline-2026.md`

## Sources

- Unicode Greek and Coptic block — https://unicode.org/charts/PDF/U0370.pdf
- Unicode Greek Extended block — https://unicode.org/charts/PDF/U1F00.pdf
- CLDR `el` collation data — https://github.com/unicode-org/cldr/tree/main/common/collation
- MDN `Intl.Collator` sensitivity — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator/Collator
- Unicode polytonic Greek input guide — https://unicode.org/faq/greek.html
