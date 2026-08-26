# BiDi in User-Generated Social Content: Hashtags, Mentions, and URLs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Users of an example.com social feed post content in Arabic and Hebrew alongside Latin usernames,
English hashtags, and HTTPS URLs. The rendered posts show garbled ordering: an Arabic sentence
ends with a URL that appears before the Arabic words rather than after; a Hebrew post where
`#music @john` appears on the left but the Hebrew text flows right; a mixed Arabic/English
hashtag `#موسيقى_Pop` triggers the Unicode BiDi algorithm to split the hashtag visually.
None of these are rendering engine bugs—they are consequences of unresolved BiDi control
character placement and inadequate base-direction assignment in the application layer.

## Context

The Unicode Bidirectional Algorithm (UBA, Unicode TR#9) resolves display order from a stream of
characters with assigned Bidi_Class properties. Social content has four classes of span that
interact badly with the default algorithm:

1. **Strong RTL text**: Arabic, Hebrew, Syriac paragraphs
2. **Weak neutral spans**: URLs (`https://example.com/track/123`), numbers, punctuation
3. **Structured Latin tokens**: `@mention`, `#hashtag`, `$cashtag`
4. **Embedded directional overrides**: users sometimes paste Unicode control characters
   (`U+202A`–`U+202E`, `U+2066`–`U+2069`) for manual override, which can escape sanitizers

The application must:
- Detect paragraph base direction correctly
- Isolate structured tokens from surrounding RTL text
- Strip or encode dangerous directional control characters from user input
- Render URLs and mentions without breaking the surrounding paragraph direction

## Detecting Base Direction

The first strong directional character in the paragraph determines its base direction.
`Intl.Segmenter` does not expose Bidi_Class; use a lightweight detector based on the `Bidi_Class`
property of the first strong character:

```ts
// src/i18n/bidi.ts

// Unicode ranges for strong RTL characters
// Covers Arabic, Hebrew, Syriac, Thaana, NKo, Samaritan, Mandaic, and other RTL scripts
const RTL_STRONG_RE = /[֐-׿؀-ۿ܀-ݏ߀-߿ࠀ-࠿ࡀ-࡟יִ-ﭏﭐ-﷿ﹰ-﻿]/;

export type Dir = 'ltr' | 'rtl' | 'auto';

/**
 * Returns 'rtl' if the first strong-directional character in the string is RTL,
 * 'ltr' if LTR. Returns 'auto' if no strong character is found (emoji-only, pure numbers).
 * Maps to the HTML `dir` attribute: set this on the paragraph/div element.
 */
export function detectBaseDir(text: string): Dir {
  for (const char of text) {
    if (RTL_STRONG_RE.test(char)) return 'rtl';
    // AL, AN, R → RTL strong (covered above)
    // L → LTR strong
    const cp = char.codePointAt(0)!;
    if (
      (cp >= 0x0041 && cp <= 0x005A) ||  // A-Z
      (cp >= 0x0061 && cp <= 0x007A) ||  // a-z
      (cp >= 0x00C0 && cp <= 0x024F) ||  // Latin Extended
      (cp >= 0x0370 && cp <= 0x03FF) ||  // Greek
      (cp >= 0x0400 && cp <= 0x04FF)     // Cyrillic
    ) {
      return 'ltr';
    }
  }
  return 'auto';
}
```

Assign the result to the post container's `dir` attribute:

```tsx
// components/SocialPost.tsx
import { detectBaseDir } from '../i18n/bidi';

function SocialPost({ content }: { content: string }) {
  const dir = detectBaseDir(content);
  return (
    <div dir={dir} className="post-body">
      <SafeRichContent content={content} />
    </div>
  );
}
```

`dir="auto"` is a valid CSS/HTML value but browsers apply it to the entire block and can produce
unexpected results with embedded Latin tokens. Explicit `'ltr'` or `'rtl'` gives the application
control.

## Isolating Structured Tokens

Hashtags, mentions, and URLs are syntactically LTR even when embedded in RTL text. Without
isolation the surrounding RTL context "bleeds" into them, reversing their visual position within
the line. The Unicode BiDi isolation characters—First Strong Isolate (`U+2068 FSI`),
Left-to-Right Isolate (`U+2066 LRI`), Right-to-Left Isolate (`U+2067 RLI`), and Pop Directional
Isolate (`U+2069 PDI`)—solve this. The HTML equivalent is `<bdi>` (Bidirectional Isolation).

Use `<bdi>` in rendered HTML output; use Unicode isolate characters for plain-text contexts
(notifications, push payloads, clipboard):

```ts
// src/i18n/bidi-markup.ts

const URL_RE    = /(https?:\/\/[^\s<>'"]+)/g;
const MENTION_RE = /(@[\w.]+)/g;
const HASHTAG_RE = /(#[\w؀-ۿ֐-׿]+)/g;

// For HTML rendering — wrap structured tokens in <bdi>
export function applyBidiMarkup(text: string): string {
  // Escape HTML first, then wrap tokens
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(URL_RE,     '<bdi dir="ltr"><a >$1</a></bdi>')
    .replace(MENTION_RE, '<bdi dir="ltr">$1</bdi>')
    .replace(HASHTAG_RE, '<bdi>$1</bdi>');  // dir=auto: hashtag may be Arabic or Latin
}

// For plain text (push notifications, clipboard) — Unicode isolate characters
const LRI = '⁦'; // Left-to-Right Isolate
const PDI = '⁩'; // Pop Directional Isolate
const FSI = '⁨'; // First Strong Isolate

export function applyBidiPlainText(text: string): string {
  return text
    .replace(URL_RE,     `${LRI}$1${PDI}`)
    .replace(MENTION_RE, `${LRI}$1${PDI}`)
    .replace(HASHTAG_RE, `${FSI}$1${PDI}`);  // FSI: let the hashtag's own content determine dir
}
```

Hashtags with mixed content (`#موسيقى_Pop`) are tricky: the Arabic portion is RTL, the Latin
suffix is LTR. Using `<bdi>` (equivalent to `dir="auto"`) lets the browser determine direction
from the first strong character, which correctly sets the display to RTL (Arabic leads). The Latin
suffix appears at the visual end of the hashtag, which is the trailing edge in RTL—this is
semantically correct.

## Sanitizing Directional Control Characters from Input

Users occasionally paste BiDi control characters (from Word documents, PDF copy-paste, or
deliberate manipulation). The "Trojan Source" attack (CVE-2021-42574) demonstrated how
`U+202A`–`U+202E` can reverse the visual appearance of source code. In social content these
characters can cause text to appear in a direction the user did not intend, disguise URLs, or
produce spoofed usernames.

```ts
// src/i18n/bidi-sanitize.ts

// Deprecated / dangerous BiDi control characters (TR9 §2)
// U+202A LRE, U+202B RLE, U+202C PDF, U+202D LRO, U+202E RLO
// U+200E LRM, U+200F RLM (less dangerous but often unintentional)
const DEPRECATED_BIDI_CONTROLS = /[‎‏‪-‮]/g;

// Isolate markers are safe when balanced; unbalanced ones from paste can corrupt layout.
// Strip unbalanced isolates rather than all of them.
const ISOLATE_OPEN  = /[⁦⁧⁨]/g;
const ISOLATE_CLOSE = /⁩/g;

export function sanitizeBidiControls(input: string): string {
  // 1. Remove deprecated directional controls unconditionally
  let out = input.replace(DEPRECATED_BIDI_CONTROLS, '');

  // 2. Balance isolate markers: count opens and closes, strip excess opens
  const opens  = (out.match(ISOLATE_OPEN)  ?? []).length;
  const closes = (out.match(ISOLATE_CLOSE) ?? []).length;

  if (opens > closes) {
    // Remove all isolate markers (simplest safe approach for UGC)
    out = out.replace(ISOLATE_OPEN, '').replace(ISOLATE_CLOSE, '');
  }

  return out;
}
```

Apply `sanitizeBidiControls` on ingestion (before storage), not only on output. Storing raw
control characters means every downstream consumer—email templates, push notifications,
analytics pipelines—must handle them independently.

## Number Direction in Mixed Content

Numbers have `Bidi_Class=EN` (European Number) or `AN` (Arabic Number). In an RTL paragraph,
sequences of EN digits behave as weak LTR and can cause surprising reordering when adjacent to
punctuation. The pattern `"السعر: 49.99 دولار"` (Arabic: "Price: 49.99 dollars") should display
as a single RTL line with the price visually between "السعر:" and "دولار", but the EN sequence
`49.99` may pull the trailing Arabic word leftward.

Wrap numeric spans in `<bdi dir="ltr">`:

```ts
const NUMERIC_RE = /(\d[\d.,٬٫]*(?:\s?[٪%])?)/g;

export function isolateNumbers(text: string): string {
  return text.replace(NUMERIC_RE, '<bdi dir="ltr">$1</bdi>');
}
```

Exception: Arabic-Indic digits (`٠١٢٣٤٥٦٧٨٩`, `U+0660–U+0669`) have `Bidi_Class=AN` and
resolve correctly inside RTL context without isolation. Do not wrap them. Limit the regex to
ASCII digits and their direct punctuation (`.`, `,`) to avoid over-isolating Arabic numerals.

## URL Display vs. Functional URL

A URL embedded in RTL text is visually fragile: the path components may appear reversed when the
browser's BiDi resolution places the URL in an RTL run. The rule is to always display URLs
inside `dir="ltr"` containers. But display and href must remain identical—do not apply visual
tricks (CSS `unicode-bidi: bidi-override; direction: ltr`) that make the display differ from the
href. Screen readers and link copy will expose the underlying href, so a display transform that
reverses characters is a security risk (IDN homograph territory).

```tsx
function PostURL({ href }: { href: string }) {
  const display = href.length > 40 ? `${href.slice(0, 37)}…` : href;
  return (
    <bdi dir="ltr">
      <a href={href} rel="noopener noreferrer" dir="ltr">
        {display}
      </a>
    </bdi>
  );
}
```

## Anti-patterns

- **Setting `dir="auto"` on the entire post container.** `dir="auto"` defers direction to the
  browser and cannot be overridden per token. Mixed posts with leading punctuation (e.g. starting
  with `"` or `-`) resolve to LTR even when the content is Arabic. Use explicit `detectBaseDir()`
  and set `'ltr'` or `'rtl'` explicitly.
- **Stripping all Unicode directional characters on output.** Stripping `U+2066`–`U+2069` from
  HTML output produced by your `applyBidiMarkup` function would remove the isolation you added.
  Sanitize user input; preserve application-applied isolation markup.
- **Applying `bidi-override` in CSS** (`unicode-bidi: bidi-override; direction: rtl`) to force
  RTL rendering on a Latin URL. This reverses the visual character order without changing the
  underlying bytes—links display as mirrored garbage and href differs from display.
- **Relying on `<br>` for paragraph separation.** Two sentences in different directions separated
  by `<br>` inside one `<div>` share a single `dir` context. Use separate `<p>` or `<div>`
  elements per paragraph; each element can then carry its own `dir` attribute.
- **Detecting direction from Accept-Language header alone.** The direction of individual posts
  depends on their content, not the viewing user's locale. A Hebrew speaker can post in English;
  a French speaker can quote Arabic. Always derive `dir` from the post text itself.

## Gotchas

- **`<bdi>` in React.** React 18+ renders `<bdi>` without transformation. Earlier versions
  treated unknown elements as custom HTML; always verify `<bdi>` passes through your sanitizer
  (`DOMPurify` allows it by default when `ALLOW_TAGS` includes `'bdi'`).
- **Twitter/X BiDi behavior is not a spec reference.** Social platforms make inconsistent choices
  about when to isolate tokens. Implement to the Unicode TR#9 spec, not to observed platform
  behavior.
- **Push notifications strip HTML.** iOS and Android push payloads are plain text. Use
  `applyBidiPlainText()` with Unicode isolate characters for notification bodies—`LRI`/`PDI`
  are supported in all modern mobile OS text renderers.
- **PDF export.** PDF text runs do not inherit HTML `dir` attributes. Libraries like Puppeteer
  rendering HTML to PDF will use the DOM `dir`, but native PDF libraries (PDFKit, reportlab)
  require explicit RTL configuration per text run. This is a known gap when exporting social
  posts as PDFs.
- **Hashtag link generation.** When building hashtag search URLs from Arabic hashtags, the URL
  must encode the Arabic characters as percent-encoded UTF-8—not as visual-order characters. Use
  `encodeURIComponent('#موسيقى')` not a manual BiDi override in the URL path.

## Verification

```ts
// src/i18n/__tests__/bidi.test.ts
import { describe, it, expect } from 'vitest';
import { detectBaseDir } from '../bidi';
import { sanitizeBidiControls } from '../bidi-sanitize';
import { applyBidiMarkup } from '../bidi-markup';

describe('detectBaseDir', () => {
  it('returns rtl for Arabic-leading text', () => {
    expect(detectBaseDir('مرحبا بالعالم')).toBe('rtl');
  });
  it('returns ltr for Latin-leading text', () => {
    expect(detectBaseDir('Hello world')).toBe('ltr');
  });
  it('returns auto for pure emoji', () => {
    expect(detectBaseDir('🎵🎶')).toBe('auto');
  });
  it('detects rtl when Arabic follows leading number', () => {
    // Number (EN) is weak; first strong character wins
    expect(detectBaseDir('123 مرحبا')).toBe('rtl');
  });
});

describe('sanitizeBidiControls', () => {
  it('removes deprecated LRE/RLE/PDF controls', () => {
    const input = 'hello‪world‬';
    expect(sanitizeBidiControls(input)).toBe('helloworld');
  });
  it('strips unbalanced isolate markers', () => {
    // Two opens, zero closes → unbalanced → strip all
    const input = '⁦hello⁦world';
    expect(sanitizeBidiControls(input)).toBe('helloworld');
  });
});

describe('applyBidiMarkup', () => {
  it('wraps URLs in <bdi dir="ltr">', () => {
    const result = applyBidiMarkup('visit https://example.com/track');
    expect(result).toContain('<bdi dir="ltr">');
    expect(result).toContain('https://example.com/track');
  });
  it('wraps mentions in <bdi dir="ltr">', () => {
    expect(applyBidiMarkup('شكراً @john')).toContain('<bdi dir="ltr">@john</bdi>');
  });
});
```

## Related

- `bidi-algorithm-unicode.md`
- `unicode-bidi-algorithm-web.md`
- `unicode-bidirectional-2026.md`
- `arabic-persian-text-rendering.md`
- `hebrew-rtl-react.md`
- `rtl-bidi-handling.md`

## Sources

- Unicode TR#9 (BiDi Algorithm): https://www.unicode.org/reports/tr9/
- Unicode TR#20 (Unicode in XML): https://www.unicode.org/reports/tr20/
- "Trojan Source" CVE-2021-42574: https://trojansource.codes/
- HTML `<bdi>` element: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
- W3C i18n: "How to use Unicode controls for bidi text": https://www.w3.org/International/questions/qa-bidi-unicode-controls
- WHATWG HTML `dir` attribute: https://html.spec.whatwg.org/multipage/dom.html#the-dir-attribute
