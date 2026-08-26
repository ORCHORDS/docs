# Critical CSS Inlining via HTMLRewriter: Injecting Above-fold Styles for LCP Improvement

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Lighthouse and CrUX data show a high Largest Contentful Paint (LCP) because the browser must download a full stylesheet (`/static/main.css`, often 80-200 kB) before it can render above-fold content. The render-blocking stylesheet delays paint by 300-900 ms on mobile.

Goal: extract the above-fold CSS from R2 (pre-generated at build time), inject it as a `<style>` block directly in `<head>`, and demote the full stylesheet to a non-blocking deferred load — all transparently at the edge without touching the origin.

---

## Context

Tools used:

- **HTMLRewriter** — streaming HTML transformer built into the Workers runtime; zero external dependencies, processes HTML as a stream without buffering the full document.
- **R2** — object storage for the pre-extracted critical CSS file (`/critical/above-fold.css`), updated on each build by a CI step.
- **Workers** — intercepts every navigation request (`text/html` responses) and applies the transformation.

The critical CSS file is generated at build time by a tool such as `critical` (npm) or `penthouse` and stored as a plain text object in R2.

---

## Build-time: Generate and Upload Critical CSS

```bash
# In your CI pipeline (GitHub Actions, etc.)
npm install --save-dev critical

# Generate above-fold CSS for the homepage
npx critical dist/index.html \
  --base dist/ \
  --width 1300 \
  --height 900 \
  --css dist/static/main.css \
  --extract \
  --inline false \
  --output /dev/stdout 2>/dev/null > critical.css

# Upload to R2
npx wrangler r2 object put my-assets-bucket/critical/above-fold.css \
  --file critical.css \
  --content-type text/css
```

---

## Worker: Fetch Critical CSS and Patch HTML Stream

```typescript
// src/middleware/critical-css.ts
import type { Env } from '../types';

const CRITICAL_CSS_R2_KEY = 'critical/above-fold.css';

/**
 * Middleware that inlines critical CSS into HTML responses.
 *
 * Strategy:
 * 1. Fetch the critical CSS from R2 (cached in-memory per isolate).
 * 2. Use HTMLRewriter to inject a <style> block as the first child of <head>.
 * 3. Rewrite the existing <link rel="stylesheet"> to be non-blocking (print media trick).
 */
export async function inlineCriticalCss(
  response: Response,
  env: Env,
): Promise<Response> {
  // Only transform HTML responses
  const contentType = response.headers.get('Content-Type') ?? '';
  if (!contentType.includes('text/html')) return response;

  // Fetch critical CSS from R2 (Workers isolate caches this in memory
  // for the lifetime of the isolate — typically minutes to hours)
  const cssText = await getCriticalCss(env);
  if (!cssText) {
    // Graceful degradation: return the original response unchanged
    return response;
  }

  // Clone response so we can transform it
  const transformedResponse = new HTMLRewriter()
    .on('head', new CriticalCssInjector(cssText))
    .on('link[rel="stylesheet"]', new StylesheetDeferrer())
    .transform(response);

  // Add a header so we can verify the transformation in logs
  const headers = new Headers(transformedResponse.headers);
  headers.set('X-Critical-CSS', 'injected');

  return new Response(transformedResponse.body, {
    status: transformedResponse.status,
    statusText: transformedResponse.statusText,
    headers,
  });
}

// --- Element Handlers ---

class CriticalCssInjector implements ElementHandler {
  private readonly cssText: string;
  private injected = false;

  constructor(cssText: string) {
    this.cssText = cssText;
  }

  element(element: Element): void {
    if (this.injected) return;
    // Prepend as first child of <head> so it applies before any other resource
    element.prepend(
      `<style id="critical-css">\n${this.cssText}\n</style>`,
      { html: true },
    );
    this.injected = true;
  }
}

class StylesheetDeferrer implements ElementHandler {
  element(element: Element): void {
    const href = element.getAttribute('href') ?? '';
    // Only defer the main stylesheet, not icon fonts or print sheets
    if (!href.includes('/static/main.css')) return;

    // Print-media trick: browser downloads but does not block rendering;
    // onload switches media back to "all"
    element.setAttribute('media', 'print');
    element.setAttribute(
      'onload',
      "this.media='all'; this.onload=null;",
    );
    // Noscript fallback so CSS still loads without JS
    element.after(
      `<noscript><link rel="stylesheet" ></noscript>`,
      { html: true },
    );
  }
}

// --- R2 fetch with in-memory isolate cache ---

let cachedCss: string | null = null;
let cachePopulatedAt = 0;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getCriticalCss(env: Env): Promise<string | null> {
  const now = Date.now();
  if (cachedCss !== null && now - cachePopulatedAt < CACHE_TTL_MS) {
    return cachedCss;
  }

  const obj = await env.ASSETS_BUCKET.get(CRITICAL_CSS_R2_KEY);
  if (!obj) {
    console.warn('Critical CSS not found in R2:', CRITICAL_CSS_R2_KEY);
    return null;
  }

  cachedCss = await obj.text();
  cachePopulatedAt = now;
  return cachedCss;
}
```

---

## Wiring the Middleware into the Fetch Handler

```typescript
// src/index.ts
import { inlineCriticalCss } from './middleware/critical-css';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only handle GET navigation requests
    if (request.method !== 'GET') {
      return fetch(request);
    }

    // Fetch from origin (or another Worker / asset binding)
    const originResponse = await fetch(request);

    // Apply critical CSS injection
    return inlineCriticalCss(originResponse, env);
  },
};
```

---

## wrangler.toml

```toml
name = "edge-html-transform"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[r2_buckets]]
binding = "ASSETS_BUCKET"
bucket_name = "my-assets-bucket"
```

---

## Measuring LCP Improvement

```bash
# Before deploying: run Lighthouse on origin
npx lighthouse https://example.com/  \
  --only-categories=performance \
  --output=json \
  --output-path=before.json

# Deploy the Worker
npx wrangler deploy

# After deploying: run Lighthouse through the Worker
npx lighthouse https://example.com/ \
  --only-categories=performance \
  --output=json \
  --output-path=after.json

# Quick diff on LCP
node -e "
  const b = require('./before.json').audits['largest-contentful-paint'];
  const a = require('./after.json').audits['largest-contentful-paint'];
  console.log('LCP before:', b.displayValue);
  console.log('LCP after:', a.displayValue);
"

# Verify the X-Critical-CSS header is present
curl -sI https://example.com/ | grep -i critical
```

---

## Anti-patterns

- **Inlining the full stylesheet**: this defeats HTTP caching. Only above-fold CSS (typically 5-15 kB) should be inlined.
- **Generating critical CSS at request time**: computing critical CSS on the fly per request costs hundreds of milliseconds. Pre-generate at build time.
- **Blocking on R2 on every request**: use the in-memory isolate cache shown above. R2 latency is 20-80 ms and should not be paid per request.
- **Injecting after `<body>`**: the `<style>` must appear in `<head>` to be applied before paint; `element.prepend` on the `head` handler ensures this.
- **No noscript fallback**: the print-media deferred stylesheet requires the `<noscript>` tag for environments where JS is disabled.

---

## Gotchas

- HTMLRewriter processes the document as a stream; you cannot read the full HTML body and then pass it to `HTMLRewriter.transform()` — the original `Response` must be passed directly.
- The isolate-level in-memory cache (`cachedCss`) is per-isolate, not global. A single Worker deployment can run in thousands of isolates across Cloudflare's network; R2 will be hit once per isolate cold-start, not once globally.
- If critical CSS changes after a deploy (without redeploying the Worker) you must either: (a) deploy the Worker to bust the isolate cache, or (b) use a versioned R2 key (`critical/above-fold.v42.css`) and update the constant.
- The print-media trick requires `onload`, which is a JavaScript attribute. Ensure your CSP allows inline event handlers or use a Service Worker approach instead.

---

## Related

- `workers-lazy-load-images-r2-srcset.md` — further reducing page weight with lazy images
- `workers-speculative-prefetch-kv.md` — pre-warming cache to reduce TTFB
- [HTMLRewriter API](https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/)
- [Cloudflare R2](https://developers.cloudflare.com/r2/)

---

## Sources

- HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Critical CSS concept — https://web.dev/articles/extract-critical-css
- R2 object storage — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
