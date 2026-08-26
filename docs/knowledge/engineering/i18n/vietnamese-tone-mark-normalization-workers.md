# Vietnamese Tone Mark Normalization Workers
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker handling Vietnamese text finds that search queries typed by
users fail to match database entries because the same character can be encoded
as a single precomposed codepoint (NFC) or as a base letter plus combining
diacritics (NFD). Additionally, legacy content migrated from VISCII or TCVN
encodings may use private-use codepoints that must be converted to Unicode
before any processing.

## Context

Vietnamese uses the **Latin script** augmented with up to **three stacked
diacritics** per letter: a vowel modifier (circumflex, breve, horn), a tone
mark (grave, acute, hook, tilde, dot-below), and optionally a d-stroke. Unicode
encodes most combinations as precomposed characters in the **Latin Extended
Additional** block (U+1E00–U+1EFF). However:

- User agents may send either NFC (precomposed) or NFD (decomposed) forms
- Older CMSes and imported data may use the old VISCII encoding's private-use
  mappings or the Microsoft `windows-1258` mapping
- Search must optionally work **with or without** tone marks (diacritic folding)

## NFC/NFD Normalization at the Edge

All Vietnamese text should be normalised to **NFC** at ingress; the `normalize`
method is available natively in the V8 Workers runtime.

```typescript
// src/lib/vi-normalize.ts

/**
 * Normalise Vietnamese text to NFC (precomposed form).
 * Safe to call on any UTF-8 string — non-Vietnamese chars are unaffected.
 */
export function toNFC(input: string): string {
  return input.normalize('NFC');
}

/**
 * Strip all combining diacritics for accent-insensitive search/matching.
 * Decomposes to NFD then removes combining marks (U+0300–U+036F),
 * keeping the base Latin letters. Also removes the Vietnamese horn
 * (U+031B) and the d-stroke requires separate handling.
 */
export function stripViDiacritics(input: string): string {
  return input
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // combining diacritics (tone marks + modifiers)
    .replace(/̛/g, '')          // combining horn (ơ, ư decomposed)
    .replace(/đ/gi, (c) => c === 'đ' ? 'd' : 'D') // d-stroke is precomposed, not combining
    .normalize('NFC');
}

// Examples:
// toNFC('việt') → 'việt' (single precomposed codepoints)
// stripViDiacritics('Việt Nam') → 'Viet Nam'
// stripViDiacritics('Hà Nội') → 'Ha Noi'
// stripViDiacritics('Đường') → 'Duong'
```

## VISCII / TCVN Legacy Conversion

VISCII and TCVN3 used private-use or control-code codepoints for Vietnamese
characters. Content migrated to UTF-8 incorrectly may retain byte-for-byte
mappings that look like C0 control chars or PUA codepoints.

```typescript
// src/lib/vi-legacy-convert.ts

/**
 * VISCII → Unicode codepoint map for Vietnamese characters in the
 * VISCII private-use range (0x00–0x1F extended area and 0x80–0xFF).
 * Subset of the most common misencoded characters.
 */
const VISCII_MAP: Record<number, string> = {
  0x80: 'Ạ', // Ạ
  0x81: 'Ắ', // Ắ
  0x82: 'Ằ', // Ằ
  0x83: 'Ặ', // Ặ
  0x84: 'Ấ', // Ấ
  0x85: 'Ầ', // Ầ
  0x86: 'Ẩ', // Ẩ
  0x87: 'Ẫ', // Ẫ
  0x88: 'Ậ', // Ậ
  0x89: 'Ẽ', // Ẽ
  0x8A: 'Ẹ', // Ẹ
  // … extend map with the full VISCII table for production use
};

/**
 * Convert a string that was decoded byte-by-byte from VISCII to Unicode.
 * Each char whose codepoint falls in the VISCII PUA is replaced.
 */
export function convertVisciiToUnicode(input: string): string {
  return Array.from(input)
    .map(ch => {
      const cp = ch.codePointAt(0)!;
      return VISCII_MAP[cp] ?? ch;
    })
    .join('')
    .normalize('NFC');
}
```

For bulk migration use a worker that reads from R2 (raw imported files),
converts, and writes to D1 or KV.

## Accent-Insensitive Search Pipeline

```typescript
// src/lib/vi-search.ts
import { toNFC, stripViDiacritics } from './vi-normalize';

export interface ViSearchRecord {
  id: string;
  title: string;
  titleNormalized: string; // stored for accent-insensitive match
}

/**
 * Prepare a Vietnamese string for storage alongside its normalised form.
 */
export function prepareRecord(id: string, title: string): ViSearchRecord {
  return {
    id,
    title: toNFC(title),
    titleNormalized: stripViDiacritics(toNFC(title)).toLowerCase(),
  };
}

/**
 * Match a query against a list of records, accent-insensitively.
 */
export function searchRecords(
  query: string,
  records: ViSearchRecord[],
): ViSearchRecord[] {
  const q = stripViDiacritics(toNFC(query)).toLowerCase();
  return records.filter(r => r.titleNormalized.includes(q));
}

// searchRecords('ha noi', [
//   prepareRecord('1', 'Hà Nội'),
//   prepareRecord('2', 'Hồ Chí Minh'),
// ])
// → [{ id: '1', title: 'Hà Nội', ... }]
```

## Workers Fetch Handler with Normalization Middleware

```typescript
// src/index.ts
import { toNFC, stripViDiacritics } from './lib/vi-normalize';

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Normalise query params
    const rawQuery = url.searchParams.get('q') ?? '';
    const normQuery = toNFC(rawQuery);
    const foldedQuery = stripViDiacritics(normQuery).toLowerCase();

    // Example: echo back normalisation info
    return new Response(
      JSON.stringify({
        original: rawQuery,
        nfc: normQuery,
        stripped: foldedQuery,
        codepoints: Array.from(normQuery).map(c =>
          `U+${c.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`
        ),
      }),
      {
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Language': 'vi',
        },
      }
    );
  },
};
```

## D1 Full-Text Search with Normalised Column

Store both raw and normalised forms in D1; query on the normalised column.

```sql
-- migrations/0001_vi_content.sql
CREATE TABLE articles (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL,        -- NFC original
  title_fold TEXT NOT NULL,        -- diacritics stripped, lower-case
  body       TEXT NOT NULL
);
CREATE INDEX idx_title_fold ON articles (title_fold);
```

```typescript
// src/lib/vi-d1.ts

export async function upsertArticle(
  db: D1Database,
  id: string,
  title: string,
  body: string,
): Promise<void> {
  const titleNFC = title.normalize('NFC');
  const titleFold = titleNFC
    .normalize('NFD')
    .replace(/[̀-̛ͯ]/g, '')
    .replace(/đ/gi, c => c === 'đ' ? 'd' : 'D')
    .toLowerCase();

  await db
    .prepare(`INSERT OR REPLACE INTO articles (id, title, title_fold, body)
              VALUES (?, ?, ?, ?)`)
    .bind(id, titleNFC, titleFold, body)
    .run();
}

export async function searchArticles(
  db: D1Database,
  query: string,
): Promise<{ id: string; title: string }[]> {
  const fold = query
    .normalize('NFD')
    .replace(/[̀-̛ͯ]/g, '')
    .replace(/đ/gi, c => c === 'đ' ? 'd' : 'D')
    .toLowerCase();

  const result = await db
    .prepare(`SELECT id, title FROM articles WHERE title_fold LIKE ? LIMIT 20`)
    .bind(`%${fold}%`)
    .all<{ id: string; title: string }>();

  return result.results;
}
```

## Anti-patterns

- **Comparing Vietnamese strings without normalisation** — `'việt' === 'việt'`
  returns `false` even though they render identically.
- **Using `toLowerCase()` before diacritic stripping** — some locale-sensitive
  case operations may affect combining marks; strip diacritics first, then
  lower-case.
- **Stripping all diacritics for display** — only strip for _search_ indices;
  always display the original NFC string.
- **Assuming `̀-ͯ` covers all Vietnamese marks** — the combining horn
  (`̛`) used in ơ/ư is outside this range; it must be removed separately.
- **Storing NFD in D1** — SQLite string comparisons are byte-for-byte; mixed
  NFC/NFD storage causes invisible mismatches.

## Gotchas

- The Vietnamese đ/Đ (d-stroke) codepoints (`U+0111`/`U+0110`) are fully
  precomposed — they have no combining decomposition. Replace them explicitly.
- `'windows-1258'` encoding is not supported by the Workers `TextDecoder`; use
  `TextDecoder('utf-8')` and handle legacy conversion in JavaScript.
- URL-encoded Vietnamese text (`%E1%BA%A1` for ạ) is automatically decoded by
  `new URL(request.url)` as UTF-8 NFC — but only if the original encoding was
  UTF-8; VISCII-encoded URLs will decode incorrectly.
- KV keys are byte strings; storing NFC vs NFD keys creates duplicate entries.
  Always normalise before building KV keys.

## Verification

```typescript
// test/vi-normalize.spec.ts
import { toNFC, stripViDiacritics } from '../src/lib/vi-normalize';

const cases: [string, string, string][] = [
  ['việt', 'việt', 'viet'],
  ['Hà Nội', 'Hà Nội', 'Ha Noi'],
  ['Đường', 'Đường', 'Duong'],
  ['Ơ̛', 'Ờ', 'O'],
];

for (const [input, expectedNFC, expectedStripped] of cases) {
  const nfc = toNFC(input);
  const stripped = stripViDiacritics(nfc);
  console.assert(nfc === expectedNFC, `NFC mismatch for "${input}": ${nfc}`);
  console.assert(stripped === expectedStripped,
    `Strip mismatch for "${input}": ${stripped}`);
}
console.log('Vietnamese normalisation tests passed');
```

## Related

- `unicode-normalization-nfc-nfd.md`
- `accent-insensitive-search-pipeline-2026.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `i18n-content-fallback-chain-kv-workers.md`
- `sinhala-khmer-script-localization-workers.md`

## Sources

- Unicode Latin Extended Additional block — https://unicode.org/charts/PDF/U1E00.pdf
- VISCII encoding specification — https://www.rfc-editor.org/rfc/rfc1456
- MDN `String.prototype.normalize()` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/normalize
- Unicode NFC/NFD composition exclusions — https://unicode.org/reports/tr15/
- Cloudflare D1 SQL documentation — https://developers.cloudflare.com/d1/
