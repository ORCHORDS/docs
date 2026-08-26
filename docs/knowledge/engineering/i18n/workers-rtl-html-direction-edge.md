# RTL HTML Direction Injection at the Edge with Cloudflare Workers + HTMLRewriter

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application serves Arabic, Hebrew, or Persian users but your origin HTML is always emitted with `dir="ltr"`. Users see mirrored layouts, misaligned text blocks, and broken bidirectional punctuation. You cannot modify the origin server, or you want the transformation to happen closer to the user without adding latency from origin round-trips.

---

## Context

HTML direction is controlled by the `dir` attribute on the root `<html>` element (and optionally on block-level descendants). RTL locales require `dir="rtl"` to trigger the browser's bidirectional layout algorithm. Missing this attribute causes:

- Text alignment defaulting to left for RTL scripts
- Punctuation characters appearing on the wrong side of a sentence
- Mixed LTR/RTL inline content (numbers, URLs) rendering out of order
- CSS `text-align: start` / `end` falling back to left/right incorrectly

Cloudflare Workers' `HTMLRewriter` lets you stream-transform HTML at the edge with zero round-trip cost. Combined with locale detection from request headers and KV-stored user preferences, you can inject the correct `dir` attribute and RTL CSS classes before a single byte reaches the client.

---

## Solution

### 1. Locale-to-Direction Mapping

```typescript
// src/i18n/direction.ts

export type TextDirection = 'ltr' | 'rtl';

/**
 * Canonical list of RTL language subtags.
 * Sources: Unicode CLDR + IANA language subtag registry.
 */
export const RTL_LANGUAGES = new Set([
  'ar',  // Arabic
  'arc', // Aramaic
  'ckb', // Central Kurdish (Sorani)
  'dv',  // Divehi / Maldivian
  'fa',  // Persian (Farsi)
  'ha',  // Hausa (written in Arabic script)
  'he',  // Hebrew
  'khw', // Khowar
  'ks',  // Kashmiri
  'ku',  // Kurdish (Kurmanji)
  'ps',  // Pashto
  'sd',  // Sindhi
  'sr',  // Serbian (Cyrillic — can be RTL in some contexts, exclude if needed)
  'ug',  // Uyghur
  'ur',  // Urdu
  'uz',  // Uzbek (Arabic script variant)
  'yi',  // Yiddish
]);

export function getDirection(locale: string): TextDirection {
  // Extract the primary language subtag (BCP 47)
  const primarySubtag = locale.split('-')[0].toLowerCase();
  return RTL_LANGUAGES.has(primarySubtag) ? 'rtl' : 'ltr';
}

export function isRTL(locale: string): boolean {
  return getDirection(locale) === 'rtl';
}
```

### 2. Locale Detection from Request

```typescript
// src/i18n/detect.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  USER_PREFS: KVNamespace;
}

/**
 * Parse Accept-Language header and return the highest-quality locale.
 * Falls back to 'en' if header is absent or unparseable.
 */
export function parseAcceptLanguage(header: string | null): string {
  if (!header) return 'en';

  return header
    .split(',')
    .map((part) => {
      const [tag, q] = part.trim().split(';q=');
      return { tag: tag.trim(), q: q ? parseFloat(q) : 1.0 };
    })
    .sort((a, b) => b.q - a.q)
    .map((entry) => entry.tag)
    .find((tag) => tag.length > 0) ?? 'en';
}

/**
 * Resolve the effective locale for a request.
 * Priority: KV user preference > Accept-Language > cf.country fallback.
 */
export async function resolveLocale(
  request: Request,
  env: Env,
): Promise<string> {
  const sessionId = request.headers.get('x-session-id');
  if (sessionId) {
    const stored = await env.USER_PREFS.get(`locale:${sessionId}`);
    if (stored) return stored;
  }

  const acceptLang = request.headers.get('accept-language');
  const parsed = parseAcceptLanguage(acceptLang);
  if (parsed !== 'en') return parsed;

  // Final fallback: Cloudflare geo hint
  const cf = (request as any).cf as { country?: string } | undefined;
  const countryToLocale: Record<string, string> = {
    SA: 'ar-SA', AE: 'ar-AE', EG: 'ar-EG',
    IL: 'he-IL', IR: 'fa-IR', PK: 'ur-PK',
  };
  if (cf?.country && countryToLocale[cf.country]) {
    return countryToLocale[cf.country];
  }

  return 'en';
}
```

### 3. HTMLRewriter — Dir Attribute + RTL CSS Class Injection

```typescript
// src/i18n/rtl-rewriter.ts
import { getDirection, isRTL } from './direction';

/**
 * ElementHandler that sets `dir` on <html> and optionally injects
 * a utility class so CSS can scope RTL overrides cleanly.
 */
class HtmlDirHandler implements HTMLRewriterElementContentHandlers {
  private readonly dir: 'ltr' | 'rtl';
  private readonly locale: string;

  constructor(locale: string) {
    this.dir = getDirection(locale);
    this.locale = locale;
  }

  element(el: Element): void {
    el.setAttribute('dir', this.dir);
    el.setAttribute('lang', this.locale);

    // Add a utility class so stylesheet can scope RTL rules:
    // [dir="rtl"] .sidebar { right: 0; left: auto; }
    if (this.dir === 'rtl') {
      const existing = el.getAttribute('class') ?? '';
      const classes = existing ? `${existing} rtl-layout` : 'rtl-layout';
      el.setAttribute('class', classes);
    }
  }
}

/**
 * ElementHandler for <body> — adds a data attribute for JS consumers
 * that need to know the page direction without reading the root element.
 */
class BodyDirHandler implements HTMLRewriterElementContentHandlers {
  private readonly locale: string;

  constructor(locale: string) {
    this.locale = locale;
  }

  element(el: Element): void {
    el.setAttribute('data-locale', this.locale);
    el.setAttribute('data-dir', getDirection(this.locale));
  }
}

/**
 * Build an HTMLRewriter configured for RTL injection.
 * Returns the rewriter — caller applies it to the Response.
 */
export function buildRTLRewriter(locale: string): HTMLRewriter {
  return new HTMLRewriter()
    .on('html', new HtmlDirHandler(locale))
    .on('body', new BodyDirHandler(locale));
}
```

### 4. Worker Entry Point

```typescript
// src/index.ts
import type { Env } from './i18n/detect';
import { resolveLocale } from './i18n/detect';
import { buildRTLRewriter } from './i18n/rtl-rewriter';
import { isRTL } from './i18n/direction';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = await resolveLocale(request, env);

    // Fetch origin HTML
    const originResponse = await fetch(request);

    const contentType = originResponse.headers.get('content-type') ?? '';
    if (!contentType.includes('text/html')) {
      // Non-HTML assets pass through untouched
      return originResponse;
    }

    // Apply RTL transformation via HTMLRewriter streaming
    const rewriter = buildRTLRewriter(locale);
    const transformed = rewriter.transform(originResponse);

    // Append a Vary header so caches key on Accept-Language
    const headers = new Headers(transformed.headers);
    headers.append('Vary', 'Accept-Language');
    headers.set('x-i18n-locale', locale);
    headers.set('x-i18n-dir', isRTL(locale) ? 'rtl' : 'ltr');

    return new Response(transformed.body, {
      status: transformed.status,
      statusText: transformed.statusText,
      headers,
    });
  },
} satisfies ExportedHandler<Env>;
```

### 5. Bidirectional Inline Text — `<bdi>` Injection

For pages that embed user-generated content mixing LTR numbers or usernames inside RTL paragraphs, inject `<bdi>` wrappers:

```typescript
// src/i18n/bdi-handler.ts

/**
 * Wraps `.user-name` spans with <bdi> to isolate LTR content
 * inside an RTL paragraph without breaking surrounding flow.
 */
class BdiInjector implements HTMLRewriterElementContentHandlers {
  element(el: Element): void {
    el.before('<bdi>', { html: true });
    el.after('</bdi>', { html: true });
  }
}

export function addBdiHandlers(
  rewriter: HTMLRewriter,
  locale: string,
): HTMLRewriter {
  const { isRTL } = require('./direction');
  if (!isRTL(locale)) return rewriter;
  return rewriter.on('.user-name, .product-code, .order-id', new BdiInjector());
}
```

### 6. wrangler.toml

```toml
name = "edge-rtl-injector"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "USER_PREFS"
id = "<YOUR_KV_NAMESPACE_ID>"
```

---

## Implementation Details

### HTMLRewriter Streaming Behaviour

`HTMLRewriter.transform()` returns a new `Response` whose body is a `ReadableStream`. The transformation is applied lazily as bytes flow through — no buffering of the entire document occurs. This means:

- Memory usage stays flat regardless of page size
- Time-to-first-byte is unaffected
- The `<html>` tag appears very early in the stream, so the `dir` attribute is set before any visible content

### Attribute Mutation vs. Append

`el.setAttribute('dir', value)` replaces an existing `dir` attribute. If your origin already sets `dir="ltr"` explicitly, the Worker overwrites it correctly. You do not need to remove it first.

### Cache Keying

Adding `Vary: Accept-Language` to the response tells Cloudflare's CDN to cache separate copies per locale. For a high-traffic site with a small locale set, pre-warm the cache at deploy time using Cache API writes inside a Durable Object or a scheduled Worker.

### CSS Architecture for RTL

The injected `rtl-layout` class lets you write scoped overrides without a full RTL stylesheet:

```css
/* Logical properties — preferred approach */
.sidebar { margin-inline-start: 1rem; }

/* Fallback for older browsers using the injected class */
.rtl-layout .sidebar { margin-right: 0; margin-left: 1rem; }
```

---

## Anti-patterns

- **Never hard-code `dir="rtl"` in templates.** A single origin template serves all locales; direction must be derived at runtime.
- **Do not use `Accept-Language` as the sole cache key.** Browsers send dozens of variants (`ar,ar-SA;q=0.9,en;q=0.8`). Normalise to a canonical locale tag before caching.
- **Avoid buffering the full HTML body** to manipulate it with string replacement. HTMLRewriter streams; string manipulation requires holding the entire document in memory and blocks TTFB.
- **Do not set `direction: rtl` only in CSS without the `dir` attribute.** The HTML `dir` attribute affects the browser's bidi algorithm; CSS `direction` alone does not fix text ordering for inline-level bidirectional content.

---

## Gotchas

- `HTMLRewriter` runs in document order. If `<html>` is missing (malformed HTML), the handler never fires. Add a fallback handler on `head` as a safety net.
- The Workers runtime does not include a full ICU data table. `Intl.Locale` is available but `Intl.Locale.prototype.textInfo` (which exposes `direction`) is not reliably present. Use the explicit `RTL_LANGUAGES` set rather than relying on runtime locale metadata.
- Persian (`fa`) and Urdu (`ur`) users often have `Accept-Language: fa` or `ur` without a region subtag. Ensure your mapping handles bare language subtags, not just `fa-IR` or `ur-PK`.
- Caches keyed on `Accept-Language` can fragment badly. Consider normalising to a two-letter language tag before using it as a cache key suffix.

---

## Verification

```bash
# Deploy to Wrangler dev
npx wrangler dev --local

# Test Arabic locale
curl -s -H 'Accept-Language: ar' http://localhost:8787/ \
  | grep -o 'dir="[^"]*"'
# Expected: dir="rtl"

# Test Hebrew locale
curl -s -H 'Accept-Language: he-IL' http://localhost:8787/ \
  | grep -o 'dir="[^"]*"'
# Expected: dir="rtl"

# Test English (should remain LTR)
curl -s -H 'Accept-Language: en-US' http://localhost:8787/ \
  | grep -o 'dir="[^"]*"'
# Expected: dir="ltr"

# Check response headers
curl -sI -H 'Accept-Language: ar' http://localhost:8787/ \
  | grep -i 'x-i18n'
# Expected: x-i18n-locale: ar  and  x-i18n-dir: rtl
```

---

## Related

- `workers-geo-redirect-locale-detection.md` — locale detection pipeline
- `workers-translation-fallback-chain-kv.md` — KV message store
- Cloudflare Workers `HTMLRewriter` API documentation
- Unicode Bidirectional Algorithm (UAX #9)
- W3C Internationalization: Structural markup and right-to-left text in HTML

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://www.w3.org/International/questions/qa-html-dir
- https://unicode.org/reports/tr9/
- https://www.rfc-editor.org/rfc/rfc5646 (BCP 47 language tags)
- https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
