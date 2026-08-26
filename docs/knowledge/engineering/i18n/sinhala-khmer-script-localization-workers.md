# Sinhala and Khmer Script Localization in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Worker serves content for Sri Lanka (Sinhala, `si`) or Cambodia (Khmer, `km`) and runs into font fallback failures, incorrect Intl output, broken word segmentation, or garbled romanization in URL slugs. Both scripts are Brahmic abugidas with complex conjunct rules that differ from Latin character handling.

---

## Context

Sinhala (`si-LK`) and Khmer (`km-KH`) belong to the Brahmic script family. They use abugida writing systems where consonant clusters, vowel diacritics, and dependent vowel signs are stacked or combined rather than written sequentially as isolated code points. This has direct consequences for:

- **Segmentation**: `Intl.Segmenter` word breaks differ from naïve `.split(' ')`.
- **Collation**: ICU ordering follows script-specific tailoring; D1 `ORDER BY` without collation produces wrong results.
- **Slug generation**: Transliteration must handle multi-code-point grapheme clusters.
- **`Intl.NumberFormat`**: Both locales use their own digit sets (`si` uses ASCII digits by default; `km` uses Khmer digits `០–៩` by default in some contexts).
- **Font delivery**: Workers + R2 pipelines must serve the correct Unicode block subsets.

Cloudflare Workers runs V8 with full ICU data, so `Intl` APIs work, but you must opt in to locale-specific behavior explicitly.

---

## 1. Detecting Sinhala and Khmer Requests

```typescript
// src/locale-detect.ts
export function detectSinhalaKhmer(request: Request): 'si-LK' | 'km-KH' | null {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country;
  if (country === 'LK') return 'si-LK';
  if (country === 'KH') return 'km-KH';

  const accept = request.headers.get('Accept-Language') ?? '';
  const primary = accept.split(',')[0].trim().split(';')[0].toLowerCase();
  if (primary.startsWith('si')) return 'si-LK';
  if (primary.startsWith('km')) return 'km-KH';
  return null;
}
```

---

## 2. Number Formatting for Sinhala and Khmer

Sinhala uses Western Arabic digits by default. Khmer has its own digit set but most web contexts fall back to Latin; explicitly request native digits with `numberingSystem`.

```typescript
// src/number-format.ts
export function formatNumber(value: number, locale: string): string {
  // Khmer: use Khmer numerals explicitly
  if (locale.startsWith('km')) {
    return new Intl.NumberFormat('km-KH-u-nu-khmr', {
      useGrouping: true,
    }).format(value);
  }

  // Sinhala: standard Western digits, comma grouping
  if (locale.startsWith('si')) {
    return new Intl.NumberFormat('si-LK', {
      useGrouping: true,
    }).format(value);
  }

  return new Intl.NumberFormat(locale).format(value);
}

export function formatCurrency(amount: number, locale: string): string {
  const options: Intl.NumberFormatOptions = {
    style: 'currency',
    currency: locale.startsWith('km') ? 'KHR' : 'LKR',
    minimumFractionDigits: locale.startsWith('km') ? 0 : 2,
  };
  return new Intl.NumberFormat(locale, options).format(amount);
}
```

---

## 3. Text Segmentation for Sinhala and Khmer

Khmer historically has no spaces between words; word boundaries rely entirely on dictionary-based segmentation, which ICU approximates. Sinhala has spaces but conjunct clusters mean grapheme segmentation differs from Latin.

```typescript
// src/segment.ts
export function segmentWords(text: string, locale: string): string[] {
  // Intl.Segmenter uses locale-tailored rules including Khmer dictionary breaks
  const seg = new Intl.Segmenter(locale, { granularity: 'word' });
  const words: string[] = [];
  for (const { segment, isWordLike } of seg.segment(text)) {
    if (isWordLike) words.push(segment);
  }
  return words;
}

export function graphemeClusters(text: string, locale: string): string[] {
  const seg = new Intl.Segmenter(locale, { granularity: 'grapheme' });
  return [...seg.segment(text)].map(s => s.segment);
}

// Worker handler
export default {
  async fetch(request: Request): Promise<Response> {
    const locale = detectLocale(request); // 'km-KH' | 'si-LK'
    const { text } = await request.json<{ text: string }>();
    const words = segmentWords(text, locale);
    return Response.json({ words, count: words.length });
  },
};
```

---

## 4. URL Slug Generation with Transliteration Fallback

For Sinhala and Khmer, slugs cannot be formed from native characters for ASCII-only routing. Romanization must be handled before `encodeURIComponent` or use transliteration tables.

```typescript
// src/slug.ts

// Minimal Khmer-to-Latin transliteration map (expand with full UNGEGN table)
const KHMER_LATIN: Record<string, string> = {
  'ក': 'k', 'ខ': 'kh', 'គ': 'g', 'ឃ': 'gh', 'ង': 'ng',
  'ច': 'c', 'ឆ': 'ch', 'ជ': 'j', 'ឈ': 'jh', 'ញ': 'ny',
  // ... full table omitted for brevity
};

export function slugify(text: string, locale: string): string {
  let out = text.toLowerCase();

  if (locale.startsWith('km')) {
    out = [...new Intl.Segmenter('km-KH', { granularity: 'grapheme' }).segment(out)]
      .map(({ segment }) => KHMER_LATIN[segment] ?? segment)
      .join('');
  }

  if (locale.startsWith('si')) {
    // Sinhala: use Unicode NFD then strip combining marks for a rough romanization
    out = out.normalize('NFD').replace(/[̀-්ͯ-෿]/g, '');
  }

  return out
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}
```

---

## 5. Date and Relative Time Formatting

```typescript
// src/dates.ts
export function formatDate(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

export function formatRelative(date: Date, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const diffMs = date.getTime() - Date.now();
  const diffDays = Math.round(diffMs / 86_400_000);

  if (Math.abs(diffDays) < 1) {
    const diffHours = Math.round(diffMs / 3_600_000);
    return rtf.format(diffHours, 'hour');
  }
  return rtf.format(diffDays, 'day');
}

// Example output for 'km-KH': "ថ្ងៃ​ច័ន្ទ ទី​១ ខែ​មករា ឆ្នាំ​២០២៦"
// Example output for 'si-LK': "2026 ජනවාරි 1"
```

---

## 6. Serving Locale-Specific Font Subsets from R2

Sinhala resides in Unicode block U+0D80–U+0DFF; Khmer in U+1780–U+17FF. Serve targeted subsets to avoid loading full CJK/Indic stacks.

```typescript
// src/fonts.ts
const FONT_SUBSETS: Record<string, string> = {
  'si': 'fonts/noto-sans-sinhala-subset.woff2',
  'km': 'fonts/noto-sans-khmer-subset.woff2',
};

export async function serveFontSubset(
  request: Request,
  env: Env,
): Promise<Response | null> {
  const locale = detectLocale(request);
  const lang = locale?.split('-')[0];
  const key = lang ? FONT_SUBSETS[lang] : undefined;
  if (!key) return null;

  const obj = await env.R2_BUCKET.get(key);
  if (!obj) return null;

  return new Response(obj.body, {
    headers: {
      'Content-Type': 'font/woff2',
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Access-Control-Allow-Origin': '*',
    },
  });
}
```

---

## Anti-patterns

- **Splitting Khmer text on spaces** — Khmer uses no inter-word spaces; `.split(' ')` produces one massive token. Always use `Intl.Segmenter`.
- **Assuming grapheme = code point** — Sinhala conjuncts span 2–4 code points. Use `Intl.Segmenter` with `granularity: 'grapheme'` for length and slicing.
- **Using `toLowerCase()` alone for slug normalization** — Sinhala and Khmer have no case; the step is harmless but does not romanize. Always apply the transliteration step first.
- **Omitting `currency` for LKR / KHR** — Both currencies have unusual minor-unit rules (KHR has no subunit in practice). Set `minimumFractionDigits` explicitly.

---

## Gotchas

- **KHR formatting**: `Intl.NumberFormat` with `currency: 'KHR'` may display with 2 decimal places in ICU but KHR amounts are always integers. Override with `minimumFractionDigits: 0, maximumFractionDigits: 0`.
- **Khmer dictionary word-break accuracy**: ICU's Khmer dictionary covers common vocabulary but misses domain-specific terms; consider post-processing with a KH NLP library where precision matters.
- **Sinhala `Intl.Collator`**: The default collation for `si` follows Unicode DUCET with Sinhala tailoring. Test sorting with actual Sinhala strings, not romanized equivalents.
- **`si` vs `si-LK`**: Both resolve identically in V8 ICU but use the full BCP 47 tag to be explicit and future-proof.
- **R2 CORS**: Font requests from the browser are cross-origin; the `Access-Control-Allow-Origin` header is mandatory.

---

## Verification

```typescript
// verify.ts — run with `wrangler dev` and call the /test endpoint
import { formatNumber, formatCurrency } from './src/number-format';
import { segmentWords } from './src/segment';

const checks = [
  // Khmer digits
  { fn: () => formatNumber(1234567, 'km-KH'), expected: '១.២៣៤.៥៦៧' },
  // Sinhala currency
  { fn: () => formatCurrency(5000, 'si-LK'), contains: 'රු' },
  // Khmer word segmentation: "ខ្ញុំស្រលាញ់ប្រទេសខ្មែរ" = "I love Cambodia"
  { fn: () => segmentWords('ខ្ញុំស្រលាញ់ប្រទេសខ្មែរ', 'km-KH').length >= 3, expected: true },
];

for (const { fn, expected, contains } of checks) {
  const result = fn();
  const pass = contains
    ? String(result).includes(contains)
    : result === expected;
  console.log(pass ? 'PASS' : 'FAIL', result);
}
```

---

## Related

- `ethiopic-amharic-script-rendering-workers.md`
- `tibetan-dzongkha-script-support-workers.md`
- `myanmar-zawgyi-unicode-conversion-workers.md`
- `indic-script-rendering.md`
- `intl-segmenter-cloudflare-workers-text-processing.md`
- `r2-font-subsetting-multi-script-pipeline-2026.md`

---

## Sources

- Unicode Sinhala block: https://www.unicode.org/charts/PDF/U0D80.pdf
- Unicode Khmer block: https://www.unicode.org/charts/PDF/U1780.pdf
- ICU Locale Data — si, km: https://github.com/unicode-org/icu/tree/main/icu4c/source/data/locales
- CLDR Khmer data: https://github.com/unicode-org/cldr/blob/main/common/main/km.xml
- CLDR Sinhala data: https://github.com/unicode-org/cldr/blob/main/common/main/si.xml
- Intl.Segmenter spec: https://tc39.es/proposal-intl-segmenter/
- Cloudflare Workers Intl support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
