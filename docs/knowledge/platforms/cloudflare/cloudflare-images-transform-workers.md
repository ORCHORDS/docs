# Cloudflare Images On-the-Fly Transformations via Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to serve responsive images — thumbnails, WebP conversions, watermarked versions — without a separate image processing service. You want Workers to transform images on the fly using Cloudflare's built-in image pipeline, serve WebP to browsers that support it, and understand the cost model before enabling it at scale.

## Context

Cloudflare provides two distinct image transformation products that are often confused:

| Feature | What it is | How to use |
|---|---|---|
| **Image Resizing** | Zone-level feature on Pro+ plans | `fetch(url, { cf: { image: { ... } } })` from a Worker |
| **Cloudflare Images** | Managed CDN image product (separate SKU) | Upload images via API; serve via `imagedelivery.net` |

This article covers **Image Resizing** — using the `cf.image` subrequest option from a Worker to transform images stored in R2 or on any origin. Image Resizing is enabled per zone and is billed per unique transformation served.

Prerequisites:
- Cloudflare zone on **Pro plan or higher** with Image Resizing enabled (Cloudflare dashboard → Speed → Optimization → Image Resizing).
- A Worker script deployed on the same zone.
- Source images accessible via a URL (R2 public bucket, external CDN, or origin server).

---

## Core Transformation Patterns

```typescript
// src/image-worker.ts

export interface Env {
  IMAGE_ORIGIN: string; // e.g. "https://images.example.com"
}

interface TransformOptions {
  width?: number;
  height?: number;
  fit?: "scale-down" | "contain" | "cover" | "crop" | "pad";
  format?: "webp" | "avif" | "json" | "jpeg" | "png";
  quality?: number;   // 1–100
  dpr?: number;       // device pixel ratio multiplier
  gravity?: "auto" | "left" | "right" | "top" | "bottom" | "face";
  sharpen?: number;   // 0–10
  blur?: number;      // 1–250
}

async function transformImage(
  originUrl: string,
  options: TransformOptions,
  request: Request
): Promise<Response> {
  // The cf.image sub-request is a Server-Side request from the Worker
  // to Cloudflare's image pipeline. The origin URL must be reachable
  // from Cloudflare's edge.
  return fetch(originUrl, {
    cf: {
      image: options,
    } as RequestInitCfProperties,
    headers: {
      // Forward Accept so Cloudflare knows what the browser supports
      Accept: request.headers.get("Accept") ?? "*/*",
    },
  });
}

function parseImagePath(pathname: string): { key: string; params: TransformOptions } | null {
  // Expected: /img/<key>?w=400&h=300&fit=cover&q=80
  const match = pathname.match(/^\/img\/(.+)$/);
  if (!match) return null;
  return { key: match[1], params: {} };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const parsed = parseImagePath(url.pathname);
    if (!parsed) return new Response("Not Found", { status: 404 });

    const sp = url.searchParams;
    const width  = sp.has("w") ? Number(sp.get("w")) : undefined;
    const height = sp.has("h") ? Number(sp.get("h")) : undefined;
    const fit    = (sp.get("fit") ?? "cover") as TransformOptions["fit"];
    const quality = sp.has("q") ? Number(sp.get("q")) : 85;

    // Negotiate format: prefer WebP, fall back to JPEG
    const acceptsWebP = (request.headers.get("Accept") ?? "").includes("image/webp");
    const acceptsAvif = (request.headers.get("Accept") ?? "").includes("image/avif");
    const format: TransformOptions["format"] = acceptsAvif ? "avif" : acceptsWebP ? "webp" : "jpeg";

    const originUrl = `${env.IMAGE_ORIGIN}/${parsed.key}`;

    const transformed = await transformImage(originUrl, { width, height, fit, quality, format }, request);

    if (!transformed.ok) {
      return new Response("Image not found", { status: transformed.status });
    }

    // Clone the response and add Vary header so the cache stores separate
    // versions for WebP vs non-WebP clients.
    const response = new Response(transformed.body, transformed);
    response.headers.set("Vary", "Accept");
    response.headers.set("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800");

    return response;
  },
};
```

---

## Chaining Transformations: Resize then Watermark

Image Resizing does not support multi-step transformations in a single `cf.image` call. To chain (e.g., resize first, then overlay a watermark), you need two approaches:

**Option A — Cloudflare Images product (not Image Resizing):** Use `imagedelivery.net` variant chaining — define a variant in the Cloudflare Images dashboard with watermark and resize together. One CDN hit, one billing event.

**Option B — Worker two-stage fetch (for Image Resizing):**

```typescript
async function resizeThenWatermark(
  originUrl: string,
  watermarkUrl: string,
  env: Env,
  request: Request
): Promise<Response> {
  // Stage 1: resize
  const resized = await fetch(originUrl, {
    cf: { image: { width: 800, height: 600, fit: "cover", format: "png" } } as RequestInitCfProperties,
  });
  if (!resized.ok) throw new Error("Resize failed");

  // Stage 2: use Cloudflare Images API "draw" option to overlay watermark.
  // This requires the Cloudflare Images product (not just Image Resizing).
  // For Image Resizing only zones, composite in the Worker using Canvas API
  // is not available — you must use an external service or Cloudflare Images.
  //
  // With Cloudflare Images (imagedelivery.net), pass the draw overlay:
  const watermarked = await fetch(
    `https://imagedelivery.net/<account_hash>/<image_id>/w=800,h=600,fit=cover,draw=${encodeURIComponent(
      JSON.stringify([{ url: watermarkUrl, bottom: 10, right: 10, width: 100, opacity: 0.8 }])
    )}`,
    { headers: { Accept: request.headers.get("Accept") ?? "*/*" } }
  );

  return watermarked;
}
```

---

## Serving WebP to Supporting Browsers

Browsers that support WebP send `Accept: image/webp` in the request. The Worker reads this header and passes `format: "webp"` to `cf.image`. The key pattern:

1. Read `Accept` from the incoming request.
2. Pass the `Accept` header (or a derived `format` option) to the `cf.image` sub-request.
3. Set `Vary: Accept` on the response so CDN caches store separate copies per format.

Without `Vary: Accept`, a cached WebP response may be served to a browser that requested JPEG, causing decode errors.

---

## Image Resizing vs Cloudflare Images — Key Differences

| | Image Resizing | Cloudflare Images |
|---|---|---|
| **Activation** | Zone plan feature (Pro+) | Separate paid product |
| **Source** | Any URL (R2, external origin) | Upload via API to Cloudflare |
| **Billing** | Per unique transformation | Per image stored + per delivery |
| **Variants** | On-the-fly via Worker params | Pre-defined in dashboard or API |
| **Watermark/draw** | Not supported | Supported via `draw` option |
| **Max input size** | 70 MP | 100 MP |
| **Output formats** | WebP, AVIF, JPEG, PNG | WebP, AVIF, JPEG, PNG |

---

## Cost Considerations

- Image Resizing bills per **unique transformation** served (not per request if cached). A `400x300` WebP and a `400x300` JPEG are two separate billable transformations.
- Transformations are cached at Cloudflare's edge after the first request. Subsequent requests for the same `(key, width, height, fit, format, quality)` tuple are served from cache at no extra transformation cost.
- To minimize cost: use a small set of canonical sizes (e.g., `200`, `400`, `800`, `1200`) rather than accepting arbitrary `?w=` values. Restrict the `w` and `h` query parameters to an allowlist in the Worker.
- Each Worker sub-request to `cf.image` counts against Worker CPU time but not against the transformation quota if the result is a cache hit.

---

## Anti-patterns

- **Accepting arbitrary `?w` and `?h` values** — this creates an unbounded number of unique cache keys and transformations, inflating costs. Snap to a fixed set of widths.
- **Not setting `Vary: Accept`** — WebP responses cached without this header get served to non-WebP clients.
- **Using Image Resizing for watermarking** — it does not support compositing. Use Cloudflare Images with the `draw` option or a dedicated image processing Worker using an external API.
- **Calling `cf.image` from outside a Workers context** — the `cf` option on `fetch` only works inside the Workers runtime. It is not available in local `wrangler dev` without `--remote`.

## Gotchas

- `wrangler dev` (local mode) does not execute `cf.image` transformations — the sub-request returns the original image. Use `wrangler dev --remote` to test transformations.
- The `format: "avif"` option requires the zone to have AVIF support enabled (Cloudflare dashboard → Speed → Optimization).
- If the origin returns a 404, `cf.image` still returns a 404 — the transformation is not attempted. Always check `transformed.ok`.
- Maximum output dimensions: 12 000 × 12 000 px. Maximum input file size: 200 MB (for Image Resizing).
- The `fit: "pad"` option fills empty space with white by default; pass `background` to specify a colour (`background: "#000000"`).

## Verification

```bash
# Request a 400px-wide WebP thumbnail
curl -si "https://your-zone.example.com/img/sample.jpg?w=400&fit=cover" \
  -H "Accept: image/webp" | head -20

# Expected response headers:
# HTTP/2 200
# content-type: image/webp
# vary: Accept
# cache-control: public, max-age=86400, stale-while-revalidate=604800
# cf-cache-status: MISS  (first request) or HIT (subsequent)

# Confirm AVIF for supporting browsers
curl -si "https://your-zone.example.com/img/sample.jpg?w=400" \
  -H "Accept: image/avif,image/webp" | grep content-type
# content-type: image/avif
```

## Related

- `r2-presigned-url-upload-workers.md`
- `cloudflare-pages-custom-headers-file.md`
- `workers-analytics-engine-custom-dashboard.md`

## Sources

- https://developers.cloudflare.com/images/image-resizing/
- https://developers.cloudflare.com/images/cloudflare-images/
- https://developers.cloudflare.com/images/image-resizing/resize-with-workers/
- https://developers.cloudflare.com/images/image-resizing/format-limitations/
