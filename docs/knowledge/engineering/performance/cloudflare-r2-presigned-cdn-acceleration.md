# R2 Presigned URLs via CDN Subdomain vs Direct R2 Endpoint

**Date:** 2026-08-22
**Author:** example.com
**Status:** active

## Symptom

example project media uploads (user-generated audio and cover art) are served
to mobile clients via direct R2 presigned URLs (`*.r2.cloudflarestorage.com`).
Mobile users on 4G/5G with high-latency cells report download stalls of
800–2 000 ms before the first byte of a presigned object arrives. Desktop
browsers on the same logical origin see 60–120 ms TTFB because browser
keep-alive pools reuse the TLS connection. Direct R2 presigned URLs bypass
Cloudflare's CDN cache entirely: every mobile client re-fetches cold bytes
from the R2 storage PoP closest to the bucket, not the PoP closest to the
user.

## Context

R2 offers two URL families for presigned access:

- **Direct endpoint**: `https://<account>.r2.cloudflarestorage.com/<bucket>/<key>?X-Amz-*`
  — bypasses CDN; hits R2 storage directly; no Cloudflare cache layer.
- **Custom domain / CDN subdomain**: `https://media.example.com/<key>` — routes
  through Cloudflare edge; CDN cache applies; Image Resizing pipeline is
  accessible; Cache-Control on the R2 object controls edge TTL.

example project audio tracks are immutable once uploaded (content-addressed keys).
Cover-art images are also immutable per upload version. Both are safe for
long-lived CDN caching. Switching the presigned URL pattern to route through
the CDN subdomain collapses cold-path TTFB for mobile clients and enables
on-the-fly AVIF/WebP transcoding via Cloudflare Image Resizing.

## CDN subdomain vs direct R2 endpoint: latency comparison

```
Scenario: 800 KB cover-art JPEG, mobile client on 4G (100 ms RTT to PoP)

Request path                  TTFB     Total download   Cache hit?
──────────────────────────────────────────────────────────────────
Direct R2 URL (cold)          820 ms   1 340 ms         No
Direct R2 URL (same session)  820 ms   1 340 ms         No  (no cache)
CDN subdomain (cold, miss)    130 ms   650 ms           No  (miss→origin fill)
CDN subdomain (warm, hit)      28 ms   350 ms           Yes (CF-Cache-Status: HIT)
CDN subdomain + Image Resize   35 ms   190 ms           Yes (AVIF, 60 % smaller)

Note: CDN cold-miss still wins on TTFB because the Cloudflare PoP is geographically
closer to the mobile client than the R2 storage PoP. The origin-fill bandwidth cost
is paid once per PoP; subsequent requests at that PoP are cache hits.
```

## Presigned URL generation: switching to CDN base URL

```typescript
// workers/presign.ts — generate a presigned GET URL that routes
// through Cloudflare CDN instead of the direct R2 endpoint.

const CDN_BASE  = "https://media.example.com";   // custom domain on the R2 bucket
const R2_BUCKET = env.R2_MEDIA;                 // Workers R2 binding

/**
 * For read access via CDN, presigning is not required — the CDN
 * subdomain can be configured as "public" in the R2 bucket settings,
 * and the object key alone is the URL.  For write operations or
 * time-limited read access to private buckets, use the AWS-compatible
 * presigned URL but rebase it onto the CDN domain.
 */
export function cdnUrl(key: string, opts?: { w?: number; h?: number; format?: "avif" | "webp" }): string {
  const url = new URL(`${CDN_BASE}/${encodeURIComponent(key)}`);

  // Cloudflare Image Resizing params (only applies to image keys)
  if (opts?.w)      url.searchParams.set("width",   String(opts.w));
  if (opts?.h)      url.searchParams.set("height",  String(opts.h));
  if (opts?.format) url.searchParams.set("format",  opts.format);

  return url.toString();
}

// Example: mobile cover-art at 640 px wide, AVIF
const mobileCover = cdnUrl("covers/track-abc123.jpg", { w: 640, format: "avif" });
// → https://media.example.com/covers/track-abc123.jpg?width=640&format=avif
```

## Cache-Control headers for R2 objects

```typescript
// Set Cache-Control at upload time so the CDN edge respects TTL.
// R2 Workers binding: httpMetadata carries Cache-Control to the CDN.

await env.R2_MEDIA.put(key, body, {
  httpMetadata: {
    contentType:  "image/jpeg",
    // Immutable content-addressed key: cache forever at the edge,
    // 1 year in browser. The CDN will serve from cache; browser
    // will not revalidate within the year.
    cacheControl: "public, max-age=31536000, s-maxage=31536000, immutable",
  },
});

// For mutable objects (e.g., user avatar, replaced in-place):
await env.R2_MEDIA.put(avatarKey, body, {
  httpMetadata: {
    contentType:  "image/jpeg",
    // Short browser TTL; long CDN TTL with SWR for fresh delivery.
    cacheControl: "public, max-age=60, s-maxage=86400, stale-while-revalidate=3600",
  },
});
```

```
Cache-Control strategy per object type in example project:

  Object type          max-age     s-maxage     Notes
  ──────────────────────────────────────────────────────────────────────
  Cover art (immutable) 31536000   31536000     content-addressed key
  Audio track (immutable) 31536000 31536000     content-addressed key
  User avatar (mutable)   60       86400        invalidate on upload
  Waveform JSON (immutable) 31536000 31536000   generated once per track
  Playlist manifest (mutable) 30   300          updated on edit
```

## AVIF and WebP via Cloudflare Image Resizing

```typescript
// Serve AVIF to supporting clients, WebP as fallback, JPEG as last resort.
// Cloudflare Image Resizing runs at the edge when requests arrive at the
// CDN subdomain and the cf.image transform is set in a Worker or via URL params.

export async function imageHandler(req: Request): Promise<Response> {
  const accept = req.headers.get("Accept") ?? "";
  const isMobile = (req.headers.get("CF-Device-Type") ?? "") !== "desktop";

  // Choose output format based on client Accept header
  const format: "avif" | "webp" | "jpeg" =
    accept.includes("image/avif") ? "avif" :
    accept.includes("image/webp") ? "webp" :
    "jpeg";

  // Mobile clients get narrower renditions
  const width = isMobile ? 640 : 1280;

  // Proxy through Cloudflare Image Resizing using fetch() with cf.image
  const originUrl = `${CDN_BASE}/${new URL(req.url).pathname.slice(1)}`;
  return fetch(originUrl, {
    cf: {
      image: {
        width,
        format,
        quality: format === "avif" ? 60 : 75,
        fit:     "cover",
      },
    },
  });
}
```

```
Bandwidth savings with Image Resizing (desktop 1280w, mobile 640w):

  Format    Desktop size   Mobile size   Mobile vs JPEG baseline
  ──────────────────────────────────────────────────────────────
  JPEG      220 KB         68 KB         baseline
  WebP      140 KB         42 KB         −38 %
  AVIF       80 KB         24 KB         −65 %

  Mobile AVIF at 640w represents a 4.6× reduction from desktop
  JPEG — critical on 4G cells where the bottleneck is bytes, not RTT.
```

## Anti-patterns

- **Serving direct R2 presigned URLs to mobile clients** — bypasses CDN
  caching entirely; every mobile session pays full cold R2 latency regardless
  of how popular the object is.
- **No Cache-Control on R2 objects** — without `cacheControl` in `httpMetadata`,
  R2 returns objects with no cache directives; Cloudflare edge defaults to
  short or zero TTL and the CDN provides no benefit.
- **Using mutable keys for immutable content** — uploading a new cover art
  to the same R2 key forces manual CDN cache purges; content-addressed keys
  (hash in the filename) make immutability structural.
- **Sending Image Resizing `format=avif` to clients that do not accept it** —
  older in-app browsers (some iOS WebViews) do not decode AVIF; always gate
  on the `Accept` header.
- **Requesting Image Resizing through the direct R2 endpoint** — Image
  Resizing only operates on requests that pass through Cloudflare's proxy;
  direct `*.r2.cloudflarestorage.com` URLs are not processed.

## Gotchas

- **CDN subdomain requires the R2 bucket to have a custom domain configured**
  — in the R2 dashboard the bucket must have the domain attached and proxied
  (orange-cloud) via DNS. Bypassed (grey-cloud) records skip the CDN layer.
- **Image Resizing is a paid Cloudflare feature** — it is available on Pro
  and above; verify the plan before deploying image transform logic.
- **`s-maxage` on R2 httpMetadata is respected by the CDN but not the
  browser** — browsers use `max-age` or `Expires`; set both when browser
  caching matters for offline scenarios.
- **AVIF encoding at the edge is CPU-intensive** — the first request for a
  novel (width, format, key) combination is slow (~400 ms); subsequent requests
  hit the CDN cache. Pre-warm popular cover art after upload with a synthetic
  request.
- **Cloudflare Cache Reserve** — for R2 objects accessed infrequently,
  enabling Cache Reserve persists CDN cache copies to R2 itself, preventing
  cold-eviction between traffic spikes. Adds per-operation cost; worthwhile
  for audio tracks rarely but periodically accessed.

## Verification

- `CF-Cache-Status: HIT` in response headers from `media.example.com` confirms
  the CDN layer is active.
- Compare TTFB via WebPageTest mobile profile (Moto G4, 4G throttle) between
  direct R2 URL and CDN subdomain URL for the same object; expect ≥ 70 %
  TTFB reduction on warm cache.
- Cloudflare Analytics → Caching tab shows hit ratio per URL prefix; target
  ≥ 90 % hit ratio for immutable cover art after warm-up.
- Use `curl -I https://media.example.com/<key>` and inspect `Cache-Control`
  response header; assert it matches the `httpMetadata.cacheControl` set at
  upload time.
- Image Resizing: assert response `Content-Type: image/avif` on an AVIF-capable
  client and `Content-Type: image/webp` on a WebP-only client for the same URL.

## Related

- `documentation/docs/policies/performance/cloudflare-image-resizing-mobile-webp-avif.md`
- `documentation/docs/policies/performance/cache-control-headers.md`
- `documentation/docs/policies/performance/cdn-cache-strategy.md`
- `documentation/docs/policies/performance/cloudflare-cache-api-workers-mobile.md`
- `documentation/docs/policies/performance/image-optimization-webp-avif.md`

## Sources

- Cloudflare R2 Custom Domains — https://developers.cloudflare.com/r2/buckets/public-buckets/
- Cloudflare Image Resizing — https://developers.cloudflare.com/images/image-resizing/
- R2 Workers API: httpMetadata — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cache-Control header (MDN) — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
- Cloudflare Cache Reserve — https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
