# Cloudflare Workers Self-Hosted Web Fonts Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Pages load external font files from `fonts.googleapis.com` or `fonts.gstatic.com`. Each
external font incurs: a DNS lookup, a TLS handshake, an additional RTT for the stylesheet
redirect, and browser privacy mitigations that block cross-origin caching since Chrome 86.
The result is a render-blocking cascade that inflates LCP and causes FOUT even with `<link
rel="preload">`. Self-hosting fonts via R2 + Workers eliminates the cross-origin overhead
and gives full control over cache lifetimes, subset selection, and delivery headers.

---

## Context

Google Fonts serves dynamically subsetted WOFF2 files based on the requesting `User-Agent`.
To self-host you need to: (1) download the WOFF2 files for each desired subset, (2) store
them in R2, (3) serve them from a Worker with correct CORS, caching, and font-display
headers, and (4) replace the `<link >` tag with an inline
`<style>` block pointing at your own origin.

example project platform benefit: fonts served from the same PoP as the HTML response are subject to
HTTP/2 stream multiplexing in the same connection, removing the cross-origin connection
setup cost entirely.

---

## Downloading and uploading font assets to R2

Use `pyftsubset` (fonttools) or Google Fonts Helper to obtain WOFF2 subsets, then push
them to R2 with Wrangler.

```bash
# Install fonttools
pip install fonttools brotli

# Download Latin subset of Inter (example)
curl -L "https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hiJ-Ek-_EeA.woff2" \
  -o inter-latin-400.woff2

# Upload to R2
wrangler r2 object put example project-assets/fonts/inter-latin-400.woff2 \
  --file inter-latin-400.woff2 \
  --content-type "font/woff2"
```

Repeat for each weight and style variant. Name files deterministically:
`{family}-{subset}-{weight}{style}.woff2` (e.g. `inter-latin-700.woff2`).

---

## Worker: serving fonts from R2 with correct headers

```typescript
const FONT_CACHE_SECONDS = 365 * 24 * 60 * 60; // 1 year — fonts are content-addressed

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only serve font paths; all other paths return 404
    if (!url.pathname.startsWith('/fonts/')) {
      return new Response('Not Found', { status: 404 });
    }

    const key = url.pathname.slice(1); // e.g. "fonts/inter-latin-400.woff2"

    // Cache API — avoids re-fetching from R2 on warm isolates
    const cacheKey = new Request(url.toString());
    const cached = await caches.default.match(cacheKey);
    if (cached) return cached;

    const obj = await env.ASSETS_BUCKET.get(key);
    if (!obj) return new Response('Font Not Found', { status: 404 });

    const response = new Response(obj.body, {
      status: 200,
      headers: {
        'Content-Type': obj.httpMetadata?.contentType ?? 'font/woff2',
        'Cache-Control': `public, max-age=${FONT_CACHE_SECONDS}, immutable`,
        'Access-Control-Allow-Origin': '*',   // Required for cross-origin font load in CSS
        ETag: obj.httpEtag,
        'Cross-Origin-Resource-Policy': 'cross-origin',
        Vary: 'Accept-Encoding',
      },
    });

    // Populate cache asynchronously
    const ctx = (globalThis as unknown as { ctx: ExecutionContext }).ctx;
    ctx?.waitUntil(caches.default.put(cacheKey, response.clone()));

    return response;
  },
};
```

> In practice, pass `ctx` through your middleware chain; the pattern above is illustrative.

---

## Inline @font-face declaration (replaces Google Fonts link)

Replace:
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap">
```

With an inlined `<style>` block served in your HTML (or as a minimal CSS file from the
same origin):

```css
/* Served from https://example project.example.com/fonts/inter.css  */

@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 400;
  font-display: swap;           /* Avoid invisible text during load */
  src: url('/fonts/inter-latin-400.woff2') format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6,
                 U+02DA, U+02DC, U+2000-206F, U+2074, U+20AC, U+2122,
                 U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}

@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('/fonts/inter-latin-700.woff2') format('woff2');
  unicode-range: U+0000-00FF;
}
```

Because the font files are now same-origin, the browser reuses the existing HTTP/2
connection without a cross-origin connection setup.

---

## Preloading self-hosted fonts for LCP improvement

With self-hosted fonts, `<link rel="preload">` is reliable because you control the URL
and can set `crossorigin="anonymous"` without credential leakage concerns.

```typescript
// Workers middleware: inject Link: preload header for critical font
function addFontPreloadHeader(response: Response): Response {
  const existing = response.headers.get('Link') ?? '';
  const preloads = [
    `</fonts/inter-latin-400.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin`,
    `</fonts/inter-latin-700.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin`,
  ].join(', ');

  const link = existing ? `${existing}, ${preloads}` : preloads;
  return new Response(response.body, {
    status: response.status,
    headers: { ...Object.fromEntries(response.headers), Link: link },
  });
}
```

Cloudflare converts `Link: rel=preload` headers into HTTP/2 PUSH frames (when Push is
enabled) or Early Hints (103) responses — both further reduce font TTFB.

---

## Cache invalidation on font version bump

Because fonts are stored under an immutable `max-age`, change the filename (or add a
content hash) when you update a font file. A simple Wrangler deploy script:

```bash
#!/usr/bin/env bash
FAMILY=inter
SUBSET=latin
WEIGHT=400
HASH=$(sha1sum inter-latin-400.woff2 | cut -c1-8)
DEST="fonts/${FAMILY}-${SUBSET}-${WEIGHT}-${HASH}.woff2"

wrangler r2 object put "example project-assets/${DEST}" \
  --file inter-latin-400.woff2 \
  --content-type "font/woff2"

echo "Update @font-face src to: /${DEST}"
```

Update the `@font-face src` URL after each upload. Because the old URL is still valid in
R2 (you did not delete it), in-flight page loads that reference the old hash continue to
resolve for as long as you keep the old object.

---

## CORS preflight handling

Browsers issue a preflight OPTIONS request for cross-origin font fetches (e.g., when the
font CSS is served from a CDN subdomain but the font files are on the same Worker). Handle
it explicitly:

```typescript
async function handleFontRequest(request: Request, env: Env): Promise<Response> {
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, HEAD',
        'Access-Control-Max-Age': '86400',
      },
    });
  }
  // … normal GET handling
}
```

---

## Anti-patterns

- **Serving fonts without `immutable` on Cache-Control.** Without `immutable`, browsers
  issue conditional revalidation requests even within `max-age`. Fonts are binary and
  deterministic; `immutable` suppresses the revalidation RTT.
- **Omitting `Access-Control-Allow-Origin`.** CSS `@font-face` always fetches fonts as
  cross-origin (even for same-origin URLs in some browsers). Without the header, the font
  fails to load silently in Firefox and Safari.
- **Serving all font weights eagerly.** Only preload weights used above the fold.
  Variable fonts (one file covering a weight range) reduce file count but increase
  per-file size; evaluate for your specific subset.
- **Forgetting `unicode-range` on subsets.** Without it the browser downloads all
  weight variants for any character, defeating the purpose of subsetting.

---

## Gotchas

- R2 egress to the internet is billed at $0.09/GB; internal Worker ↔ R2 reads are free.
  For very high-traffic sites, placing an additional CDN cache rule in front of the font
  Worker can eliminate R2 read costs almost entirely.
- `font-display: swap` causes FOUT (flash of unstyled text). If the brand font is critical
  to brand identity, consider `font-display: optional` with a local fallback that closely
  matches the metric box of the web font to eliminate layout shift.
- Workers `caches.default.put()` has a minimum TTL of 1 second. Fonts served with
  `max-age=0` are not cacheable by the Cache API.
- Self-hosted fonts do not automatically benefit from Google's font subsetting heuristics;
  you must manually generate and upload subsets for every character range you support
  (Latin, Greek, Cyrillic, etc.).

---

## Verification

```bash
# Confirm font served with correct headers
curl -I https://example project.example.com/fonts/inter-latin-400.woff2
# Expect: Cache-Control: public, max-age=31536000, immutable
# Expect: Access-Control-Allow-Origin: *
# Expect: Content-Type: font/woff2

# Measure LCP before and after self-hosting
npx lighthouse https://example project.example.com --only-audits=largest-contentful-paint --output=json \
  | jq '.audits["largest-contentful-paint"].numericValue'
```

In Chrome DevTools → Network → filter by "font": cross-origin fonts show a grey "blocked"
bar for CORS pre-check; same-origin fonts show no such bar. After self-hosting, all font
entries should share the same connection ID as the HTML document.

---

## Related

- `font-loading-fout.md`
- `font-loading-fout-mobile-variable-fonts.md`
- `font-preloading.md`
- `font-subsetting.md`
- `early-hints-103.md`
- `cloudflare-r2-presigned-cdn-acceleration.md`

---

## Sources

- Google Fonts + privacy: https://developers.google.com/fonts/faq/privacy
- R2 Workers API: https://developers.cloudflare.com/r2/api/workers/
- font-display: https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display
- Workers Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
- Subramanian (2021) — Cross-origin font cache partitioning: https://developer.chrome.com/blog/http-cache-partitioning/
