# Font Subsetting and Optimization with R2 and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You pay to serve full variable-font WOFF2 files (often 300–800 kB) for every
visitor, even those who only need Latin characters. You want to:
1. Subset fonts by unicode range and upload to R2
2. Serve each subset from Workers with correct `font-display: swap` and
   `Cache-Control` headers
3. Inject preload hints per-request so the browser fetches the right subsets early

## Context

- **pyftsubset** (part of `fonttools`) is the de-facto CLI for font subsetting;
  run offline or in a CI step
- Subsetted WOFF2 files are immutable; R2 is the right store (no KV 25 MB limit,
  no D1 blob constraints)
- Workers act as a caching reverse proxy in front of R2, adding
  `Cache-Control: public, max-age=31536000, immutable` and the right
  `Content-Type`
- `unicode-range` in `@font-face` lets the browser download only the subset it
  actually needs for the text on the page

---

## 1 — Subset fonts offline (CI step)

```bash
# Install fonttools
pip install fonttools brotli

# Subset Latin (U+0000-00FF) — covers most Western European languages
pyftsubset InterVariable.ttf \
  --unicodes="U+0000-00FF" \
  --layout-features="kern,liga,calt" \
  --flavor=woff2 \
  --output-file=inter-latin.woff2

# Subset Latin Extended (U+0100-024F)
pyftsubset InterVariable.ttf \
  --unicodes="U+0100-024F" \
  --layout-features="kern,liga,calt" \
  --flavor=woff2 \
  --output-file=inter-latin-ext.woff2

# Subset Greek (U+0370-03FF)
pyftsubset InterVariable.ttf \
  --unicodes="U+0370-03FF" \
  --layout-features="kern,liga,calt" \
  --flavor=woff2 \
  --output-file=inter-greek.woff2

# Subset Cyrillic (U+0400-04FF)
pyftsubset InterVariable.ttf \
  --unicodes="U+0400-04FF" \
  --layout-features="kern,liga,calt" \
  --flavor=woff2 \
  --output-file=inter-cyrillic.woff2

# Upload all subsets to R2
for f in inter-latin.woff2 inter-latin-ext.woff2 inter-greek.woff2 inter-cyrillic.woff2; do
  npx wrangler r2 object put fonts-bucket/inter/$f --file=$f --content-type="font/woff2"
done
```

## 2 — R2 bucket and Worker binding

```toml
# wrangler.toml
name = "font-proxy"
main = "src/worker/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding  = "FONTS"
bucket_name = "fonts-bucket"
```

## 3 — Worker: serve fonts from R2

```typescript
// src/worker/index.ts
export interface Env {
  FONTS: R2Bucket;
}

const FONT_MIME: Record<string, string> = {
  '.woff2': 'font/woff2',
  '.woff':  'font/woff',
  '.ttf':   'font/ttf',
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only handle /fonts/* paths
    if (!url.pathname.startsWith('/fonts/')) {
      return new Response('Not found', { status: 404 });
    }

    const key = url.pathname.slice(1); // strip leading '/'
    const ext = key.slice(key.lastIndexOf('.'));
    const contentType = FONT_MIME[ext] ?? 'application/octet-stream';

    // Conditional GET — honour If-None-Match from browser cache
    const ifNoneMatch = request.headers.get('if-none-match');

    const object = await env.FONTS.get(key, {
      onlyIf: ifNoneMatch ? { etagDoesNotMatch: ifNoneMatch } : undefined,
    });

    if (object === null) {
      return new Response('Font not found', { status: 404 });
    }

    // 304 Not Modified
    if (!(object instanceof R2ObjectBody)) {
      return new Response(null, {
        status: 304,
        headers: { etag: object.etag },
      });
    }

    const headers = new Headers({
      'content-type': contentType,
      // Immutable — subsets are named by content hash in production
      'cache-control': 'public, max-age=31536000, immutable',
      etag: object.etag,
      'access-control-allow-origin': '*',   // fonts must be CORS-accessible
    });

    // Write R2 custom metadata as response headers if present
    if (object.customMetadata?.['original-name']) {
      headers.set('x-font-name', object.customMetadata['original-name']);
    }

    return new Response(object.body, { headers });
  },
};
```

## 4 — CSS `@font-face` with `unicode-range`

```css
/* public/styles/fonts.css */

/* Latin — downloaded by almost every visitor */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 100 900;          /* variable range */
  font-display: swap;            /* show fallback immediately, swap when ready */
  src: url('/fonts/inter/inter-latin.woff2') format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6,
                 U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F,
                 U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}

/* Latin Extended */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/fonts/inter/inter-latin-ext.woff2') format('woff2');
  unicode-range: U+0100-02AF, U+0304, U+0308, U+0329, U+1E00-1E9F,
                 U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113,
                 U+2C60-2C7F, U+A720-A7FF;
}

/* Greek */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/fonts/inter/inter-greek.woff2') format('woff2');
  unicode-range: U+0370-03FF;
}

/* Cyrillic */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/fonts/inter/inter-cyrillic.woff2') format('woff2');
  unicode-range: U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;
}
```

## 5 — Preload hints via Pages Function

```typescript
// functions/index.ts  — inject preload <link> for the user's likely script
import type { PagesFunction } from '@cloudflare/workers-types';

export const onRequestGet: PagesFunction = async ({ request, next }) => {
  const response = await next();

  // Only mutate HTML responses
  const ct = response.headers.get('content-type') ?? '';
  if (!ct.includes('text/html')) return response;

  // Detect locale from Accept-Language header
  const acceptLang = request.headers.get('accept-language') ?? 'en';
  const preloads: string[] = ['</fonts/inter/inter-latin.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin'];

  if (/^(ru|uk|bg|sr)/i.test(acceptLang)) {
    preloads.push('</fonts/inter/inter-cyrillic.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin');
  }
  if (/^(el)/i.test(acceptLang)) {
    preloads.push('</fonts/inter/inter-greek.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin');
  }

  // Clone response and add Link header
  const headers = new Headers(response.headers);
  headers.append('link', preloads.join(', '));

  return new Response(response.body, { status: response.status, headers });
};
```

## 6 — Content-hash naming for cache busting (CI)

```bash
#!/usr/bin/env bash
# scripts/upload-fonts.sh
set -euo pipefail

for FILE in dist/fonts/*.woff2; do
  HASH=$(sha256sum "$FILE" | awk '{print $1}' | head -c 12)
  BASENAME=$(basename "$FILE" .woff2)
  KEY="fonts/inter/${BASENAME}-${HASH}.woff2"
  echo "Uploading $FILE → $KEY"
  npx wrangler r2 object put "fonts-bucket/$KEY" \
    --file="$FILE" \
    --content-type="font/woff2" \
    --cache-control="public, max-age=31536000, immutable"
done
```

## Anti-patterns

- **Serving fonts without `access-control-allow-origin: *`** — browsers block
  cross-origin font loads by default; Workers must add the CORS header.
- **Using `font-display: block`** — invisible text for up to 3 s; prefer `swap`
  or `optional` for body text.
- **Uploading the full variable font to R2 without subsetting** — negates the
  entire optimization; a full Inter variable font is ~560 kB; Latin subset is ~90 kB.
- **Cache-Control without `immutable`** — browsers still revalidate on reload;
  `immutable` prevents that for assets with content-hash names.

## Gotchas

1. `pyftsubset` strips OpenType features not listed in `--layout-features`;
   always include `kern` and `liga` for body text, `dnom/numr/frac` for
   numeric content.
2. R2's `onlyIf` conditional-get returns an `R2Object` (no body) on a 304;
   check `instanceof R2ObjectBody` before accessing `.body`.
3. Variable fonts with `font-weight: 100 900` require both endpoints of the
   weight axis to survive subsetting; pass `--layout-features="wght"` to preserve it.
4. The `link` header preload fires only if the font URL exactly matches the
   `src` in the `@font-face` rule (same URL, same CORS mode).

## Verification

```bash
# Confirm subset sizes
ls -lh dist/fonts/
# inter-latin.woff2      ~90 kB
# inter-latin-ext.woff2  ~30 kB
# inter-greek.woff2      ~18 kB
# inter-cyrillic.woff2   ~25 kB

# Start worker locally
npx wrangler dev src/worker/index.ts --local

# Test font delivery
curl -I http://localhost:8787/fonts/inter/inter-latin.woff2
# content-type: font/woff2
# cache-control: public, max-age=31536000, immutable
# access-control-allow-origin: *

# Test ETag conditional GET
ETAG=$(curl -sI http://localhost:8787/fonts/inter/inter-latin.woff2 | grep etag | awk '{print $2}' | tr -d '\r')
curl -I -H "if-none-match: $ETAG" http://localhost:8787/fonts/inter/inter-latin.woff2
# HTTP/2 304

# Lighthouse — CLS should be near 0 with font-display:swap + preload
npx lighthouse http://localhost:8787/ --output=json \
  | jq '.audits["cumulative-layout-shift"].numericValue'
```

## Related

- `documentation/workers/workers-r2-object-storage.md`
- `documentation/categories/frontend/workers-pwa-manifest-offline-pages.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://fonttools.readthedocs.io/en/latest/subset/index.html
- https://web.dev/font-best-practices/
- https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/unicode-range
