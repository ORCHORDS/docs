# Lazy Loading Images from R2: Responsive srcset, loading="lazy", and On-the-fly WebP

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A content-heavy page (blog listing, product grid) ships dozens of `<img>` tags pointing at full-resolution JPEGs stored in R2. All images load eagerly at page open, consuming 3-8 MB of bandwidth even for images below the fold that the user may never see. This bloats Time to Interactive (TTI) and wastes mobile data.

Goal:

1. Rewrite all `<img>` tags in the HTML stream to add `loading="lazy"` and a responsive `srcset` with multiple widths.
2. Serve images from a Workers image endpoint that pulls the source from R2, converts to WebP on the fly using Cloudflare Images (Image Resizing), and returns the correct width variant.
3. Ship no external image CDN dependency — the Worker is the CDN.

---

## Context

- **Cloudflare Image Resizing** — built-in feature available on Workers paid plans. Invoked by calling `fetch(url, { cf: { image: { ... } } })` inside a Worker. No separate service setup required.
- **R2** — object storage for original images uploaded at authoring time.
- **HTMLRewriter** — rewrites `<img >` tags in the HTML stream.
- The Worker handles two route types:
  - `GET /` (and other HTML routes) — HTML transformation for `<img>` rewriting.
  - `GET /img/:key` — image endpoint that serves resized/converted images from R2.

---

## Image Endpoint Worker

```typescript
// src/handlers/image.ts
import type { Env } from '../types';

const SUPPORTED_WIDTHS = [320, 640, 960, 1280, 1920] as const;
type Width = (typeof SUPPORTED_WIDTHS)[number];

function clampWidth(raw: string | null): Width {
  const n = parseInt(raw ?? '960', 10);
  // Pick the smallest supported width >= requested width
  return (SUPPORTED_WIDTHS.find((w) => w >= n) ?? 1920) as Width;
}

/**
 * Serve a resized, WebP-converted image from R2.
 *
 * Route: GET /img/:key?w=<width>
 *   key  — R2 object key, e.g. "posts/hero-2024.jpg"
 *   w    — desired width in pixels (optional, defaults to 960)
 */
export async function handleImage(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  // Extract R2 key from path: /img/posts/hero.jpg → posts/hero.jpg
  const key = url.pathname.replace(/^\/img\//, '');
  if (!key) return new Response('Bad Request', { status: 400 });

  const width = clampWidth(url.searchParams.get('w'));

  // Build the public R2 URL (served via a Worker Assets or custom domain)
  // Replace with your actual R2 public endpoint
  const r2PublicUrl = `https://assets.example.com/${key}`;

  // Fetch and resize via Cloudflare Image Resizing
  // This piggybacks on Cloudflare's image processing infrastructure;
  // the source image is fetched from R2 by the CF edge, not by this Worker.
  const imageResponse = await fetch(r2PublicUrl, {
    cf: {
      image: {
        width,
        format: 'webp',
        quality: 82,
        fit: 'scale-down',
      },
    },
  });

  if (!imageResponse.ok) {
    // Fall back to the original image if resizing fails
    const original = await env.IMAGES_BUCKET.get(key);
    if (!original) return new Response('Not Found', { status: 404 });
    return new Response(original.body, {
      headers: {
        'Content-Type': original.httpMetadata?.contentType ?? 'image/jpeg',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  }

  // Forward the resized image with long-lived caching
  return new Response(imageResponse.body, {
    headers: {
      'Content-Type': 'image/webp',
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Vary': 'Accept',
      'X-Image-Width': String(width),
    },
  });
}
```

---

## HTMLRewriter: Rewrite `<img>` Tags

```typescript
// src/middleware/lazy-images.ts
import type { Env } from '../types';

const IMG_ENDPOINT = '/img';
const WIDTHS = [320, 640, 960, 1280, 1920];

/**
 * Build a srcset string for a given R2 image key.
 *
 * Example output:
 *   /img/posts/hero.jpg?w=320 320w,
 *   /img/posts/hero.jpg?w=640 640w,
 *   ...
 */
function buildSrcset(key: string): string {
  return WIDTHS.map((w) => `${IMG_ENDPOINT}/${key}?w=${w} ${w}w`).join(', ');
}

/**
 * Extract the R2 key from an existing <img src> attribute.
 * Handles:
 *   - Absolute URLs:  https://assets.example.com/posts/hero.jpg  → posts/hero.jpg
 *   - Root-relative:  /uploads/posts/hero.jpg                    → posts/hero.jpg
 *   - Already rewritten:  /img/posts/hero.jpg                    → posts/hero.jpg
 */
function extractKey(src: string): string | null {
  try {
    // Already our image endpoint
    if (src.startsWith(`${IMG_ENDPOINT}/`)) {
      return src.replace(`${IMG_ENDPOINT}/`, '');
    }
    // Root-relative under /uploads/
    const match = src.match(/\/uploads\/(.+)$/);
    if (match) return match[1];
    // Absolute URL — extract path after hostname
    const u = new URL(src);
    return u.pathname.replace(/^\//, '');
  } catch {
    return null;
  }
}

class LazyImageTransformer implements ElementHandler {
  element(element: Element): void {
    const src = element.getAttribute('src');
    if (!src) return;

    // Skip external images (data: URIs, other domains)
    if (src.startsWith('data:') || (src.startsWith('http') && !src.includes('example.com'))) {
      return;
    }

    const key = extractKey(src);
    if (!key) return;

    // Rewrite src to go through our image endpoint at default width 960
    element.setAttribute('src', `${IMG_ENDPOINT}/${key}?w=960`);

    // Add srcset for responsive images
    element.setAttribute('srcset', buildSrcset(key));

    // Add sizes if not already present
    if (!element.getAttribute('sizes')) {
      element.setAttribute(
        'sizes',
        '(max-width: 640px) 100vw, (max-width: 1280px) 50vw, 960px',
      );
    }

    // Add lazy loading
    if (!element.getAttribute('loading')) {
      element.setAttribute('loading', 'lazy');
    }

    // Add decoding async for off-screen images
    element.setAttribute('decoding', 'async');
  }
}

/**
 * Apply lazy-loading image rewriting to an HTML response.
 */
export function applyLazyImages(response: Response, _env: Env): Response {
  const contentType = response.headers.get('Content-Type') ?? '';
  if (!contentType.includes('text/html')) return response;

  return new HTMLRewriter()
    .on('img', new LazyImageTransformer())
    .transform(response);
}
```

---

## Main Worker — Routing

```typescript
// src/index.ts
import { handleImage } from './handlers/image';
import { applyLazyImages } from './middleware/lazy-images';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Image endpoint
    if (url.pathname.startsWith('/img/')) {
      return handleImage(request, env);
    }

    // HTML pages — fetch from origin and rewrite
    if (request.method === 'GET') {
      const originResponse = await fetch(request);
      return applyLazyImages(originResponse, env);
    }

    return fetch(request);
  },
};
```

---

## wrangler.toml

```toml
name = "image-optimizer"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[r2_buckets]]
binding = "IMAGES_BUCKET"
bucket_name = "my-images-bucket"

# Image Resizing is enabled on paid Workers plans by default — no extra config needed.
```

---

## Upload an Image to R2 for Testing

```bash
# Upload a test image
npx wrangler r2 object put my-images-bucket/posts/hero.jpg \
  --file ./local/hero.jpg \
  --content-type image/jpeg

# Test the image endpoint directly
curl -sI "https://my-worker.workers.dev/img/posts/hero.jpg?w=640" | grep -E 'Content-Type|X-Image'

# Test HTML rewriting — inspect img tags
curl -s "https://my-worker.workers.dev/blog" | grep -o '<img[^>]*>' | head -5
```

---

## Anti-patterns

- **Eager-loading all images**: the default browser behaviour. Removing `loading="lazy"` from below-fold images wastes bandwidth and delays TTI.
- **No `sizes` attribute with `srcset`**: without `sizes`, the browser downloads the full-width image for every viewport, defeating the purpose of responsive images.
- **Converting images on every request without caching**: Cloudflare Image Resizing caches the output automatically at the edge, but this only works when the Worker returns the response without body manipulation. Do not buffer and re-stream the image body.
- **Serving originals as fallback without content negotiation**: if a browser does not support WebP, `format: 'webp'` still serves WebP. Use `format: 'auto'` to let Cloudflare choose based on `Accept` headers.

---

## Gotchas

- `cf.image` options are only respected when Image Resizing is enabled on your account (paid plan). On free plans the fetch succeeds but the image is served unmodified.
- The source URL passed to `fetch(..., { cf: { image: ... } })` must be publicly accessible. R2 objects without a public bucket domain require a Worker to serve them first, creating a subrequest chain.
- HTMLRewriter `element()` callbacks are synchronous — you cannot `await` inside them. All URL construction must be synchronous.
- `loading="lazy"` is ignored by browsers for images within the initial viewport (LCP candidate). Use `loading="eager"` for the hero/LCP image and `lazy` for everything below.

---

## Related

- `workers-critical-css-inline-html-rewriter.md` — other HTMLRewriter transforms on the same response
- `workers-tcp-connection-reuse-upstream.md` — connection reuse for the R2 subrequest
- [Cloudflare Image Resizing](https://developers.cloudflare.com/images/transform-images/)
- [HTMLRewriter](https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/)

---

## Sources

- Cloudflare Image Resizing — https://developers.cloudflare.com/images/transform-images/transform-via-workers/
- R2 Worker API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- MDN lazy loading — https://developer.mozilla.org/en-US/docs/Web/Performance/Lazy_loading
- Responsive images — https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Structuring_content/HTML_images#use_modern_image_formats
