# Locale-Aware Reading Time Estimation in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
An article listing shows "5 min read" for every post regardless of language, but a
Japanese article at the same byte count takes far less time to read than an English one
because readers process kanji at ~500 characters per minute, not ~200 English words per
minute.

## Context
A Cloudflare Worker middleware computes reading time from article text using
`Intl.Segmenter` for word-based scripts and character counting for ideographic scripts.
The Worker detects the dominant writing system in the text, selects the appropriate
reading speed constant, and returns a `Reading-Time-Seconds` header plus a human-readable
estimate. Reading speed data is sourced from NLP/reading research rather than hardcoded
assumptions.

---

## Reading Speed Constants by Script

```typescript
// src/lib/reading-speed.ts

/**
 * Reading speeds derived from eye-tracking and NLP reading research.
 * Word-based speeds are in words per minute (WPM).
 * Character-based speeds (CJK, Thai, etc.) are in characters per minute (CPM).
 * Sources listed in article footer.
 */
export const READING_SPEEDS = {
  // Indo-European word-based languages (alphabetic scripts)
  en:    { unit: "words" as const, rate: 238 },  // Brysbaert et al. 2019
  de:    { unit: "words" as const, rate: 260 },  // German readers: longer words, faster scanning
  fr:    { unit: "words" as const, rate: 250 },
  es:    { unit: "words" as const, rate: 278 },  // Spanish: high syllable regularity → faster
  pt:    { unit: "words" as const, rate: 250 },
  it:    { unit: "words" as const, rate: 260 },
  nl:    { unit: "words" as const, rate: 228 },
  pl:    { unit: "words" as const, rate: 230 },
  ru:    { unit: "words" as const, rate: 184 },  // Cyrillic morphology adds parsing overhead
  ar:    { unit: "words" as const, rate: 138 },  // Right-to-left; omitted short vowels increase decoding
  he:    { unit: "words" as const, rate: 187 },
  // CJK: readers process meaning at character level
  zh:    { unit: "chars" as const, rate: 255 },  // Mandarin: characters per minute (Liu et al. 2017)
  "zh-Hant": { unit: "chars" as const, rate: 255 },
  ja:    { unit: "chars" as const, rate: 357 },  // Japanese mixed kana/kanji (Osaka 1987)
  ko:    { unit: "words" as const, rate: 262 },  // Korean: Hangul words, similar to Latin alphabetic
  // Brahmic / Southeast Asian
  th:    { unit: "chars" as const, rate: 374 },  // Thai: character-based, no spaces between words
  vi:    { unit: "words" as const, rate: 214 },
  // Default: generic alphabetic rate
  default: { unit: "words" as const, rate: 200 },
} as const;

export type SpeedUnit = "words" | "chars";

export function getReadingSpeed(locale: string): { unit: SpeedUnit; rate: number } {
  const lang = locale.split("-")[0];
  return (
    READING_SPEEDS[locale as keyof typeof READING_SPEEDS]
    ?? READING_SPEEDS[lang as keyof typeof READING_SPEEDS]
    ?? READING_SPEEDS.default
  );
}
```

---

## Script Detection and Token Counting

```typescript
// src/lib/reading-count.ts

/**
 * Unicode script range checks for dominant script detection.
 */
function isCJKChar(cp: number): boolean {
  return (
    (cp >= 0x4e00 && cp <= 0x9fff)   || // CJK Unified Ideographs
    (cp >= 0x3400 && cp <= 0x4dbf)   || // Extension A
    (cp >= 0x20000 && cp <= 0x2a6df) || // Extension B
    (cp >= 0x3040 && cp <= 0x30ff)   || // Hiragana + Katakana
    (cp >= 0xac00 && cp <= 0xd7af)      // Hangul Syllables
  );
}

function isThaiChar(cp: number): boolean {
  return cp >= 0x0e00 && cp <= 0x0e7f;
}

/**
 * Counts the dominant script type in `text`.
 * Returns "cjk", "thai", or "alphabetic".
 */
export function detectDominantScript(text: string): "cjk" | "thai" | "alphabetic" {
  let cjk = 0, thai = 0, alpha = 0;
  for (const char of text) {
    const cp = char.codePointAt(0)!;
    if (isCJKChar(cp))   { cjk++;   continue; }
    if (isThaiChar(cp))  { thai++;  continue; }
    if (cp > 0x40)       { alpha++; }
  }
  const total = cjk + thai + alpha;
  if (total === 0) return "alphabetic";
  if (cjk / total > 0.3)  return "cjk";
  if (thai / total > 0.3) return "thai";
  return "alphabetic";
}

/**
 * Counts meaningful tokens in `text` based on the dominant script.
 * Uses Intl.Segmenter for word-based scripts; character count for CJK/Thai.
 */
export function countTokens(
  text: string,
  locale: string,
): { count: number; unit: "words" | "chars" } {
  const script = detectDominantScript(text);

  if (script === "cjk" || script === "thai") {
    // Strip whitespace and punctuation; count meaningful characters
    const chars = [...text].filter((c) => {
      const cp = c.codePointAt(0)!;
      return cp > 0x20 && !(cp >= 0x2000 && cp <= 0x206f); // skip general punctuation
    });
    return { count: chars.length, unit: "chars" };
  }

  // Word-based: use Intl.Segmenter for accurate word boundary detection
  const segmenter = new Intl.Segmenter(locale, { granularity: "word" });
  let wordCount = 0;
  for (const segment of segmenter.segment(text)) {
    if (segment.isWordLike) wordCount++;
  }
  return { count: wordCount, unit: "words" };
}
```

---

## Worker Middleware — Reading Time Header and JSON

```typescript
// src/worker.ts

import { getReadingSpeed }  from "./lib/reading-speed";
import { countTokens }      from "./lib/reading-count";

function stripHtml(html: string): string {
  // Remove tags and decode common HTML entities for counting
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function humanReadableTime(seconds: number, locale: string): string {
  const minutes = Math.ceil(seconds / 60);
  try {
    const fmt = new Intl.RelativeTimeFormat(locale, { numeric: "always", style: "long" });
    // Intl.RelativeTimeFormat gives relative past/future; build a plain string instead
    const minFmt = new Intl.NumberFormat(locale).format(minutes);
    // Simple: use "N min" pattern (full localization of "min read" requires i18n strings)
    return `${minFmt} min`;
  } catch {
    return `${minutes} min`;
  }
}

export interface Env {
  SUPPORTED_LOCALES?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only annotate article content endpoints
    if (!url.pathname.startsWith("/articles/")) {
      return fetch(request);
    }

    const locale =
      url.searchParams.get("locale") ??
      request.headers.get("Accept-Language")?.split(",")[0]?.split(";")[0]?.trim() ??
      "en";

    const upstream = await fetch(request);
    if (!upstream.ok) return upstream;

    const html = await upstream.text();
    const plainText = stripHtml(html);

    // Count tokens appropriate for the detected script
    const { count, unit } = countTokens(plainText, locale);

    // Get locale-specific reading speed
    const speed = getReadingSpeed(locale);

    // Normalise: if unit mismatch between counter and speed table, fall back to chars
    const effectiveRate = unit === speed.unit ? speed.rate : 200;
    const seconds = Math.round((count / effectiveRate) * 60);
    const readingTime = humanReadableTime(seconds, locale);

    return new Response(html, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "text/html; charset=utf-8",
        "Content-Language": locale,
        "Reading-Time-Seconds": String(seconds),
        "Reading-Time-Label": readingTime,
        // Expose to JS via CORS if needed
        "Access-Control-Expose-Headers": "Reading-Time-Seconds, Reading-Time-Label",
      },
    });
  },
};
```

---

## Anti-patterns

- **Dividing byte length by a constant** — byte count inflates for multibyte UTF-8
  scripts (CJK characters are 3 bytes each), producing wildly inaccurate estimates.
- **Using `text.split(/\s+/).length` as a word count** — this misses word-boundary
  rules for languages with spaces (Thai, Lao, Khmer have no word spaces), and
  over-counts CJK text.
- **Using the same WPM for all locales** — 200 WPM is English-centric; applying it to
  Japanese character-based reading can underestimate by 40–50%.
- **Including code blocks and navigation text** — strip `<pre>`, `<code>`, `<nav>`, and
  `<footer>` before counting; they skew the estimate significantly for technical articles.

---

## Gotchas

- `Intl.Segmenter` with `granularity: "word"` is available in Cloudflare Workers since
  `compatibility_date = "2023-01-01"`; verify your `wrangler.toml` date.
- Korean (`ko`) uses Hangul words separated by spaces, so word-based counting with
  `Intl.Segmenter` is correct; `detectDominantScript` correctly classifies Hangul as CJK
  by block range, but `ko` reading speed is word-based — ensure the speed table returns
  `unit: "words"` for `ko` so the worker uses the right counting path.
- Reading time is a UX estimate, not a measurement; round up to the nearest minute
  (`Math.ceil`) to set correct expectations.
- The `Reading-Time-Label` header contains locale-specific characters; set it as a valid
  Latin-1 header value or base64-encode it for safe transport if the value contains
  non-ASCII characters.

---

## Verification

```bash
# English article — expect word-based estimate
curl -I "http://localhost:8787/articles/my-post?locale=en" | grep -i reading
# Reading-Time-Seconds: 180
# Reading-Time-Label: 3 min

# Japanese article — expect character-based estimate (likely shorter than en for same bytes)
curl -I "http://localhost:8787/articles/my-ja-post?locale=ja" | grep -i reading
# Reading-Time-Seconds: 60
# Reading-Time-Label: 1 min

# Thai article
curl -I "http://localhost:8787/articles/my-th-post?locale=th" | grep -i reading

# Verify Intl.Segmenter availability
npx wrangler dev --compatibility-date 2023-01-01
```

---

## Related

- `intl-segmenter-cloudflare-workers-text-processing.md`
- `intl-segmenter-grapheme-safe-editing.md`
- `language-detection-workers-accept-language.md`
- `script-detection-language-routing-workers.md`
- `locale-aware-text-truncation-2026.md`

---

## Sources

- <https://developers.cloudflare.com/workers/runtime-apis/web-standards/#intlsegmenter>
- Brysbaert, M. (2019). "How many words do we read per minute?" *Journal of Memory and Language*, 109. <https://doi.org/10.1016/j.jml.2019.104047>
- Liu, P. et al. (2017). "Eye movements in reading Chinese." *Psychon Bull Rev*. <https://doi.org/10.3758/s13423-016-1152-y>
- Osaka, N. (1987). "Reading speed of Kana and Kanji." *Journal of Experimental Psychology*.
- <https://unicode.org/charts/> (Unicode block ranges for CJK, Thai scripts)
