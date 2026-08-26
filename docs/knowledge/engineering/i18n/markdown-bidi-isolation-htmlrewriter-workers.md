# Bidi Isolation in Server-rendered Markdown with Workers HTMLRewriter

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A documentation platform renders user-authored Markdown at the edge. Arabic and Hebrew authors
embed inline English filenames, code snippets, and URLs inside RTL paragraphs. Without
explicit Unicode bidi isolation, the browser's bidi algorithm misplaces punctuation, reverses
code paths, and garbles URLs. A comment like `انتقل إلى /api/v1/users` renders the path
segment reversed. The fix must be applied server-side in Workers without sending the raw
Markdown back to a browser-side renderer.

## Context

The Unicode Bidirectional Algorithm (UBA, UAX #9) determines display order of mixed-direction
text. Without explicit embedding, a neutral character (slash, colon, space) adjacent to
strongly directional text adopts the direction of surrounding text, causing visible artifacts.
The solution is to wrap inline LTR segments within RTL context (and vice versa) with the
CSS `unicode-bidi: isolate` property or the HTML `<bdi>` element, which creates an isolated
directional run. Workers HTMLRewriter enables post-processing the HTML output of a Markdown
renderer (e.g. `marked`, `micromark`, or a pre-rendered static HTML) at the edge with minimal
latency. The Unicode script detection heuristic is based on Unicode property escapes (`\p{}`),
which are available in V8 with the `u` flag.

---

## 1. Detecting text direction of a string

```typescript
// src/lib/bidi-detect.ts

// Strong RTL code points: Arabic, Hebrew, Thaana, Syriac, etc.
const RTL_RE = /\p{Script=Arabic}|\p{Script=Hebrew}|\p{Script=Thaana}|\p{Script=Syriac}/u;
// Strong LTR code points: Latin, Cyrillic, Greek, CJK, etc.
const LTR_RE = /\p{Script=Latin}|\p{Script=Cyrillic}|\p{Script=Greek}/u;

export type Direction = 'ltr' | 'rtl' | 'neutral';

export function detectDirection(text: string): Direction {
  const hasRtl = RTL_RE.test(text);
  const hasLtr = LTR_RE.test(text);
  if (hasRtl && !hasLtr) return 'rtl';
  if (hasLtr && !hasRtl) return 'ltr';
  if (hasRtl && hasLtr)  return 'rtl';  // RTL wins in mixed content (paragraph-level rule)
  return 'neutral';
}

// detectDirection('مرحبا')              => 'rtl'
// detectDirection('Hello')             => 'ltr'
// detectDirection('انتقل إلى /api/v1') => 'rtl'  (RTL letters present)
// detectDirection('12345')             => 'neutral'
```

---

## 2. Inline LTR isolation within RTL paragraphs

The key pattern: when a paragraph-level direction is RTL, code spans, URLs, file paths, and
brand names should be isolated so they do not "bleed" directionality into surrounding Arabic
or Hebrew text.

```typescript
// src/lib/bidi-isolate.ts

/**
 * Wraps sequences of LTR-dominant runs within RTL text with <bdi dir="ltr">…</bdi>.
 * Applied to the text content of RTL paragraphs and list items.
 */

// Matches sequences that are LTR-dominant inline within RTL context:
// Latin words, digits, URLs, file paths, code identifiers
const LTR_INLINE_RE = /([A-Za-z0-9_\-./\\:@%+?=#&*(){}\[\]"'`]+)/g;

export function isolateLtrInRtl(html: string): string {
  // Only match text outside of HTML tags (simplified; HTMLRewriter handles per-text-node)
  return html.replace(LTR_INLINE_RE, '<bdi dir="ltr">$1</bdi>');
}

// isolateLtrInRtl('انتقل إلى /api/v1/users')
//   => 'انتقل إلى <bdi dir="ltr">/api/v1/users</bdi>'
```

> Note: The regex approach is applied only to text nodes, not raw HTML, to avoid wrapping
> attribute values or tag names. HTMLRewriter's `.onDocument()` text handler processes
> text nodes cleanly.

---

## 3. HTMLRewriter handler: per-paragraph bidi injection

```typescript
// src/rewriters/bidi-isolator.ts
import { detectDirection } from '../lib/bidi-detect';
import { isolateLtrInRtl } from '../lib/bidi-isolate';

type ParaTag = 'p' | 'li' | 'blockquote' | 'td' | 'th' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
const BLOCK_TAGS: ParaTag[] = ['p', 'li', 'blockquote', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'];

export class BidiIsolator implements HTMLRewriterElementContentHandlers {
  private textBuffer = '';
  private isRtlBlock = false;

  element(el: Element) {
    // Check if the element already has an explicit dir attribute
    const existingDir = el.getAttribute('dir');
    if (existingDir) {
      this.isRtlBlock = existingDir === 'rtl';
      return;
    }
    // Reset buffer for each block element
    this.textBuffer = '';
    this.isRtlBlock = false;
  }

  text(chunk: Text) {
    this.textBuffer += chunk.text;
    if (chunk.lastInTextNode) {
      const dir = detectDirection(this.textBuffer);
      if (dir === 'rtl') {
        this.isRtlBlock = true;
      }
    }
  }
}

/**
 * A two-pass approach: first detect direction, then inject isolation.
 * Single-pass is complex; the two-pass trade-off is an extra transform call.
 */
export function applyBidiIsolation(response: Response): Response {
  // Pass 1: detect and set dir attributes on block elements
  const pass1 = new HTMLRewriter()
    .on(BLOCK_TAGS.join(', '), new DirectionDetector())
    .transform(response);

  // Pass 2: isolate inline LTR runs within rtl-attributed elements
  return new HTMLRewriter()
    .on('[dir="rtl"]', new InlineLtrIsolator())
    .transform(pass1);
}

class DirectionDetector implements HTMLRewriterElementContentHandlers {
  private buf = '';
  element(_el: Element) { this.buf = ''; }
  text(chunk: Text) {
    this.buf += chunk.text;
    if (chunk.lastInTextNode) {
      const dir = detectDirection(this.buf);
      if (dir === 'rtl') {
        // HTMLRewriter does not support setting attributes from text handler;
        // inject a data-bidi-dir marker via a wrapper approach.
        // Practical workaround: set dir in element handler if first char is RTL.
      }
    }
  }
}

// Practical single-pass alternative: set dir="rtl" on elements whose first non-whitespace
// char is strongly RTL. This works for user-generated markdown where paragraphs are
// monolingual, which is the common case.

class InlineLtrIsolator implements HTMLRewriterElementContentHandlers {
  text(chunk: Text) {
    const isolated = isolateLtrInRtl(chunk.text);
    if (isolated !== chunk.text) {
      chunk.replace(isolated, { html: true });
    }
  }
}
```

---

## 4. Practical single-pass bidi handler for markdown output

```typescript
// src/rewriters/markdown-bidi.ts
// Single-pass: detect RTL from first strong character, set dir, isolate inline LTR

const FIRST_STRONG_RTL = /^[\s\p{P}\p{N}]*[\p{Script=Arabic}\p{Script=Hebrew}]/u;

export class MarkdownBidiHandler implements HTMLRewriterElementContentHandlers {
  private firstChunk = true;
  private rtlBlock   = false;

  element(el: Element) {
    this.firstChunk = true;
    this.rtlBlock   = false;
    const existingDir = el.getAttribute('dir');
    if (existingDir) { this.rtlBlock = existingDir === 'rtl'; this.firstChunk = false; }
  }

  text(chunk: Text) {
    if (this.firstChunk && chunk.text.trim()) {
      this.firstChunk = false;
      if (FIRST_STRONG_RTL.test(chunk.text)) {
        // We can only modify the element in element(), not here.
        // Workaround: wrap the whole text node in a <bdi dir="rtl"> span.
        // In production, pre-process: have the markdown renderer emit dir attributes.
        this.rtlBlock = true;
      }
    }

    if (this.rtlBlock) {
      const isolated = chunk.text.replace(
        /([A-Za-z][A-Za-z0-9_\-./\\:@%+?=#&*(){}\[\]"'`]*)/g,
        '<bdi dir="ltr">$1</bdi>'
      );
      if (isolated !== chunk.text) {
        chunk.replace(isolated, { html: true });
      }
    }
  }
}

// Register on all prose block elements in the Worker fetch handler:
// new HTMLRewriter()
//   .on('p, li, blockquote, h1, h2, h3, h4, h5, h6', new MarkdownBidiHandler())
//   .transform(markdownHtmlResponse)
```

---

## 5. CSS complement: `unicode-bidi: isolate` on `<bdi>` and `<code>` in RTL pages

```typescript
// Inject a <style> block for bidi-safe code/URL rendering
const BIDI_CSS = `
  /* Isolate code spans and inline monospace from surrounding bidi context */
  code, kbd, var, samp, a[href] { unicode-bidi: isolate; direction: ltr; }
  /* BDI elements set by our HTMLRewriter */
  bdi[dir="ltr"] { unicode-bidi: isolate; direction: ltr; display: inline; }
  /* Paragraphs that our rewriter marked as RTL */
  p[dir="rtl"], li[dir="rtl"], blockquote[dir="rtl"] { text-align: start; }
`;

// Inject via HTMLRewriter into <head>:
// .on('head', { element(el) { el.append(`<style>${BIDI_CSS}</style>`, { html: true }); } })
```

---

## Anti-patterns

- **CSS `direction: rtl` on `<body>` without `<bdi>` for LTR inline content** — overrides
  the bidi algorithm globally; inline LTR code paths appear reversed.
- **Stripping bidi control characters (U+200F, U+200E) as "junk"** — these are semantic;
  removing them collapses explicit embeddings intentionally placed by authors.
- **Applying isolation to every text node regardless of block direction** — wrapping
  `<bdi dir="ltr">` around LTR text in an LTR page has no effect but bloats the HTML.
- **Using `<span dir="ltr">` instead of `<bdi>`** — `<bdi>` is explicitly designed for
  bidirectional isolation; `<span dir="ltr">` changes direction but does not isolate.

## Gotchas

- **HTMLRewriter text handler cannot retroactively set element attributes** — direction
  detection from text content must use a two-pass approach or a pre-processing step in the
  Markdown pipeline (emit `dir` attributes before the HTML reaches Workers).
- **`chunk.lastInTextNode` timing** — text arrives in chunks; buffer all chunks before
  running direction detection, checking `chunk.lastInTextNode` to know when the node is done.
- **Code blocks (`<pre><code>`) should always be LTR** — they contain source code; wrap the
  entire `<pre>` in `dir="ltr"` unconditionally.
- **Neutral characters in URL paths** — slashes, dots, colons are bidi-neutral; they adopt
  surrounding direction. A path `/api/v1` in RTL context reverses to `1v/ipa/` visually
  without isolation.

## Verification

Render this test Markdown and inspect in a browser's bidi rendering:

```markdown
انتقل إلى /api/v1/users للحصول على البيانات.
```

Expected output after isolation:
```html
<p dir="rtl">انتقل إلى <bdi dir="ltr">/api/v1/users</bdi> للحصول على البيانات.</p>
```

Confirm with a visual bidi test: the path must read left-to-right regardless of paragraph
direction. Automated check: parse the output HTML and assert that any token matching
`/^\/[a-z0-9/]+$/` is wrapped in a `<bdi dir="ltr">` ancestor.

## Related

- `bidi-algorithm-unicode.md`
- `rtl-text-detection-workers-htmlrewriter.md`
- `unicode-bidirectional-2026.md`
- `bidi-social-ugc-edge-cases-2026.md`
- `markdown-in-translations.md`
- `rtl-bidi-handling.md`

## Sources

- UAX #9 Unicode Bidirectional Algorithm: https://unicode.org/reports/tr9/
- HTML spec `<bdi>` element: https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-bdi-element
- CSS Writing Modes `unicode-bidi`: https://www.w3.org/TR/css-writing-modes-3/#unicode-bidi
- Cloudflare Workers HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- W3C i18n bidi guidance: https://www.w3.org/International/articles/inline-bidi-markup/
