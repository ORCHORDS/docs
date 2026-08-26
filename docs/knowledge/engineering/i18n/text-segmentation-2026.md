# text-segmentation-2026

**Issue:** A team truncates a chat message at 100 characters. The truncation lands in the middle of an emoji and renders as tofu. The team splits text on whitespace to count words. The Chinese text returns 1 word. The team uses `string.length` to validate input. The user pastes an emoji and the validation fails.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Text segmentation by whitespace or by code unit is wrong for non-Latin scripts and for emoji. The 2026 fix is `Intl.Segmenter`, which is now Baseline (newly available) in all major browsers.

## Root cause

`String.prototype.split(' ')` and `string.length` operate on whitespace and UTF-16 code units, respectively. They are wrong for:
- Chinese, Japanese, Korean (no spaces between words)
- Emoji (one user-perceived character can be 4-7 UTF-16 code units; ZWJ sequences are 1 grapheme)
- Combining marks (é = e + combining acute accent = 2 code units)
- Locale-specific word boundary rules (German compound words, Thai word segmentation)

UAX #29 defines grapheme cluster, word, and sentence boundaries. ECMA-402's `Intl.Segmenter` exposes them.

## The Intl.Segmenter API

```javascript
// 3 granularities
const graphemeSegmenter = new Intl.Segmenter('en', { granularity: 'grapheme' });
const wordSegmenter = new Intl.Segmenter('en', { granularity: 'word' });
const sentenceSegmenter = new Intl.Segmenter('en', { granularity: 'sentence' });

// Grapheme: user-perceived characters
const graphemes = [...graphemeSegmenter.segment('Hello👋🏽')];
// 6 graphemes: H, e, l, l, o, 👋🏽 (one emoji + skin tone modifier)

// Word: locale-aware word boundaries
const words = [...wordSegmenter.segment('Hello world!')];
// 3 segments: "Hello" (word-like), " " (not word-like), "world!" (word-like)
const wordTexts = words.filter(s => s.isWordLike).map(s => s.segment);
// ["Hello", "world!"]

// Sentence: locale-aware sentence boundaries
const sentences = [...sentenceSegmenter.segment('Dr. Smith said hi. He left.')];
// 2 sentences (the period after "Dr" is not a sentence break)
```

`Intl.Segmenter` is Stage 4 (finalized) in ECMA-402, Baseline in all major browsers as of 2026, and available in Node.js 16+.

## The grapheme-based safe truncation pattern

```javascript
function truncate(input, maxGraphemes) {
  const segmenter = new Intl.Segmenter('en', { granularity: 'grapheme' });
  const graphemes = [...segmenter.segment(input)];
  if (graphemes.length <= maxGraphemes) return input;
  return graphemes.slice(0, maxGraphemes).map(g => g.segment).join('') + '…';
}

truncate('Hi 👋🏽!', 5);  // "Hi 👋🏽!…" (never cuts an emoji in half)
truncate('short', 80);   // "short"
```

Slicing by UTF-16 index (`input.slice(0, 5)`) can land inside an emoji. Segmenting by grapheme never does.

## The locale-aware word count

```javascript
// English: split on whitespace (works)
'Hello world'.split(' ').length;  // 2

// Chinese: no spaces (broken)
'你好世界'.split(' ').length;  // 1 (wrong! 4 words)

// Japanese: use Intl.Segmenter
const jaSegmenter = new Intl.Segmenter('ja-JP', { granularity: 'word' });
const jaWords = [...jaSegmenter.segment('今日は天気がいい')].filter(s => s.isWordLike);
// ["今日", "は", "天気", "が", "いい"]
```

The Japanese segmentation uses UAX #29 word boundary rules, which know that `今日` is a word even without spaces.

## The 5 use cases

1. **Character counting** — `Intl.Segmenter({ granularity: 'grapheme' })` for user-perceived character count
2. **Word counting** — `Intl.Segmenter({ granularity: 'word' })` for search, indexing, reading time estimates
3. **Sentence splitting** — `Intl.Segmenter({ granularity: 'sentence' })` for TTS, summarization
4. **Safe text truncation** — grapheme-based slicing (see above)
5. **Search and highlight** — word boundaries to identify query matches

## The emoji + ZWJ sequence rules

Modern emoji are sequences of code points joined by Zero-Width Joiner (ZWJ, U+200D).

- 👨‍👩‍👧‍👦 = 👨 + ZWJ + 👩 + ZWJ + 👧 + ZWJ + 👦 (7 code points, 1 grapheme)
- 👋🏽 = 👋 + 🏽 (2 code points, 1 grapheme)
- 🇺🇸 = 🇺 + 🇸 (2 regional indicator code points, 1 grapheme)

`string.length` returns 7 for 👨‍👩‍👧‍👦. `Intl.Segmenter({ granularity: 'grapheme' })` returns 1.

## The 5 anti-patterns

1. **`string.length` for character count.** Returns UTF-16 code units, not user-perceived characters. Wrong for emoji, combining marks, CJK.
2. **`text.split(' ')` for word count.** Wrong for CJK, wrong for hyphenated words, wrong for German compounds.
3. **`text.slice(0, n)` for truncation.** Can cut emoji in half; user sees tofu.
4. **Regex-based word splitting.** `/\b\w+\b/g` is English-centric. Misses CJK, emoji, combining marks.
5. **No locale argument.** `new Intl.Segmenter()` (no locale) uses the runtime default; for multilingual input, pass the locale explicitly.

## The polyfill strategy

`Intl.Segmenter` is Baseline 2026. For older runtimes:

- `graphemer` (npm) — pure-JS grapheme splitter
- `Intl.Segmenter` polyfill from FormatJS
- `@formatjs/intl-segmenter/polyfill.js` — for older Safari and Node 14

Don't ship without segmentation. The polyfill is <5KB.

## Verification

The tell that text segmentation is real:

- `Intl.Segmenter` is used for character count, word count, truncation
- The locale is passed explicitly to the segmenter
- The polyfill is loaded for older runtimes
- Tests cover emoji + CJK + combining marks
- Search and highlight use word boundaries, not regex

The tell it isn't:

- `string.length` for character limits
- `split(' ')` for word counts
- `slice(0, n)` for truncation (without grapheme check)
- A user reports "my emoji got cut in half"

## Gotchas

- **`isWordLike` is `undefined` for non-word granularities.** Don't filter on it for grapheme/sentence.
- **Regional indicators combine into flags.** 🇺🇸 is a 2-code-point sequence; `length` returns 4 (2 surrogate pairs).
- **Indic script vowel signs are combining marks.** हिंदी = ह + ि + न् + द + ी (multiple combining marks). `length` returns 6; grapheme count is 3.
- **Sentence boundaries are locale-aware.** English period-after-abbreviation logic differs from French double-space. Pass the locale.
- **Grapheme segmentation is not free.** For very long strings, the cost adds up. Cache the segmenter; don't recreate per call.

## Related

- `i18n/character-encoding-utf-8-2026.md` — UTF-8 and code point handling
- `i18n/number-currency-formatting-2026.md` — Intl.NumberFormat
- `i18n/Intl-PluralRules-2026.md` — Intl.PluralRules
- `i18n/rtl-bidi-handling-2026.md` — Bidi and segmentation together

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- https://web.dev/blog/intl-segmenter — Baseline status (2026)
- https://github.com/tc39/proposal-intl-segmenter
- https://formatjs.github.io/docs/polyfills/intl-segmenter/
- https://www.unicode.org/reports/tr29/ — UAX #29 Unicode Text Segmentation
- https://developer.mozilla.org/en-US/blog/javascript-intl-segmenter-i18n/
- https://lingo.dev/en/javascript-i18n/intl-segmenter-api
- https://docs.deno.com/examples/intl_segmenter/ — Deno segmentation example
