# Injecting `dir="rtl"` and `lang` Attributes into HTML Responses at the Edge

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your origin serves a single English HTML template. For Arabic, Hebrew, or Farsi visitors the layout must flip to RTL — `dir="rtl"` on `<html>`, a different stylesheet, and the correct `lang` attribute — without modifying the origin server or deploying per-locale HTML files.

## Context

Cloudflare Workers' `HTMLRewriter` API streams through HTML responses and applies transformations at the edge with minimal latency overhead. By inspecting the request URL or a locale cookie, the Worker determines the target locale and rewrites just the attributes that vary by direction, then injects the correct CSS `<link>` and sets `Content-Language` on the response.

---

## Core Implementation

```typescript
export interface Env {
  ORIGIN: Fetcher; // Service binding to origin, or use fetch()
}

/** Locales that require RTL layout */
const RTL_LOCALES = new Set(["ar", "he", "fa", "ur", "ps", "ku"]);

/** Map locale tag → ISO 639-1 for the lang attribute */
function normaliseLang(locale: string): string {
  return locale.split("-")[0].toLowerCase();
}

/**
 * Resolve the request locale from:
 *  1. URL path prefix: /ar/...
 *  2. `locale` cookie
 *  3. Accept-Language header (first tag)
 *  4. Default: "en"
 */
function resolveLocale(request: Request): string {
  const url = new URL(request.url);
  const pathLocale = url.pathname.split("/")[1];
  if (pathLocale && /^[a-z]{2}(-[A-Z]{2})?$/.test(pathLocale)) {
    return pathLocale;
  }

  const cookie = request.headers.get("Cookie") ?? "";
  const cookieLocale = cookie.match(/(?:^|;\s*)locale=([^;]+)/)?.[1];
  if (cookieLocale) return cookieLocale;

  const acceptLang = request.headers.get("Accept-Language") ?? "";
  return acceptLang.split(",")[0].split(";")[0].trim() || "en";
}

class HtmlAttributeHandler implements HTMLRewriterElementContentHandlers {
  constructor(
    private readonly locale: string,
    private readonly isRtl: boolean
  ) {}

  element(el: Element): void {
    const lang = normaliseLang(this.locale);
    el.setAttribute("lang", lang);
    if (this.isRtl) {
      el.setAttribute("dir", "rtl");
    } else {
      el.removeAttribute("dir");
    }
  }
}

class StylesheetSwapHandler implements HTMLRewriterElementContentHandlers {
  constructor(
    private readonly locale: string,
    private readonly isRtl: boolean
  ) {}

  element(el: Element): void {
    const href = el.getAttribute("href") ?? "";
    if (!href.includes("/styles/")) return;

    if (this.isRtl && !href.includes(".rtl.")) {
      // Swap main.css → main.rtl.css
      el.setAttribute("href", href.replace(/(\.[^.]+)$/, ".rtl$1"));
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = resolveLocale(request);
    const isRtl = RTL_LOCALES.has(normaliseLang(locale));

    // Fetch from origin (strip the locale path prefix for the origin request)
    const url = new URL(request.url);
    const originUrl = new URL(request.url);
    if (/^\/[a-z]{2}(-[A-Z]{2})?\//.test(url.pathname)) {
      originUrl.pathname = url.pathname.replace(/^\/[a-z]{2}(-[A-Z]{2})?/, "") || "/";
    }
    const originRequest = new Request(originUrl.toString(), request);
    const originResponse = await fetch(originRequest);

    const ct = originResponse.headers.get("Content-Type") ?? "";
    if (!ct.includes("text/html")) return originResponse;

    // Build rewritten response
    const rewriter = new HTMLRewriter()
      .on("html", new HtmlAttributeHandler(locale, isRtl))
      .on('link[rel="stylesheet"]', new StylesheetSwapHandler(locale, isRtl));

    const rewritten = rewriter.transform(originResponse);

    // Clone headers and set Content-Language
    const headers = new Headers(rewritten.headers);
    headers.set("Content-Language", locale);
    if (isRtl) {
      headers.set("X-Text-Direction", "rtl");
    }

    return new Response(rewritten.body, {
      status: rewritten.status,
      statusText: rewritten.statusText,
      headers,
    });
  },
};
```

---

## Locale Resolution Priority

| Source | Example | Priority |
|---|---|---|
| URL path prefix | `/ar/products` | Highest |
| `locale` cookie | `locale=ar` | 2nd |
| `Accept-Language` header | `ar,en;q=0.9` | 3rd |
| Default | `en` | Lowest |

---

## Stylesheet Swap Strategy

Maintain mirrored RTL stylesheets at a predictable path:

```
/styles/main.css      ← LTR (default)
/styles/main.rtl.css  ← RTL overrides (margins, padding, flex-direction, text-align)
```

The `StylesheetSwapHandler` renames `main.css` to `main.rtl.css` in-stream. Only include overrides in the RTL file — cascade from the base LTR stylesheet by importing it:

```css
/* main.rtl.css */
@import url('/styles/main.css');

body { direction: rtl; }
.sidebar { float: right; margin-left: 1rem; margin-right: 0; }
```

---

## Setting `Content-Language` and Caching

`Content-Language` tells downstream caches and browsers the language of the response body. When using Cloudflare Cache, add `Vary: Accept-Language` (or your locale cookie name) at the origin so locale-specific HTML variants are cached separately:

```typescript
headers.set("Content-Language", locale);
headers.append("Vary", "Accept-Language");
```

---

## Anti-patterns

- Applying `dir="rtl"` only to `<body>` and not `<html>` — browsers derive initial directionality from `<html>`; missing it causes bidirectional text issues in the `<head>` (title, meta).
- Hard-coding the RTL locale set in the Worker — use a KV value (`i18n:rtl-locales`) so new RTL languages can be added without redeployment.
- Swapping stylesheets by injecting an extra `<link>` without removing the LTR one — both stylesheets load, increasing bandwidth and causing specificity conflicts.
- Caching the rewritten HTML without `Vary` — one visitor's RTL response gets served to an LTR visitor.

---

## Gotchas

- **`HTMLRewriter` is streaming**: the `element` handler fires as the tag is parsed. You cannot read the full document before rewriting; the `on("html")` handler fires on the opening `<html>` tag only.
- **`Response` body can only be consumed once**: do not call `originResponse.text()` before passing to `HTMLRewriter`. Pass the raw `Response` object; `rewriter.transform()` consumes the body stream.
- **Service Workers and `dir`**: if your frontend uses a Service Worker that caches HTML, it may serve the cached LTR version to RTL users. Ensure SW cache keys include locale.
- **Bidirectional text (bidi) inside the page**: `dir="rtl"` on `<html>` sets the block direction. Inline LTR content (code, URLs, phone numbers) still needs `dir="ltr"` locally or Unicode bidi control characters.

---

## Verification

```bash
# Request Arabic locale via URL prefix
curl -i https://your-worker.workers.dev/ar/
# Expected headers:
#   Content-Language: ar
#   X-Text-Direction: rtl
# Expected HTML opening tag: <html lang="ar" dir="rtl">

# Request English (default)
curl -i https://your-worker.workers.dev/
# Expected: <html lang="en">, no dir attribute, Content-Language: en

# Verify stylesheet swap
curl -s https://your-worker.workers.dev/ar/ | grep 'stylesheet'
# Expected:
```

---

## Related

- `locale-fallback-chain-kv-workers.md`
- `language-detection-workers-ai-d1.md`
- `unicode-normalization-nfc-nfd-workers-text.md`

## Sources

- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- W3C: Internationalization and HTML — https://www.w3.org/International/questions/qa-html-dir
- MDN: `Content-Language` header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Language
- Unicode Bidirectional Algorithm — https://www.unicode.org/reports/tr9/
