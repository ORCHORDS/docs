# Cloudflare Image Resizing for Mobile: WebP/AVIF, srcset, R2

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project media uploads stored in R2 are served at original
resolution (often 3–8 MP JPEGs from camera rolls) to every
client. Mobile users on social feeds download 2–4 MB images
that are rendered at 360×640 CSS pixels, wasting 95 % of the
transferred bytes. LCP times on mobile hover around 3.5–5 s
even though the Cloudflare edge is geographically close. Desktop
browsers receive the same oversized originals, but their faster
connections and larger caches mask the pain. When measured with
WebPageTest on an emulated Moto G Power (throttled 4G), LCP is
dominated entirely by the hero image transfer time.

## Context

Cloudflare Image Resizing is a zone-level feature (requires Pro
plan or above) that transforms images on-the-fly at the edge
using a URL-parameter API (`/cdn-cgi/image/`) or a Workers
`fetch()` call with a `cf.image` option object. R2 objects can
be used directly as the transform source via a Worker — the
bucket is not publicly exposed, and the transform Worker acts
as the sole read path. The key mobile optimisations are:
(1) serve AVIF to capable clients, WebP as fallback, JPEG as
last resort; (2) resize to the actual rendered width per
breakpoint; (3) apply lazy loading via Intersection Observer so
off-screen images are never fetched at all on mobile viewports.

## Format detection across iOS and Android

```
Browser / client                AVIF    WebP    Notes
──────────────────────────────────────────────────────────
Chrome Android ≥ 85             YES     YES     majority Android
Samsung Internet ≥ 14           YES     YES     significant share
Firefox Android ≥ 93            YES     YES
iOS Safari ≥ 16.0               YES     YES     iOS 16+ (2022+)
iOS Safari 14.x / 15.x          NO      YES     still in field
iOS in-app (WKWebView) ≥ 16     YES     YES     same as Safari
iOS in-app (WKWebView) < 16     NO      YES
Android WebView (Chrome-based)  YES     YES     mirrors Chrome ver
Twitter/TikTok in-app iOS       NO*     YES     often frozen < 16

* Twitter's in-app browser on iOS uses a private WKWebView; the
  AVIF decode capability tracks the host OS Safari version, not
  an independently updated engine.
```

Always negotiate format via the `Accept` header, not the UA
string. When `Accept: image/avif` is present, serve AVIF.
When `Accept: image/webp` is present (and no AVIF), serve WebP.
Fall back to the original format (JPEG/PNG) otherwise.

## Serving transforms from a Worker backed by R2

```typescript
// workers/image-transform.ts
// Bindings: R2_MEDIA (R2 bucket), IMAGE_TRANSFORM (service)
// Route: /media/image/:key
//   ?w=<width>  optional explicit width
//   ?q=<1-100>  optional quality override

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url   = new URL(req.url);
    const key   = url.pathname.replace("/media/image/", "");
    const width = Number(url.searchParams.get("w") ?? 0) || null;
    const qual  = Number(url.searchParams.get("q") ?? 75);

    // Format negotiation from Accept header
    const accept = req.headers.get("Accept") ?? "";
    const format: "avif" | "webp" | "jpeg" =
      accept.includes("image/avif") ? "avif"
      : accept.includes("image/webp") ? "webp"
      : "jpeg";

    // Build the Cloudflare Image Resizing fetch options.
    // The fetch target can be an R2 public-access URL or a
    // Workers fetch to the R2 binding object URL.
    const r2Url = `https://${env.R2_DOMAIN}/originals/${key}`;

    const transformed = await fetch(r2Url, {
      cf: {
        image: {
          format,
          quality: qual,
          ...(width ? { width } : {}),
          fit:      "scale-down",  // never upscale
          metadata: "none",        // strip EXIF — privacy + bytes
        },
      },
    });

    if (!transformed.ok) {
      return new Response("Image not found", { status: 404 });
    }

    // Propagate Content-Type set by the image transform
    const resHeaders = new Headers(transformed.headers);
    resHeaders.set(
      "Cache-Control",
      "public, max-age=31536000, immutable"
    );
    resHeaders.set("Vary", "Accept");   // required for AVIF/WebP split

    return new Response(transformed.body, {
      status:  transformed.status,
      headers: resHeaders,
    });
  },
};
```

## Responsive srcset generation in the Worker

```typescript
// Generate a srcset string for a given R2 image key.
// Called from the feed SSR Worker or a dedicated API endpoint.

const BREAKPOINTS = [320, 480, 640, 750, 828, 1080, 1200, 1920];

function buildSrcset(key: string, baseUrl: string): string {
  return BREAKPOINTS
    .map(w => `${baseUrl}/media/image/${key}?w=${w} ${w}w`)
    .join(", ");
}

// Usage in HTML (Next.js or raw HTML from a Worker):
//   <img
//
//     srcset="... generated srcset ..."
//     sizes="(max-width: 600px) 100vw, (max-width: 1200px) 50vw, 33vw"
//     loading="lazy"
//     decoding="async"
//     width="828"
//     height="828"
//   />
//
// "sizes" is critical: without it the browser fetches the
// largest srcset candidate. On a 360 px phone the correct
// candidate is 480w — without sizes the browser may pick 1920w.
```

## Lazy loading strategy for mobile feeds

```typescript
// For above-the-fold images (hero, first feed card): no lazy
// loading. Add fetchpriority="high" to the LCP candidate.
// For all other images in the feed: loading="lazy" is enough
// for Chrome/Firefox. iOS Safari ≥ 15.4 supports it natively.
//
// Intersection Observer fallback for older iOS:

function lazyLoadFallback() {
  if ("loading" in HTMLImageElement.prototype) return; // native

  const images = document.querySelectorAll("img[data-src]");
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const img = entry.target as HTMLImageElement;
      img.src    = img.dataset.src!;
      img.srcset = img.dataset.srcset ?? "";
      observer.unobserve(img);
    });
  }, { rootMargin: "200px" });   // 200 px pre-load buffer

  images.forEach(img => observer.observe(img));
}
```

```
Lazy loading browser support (2026):

  Browser              native loading="lazy"  IO fallback needed
  ──────────────────────────────────────────────────────────────
  Chrome Android ≥ 77  YES                    NO
  iOS Safari ≥ 15.4    YES                    NO
  iOS Safari 14.x      NO                     YES
  Firefox Android ≥ 75 YES                    NO
  Samsung Internet ≥13 YES                    NO

  Coverage of native lazy loading: ~95 % of mobile sessions.
  IO fallback covers the tail; cost is ~800 bytes of JS.
```

## AVIF vs WebP: byte savings on mobile

```
Source: typical feed image (3 MP JPEG, 2.1 MB)
Rendered at 480px wide on mobile.

Format  Width  Quality  File size  vs original JPEG
────────────────────────────────────────────────────
JPEG    1920   85       2,100 KB   baseline
JPEG     480   85         148 KB   -93 %
WebP     480   80          82 KB   -96 %
AVIF     480   65          44 KB   -98 %

→ Serving a 480 px AVIF vs serving the original JPEG cuts
  transfer by 98 %. On a throttled 4G link (5 Mbps):
    2100 KB → 3.36 s transfer
      44 KB → 0.07 s transfer
  LCP improvement: ~3.3 s on the image alone.
```

## Anti-patterns

- **Serving originals from R2 directly via public bucket URL** —
  this bypasses image resizing entirely. All R2 media must route
  through the transform Worker; disable public bucket access or
  the DNS CNAME will serve unoptimised originals.
- **Omitting `sizes` on responsive images** — `srcset` alone is
  not enough; without `sizes`, Chrome uses 100vw as the assumed
  width and selects a candidate far larger than the rendered size.
- **Setting `Vary: Accept` on the HTML page that references
  images** — `Vary` should be on the image responses, not the
  page. Setting it on HTML causes edge caches to store per-Accept
  variants of the whole page, multiplying cache storage.
- **Using the `/cdn-cgi/image/` URL directly in `<img src>`**
  — this works but bypasses the R2 Worker auth layer. If R2 has
  private objects they will 403 when accessed via the public
  transform URL without a Worker in the path.
- **Transforming animated GIFs to AVIF** — Cloudflare's image
  resizing will strip animation. Convert to WebM/MP4 instead of
  AVIF for animated content.

## Gotchas

- **iOS in-app browsers cannot use AVIF below iOS 16** — if
  example project's traffic includes iOS 14/15 in-app browser sessions
  (which CrUX will not capture), those sessions will get the
  JPEG fallback. The `Accept` header is the reliable gate; do
  not assume AVIF from a mobile UA alone.
- **Image Resizing requires a zone-level feature flag** —
  available on Pro+. Confirm with `curl -I` that the
  `cf-resized` response header is present; its absence means
  the plan does not have the feature or the transform did not
  trigger.
- **R2 egress inside the same Cloudflare account is free** — but
  image transform compute is billed per unique transformation.
  Cache the transformed output (`Cache-Control: immutable`) to
  avoid re-transforming the same key+width+format combination.
- **`metadata: "none"` strips GPS/EXIF** — for a social platform
  this is the correct default (privacy). If you need to retain
  orientation (Exif tag 0x0112), use `metadata: "copyright"`
  which retains orientation correction.
- **Lazy loading + LCP candidate conflict** — if the LCP image
  also has `loading="lazy"`, Chrome will defer it and LCP time
  will be catastrophic. Always set the first visible feed image
  to `loading="eager"` and `fetchpriority="high"`.

## Verification

- WebPageTest (throttled 4G, Moto G4 profile): LCP image
  transfer time ≤ 0.3 s; total image bytes ≤ 200 KB per feed
  screen on mobile.
- Response headers on `/media/image/:key?w=480` include
  `Content-Type: image/avif` for Chrome Android, `image/webp`
  for iOS Safari 15, `image/jpeg` for legacy agents.
- `Vary: Accept` confirmed present on image responses (ensures
  edge does not serve AVIF to iOS).
- Lazy images confirmed to not appear in the waterfall for items
  below the first viewport on a throttled connection.
- R2 transform billing: verify unique transformation count in
  Cloudflare dashboard does not grow for repeated requests to
  same URL (confirms cache immutability is working).

## Related

- `documentation/docs/policies/performance/image-optimization-webp-avif.md`
- `documentation/docs/policies/performance/lcp-optimization.md`
- `documentation/docs/policies/performance/image-lazy-loading-intersection-observer.md`
- `documentation/docs/policies/performance/cloudflare-cache-api-workers-mobile.md`
- `documentation/docs/policies/performance/responsive-images-srcset.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Image Resizing docs — https://developers.cloudflare.com/images/transform-images/
- Image Resizing via Workers fetch — https://developers.cloudflare.com/images/transform-images/transform-via-workers/
- AVIF browser support (caniuse) — https://caniuse.com/avif
- WebP browser support (caniuse) — https://caniuse.com/webp
- Native image lazy loading (MDN) — https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Lazy_loading
