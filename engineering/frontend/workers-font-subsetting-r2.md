# Web Font Subsetting and Optimised Delivery from R2 via Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You ship a custom typeface with your site but the full WOFF2 file is 300–600 KB. Most pages use only Latin characters; some use Cyrillic or CJK. You want to serve only the glyphs each page actually needs, cache those subsets immutably on R2, and eliminate render-blocking font load with correct `font-display: swap` and preload headers — all from the edge without a font CDN vendor.

## Context

Font subsetting reduces file size by 60–90% for Latin-only pages. Traditional approaches:

- **Build-time subsetting** — generates every possible subset ahead of time (manageable for Latin/Cyrillic/Greek; impractical for CJK with tens of thousands of glyphs).
- **On-demand subsetting** — a server subsets on first request and caches the result.

Cloudflare Workers + R2 enable a hybrid: the Worker checks R2 for a cached subset, returns it instantly on a hit, and on a miss calls a subsetting microservice, stores the result in R2 with an immutable cache header, then serves it. Subsequent requests hit R2 with < 5 ms latency.

Unicode ranges tell the browser which subset to load per character block, matching the CSS `unicode-range` descriptor — so the browser only fetches the font file(s) covering characters actually on the page.

## Solution

### 1. R2 bucket layout

```
r2://fonts-bucket/
  Inter/
    v4.0/
      latin.woff2          # full Latin subset, pre-generated at build time
      latin-ext.woff2
      cyrillic.woff2
      greek.woff2
      dynamic/
        {sha256-of-unicodes}.woff2   # on-demand subsets
```

### 2. CSS `@font-face` with unicode-range descriptors

```css
/* served from /fonts/inter.css via the Worker */

/* Latin subset — loaded on virtually every page */
@font-face {
  font-family: 'Inter';
  font-style:  normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/fonts/Inter/v4.0/latin.woff2') format('woff2');
  unicode-range:
    U+0000-00FF, /* Basic Latin + Latin-1 Supplement */
    U+0131,      /* ı — dotless i */
    U+0152-0153, /* Œœ */
    U+02BB-02BC, /* ʻʼ */
    U+02C6,      /* ˆ */
    U+02DA,      /* ˚ */
    U+02DC,      /* ˜ */
    U+2000-206F, /* General Punctuation */
    U+2074,      /* ⁴ */
    U+20AC,      /* € */
    U+2122,      /* ™ */
    U+2191,      /* ↑ */
    U+2193,      /* ↓ */
    U+2212,      /* − */
    U+2215,      /* ∕ */
    U+FEFF,      /* BOM */
    U+FFFD;      /* replacement char */
}

/* Cyrillic — only fetched on pages with Cyrillic characters */
@font-face {
  font-family: 'Inter';
  font-style:  normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/fonts/Inter/v4.0/cyrillic.woff2') format('woff2');
  unicode-range: U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;
}
```

### 3. Worker: serve static prebuilt subsets from R2

```typescript
// worker/index.ts
import { Env } from './types';

const IMMUTABLE = 'public, max-age=31536000, immutable';
const ONE_HOUR  = 'public, max-age=3600, stale-while-revalidate=86400';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Route: /fonts/**
    if (!url.pathname.startsWith('/fonts/')) {
      return new Response('Not found', { status: 404 });
    }

    // /fonts/inter.css — return the CSS with preload link header
    if (url.pathname === '/fonts/inter.css') {
      return serveFontCss(env);
    }

    // /fonts/**/*.woff2 — serve from R2
    if (url.pathname.endsWith('.woff2')) {
      return serveFontFile(url.pathname, request, env);
    }

    // /fonts/dynamic?text=... — on-demand subset by character set
    if (url.pathname === '/fonts/dynamic') {
      return serveDynamicSubset(url, env);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 4. Serve CSS with Link: preload header

```typescript
async function serveFontCss(env: Env): Promise<Response> {
  const obj = await env.FONTS_BUCKET.get('inter.css');
  if (!obj) return new Response('Font CSS not found', { status: 404 });

  const css = await obj.text();
  return new Response(css, {
    headers: {
      'Content-Type': 'text/css; charset=utf-8',
      'Cache-Control': ONE_HOUR,
      // Preload the Latin subset — it is needed on virtually every page
      'Link': '</fonts/Inter/v4.0/latin.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin',
    },
  });
}
```

### 5. Serve static WOFF2 subset from R2

```typescript
async function serveFontFile(
  pathname: string,
  request:  Request,
  env:      Env
): Promise<Response> {
  // Strip leading /fonts/ to get the R2 key
  const key = pathname.replace(/^\/fonts\//, '');

  // Support range requests (important for large font files)
  const range = request.headers.get('Range');
  const obj   = range
    ? await env.FONTS_BUCKET.get(key, { range: parseRange(range) })
    : await env.FONTS_BUCKET.get(key);

  if (!obj) return new Response('Font not found', { status: 404 });

  const status  = range ? 206 : 200;
  const headers: Record<string, string> = {
    'Content-Type':  'font/woff2',
    'Cache-Control': IMMUTABLE,
    'ETag':          obj.httpEtag,
    'Access-Control-Allow-Origin': '*', // fonts must be CORS-accessible
  };

  if (range && obj.range) {
    headers['Content-Range'] = rangeHeader(obj.range, obj.size);
  }

  return new Response(obj.body, { status, headers });
}

function parseRange(header: string): R2Range {
  // Supports single-range "bytes=START-END" or "bytes=START-"
  const m = header.match(/bytes=(\d+)-(\d*)/);
  if (!m) throw new Error('Unsupported range format');
  const offset = parseInt(m[1], 10);
  const length = m[2] ? parseInt(m[2], 10) - offset + 1 : undefined;
  return length ? { offset, length } : { offset, suffix: undefined };
}

function rangeHeader(range: R2Range, total: number): string {
  if ('offset' in range && 'length' in range && range.length) {
    return `bytes ${range.offset}-${range.offset + range.length - 1}/${total}`;
  }
  return `bytes */${total}`;
}
```

### 6. Dynamic subset generation on demand

```typescript
// GET /fonts/dynamic?family=Inter&version=v4.0&text=Hello+World
async function serveDynamicSubset(
  url: URL,
  env: Env
): Promise<Response> {
  const family  = url.searchParams.get('family')  ?? 'Inter';
  const version = url.searchParams.get('version') ?? 'v4.0';
  const text    = url.searchParams.get('text')    ?? '';

  if (!text) return new Response('text param required', { status: 400 });

  // Unique unicode set → stable cache key
  const unicodes = uniqueCodepoints(text);
  const cacheKey = await hashKey(`${family}:${version}:${unicodes.join(',')}`);
  const r2Key   = `${family}/${version}/dynamic/${cacheKey}.woff2`;

  // R2 cache hit?
  const cached = await env.FONTS_BUCKET.get(r2Key);
  if (cached) {
    return new Response(cached.body, {
      headers: {
        'Content-Type':  'font/woff2',
        'Cache-Control': IMMUTABLE,
        'Access-Control-Allow-Origin': '*',
        'X-Font-Cache':  'HIT',
      },
    });
  }

  // Miss: call subsetting service (self-hosted fonttools worker or external API)
  const subsetReq = await fetch(env.SUBSET_SERVICE_URL, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ family, version, unicodes }),
  });

  if (!subsetReq.ok) {
    return new Response('Subsetting failed', { status: 502 });
  }

  const woff2 = await subsetReq.arrayBuffer();

  // Store in R2 for future requests (fire-and-forget)
  void env.FONTS_BUCKET.put(r2Key, woff2, {
    httpMetadata: {
      contentType: 'font/woff2',
      cacheControl: IMMUTABLE,
    },
  });

  return new Response(woff2, {
    headers: {
      'Content-Type':  'font/woff2',
      'Cache-Control': IMMUTABLE,
      'Access-Control-Allow-Origin': '*',
      'X-Font-Cache':  'MISS',
    },
  });
}

function uniqueCodepoints(text: string): number[] {
  return [...new Set([...text].map((c) => c.codePointAt(0)!))].sort((a, b) => a - b);
}

async function hashKey(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

### 7. Types and wrangler.toml

```typescript
// worker/types.ts
export interface Env {
  FONTS_BUCKET:       R2Bucket;
  SUBSET_SERVICE_URL: string;
}
```

```toml
# wrangler.toml
name = "font-worker"
main = "worker/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding     = "FONTS_BUCKET"
bucket_name = "fonts-bucket"

[vars]
SUBSET_SERVICE_URL = "https://subset.internal.example.com/subset"
```

## Implementation Details

- **`font-display: swap`** ensures text renders immediately in a fallback font while the custom font loads; `optional` is a stricter alternative that only uses the custom font if it loads within a very short window.
- **CORS on font files** (`Access-Control-Allow-Origin: *`) is mandatory when fonts are served from a different origin to the HTML document. Browsers enforce CORS for font fetches.
- **Immutable cache headers** (`max-age=31536000, immutable`) are safe only when the file URL encodes its version (e.g. `/Inter/v4.0/latin.woff2`). Never use immutable on a URL that can change content.
- **Link: preload** on the CSS response allows the browser to discover and fetch the Latin subset before it parses the stylesheet, shaving one round-trip.
- **R2 range request support** matters for browsers that resume interrupted downloads.

## Anti-patterns

- **Serving fonts with `Cache-Control: no-cache`** — forces re-validation on every page load; fonts are binary assets that should be immutably cached.
- **Serving all unicode blocks in a single file** — wastes bandwidth for Latin-only pages; use unicode-range splitting.
- **Generating subsets on every request** without caching in R2 — subsetting via fonttools can take 50–200 ms; cache aggressively.
- **Omitting `crossorigin` on `<link rel=preload>`** — the font will be preloaded with a non-CORS fetch, then re-fetched as CORS when the `@font-face` rule fires, wasting the preload.

## Gotchas

- `R2Object.body` is a `ReadableStream`; it can only be consumed once. If you need to both store and serve it, `tee()` the stream or consume it to an `ArrayBuffer` first.
- R2 `put` with `httpMetadata.cacheControl` sets the object-level cache header returned in `R2Object.httpMetadata` on `get`. This is separate from Workers Cache API and from Cloudflare's edge cache.
- `font/woff2` is the correct MIME type (not `application/font-woff2`); use it to pass browser security checks.
- Variable fonts (`font-weight: 100 900`) require the `wght` axis to be present in the WOFF2 file. Verify with `woff2_info` that the axis survived subsetting.

## Verification

1. Upload test subsets: `wrangler r2 object put fonts-bucket/Inter/v4.0/latin.woff2 --file ./Inter-latin.woff2`.
2. `wrangler dev` — open a test page, DevTools Network → filter by `Font`, confirm `latin.woff2` is 200 with `immutable` headers.
3. Reload — confirm `latin.woff2` is served from disk cache (status `(disk cache)` in Chrome).
4. Add a Cyrillic character to the test page — confirm `cyrillic.woff2` is fetched on demand.
5. Check `X-Font-Cache` header on `/fonts/dynamic?text=Hello` — first request is `MISS`, second is `HIT`.

## Related

- `workers-islands-architecture-partial-hydration.md` — island-specific asset loading pattern
- `workers-static-form-handler-d1.md` — R2 and D1 usage patterns

## Sources

- Cloudflare R2 API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- MDN @font-face unicode-range: https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/unicode-range
- Google Fonts CSS explainer: https://developers.google.com/fonts/docs/css2
- fonttools pyftsubset: https://fonttools.readthedocs.io/en/latest/subset/
- web.dev font-display: https://web.dev/articles/font-display
