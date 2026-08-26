# Tibetan and Dzongkha Script Support in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Pages serving Tibetan (`bo`) or Dzongkha (`dz`) content display broken stacked consonant clusters,
incorrect line breaks, or fallback Latin glyphs because the origin returns content without the
necessary font, segmentation, or line-breaking metadata.

## Context
Tibetan script (Unicode block U+0F00–U+0FFF) is used for Tibetan (spoken in Tibet, Ladakh, Sikkim),
Dzongkha (the national language of Bhutan), and several other Himalayan languages. Unlike most
scripts, Tibetan has no spaces between syllables; syllables are separated by a tsheg (U+0F0B ་) and
sentences by a shad (U+0F0D །). Stacking consonants (subjoined letters) use U+0F90–U+0FAD and must
render as ligatures, requiring an OpenType font. Cloudflare Workers can inject the correct font,
enforce line-break opportunities, and serve locale-aware segmentation metadata.

## Unicode Tibetan Block Overview

```typescript
// tibetan-ranges.ts
export const TIBETAN = {
  TSHEG: "་",           // syllable separator ་
  SHAD: "།",            // single shad (sentence terminator) །
  DOUBLE_SHAD: "༎",     // double shad ༎
  SUBJOINED_START: 0x0F90,   // start of subjoined consonants
  SUBJOINED_END: 0x0FAD,     // end of subjoined consonants
  BLOCK_START: 0x0F00,
  BLOCK_END: 0x0FFF,
};

export function isTibetanCodepoint(cp: number): boolean {
  return cp >= TIBETAN.BLOCK_START && cp <= TIBETAN.BLOCK_END;
}

export function hasTibetanContent(text: string): boolean {
  for (const ch of text) {
    if (isTibetanCodepoint(ch.codePointAt(0)!)) return true;
  }
  return false;
}
```

## Line-Break Opportunity Injection

Tibetan text must break only at tsheg or shad boundaries, never mid-syllable. CSS
`word-break: keep-all` does not help with Tibetan; instead, inject a zero-width space (U+200B)
after each tsheg and shad so the browser's line-breaker has explicit opportunities.

```typescript
// tibetan-linebreak.ts
const TSHEG = "་";
const SHAD_RE = /[།༎༑༔]/g;
const ZWS = "​";

export function injectTibetanLineBreaks(text: string): string {
  return text
    .replaceAll(TSHEG, TSHEG + ZWS)
    .replace(SHAD_RE, m => m + ZWS);
}

export function stripTibetanLineBreaks(text: string): string {
  // Remove injected ZWS for storage or indexing
  return text.replaceAll(ZWS, "");
}
```

## HTMLRewriter: Font and Line-Break Injection

Use `HTMLRewriter` to inject both the Noto Serif Tibetan font (which includes stacking ligatures)
and the processed text nodes in a single O(n) pass without buffering the full HTML.

```typescript
// tibetan-rewriter.ts
import { hasTibetanContent, injectTibetanLineBreaks } from "./tibetan-linebreak";

const FONT_LINK = `<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Noto+Serif+Tibetan:wght@400;700&display=swap">
<style>
  :lang(bo), :lang(dz) {
    font-family: 'Noto Serif Tibetan', serif;
    line-height: 1.8;        /* stacked consonants need extra vertical space */
    word-break: keep-all;    /* belt-and-suspenders for non-Tibetan-aware engines */
  }
</style>`;

export function applyTibetanRewriter(response: Response): Response {
  return new HTMLRewriter()
    .on("head", {
      element(el) {
        el.prepend(FONT_LINK, { html: true });
      },
    })
    .on("*", {
      text(chunk) {
        if (hasTibetanContent(chunk.text)) {
          chunk.replace(injectTibetanLineBreaks(chunk.text), { html: false });
        }
      },
    })
    .transform(response);
}
```

## Segmenting Tibetan Syllables in a Worker API

An API endpoint that returns Tibetan text for a mobile app may need to pre-segment syllables so the
client can highlight them during audio playback. Syllables are sequences between tsheg marks.

```typescript
// tibetan-segmenter.ts
const TSHEG = "་";
const SHAD_PATTERN = /[།༎]/;

export interface TibetanSegment {
  text: string;
  type: "syllable" | "shad" | "other";
}

export function segmentTibetan(text: string): TibetanSegment[] {
  const segments: TibetanSegment[] = [];
  for (const part of text.split(TSHEG)) {
    if (SHAD_PATTERN.test(part)) {
      const [syllable, ...rest] = part.split(SHAD_PATTERN);
      if (syllable) segments.push({ text: syllable, type: "syllable" });
      for (const r of rest) {
        segments.push({ text: r, type: "shad" });
      }
    } else if (part) {
      segments.push({ text: part, type: "syllable" });
    }
  }
  return segments;
}

// Worker route: POST /api/segment?lang=bo
export async function handleSegmentRequest(request: Request): Promise<Response> {
  const { text } = await request.json<{ text: string }>();
  if (typeof text !== "string" || text.length > 10_000) {
    return Response.json({ error: "invalid input" }, { status: 400 });
  }
  return Response.json({ segments: segmentTibetan(text) });
}
```

## Collation for Tibetan Search

Tibetan alphabetical order follows the traditional 30-letter order (ka, kha, ga…), not Unicode
codepoint order. Use `Intl.Collator` with `locale: "bo"` for sort operations on D1 result sets.

```typescript
// tibetan-collation.ts
const collator = new Intl.Collator("bo", { sensitivity: "base" });

export function sortTibetanWords(words: string[]): string[] {
  return [...words].sort(collator.compare);
}

// For D1: fetch rows then sort in the Worker (SQLite has no Tibetan ICU collation by default)
export async function searchTibetan(
  db: D1Database,
  query: string
): Promise<string[]> {
  const results = await db
    .prepare("SELECT title FROM articles WHERE script = 'Tibt' AND title LIKE ?")
    .bind(`%${query}%`)
    .all<{ title: string }>();
  return sortTibetanWords(results.results.map(r => r.title));
}
```

## Locale Tag Handling for Tibetan Languages

The IANA subtag registry includes `bo` (Tibetan), `dz` (Dzongkha), and `lep` (Lepcha). The script
subtag `Tibt` is useful when content may be transliterated into Latin (`bo-Latn`).

```typescript
// locale-tags.ts
const TIBETAN_LOCALES = ["bo", "bo-CN", "bo-IN", "dz", "dz-BT"];

export function isTibetanLocale(locale: string): boolean {
  const lang = locale.split("-")[0].toLowerCase();
  return lang === "bo" || lang === "dz";
}

export function getTibetanScript(locale: string): "Tibt" | "Latn" {
  return locale.includes("Latn") ? "Latn" : "Tibt";
}
```

## Anti-patterns
- Using `Intl.Segmenter` with `granularity: "word"` for Tibetan — it falls back to Unicode word
  break rules which do not understand tsheg-delimited syllables
- Breaking lines at U+0020 (space) — Tibetan text rarely contains spaces; use tsheg boundaries
- Requesting `Noto Sans Tibetan` (sans) for body text — use `Noto Serif Tibetan` which has better
  stacking glyph coverage
- Normalising Tibetan text to NFC only — some stacking sequences require canonical ordering in NFD
  first; use NFC as the final form after NFD intermediate
- Treating all U+0F00–U+0FFF codepoints as printable text — includes Om symbols and astrological
  marks that should not be segmented as syllables

## Gotchas
- Stacked consonants increase line height by 50–100%; set `line-height: 1.8` minimum in CSS
- U+0F00 (Tibetan Syllable Om) is a single codepoint, not a consonant sequence
- Dzongkha (`dz`) uses the same Unicode block as Tibetan (`bo`) but has different orthographic rules
- `font-feature-settings: "mark" 1, "mkmk" 1` must be enabled for proper accent mark attachment
- Tibetan digits (U+0F20–U+0F29) and Latin digits may coexist in a single string — handle both
  with `Intl.NumberFormat("bo")` for Tibetan numerals or `"bo-u-nu-latn"` for Latin

## Verification
1. Render a page with the string `སྐྱེ་བོ་མི་ཡིས།` in Chrome DevTools and confirm no tofu (□)
   glyphs appear and stacked letters render as ligatures.
2. Call `injectTibetanLineBreaks` on a 500-character Tibetan string and assert every tsheg is
   followed by U+200B.
3. Call `segmentTibetan("སྐྱེ་བོ་")` and assert the result contains two syllable segments.
4. Sort `["ད", "ཀ", "ཕ", "ག"]` with the Tibetan collator and assert the order matches the
   traditional alphabet: ཀ, ག, ད, ཕ.

## Related
- `/documentation/docs/policies/i18n/thai-line-breaking.md`
- `/documentation/docs/policies/i18n/indic-script-rendering.md`
- `/documentation/docs/policies/i18n/multilingual-font-loading-subsetting.md`
- `/documentation/docs/policies/i18n/unicode-normalization-nfc-nfd.md`
- `/documentation/docs/policies/i18n/intl-segmenter-cloudflare-workers-text-processing.md`

## Sources
- Unicode Tibetan block: https://www.unicode.org/charts/PDF/U0F00.pdf
- Noto Serif Tibetan: https://fonts.google.com/noto/specimen/Noto+Serif+Tibetan
- CLDR Tibetan locale data: https://github.com/unicode-org/cldr/blob/main/common/main/bo.xml
- OpenType Tibetan shaping: https://docs.microsoft.com/en-us/typography/script-development/tibetan
- BCP 47 `bo` subtag: https://www.iana.org/assignments/language-subtag-registry
