# Using `Intl.Segmenter` in Cloudflare Workers for Text Tokenization

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to count words across CJK and Latin scripts, split text into sentences for AI summarisation, or truncate strings at grapheme boundaries without splitting emoji or combining characters — all inside a Cloudflare Worker.

## Context

`Intl.Segmenter` is part of the ECMAScript Internationalisation API and provides linguistically correct segmentation at the grapheme, word, or sentence level. Cloudflare Workers runtime (V8-based) has supported `Intl.Segmenter` since Workers runtime version **2023-03-01**. Older compatibility dates may not include it; check your `compatibility_date` in `wrangler.toml`.

The built-in `String.prototype.split()` is inadequate for CJK word boundaries (no spaces) and will incorrectly split multi-codepoint emoji sequences when used with array spread or `.length`.

---

## Core Helper: `segmentText`

```typescript
/**
 * segmentText — general-purpose Intl.Segmenter wrapper
 *
 * @param text        - Input string to segment
 * @param locale      - BCP 47 locale tag, e.g. "en", "ja", "zh-Hant"
 * @param granularity - "grapheme" | "word" | "sentence"
 * @returns           Array of segment strings
 */
export function segmentText(
  text: string,
  locale: string,
  granularity: Intl.SegmenterOptions["granularity"]
): string[] {
  const segmenter = new Intl.Segmenter(locale, { granularity });
  const segments: string[] = [];
  for (const { segment } of segmenter.segment(text)) {
    segments.push(segment);
  }
  return segments;
}

/** Count words, filtering out whitespace-only segments */
export function countWords(text: string, locale: string): number {
  const segmenter = new Intl.Segmenter(locale, { granularity: "word" });
  let count = 0;
  for (const { segment, isWordLike } of segmenter.segment(text)) {
    if (isWordLike) count++;
  }
  return count;
}

/** Split text into sentences for AI summarisation input */
export function splitSentences(text: string, locale: string): string[] {
  const segmenter = new Intl.Segmenter(locale, { granularity: "sentence" });
  return Array.from(segmenter.segment(text), ({ segment }) => segment.trim()).filter(Boolean);
}

/**
 * Truncate at a grapheme boundary — safe for emoji and combining characters.
 * Returns a string of at most `maxGraphemes` grapheme clusters.
 */
export function truncateGraphemes(text: string, maxGraphemes: number): string {
  const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  const clusters: string[] = [];
  for (const { segment } of segmenter.segment(text)) {
    if (clusters.length >= maxGraphemes) break;
    clusters.push(segment);
  }
  return clusters.join("");
}

// Worker handler example
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const text = url.searchParams.get("text") ?? "";
    const locale = url.searchParams.get("locale") ?? "en";

    const wordCount = countWords(text, locale);
    const sentences = splitSentences(text, locale);
    const preview = truncateGraphemes(text, 20);

    return Response.json({ wordCount, sentences, preview });
  },
};
```

---

## Word-Count for CJK vs Latin

For Latin text, word boundaries align with spaces; for Japanese and Chinese there are no spaces. `Intl.Segmenter` with `granularity: "word"` handles both:

```typescript
countWords("Hello world", "en");        // 2
countWords("こんにちは世界", "ja");        // 2 ("こんにちは" + "世界")
countWords("你好世界", "zh");              // 2 ("你好" + "世界")
countWords("Héllo wörld", "de");         // 2
```

The `isWordLike` flag on each segment filters punctuation and whitespace automatically.

---

## Sentence-Splitting for AI Summarisation

Pass sentence segments as individual items to Workers AI to stay within context windows and improve summarisation coherence:

```typescript
async function summariseSentences(
  text: string,
  locale: string,
  ai: Ai
): Promise<string[]> {
  const sentences = splitSentences(text, locale);
  return Promise.all(
    sentences.map((s) =>
      ai
        .run("@cf/facebook/bart-large-cnn", { input_text: s, max_length: 50 })
        .then((r: any) => r.summary)
    )
  );
}
```

---

## Grapheme-Safe Truncation

Using `.slice(0, n)` on a string truncates by UTF-16 code unit, which splits surrogate pairs (emoji) and leaves dangling combining characters:

```typescript
// Dangerous — may split emoji:
const bad = "👨‍👩‍👧‍👦hello".slice(0, 3); // broken bytes

// Safe:
const good = truncateGraphemes("👨‍👩‍👧‍👦hello", 2); // "👨‍👩‍👧‍👦h"
```

Always use `truncateGraphemes` when building display-facing truncation for user-generated content.

---

## Anti-patterns

- Using `text.split(" ")` for word counting — fails for CJK, double spaces, punctuation.
- Using `text.split(". ")` for sentence splitting — misses abbreviations, ellipses, and CJK sentence endings (`。`).
- Using `[...text].length` as grapheme count — counts codepoints, not clusters; breaks ZWJ emoji sequences.
- Creating a new `Intl.Segmenter` inside a hot loop per character — constructors are expensive; reuse or cache instances.

---

## Gotchas

- **Compatibility date**: `Intl.Segmenter` requires `compatibility_date = "2023-03-01"` or later in `wrangler.toml`. Earlier dates will throw `ReferenceError: Intl.Segmenter is not defined`.
- **Locale accuracy**: Word segmentation quality is locale-dependent. Passing `"zh"` for Traditional Chinese (should be `"zh-Hant"`) may give subtly different boundaries.
- **Sentence granularity + CJK**: V8's sentence segmenter for CJK is less accurate than a dedicated NLP model. For high-precision CJK sentence splitting, consider a short-circuit rule on `。！？` first.
- **Memory**: `Intl.Segmenter.segment()` returns a lazy iterator; for very large texts prefer iterating rather than converting to an array with `Array.from()`.

---

## Verification

```bash
# Local test via wrangler dev
curl "http://localhost:8787/?text=Hello+world.+How+are+you%3F&locale=en"
# Expected: { wordCount: 5, sentences: ["Hello world.", "How are you?"], preview: "Hello world. How are " }

curl "http://localhost:8787/?text=%E3%81%93%E3%82%93%E3%81%AB%E3%81%A1%E3%81%AF%E4%B8%96%E7%95%8C&locale=ja"
# Expected wordCount: 2
```

---

## Related

- `locale-fallback-chain-kv-workers.md`
- `unicode-normalization-nfc-nfd-workers-text.md`
- `language-detection-workers-ai-d1.md`

## Sources

- MDN: `Intl.Segmenter` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- Cloudflare Workers Runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- TC39 Proposal: Intl.Segmenter — https://github.com/tc39/proposal-intl-segmenter
