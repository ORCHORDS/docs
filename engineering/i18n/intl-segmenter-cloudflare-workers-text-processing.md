# Intl.Segmenter for Multilingual Text Processing in Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Safe Text Truncation and Segmentation Across Scripts in Workers

Slicing a string with `.slice(0, n)` cuts mid-grapheme in Devanagari, mid-emoji-sequence, or
mid-word in Thai (which has no word-boundary spaces). Cloudflare Workers V8 runtime ships
`Intl.Segmenter` natively; no polyfill or bundled ICU library is required. This article covers
word/sentence/grapheme segmentation patterns, CJK-aware truncation, RTL-aware ellipsis insertion,
and practical use in search snippets and content previews.

## Context

`Intl.Segmenter` accepts a locale string and a `{ granularity }` option (`'grapheme'`, `'word'`,
`'sentence'`). Word segmentation for scripts without spaces (CJK, Thai, Khmer) depends on the
locale subtag to select the correct dictionary. Workers V8 includes the ICU locale data bundle
that powers `Intl.Segmenter` without any additional imports.

## Grapheme-Safe Truncation

Naively slicing Unicode strings breaks extended grapheme clusters (family emoji, Devanagari
conjuncts, Arabic ligatures). Use grapheme granularity as the safe primitive:

```typescript
// src/segmenter.ts
export function truncateGraphemes(text: string, maxGraphemes: number, locale = 'und'): string {
  const seg = new Intl.Segmenter(locale, { granularity: 'grapheme' });
  let count = 0;
  let lastIndex = 0;
  for (const { index, segment } of seg.segment(text)) {
    if (count >= maxGraphemes) {
      return text.slice(0, lastIndex);
    }
    lastIndex = index + segment.length;
    count++;
  }
  return text; // shorter than maxGraphemes
}

// Usage in a content-preview Worker
const preview = truncateGraphemes('नमस्ते दुनिया 🌍', 5); // 'नमस्ते' (3 graphemes) + ' ' + 'द'
```

## CJK-Aware Text Truncation for Search Snippets

CJK text has no word-boundary spaces; slicing by character count can cut mid-word only when the
locale is set correctly for word granularity:

```typescript
// src/cjk-truncate.ts
export function truncateWords(
  text: string,
  maxWords: number,
  locale: string,
  ellipsis = '…' // …
): string {
  const seg = new Intl.Segmenter(locale, { granularity: 'word' });
  const words: string[] = [];
  for (const { segment, isWordLike } of seg.segment(text)) {
    if (!isWordLike) continue;
    words.push(segment);
    if (words.length >= maxWords) break;
  }
  const joined = words.join('');
  return joined.length < text.length ? joined + ellipsis : joined;
}

// Example
const zhSnippet = truncateWords(
  '这是一个关于国际化的测试句子，用于验证分词功能。',
  6,
  'zh-Hans'
); // '这是一个关于…'

const jaSnippet = truncateWords(
  '日本語のテキストを正しく分割するテストです。',
  5,
  'ja'
); // '日本語のテキスト…'
```

## RTL-Aware Ellipsis Insertion

In RTL languages the ellipsis visually belongs at the logical end of the string (which is on the
left in display). Do not concatenate `…` naively in Arabic or Hebrew; insert a Unicode directional
marker to anchor it correctly:

```typescript
// src/rtl-ellipsis.ts
const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur', 'yi', 'dv']);

function isRtlLocale(locale: string): boolean {
  const base = locale.split('-')[0].toLowerCase();
  return RTL_LOCALES.has(base);
}

export function truncateWithEllipsis(
  text: string,
  maxGraphemes: number,
  locale: string
): string {
  const seg = new Intl.Segmenter(locale, { granularity: 'grapheme' });
  const graphemes: string[] = [];
  for (const { segment } of seg.segment(text)) {
    graphemes.push(segment);
    if (graphemes.length >= maxGraphemes) break;
  }
  if (graphemes.length < text.replace(/\s+/g, '').length / 1 /* rough check */) {
    // full text was shorter
    return text;
  }
  const truncated = graphemes.join('');
  if (isRtlLocale(locale)) {
    // RLM + … keeps the ellipsis anchored at the logical end (visually left)
    return truncated + '‏…';
  }
  return truncated + '…';
}
```

## Sentence Segmentation for Search Highlight Context

Search UIs need to display the sentence containing a matched term, not an arbitrary character
window:

```typescript
// src/search-context.ts
export function extractSentenceContext(
  text: string,
  matchStart: number,
  matchEnd: number,
  locale: string
): string {
  const seg = new Intl.Segmenter(locale, { granularity: 'sentence' });
  let bestSentence = text;
  let bestScore = Infinity;

  for (const { segment, index } of seg.segment(text)) {
    const sentEnd = index + segment.length;
    if (sentEnd < matchStart) continue; // sentence before the match
    if (index > matchEnd) break;        // sentence after the match

    // pick the sentence whose center is closest to the match center
    const matchCenter = (matchStart + matchEnd) / 2;
    const sentCenter = index + segment.length / 2;
    const score = Math.abs(sentCenter - matchCenter);
    if (score < bestScore) {
      bestScore = score;
      bestSentence = segment.trim();
    }
  }
  return bestSentence;
}
```

## Full Worker Handler: Content Preview

```typescript
// src/worker.ts
import { truncateWords } from './cjk-truncate';
import { truncateWithEllipsis } from './rtl-ellipsis';
import { extractSentenceContext } from './search-context';

interface Env {
  PREVIEW_MAX_WORDS: string; // 20
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const text = url.searchParams.get('text') ?? '';
    const locale = url.searchParams.get('locale') ?? 'en';
    const mode = url.searchParams.get('mode') ?? 'words'; // 'words' | 'graphemes' | 'ellipsis'
    const max = parseInt(url.searchParams.get('max') ?? '20', 10);

    let result: string;
    if (mode === 'graphemes') {
      result = truncateWithEllipsis(text, max, locale);
    } else {
      result = truncateWords(text, max, locale);
    }

    return Response.json({ locale, mode, max, result });
  },
};
```

## Anti-patterns

- Using `.slice(0, n)` for display truncation in any locale — always use grapheme granularity.
- Passing `'und'` (undetermined) locale to word segmentation — for CJK languages this falls back
  to a generic algorithm and produces wrong word boundaries.
- Concatenating `…` without considering text direction — Arabic/Hebrew truncated strings need
  `‏` before the ellipsis.
- Using `Intl.Segmenter` for sentence boundary detection in languages where CLDR sentence data is
  sparse (some African scripts) — verify coverage before shipping.
- Caching `Intl.Segmenter` instances across requests at module scope when the locale changes per
  request — the constructor is cheap; create it per call or cache with a `Map<locale, Segmenter>`.

## Gotchas

- Thai word segmentation in V8 ICU works for the `th` locale; `th-TH` also works and is preferred
  when the full BCP 47 tag is available from the request.
- `isWordLike` is `false` for punctuation and whitespace segments — always filter on it when
  counting words for truncation.
- `Intl.Segmenter` at `'sentence'` granularity can return a segment containing only whitespace at
  certain boundaries; trim before display.
- Workers V8 ICU data bundle may not include word-break dictionaries for all scripts in all runtime
  versions — test Khmer and Lao truncation after any Workers runtime upgrade.
- Emoji with skin-tone or hair modifiers are single grapheme clusters; `maxGraphemes: 10` on
  emoji-heavy strings will not mean 10 characters in byte terms.

## Verification

```typescript
// test/segmenter.test.ts
import { describe, expect, it } from 'vitest';
import { truncateGraphemes } from '../src/segmenter';
import { truncateWords } from '../src/cjk-truncate';

describe('truncateGraphemes', () => {
  it('does not cut Devanagari conjuncts', () => {
    const result = truncateGraphemes('नमस्ते', 3);
    // 'न', 'म', 'स्ते' are 3 grapheme clusters
    expect([...new Intl.Segmenter('hi', { granularity: 'grapheme' }).segment(result)]).toHaveLength(3);
  });

  it('preserves family emoji as single grapheme', () => {
    const family = '\u{1F468}‍\u{1F469}‍\u{1F467}';
    expect(truncateGraphemes(family + 'abc', 2)).toBe(family + 'a');
  });
});

describe('truncateWords', () => {
  it('correctly segments Chinese', () => {
    const result = truncateWords('今天天气很好，适合出行。', 3, 'zh-Hans');
    expect(result).toBe('今天天气很好…');
  });
});
```

## Related

- `intl-segmenter-grapheme-safe-editing.md`
- `text-segmentation-2026.md`
- `cjk-ime-composition-events-2026.md`
- `rtl-logical-properties-cloudflare-pages-headers.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- https://unicode.org/reports/tr29/ (Unicode Text Segmentation)
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/
