# Locale-Aware URL Slug Normalization

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A German blog post titled "Über den Süßwasser-Ökosystem" should produce the slug
`ueber-den-suesswasser-oekosystem` for German audiences but `uber-den-susswasser-okosystem`
would be a lossy English transliteration. A Japanese article "東京の春祭り" needs to
become either a romanized slug (`tokyo-no-haru-matsuri`) or a percent-encoded path
(`%E6%9D%B1%E4%BA%AC%E3%81%AE%E6%98%A5%E7%A5%AD%E3%82%8A`). RTL Arabic titles must be
slug-safe without reversing word order. CMS slug generators that `toLowerCase()` and
replace spaces break for virtually every non-Latin script.

You need a deterministic, reversible-enough slug strategy per locale that is SEO-friendly,
URL-safe, and consistent across deploys.

## Context

A URL slug is the path segment that identifies a resource: `/blog/uber-den-suesswasser-oekosystem`.
Slugs must satisfy:

1. RFC 3986 unreserved characters only: `A-Z a-z 0-9 - . _ ~`
2. Lowercase for canonical matching (HTTP servers are case-sensitive)
3. Human-readable where possible (Google prefers words over opaque IDs)
4. Stable over time — changing slugs breaks inbound links and Google ranking

The challenge is that "human-readable" is locale-dependent. German special characters have
conventional ASCII equivalents (`ü→ue`, `ö→oe`, `ß→ss`). French drops diacritics
(`é→e`). Japanese has Hepburn romanization. Arabic has no universally accepted single
romanization standard.

Unicode normalization alone (`NFKD` + strip non-ASCII) is insufficient and produces
wrong output for German (`ü` → `u` instead of `ue`).

## Step 1 — Locale-Specific Character Mapping

Apply locale-specific substitutions before Unicode normalization:

```typescript
// lib/slug/locale-maps.ts
export const LOCALE_MAPS: Record<string, Record<string, string>> = {
  de: {
    ä: 'ae', ö: 'oe', ü: 'ue', Ä: 'ae', Ö: 'oe', Ü: 'ue', ß: 'ss',
  },
  sv: {
    å: 'a', ä: 'a', ö: 'o', Å: 'a', Ä: 'a', Ö: 'o',  // Swedish differs from German!
  },
  fi: {
    å: 'a', ä: 'a', ö: 'o',  // Finnish — same as Swedish
  },
  da: {
    æ: 'ae', ø: 'oe', å: 'aa', Æ: 'ae', Ø: 'oe', Å: 'aa',
  },
  no: {
    æ: 'ae', ø: 'oe', å: 'aa', Æ: 'ae', Ø: 'oe', Å: 'aa',
  },
  cs: {
    č: 'c', š: 's', ž: 'z', ř: 'r', ů: 'u', ě: 'e', ň: 'n', ť: 't', ď: 'd',
    Č: 'c', Š: 's', Ž: 'z', Ř: 'r', Ů: 'u', Ě: 'e', Ň: 'n', Ť: 't', Ď: 'd',
  },
  pl: {
    ą: 'a', ć: 'c', ę: 'e', ł: 'l', ń: 'n', ó: 'o', ś: 's', ź: 'z', ż: 'z',
    Ą: 'a', Ć: 'c', Ę: 'e', Ł: 'l', Ń: 'n', Ó: 'o', Ś: 's', Ź: 'z', Ż: 'z',
  },
  tr: {
    ç: 'c', ğ: 'g', ı: 'i', İ: 'i', ö: 'o', ş: 's', ü: 'u',
    Ç: 'c', Ğ: 'g', Ö: 'o', Ş: 's', Ü: 'u',
  },
};
```

Note: `ü` maps to `ue` in German but to `u` in Swedish — applying a generic Latin
diacritic stripper would silently produce wrong results for German.

## Step 2 — Unicode NFKD Normalization and ASCII Stripping

After locale-specific substitution, apply NFKD normalization to decompose remaining
composed characters (e.g. French `é` → `e` + combining accent), then strip non-ASCII:

```typescript
// lib/slug/normalize.ts
import { LOCALE_MAPS } from './locale-maps.js';

export function slugify(text: string, locale: string): string {
  const lang = new Intl.Locale(locale).language;  // strip region/script
  const map = LOCALE_MAPS[lang] ?? {};

  // 1. Locale-specific substitutions
  let s = text;
  for (const [from, to] of Object.entries(map)) {
    s = s.replaceAll(from, to);
  }

  // 2. NFKD decompose → strip combining marks
  s = s.normalize('NFKD').replace(/[̀-ͯ]/g, '');

  // 3. Lowercase (after decomposition, before script detection)
  s = s.toLowerCase();

  // 4. Replace non-alphanumeric runs with hyphens
  s = s.replace(/[^a-z0-9]+/g, '-');

  // 5. Trim leading/trailing hyphens
  s = s.replace(/^-+|-+$/g, '');

  return s || 'post';  // fallback for all-non-Latin input
}
```

## Step 3 — CJK and Non-Latin Script Handling

For Japanese, Chinese, and Korean — where no standard romanization is universally expected
in URLs — choose one of three strategies:

### Option A: Pinyin/Hepburn romanization (SEO-optimised)

Use a dedicated library:

```typescript
// For Japanese (hiragana/katakana → romaji)
import Kuroshiro from 'kuroshiro';
import KuromojiAnalyzer from 'kuroshiro-analyzer-kuromoji';

const kuroshiro = new Kuroshiro();
await kuroshiro.init(new KuromojiAnalyzer());

export async function slugifyCJK(text: string, locale: string): Promise<string> {
  const lang = new Intl.Locale(locale).language;

  if (lang === 'ja') {
    const romaji = await kuroshiro.convert(text, { to: 'romaji', mode: 'spaced' });
    return slugify(romaji, 'en');
  }

  // For zh: use pinyin library (e.g. 'pinyin' npm package)
  // For ko: use Revised Romanization (e.g. 'korean-romanize')
  // Fall through to Option B if no library available
  return encodeURIComponent(text.toLowerCase()).replace(/%../g, '-').replace(/-+/g, '-');
}
```

### Option B: Percent-encoded Unicode slugs (standards-compliant)

RFC 3987 allows IRI paths with Unicode code points. Modern browsers display decoded
characters in the address bar. Store the percent-encoded form canonically:

```typescript
export function slugifyIRI(text: string): string {
  // Normalize to NFC first (composed form is shorter)
  const nfc = text.normalize('NFC').toLowerCase();
  return nfc
    .replace(/\s+/g, '-')
    .replace(/[^\p{L}\p{N}-]/gu, '')  // keep letters, numbers, hyphens
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}
```

URLs like `/ja/東京の春祭り` are valid and indexed by Google, but they should be
NFC-normalized and consistently encoded.

### Option C: Opaque ID + title suffix (simplest, least SEO value)

```
/ja/posts/a1b2c3-東京の春祭り
```

The ID guarantees stability; the human-readable suffix aids accessibility but is
not used for routing (a 301 redirect if it changes).

## Step 4 — Collision Resolution and Deduplication

Slugs from different source strings may collide after normalization:

```typescript
// db/slugs.ts (using D1 or any key-value store)
export async function uniqueSlug(
  base: string,
  locale: string,
  db: D1Database,
): Promise<string> {
  const row = await db
    .prepare('SELECT COUNT(*) as n FROM slugs WHERE locale = ? AND slug LIKE ?')
    .bind(locale, `${base}%`)
    .first<{ n: number }>();

  if (!row || row.n === 0) return base;
  return `${base}-${row.n + 1}`;
}
```

## Step 5 — RTL Language Slugs

Arabic and Hebrew titles must not be reversed when converted to LTR slugs. Apply
transliteration or use Option B above. Never apply `.split(' ').reverse()` thinking you
are correcting RTL order — the internal logical word order of Arabic text is already LTR
in storage; only the display direction is RTL.

```typescript
// Arabic: ALA-LC romanization (Library of Congress standard)
// No standard npm package; use a lookup table for common characters
// or fallback to percent-encoding
const ARABIC_MAP: Record<string, string> = {
  'ا': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th', 'ج': 'j', 'ح': 'h',
  'خ': 'kh', 'د': 'd', 'ذ': 'dh', 'ر': 'r', 'ز': 'z', 'س': 's',
  'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': "'",
  'غ': 'gh', 'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm',
  'ن': 'n', 'ه': 'h', 'و': 'w', 'ي': 'y',
};
```

## Anti-patterns

- **Generic diacritic stripper** — `normalize('NFKD').replace(/\p{M}/gu,'')` maps German
  `ü` to `u` rather than `ue`; always check locale-specific maps first.
- **`toLowerCase()` before locale substitution** — German `Ü` must be replaced before
  lowercasing because the map entry is case-specific.
- **Changing slug strategy mid-lifecycle** — existing links will 404. If you must
  change, emit 301 redirects and keep a slug-history table.
- **Truncating slugs at a fixed byte limit** — a slug composed of CJK percent-encoded
  characters hits the byte limit at very few visible characters; truncate by grapheme
  cluster or visible character count, not bytes.
- **Using the same slug function for all locales** — the Danish `å→aa` expansion means a
  title with "årsrapport" produces a different slug than the Norwegian equivalent; locale
  context is mandatory.

## Gotchas

- `Intl.Locale(locale).language` strips region and script codes; `zh-Hant` and `zh-Hans`
  both become `zh`. For Chinese you may need to distinguish traditional from simplified
  for romanization purposes.
- Slugs stored in D1 are strings; collation for `LIKE` is binary by default, which is
  correct for slug deduplication (slugs are ASCII at rest).
- Google treats hyphen (`-`) and underscore (`_`) differently: hyphens are word
  separators (preferred), underscores are treated as connectors (less SEO value).
- Percent-encoded slugs are stored encoded in the database; always decode before
  displaying in breadcrumbs and `<title>` elements.

## Verification

```typescript
// tests/slug.test.ts
import { slugify } from '../lib/slug/normalize';

test('German umlaut expansion', () => {
  expect(slugify('Über den Süßwasser-Ökosystem', 'de')).toBe('ueber-den-suesswasser-oekosystem');
});
test('Swedish umlaut stripping (not expansion)', () => {
  expect(slugify('Österreich', 'sv')).toBe('osterreich');  // 'o' not 'oe'
});
test('French diacritic stripping', () => {
  expect(slugify('Déjà vu', 'fr')).toBe('deja-vu');
});
test('Polish special chars', () => {
  expect(slugify('Łódź', 'pl')).toBe('lodz');
});
test('Danish aa expansion', () => {
  expect(slugify('Årsrapport', 'da')).toBe('aarsrapport');
});
```

## Related

- `internationalized-routing-url-localization.md`
- `unicode-normalization-nfc-nfd.md`
- `hreflang-seo-2026.md`
- `locale-aware-seo-hreflang.md`
- `database-collation-locale-indexing.md`
- `idn-punycode-internationalized-email.md`

## Sources

- RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax
- RFC 3987 — Internationalized Resource Identifiers (IRIs)
- Unicode Standard Annex #15 — Unicode Normalization Forms (NFKD)
- Google Search Central: URL structure best practices
- Kuroshiro Japanese romanization library: https://kuroshiro.org/
- ALA-LC Romanization Tables (Library of Congress)
