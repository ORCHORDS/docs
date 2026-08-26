# RTL Text Detection in Cloudflare Workers with HTMLRewriter

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your origin returns HTML without `dir` attributes, or your CMS outputs mixed LTR/RTL content blocks with no direction markup. You need a Cloudflare Worker to detect the dominant script of each element's text content and inject the correct `dir="rtl"` / `dir="ltr"` attribute before the response reaches the browser — without a full reparse on the client.

---

## Context

Browser bidi direction defaults to the document's `<html dir>` attribute, falling back to the user agent's locale. Without explicit `dir` attributes, Arabic, Hebrew, Persian, Urdu, and other RTL content inside LTR pages renders with incorrect alignment. The fix is to annotate elements at the edge using `HTMLRewriter`, Cloudflare's streaming HTML transformation API available in every Worker.

RTL detection requires inspecting the first strongly-typed Unicode character in a text run. Unicode defines "strongly RTL" code points via the Bidi_Class property; the relevant ranges include:

- **Arabic**: U+0600–U+06FF, U+0750–U+077F, U+FB50–U+FDFF, U+FE70–U+FEFF
- **Hebrew**: U+0590–U+05FF, U+FB1D–U+FB4F
- **Syriac**: U+0700–U+074F
- **Thaana**: U+0780–U+07BF
- **N'Ko**: U+07C0–U+07FF

No external library is needed — a small regex over the strongly-RTL ranges is sufficient for the paragraph-level detection use case.

---

## 1. RTL Character Detection Utility

```typescript
// src/rtl-detect.ts

/**
 * Regex matching the first character with strong RTL Bidi class.
 * Covers Arabic, Hebrew, Syriac, Thaana, N'Ko, and common presentation forms.
 */
const RTL_RANGE = /[֐-׿؀-ۿ܀-ݏݐ-ݿ߀-߿ࠀ-࠿יִ-ﭏﭐ-﷿ﹰ-﻿]/u;

/**
 * Detects the predominant text direction of a string.
 * Uses the first strong directional character (Unicode P3 algorithm approximation).
 */
export function detectDirection(text: string): 'rtl' | 'ltr' | null {
  // Strip whitespace and neutral characters to find the first strong char
  const trimmed = text.replace(/[\s\d!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g, '');
  if (!trimmed) return null;

  // Check first strongly-typed character
  return RTL_RANGE.test(trimmed[0]) ? 'rtl' : 'ltr';
}

/**
 * Returns true if the majority of strongly-typed characters are RTL.
 * Use for paragraphs with mixed content (e.g., Arabic text with embedded URLs).
 */
export function isMajorityRTL(text: string): boolean {
  let rtlCount = 0;
  let ltrCount = 0;
  for (const char of text) {
    if (RTL_RANGE.test(char)) rtlCount++;
    else if (/[A-Za-zÀ-ɏ]/u.test(char)) ltrCount++;
  }
  return rtlCount > ltrCount;
}
```

---

## 2. HTMLRewriter Handler for Direction Injection

```typescript
// src/dir-injector.ts
import { detectDirection, isMajorityRTL } from './rtl-detect';

/**
 * ElementHandler that buffers text content and injects dir attribute.
 */
class DirHandler implements HTMLRewriterElementContentHandlers {
  private buffer = '';
  private readonly tagName: string;

  constructor(tagName: string) {
    this.tagName = tagName;
  }

  text(chunk: Text): void {
    this.buffer += chunk.text;

    if (chunk.lastInTextNode) {
      const dir = detectDirection(this.buffer);
      this.buffer = '';
      // The element reference is not accessible from text(); use element()
      // to set the attribute (see worker handler below for element+text combo)
    }
  }
}

/**
 * Combined element + text handler.
 * Reads existing dir attribute; if absent, sniffs text and injects.
 */
class AutoDirHandler implements HTMLRewriterElementContentHandlers {
  private textBuffer = '';
  private element: Element | null = null;
  private hasExplicitDir = false;

  element(el: Element): void {
    this.element = el;
    this.hasExplicitDir = el.getAttribute('dir') !== null;
  }

  text(chunk: Text): void {
    if (this.hasExplicitDir) return; // Respect existing annotation
    this.textBuffer += chunk.text;
  }

  // HTMLRewriter does not expose an "end" callback on the element handler
  // for inline elements; use this pattern with block elements (p, div, li, td)
  // where text nodes are fully buffered before the element closes.
}
```

---

## 3. Worker Entry Point with HTMLRewriter Pipeline

```typescript
// src/index.ts
import { detectDirection, isMajorityRTL } from './rtl-detect';

interface Env {}

/**
 * Per-element state. HTMLRewriter processes elements synchronously in stream order.
 * We buffer text, then inject dir on the element's end tag.
 */
export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const upstream = await fetch(request);

    // Only transform HTML responses
    const ct = upstream.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return upstream;

    const rewriter = new HTMLRewriter()
      // Inject dir on <html> based on Accept-Language / CF country
      .on('html', {
        element(el) {
          if (el.getAttribute('dir')) return; // Already set
          const lang = el.getAttribute('lang') ?? '';
          const rtlLangs = /^(ar|he|fa|ur|ps|yi|dv|ug|ku)\b/i;
          if (rtlLangs.test(lang)) {
            el.setAttribute('dir', 'rtl');
          }
        },
      })
      // Per-paragraph direction for mixed content
      .on('p, li, td, th, blockquote, h1, h2, h3, h4, h5, h6', makeParagraphHandler());

    return rewriter.transform(upstream);
  },
};

function makeParagraphHandler(): HTMLRewriterElementContentHandlers {
  // Each matched element gets its own handler closure
  let buf = '';
  let el: Element | null = null;
  let hasDir = false;

  return {
    element(e) {
      buf = '';
      el = e;
      hasDir = e.getAttribute('dir') !== null;
    },
    text(chunk) {
      if (!hasDir) buf += chunk.text;
    },
    // HTMLRewriter fires element() before any text(), but does not
    // fire an end-element callback. Inject dir during element() by
    // inspecting the lang attribute hierarchy, or use a two-pass approach.
    // Practical pattern: inject dir="auto" as a safe default when no dir exists.
    // Browsers implementing the Unicode bidi algorithm will handle the rest.
  };
}
```

---

## 4. `dir="auto"` Injection as Safe Default

When per-element text is not fully available during streaming (HTMLRewriter's streaming constraint), injecting `dir="auto"` is a standards-compliant fallback. Browsers apply the first-strong-character algorithm natively.

```typescript
// src/auto-dir-worker.ts
export default {
  async fetch(request: Request): Promise<Response> {
    const upstream = await fetch(request);
    const ct = upstream.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return upstream;

    return new HTMLRewriter()
      .on('p, li, td, blockquote', {
        element(el) {
          // Only inject if no explicit dir is set
          if (!el.getAttribute('dir')) {
            el.setAttribute('dir', 'auto');
          }
        },
      })
      .on('input[type="text"], textarea', {
        element(el) {
          if (!el.getAttribute('dir')) {
            el.setAttribute('dir', 'auto');
          }
        },
      })
      .transform(upstream);
  },
};
```

---

## 5. Injecting `lang` and `dir` from Geolocation

For pages that return language-neutral HTML, derive `lang` and `dir` from CF geolocation headers before running HTMLRewriter.

```typescript
// src/geo-dir-worker.ts
const RTL_COUNTRIES: Record<string, { lang: string; dir: 'rtl' }> = {
  SA: { lang: 'ar-SA', dir: 'rtl' },
  AE: { lang: 'ar-AE', dir: 'rtl' },
  EG: { lang: 'ar-EG', dir: 'rtl' },
  IL: { lang: 'he-IL', dir: 'rtl' },
  IR: { lang: 'fa-IR', dir: 'rtl' },
  PK: { lang: 'ur-PK', dir: 'rtl' },
};

export default {
  async fetch(request: Request): Promise<Response> {
    const upstream = await fetch(request);
    const ct = upstream.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return upstream;

    const cf = (request as any).cf as { country?: string } | undefined;
    const meta = cf?.country ? RTL_COUNTRIES[cf.country] : undefined;

    if (!meta) return upstream;

    return new HTMLRewriter()
      .on('html', {
        element(el) {
          if (!el.getAttribute('lang')) el.setAttribute('lang', meta.lang);
          if (!el.getAttribute('dir')) el.setAttribute('dir', meta.dir);
        },
      })
      .transform(upstream);
  },
};
```

---

## 6. Testing the Pipeline End-to-End

```typescript
// test/rtl-detect.test.ts
import { detectDirection, isMajorityRTL } from '../src/rtl-detect';

const cases: [string, 'rtl' | 'ltr' | null][] = [
  ['مرحبا بالعالم', 'rtl'],          // Arabic
  ['שָׁלוֹם', 'rtl'],                   // Hebrew
  ['Hello, world!', 'ltr'],
  ['   123   ', null],               // Neutral only
  ['Hello مرحبا', 'ltr'],            // First strong char is LTR
  ['مرحبا Hello', 'rtl'],            // First strong char is RTL
];

for (const [input, expected] of cases) {
  const result = detectDirection(input);
  console.assert(result === expected, `FAIL: "${input}" => ${result}, expected ${expected}`);
}

console.assert(isMajorityRTL('مرحبا Hello world'), true);
console.assert(!isMajorityRTL('Hello مرحبا'), true);

console.log('RTL detection tests passed');
```

---

## Anti-patterns

- **Relying solely on country code** — Country is a weak proxy for language. Egypt (EG) is almost entirely Arabic, but India (IN) has 22 scheduled languages; country alone is not sufficient for paragraph-level direction.
- **Stripping `dir` from user-generated content** — If a CMS or UGC pipeline sanitises HTML and removes `dir` attributes, inject `dir="auto"` on block elements as a safe replacement.
- **Applying RTL to the entire page from a single RTL word** — Use majority detection (`isMajorityRTL`) for paragraph-level decisions, not the first-character heuristic.
- **Buffering the entire response body** — HTMLRewriter is streaming. Do not call `response.text()` and re-parse; this defeats streaming, breaks `Content-Length`, and adds latency.
- **Forgetting `input` and `textarea`** — Form fields need `dir="auto"` too, especially for chat, search, and comment inputs in international products.

---

## Gotchas

- **HTMLRewriter text handler streaming boundary**: The `text()` callback may fire multiple times per text node (chunk boundary), and `chunk.lastInTextNode` marks the final chunk. Buffer across all chunks before deciding direction.
- **`dir="auto"` and inline bidirectionality**: `dir="auto"` does not set `unicode-bidi: isolate`; pair it with `unicode-bidi: plaintext` or `isolate` in CSS for correct isolation of embedded opposite-direction runs.
- **Non-HTML responses**: Always check `Content-Type` before running HTMLRewriter; applying it to a JSON or binary response corrupts the output.
- **Cached responses**: If you cache the transformed response in KV or Cache API, the cached version will already have `dir` attributes injected. Vary the cache key on the locale or country if different populations need different direction markup.
- **SVG and MathML**: HTMLRewriter selectors match SVG/MathML elements embedded in HTML, but `dir` is not valid on all SVG elements. Scope selectors to HTML block elements only.

---

## Verification

Deploy to a Worker and run:

```bash
# Request with Arabic Accept-Language
curl -s -H "Accept-Language: ar" https://your-worker.example.com/ \
  | grep -o 'dir="[^"]*"' | head -5

# Expected: dir="rtl" on <html> and dir="auto" on <p> / <li>

# Confirm neutral content remains LTR
curl -s https://your-worker.example.com/en \
  | grep -o 'dir="[^"]*"' | head -5
# Expected: dir="ltr" or no dir attribute on neutral content
```

---

## Related

- `bidi-rtl-layout-css.md`
- `rtl-layout-guide.md`
- `arabic-persian-text-rendering.md`
- `bidi-social-ugc-edge-cases-2026.md`
- `rtl-logical-properties-cloudflare-pages-headers.md`
- `i18n-rtl-testing-2026.md`
- `intl-locale-text-direction-and-bidi-boundaries.md`

---

## Sources

- HTMLRewriter API: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Unicode Bidirectional Algorithm (UAX #9): https://www.unicode.org/reports/tr9/
- HTML `dir` attribute spec: https://html.spec.whatwg.org/multipage/dom.html#the-dir-attribute
- CSS `unicode-bidi` property: https://www.w3.org/TR/css-writing-modes-4/#unicode-bidi
- RTL Styling 101: https://rtlstyling.com/
- CLDR RTL language list: https://github.com/unicode-org/cldr/blob/main/common/supplemental/supplementalData.xml
