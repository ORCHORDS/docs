# Lazy Loading R2-Hosted Images with IntersectionObserver

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You serve media from Cloudflare R2 through a Worker proxy and need images below the fold to
load only when they enter the viewport — without incurring R2 GET costs or bandwidth for content
the user never sees.

## Context
R2 charges per-operation (Class B reads) and per-GB egress, so lazy loading is directly cost-
relevant in addition to improving page performance. A Cloudflare Worker sits in front of the R2
bucket (R2 buckets are not publicly accessible by default), signs or validates requests, and
optionally rewrites image dimensions via Cloudflare Image Resizing. IntersectionObserver in the
browser handles the client-side deferral, with a `data-r2-src` attribute pattern keeping markup
semantic and crawler-friendly via `<noscript>` fallbacks.

---

## Worker: R2 Image Proxy

```typescript
// workers/r2-image-proxy/src/index.ts
export interface Env {
  IMAGES_BUCKET: R2Bucket;
  ALLOWED_ORIGIN: string; // e.g. "https://mysite.pages.dev"
}

const IMAGE_CACHE_TTL = 60 * 60 * 24 * 7; // 7 days

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, HEAD",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    // Strip leading slash: /photos/hero.webp → photos/hero.webp
    const key = url.pathname.slice(1);

    if (!key || key.includes("..")) {
      return new Response("Bad Request", { status: 400 });
    }

    // Cache lookup — keyed by full URL including potential query params
    const cacheKey = new Request(request.url);
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const object = await env.IMAGES_BUCKET.get(key, {
      onlyIf: request.headers,        // Honour If-None-Match / If-Modified-Since
      range: request.headers,         // Support Range requests for large images
    });

    if (!object) {
      return new Response("Not Found", { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("Cache-Control", `public, max-age=${IMAGE_CACHE_TTL}, immutable`);
    headers.set("Access-Control-Allow-Origin", env.ALLOWED_ORIGIN);
    headers.set("Vary", "Accept");

    // R2 conditional-request shortcut
    if (object.range) {
      headers.set("Content-Range", `bytes ${(object.range as any).offset}-${(object.range as any).end}/${object.size}`);
    }

    const status = object.range ? 206 : 200;
    const response = new Response(object.body as ReadableStream, { status, headers });

    // Populate CDN cache (skip for range requests — partial content must not be cached globally)
    if (!object.range) {
      await cache.put(cacheKey, response.clone());
    }

    return response;
  },
} satisfies ExportedHandler<Env>;
```

---

## Client-Side IntersectionObserver Integration

```typescript
// src/lib/lazyR2Images.ts

const R2_PROXY_BASE = "https://images.myworker.workers.dev";

interface LazyImageOptions {
  /** Root margin — pre-load images within N px of the viewport */
  rootMargin?: string;
  /** Intersection threshold to trigger load */
  threshold?: number;
  /** Callback fired after each image loads */
  onLoad?: (img: HTMLImageElement) => void;
}

/**
 * Observe all [data-r2-src] elements and swap in the real src
 * when they enter the viewport.
 */
export function initLazyR2Images(options: LazyImageOptions = {}): () => void {
  const {
    rootMargin = "200px 0px",
    threshold = 0,
    onLoad,
  } = options;

  if (typeof window === "undefined" || !("IntersectionObserver" in window)) {
    // SSR or old browsers — load eagerly
    document.querySelectorAll<HTMLImageElement>("[data-r2-src]").forEach(loadImage);
    return () => {};
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const img = entry.target as HTMLImageElement;
        loadImage(img, onLoad);
        observer.unobserve(img);
      }
    },
    { rootMargin, threshold }
  );

  const images = document.querySelectorAll<HTMLImageElement>("[data-r2-src]");
  images.forEach((img) => observer.observe(img));

  return () => observer.disconnect();
}

function loadImage(img: HTMLImageElement, onLoad?: (img: HTMLImageElement) => void): void {
  const r2Key = img.dataset.r2Src;
  if (!r2Key) return;

  const width = img.dataset.width;
  const url = new URL(`${R2_PROXY_BASE}/${r2Key}`);
  if (width) url.searchParams.set("w", width);

  img.src = url.toString();
  img.removeAttribute("data-r2-src");

  if (onLoad) {
    img.addEventListener("load", () => onLoad(img), { once: true });
  }
}
```

```typescript
// src/main.ts — wire up on page load
import { initLazyR2Images } from "./lib/lazyR2Images";

document.addEventListener("DOMContentLoaded", () => {
  const cleanup = initLazyR2Images({
    rootMargin: "300px 0px",      // pre-load 300 px before entering viewport
    onLoad: (img) => {
      img.classList.add("loaded"); // fade-in via CSS transition
    },
  });

  // Clean up when navigating away (SPA or View Transitions)
  document.addEventListener("astro:before-preparation", cleanup, { once: true });
});
```

---

## Markup Pattern

```html
<!-- Semantic HTML with noscript fallback for crawlers -->
<figure class="photo-card">
  <img
    data-r2-
    data-width="800"
    alt="Mountain sunrise over the Alps"
    width="800"
    height="533"
    class="lazy-image"
    src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 533'%3E%3C/svg%3E"
  />
  <noscript>
    <img
      src="https://images.myworker.workers.dev/photos/mountain-sunrise.webp?w=800"
      alt="Mountain sunrise over the Alps"
      width="800"
      height="533"
    />
  </noscript>
  <figcaption>The Alps at dawn</figcaption>
</figure>

<style>
.lazy-image {
  opacity: 0;
  transition: opacity 0.3s ease;
  background: #e2e8f0; /* skeleton colour */
}
.lazy-image.loaded {
  opacity: 1;
}
</style>
```

---

## Cloudflare Image Resizing (Optional)

If Image Resizing is enabled on your zone, the Worker can delegate resizing to Cloudflare's
pipeline instead of serving the raw R2 object:

```typescript
// Inside the Worker fetch handler — replace the R2 lookup with a resizing subrequest
const resizedUrl = new URL(request.url);
const width = resizedUrl.searchParams.get("w");

if (width && Number(width) > 0) {
  const r2PublicUrl = `https://pub-XXXXX.r2.dev/${key}`; // dev-only public bucket
  return fetch(r2PublicUrl, {
    cf: {
      image: {
        width: Number(width),
        format: "webp",
        quality: 85,
      },
    },
  });
}
```

---

## Anti-patterns
- Setting `src` to a real low-res placeholder hosted on R2 — doubles R2 operations; use an inline SVG or CSS background instead
- Observing `document` instead of a scoped container — wastes observer memory when only a gallery section needs lazy loading
- Not specifying `width` and `height` attributes — causes CLS (Cumulative Layout Shift) as images load
- Caching range responses in `caches.default` — partial responses served to a client requesting the full file corrupt the payload
- Using `loading="lazy"` and IntersectionObserver simultaneously — browser-native lazy load takes precedence unpredictably

## Gotchas
- R2 `get()` with `onlyIf` returns an `R2ObjectBody` even on a 304 scenario — check `object.body` before reading
- `writeHttpMetadata()` sets `Content-Type` from R2 object metadata; ensure objects were uploaded with correct MIME types
- IntersectionObserver `rootMargin` is relative to the **viewport**, not the document; percentage values are not supported in all browsers
- Cloudflare Image Resizing requires a paid plan and is only available when the Worker is on the same zone as the origin
- `data-r2-src` attributes are stripped by the observer on load; re-initialise after dynamic content injection (e.g. infinite scroll)

## Verification
```bash
# Confirm R2 object exists
wrangler r2 object get IMAGES_BUCKET photos/mountain-sunrise.webp --file /tmp/test.webp

# Check proxy response headers
curl -I https://images.myworker.workers.dev/photos/mountain-sunrise.webp
# Expect: Cache-Control: public, max-age=604800, immutable
# Expect: Content-Type: image/webp

# Verify cache is populated on second request (CF-Cache-Status: HIT)
curl -I https://images.myworker.workers.dev/photos/mountain-sunrise.webp | grep CF-Cache-Status

# Run Lighthouse to confirm no LCP images are lazy-loaded (LCP images must be eager)
npx lighthouse https://yoursite.com --only-audits=uses-lazy-load-on-images
```

## Related
- `browser-intersection-observer.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `infinite-scroll-intersection-observer-mobile.md`
- `image-format-selection-webp-avif.md`
- `html-lazy-loading-images.md`

## Sources
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/images/image-resizing/
- https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
- https://web.dev/lazy-loading-images/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
