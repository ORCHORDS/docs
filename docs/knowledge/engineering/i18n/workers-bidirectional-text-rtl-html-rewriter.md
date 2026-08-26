# Injecting `dir="rtl"` and Bidirectional CSS via HTMLRewriter in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves a single-origin HTML application to both LTR (English,
French) and RTL (Arabic, Hebrew, Persian) audiences. The upstream HTML is
always LTR. You need to:

1. Detect the user's RTL locale from `Accept-Language`.
2. Add `dir="rtl"` to `<html>` and inject a minimal RTL stylesheet.
3. Wrap inline bidirectional fragments in `<bdi>` so mixed-direction text
   renders correctly.

All of this must happen at the edge without touching the origin server.

## Context

- Runtime: Cloudflare Workers with HTMLRewriter (streaming HTML transform)
- RTL locales targeted: `ar`, `he`, `fa`, `ur`
- The upstream is an origin or a static asset served via Cloudflare Pages
- No framework; plain TypeScript

---

## 1. Detecting RTL Locale from `Accept-Language`

Parse the `Accept-Language` header, respecting quality weights (q-values), and
return the best matching locale.

```typescript
// src/locale-detect.ts

const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur', 'ps', 'sd', 'ug']);

export interface LocaleResult {
  locale: string;  // BCP-47 tag, e.g. "ar-SA"
  lang:   string;  // primary subtag, e.g. "ar"
  isRtl:  boolean;
}

/**
 * Parse Accept-Language and return the highest-quality locale.
 * Falls back to `defaultLocale` when the header is absent or unparseable.
 */
export function detectLocale(
  acceptLanguage: string | null,
  defaultLocale = 'en'
): LocaleResult {
  if (!acceptLanguage) return makeResult(defaultLocale);

  const entries = acceptLanguage
    .split(',')
    .map(entry => {
      const [tag, q] = entry.trim().split(';q=');
      return { tag: tag.trim(), q: q ? parseFloat(q) : 1.0 };
    })
    .filter(e => e.tag && !isNaN(e.q))
    .sort((a, b) => b.q - a.q);

  const best = entries[0]?.tag ?? defaultLocale;
  return makeResult(best);
}

function makeResult(locale: string): LocaleResult {
  const lang = locale.split('-')[0].toLowerCase();
  return { locale, lang, isRtl: RTL_LOCALES.has(lang) };
}
```

---

## 2. HTMLRewriter Handlers

### 2a. `<html>` element — add `dir` and `lang` attributes

```typescript
// src/handlers/html-element-handler.ts
import type { LocaleResult } from '../locale-detect';

export class HtmlElementHandler implements ElementHandler {
  constructor(private localeResult: LocaleResult) {}

  element(el: Element): void {
    const { locale, isRtl } = this.localeResult;
    el.setAttribute('lang', locale);
    if (isRtl) {
      el.setAttribute('dir', 'rtl');
    } else {
      el.removeAttribute('dir');  // strip any stale RTL dir from cache
    }
  }
}
```

### 2b. `<head>` element — inject RTL stylesheet

```typescript
// src/handlers/head-element-handler.ts

const RTL_CSS = `
/* Injected RTL overrides */
[dir="rtl"] body          { text-align: right; }
[dir="rtl"] .layout       { flex-direction: row-reverse; }
[dir="rtl"] .nav          { padding-right: 1rem; padding-left: 0; }
[dir="rtl"] input,
[dir="rtl"] textarea      { unicode-bidi: embed; direction: rtl; }
bdi                        { unicode-bidi: isolate; }
`.trim();

export class HeadElementHandler implements ElementHandler {
  element(el: Element): void {
    el.append(`<style id="rtl-overrides">${RTL_CSS}</style>`, {
      html: true
    });
  }
}
```

### 2c. `<span>` / `<p>` elements — wrap user-generated content in `<bdi>`

User-generated content (names, titles) may mix directions. Wrapping in `<bdi>`
isolates each fragment's base direction from surrounding text.

```typescript
// src/handlers/bdi-handler.ts

/**
 * Wraps the inner content of elements matching [data-user-content]
 * in <bdi> to isolate bidirectional text.
 */
export class BdiHandler implements ElementHandler {
  element(el: Element): void {
    // HTMLRewriter cannot wrap inner HTML directly; instead we prepend/append
    // <bdi> open/close tags around the content with html:true
    el.prepend('<bdi>', { html: true });
    el.append('</bdi>',  { html: true });
  }
}
```

---

## 3. Worker Entry Point

```typescript
// src/index.ts
import { detectLocale }         from './locale-detect';
import { HtmlElementHandler }   from './handlers/html-element-handler';
import { HeadElementHandler }   from './handlers/head-element-handler';
import { BdiHandler }           from './handlers/bdi-handler';

export interface Env {}

export default {
  async fetch(request: Request, _env: Env, ctx: ExecutionContext): Promise<Response> {
    const localeResult = detectLocale(
      request.headers.get('Accept-Language')
    );

    // Fetch upstream HTML
    const upstream = await fetch(request);

    // Only transform HTML responses
    const ct = upstream.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return upstream;

    // Clone response headers; add Vary so caches respect Accept-Language
    const headers = new Headers(upstream.headers);
    headers.set('Vary', combineVary(headers.get('Vary'), 'Accept-Language'));
    if (localeResult.isRtl) {
      headers.set('Content-Language', localeResult.locale);
    }

    const transformed = new HTMLRewriter()
      .on('html',                    new HtmlElementHandler(localeResult))
      .on(localeResult.isRtl ? 'head' : 'x-never',
                                     new HeadElementHandler())
      .on('[data-user-content]',     new BdiHandler())
      .transform(upstream);

    return new Response(transformed.body, {
      status:     upstream.status,
      statusText: upstream.statusText,
      headers
    });
  }
};

// Merge an existing Vary value with a new field
function combineVary(existing: string | null, field: string): string {
  if (!existing) return field;
  const parts = existing.split(',').map(s => s.trim());
  if (parts.map(p => p.toLowerCase()).includes(field.toLowerCase())) {
    return existing;
  }
  return [...parts, field].join(', ');
}
```

---

## 4. Marking User-Generated Content in HTML

In your templates (or upstream CMS output), mark dynamic name/title spans:

```html
<!-- Before transformation -->
<p>Uploaded by <span data-user-content>محمد علي</span> yesterday.</p>

<!-- After HTMLRewriter BdiHandler -->
<p>Uploaded by <span data-user-content><bdi>محمد علي</bdi></span> yesterday.</p>
```

---

## Anti-patterns

- **Setting `dir` only on `<body>`** — the `lang` attribute on `<html>` is what
  browsers use for font selection and spell-check. Always set both.
- **Hardcoding `direction: rtl` in a global stylesheet** — this breaks LTR
  visitors who share cached pages. Use `[dir="rtl"]` selector scoping.
- **Skipping `unicode-bidi: isolate` on `<bdi>`** — without this CSS the
  element has no effect on browsers that don't natively understand `<bdi>`.
- **Ignoring `Vary: Accept-Language`** — Cloudflare's cache will serve the RTL
  version to LTR users if `Vary` is missing.

## Gotchas

- `HTMLRewriter` handlers receive _streaming_ chunks; never assume you see the
  full document in one `element()` call. Attribute mutation is safe; reading
  inner text requires a `text()` handler.
- `el.prepend`/`el.append` with `{ html: true }` insert raw markup. Make sure
  the injected strings are not user-supplied (XSS risk).
- The `.on('x-never', ...)` selector trick conditionally registers a handler
  by pointing it at a tag that never exists. This avoids branching inside a
  handler or re-building the `HTMLRewriter` chain.
- Persian (`fa`) and Urdu (`ur`) are RTL but use Arabic script with a different
  Unicode block. They must be in `RTL_LOCALES`; do not rely on script detection
  alone.

## Verification

```bash
# Start local dev server
npx wrangler dev src/index.ts

# LTR request — no dir attribute expected
curl -s -H 'Accept-Language: en-US,en;q=0.9' http://localhost:8787/ \
  | grep -o 'dir="[^"]*"'
# (no output)

# RTL request — dir=rtl expected on <html>
curl -s -H 'Accept-Language: ar,en;q=0.5' http://localhost:8787/ \
  | grep -o 'dir="[^"]*"'
# → dir="rtl"

# Verify Vary header
curl -sI -H 'Accept-Language: ar' http://localhost:8787/ \
  | grep -i vary
# → Vary: Accept-Language

# Check RTL stylesheet injected
curl -s -H 'Accept-Language: he' http://localhost:8787/ \
  | grep -o 'id="rtl-overrides"'
# → id="rtl-overrides"
```

## Related

- `workers-icu-message-format-complex-plural.md` — plural/select for RTL languages
- `workers-number-system-arabic-indic.md` — Arabic-Indic numerals
- `workers-locale-content-negotiation-d1.md` — `Vary: Accept-Language` with D1

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://html.spec.whatwg.org/multipage/dom.html#the-dir-attribute
- https://www.w3.org/International/articles/inline-bidi-markup/
- https://developer.mozilla.org/en-US/docs/Web/CSS/unicode-bidi
