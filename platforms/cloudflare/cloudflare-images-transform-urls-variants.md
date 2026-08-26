# Cloudflare Images Transform URLs and Variants

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You store originals in Cloudflare Images and need to serve them at multiple resolutions — thumbnails for listing pages, medium crops for cards, full-quality for lightboxes — without storing separate files. You want `<img srcset>` URLs that encode transform parameters directly, and you want to lock down the allowed transforms so users cannot request arbitrary dimensions and exhaust your transformation budget.

---

## Context

Cloudflare Images has two delivery surfaces:

1. **Named variants** — predefined transform profiles you define in the dashboard or via API. Each variant gets a stable path segment (`/public`, `/thumbnail`, etc.) appended to the delivery URL. Safe and cacheable by definition.
2. **Flexible variants (transform URLs)** — parameters encoded in the URL path using the `/cdn-cgi/image/` prefix (or your custom domain). These allow arbitrary transforms but must be explicitly enabled per zone and are **disabled by default** to prevent abuse.

Both surfaces share the same underlying transform pipeline: Cloudflare resizes, crops, and re-encodes the image at the edge and caches the result at that CDN node. Subsequent requests for the same transform hit the cache, not the origin.

### Delivery URL anatomy

```
# Named variant
https://imagedelivery.net/<accountHash>/<imageId>/<variantName>

# Flexible variant (arbitrary params)
https://imagedelivery.net/<accountHash>/<imageId>/w=800,h=600,fit=cover,format=auto,quality=85
```

---

## Defining Named Variants via API

Named variants are the recommended path for production: predictable CDN cache keys, no parameter injection risk, and fine-grained CORS control per variant.

```bash
# Create a "thumbnail" variant  (200×200, cropped, WebP)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/variants" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "thumbnail",
    "options": {
      "width": 200,
      "height": 200,
      "fit": "cover",
      "metadata": "none",
      "quality": 80
    },
    "neverRequireSignedURLs": false
  }'

# Create a "card" variant  (640px wide, proportional height)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/variants" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "card",
    "options": {
      "width": 640,
      "fit": "scale-down",
      "metadata": "none",
      "quality": 85
    },
    "neverRequireSignedURLs": true
  }'
```

Available `fit` values:

| `fit` | Behaviour |
|-------|-----------|
| `scale-down` | Shrinks proportionally; never enlarges |
| `contain` | Fits inside the box; letterboxes if needed |
| `cover` | Crops to fill the box exactly |
| `crop` | Same as `cover` |
| `pad` | Fills box with padding (use `background` for colour) |

---

## Flexible Variant Transform Parameters

When flexible variants are enabled on the account, you can pass transform parameters directly in the URL. This is useful for dynamically-sized embeds (e.g., OG images at caller-specified dimensions) and developer tooling.

```
https://imagedelivery.net/<accountHash>/<imageId>/w=1200,h=630,fit=cover,format=webp,quality=90,dpr=2
```

### Full parameter reference

```
w=<px>            Width in pixels (1–12000)
h=<px>            Height in pixels (1–12000)
fit=<mode>        scale-down | contain | cover | crop | pad
gravity=<dir>     auto | left | right | top | bottom | center
                  or  gravity=0.5x0.3  (focal point as fraction)
format=<fmt>      auto | webp | avif | jpeg | png | json
quality=<1–100>   Lossy quality level (default 85)
metadata=keep|copyright|none
sharpen=<0–10>    Unsharp-mask strength
blur=<1–250>      Gaussian blur radius (pixels)
brightness=<num>  1.0 = unchanged; 0.5 = 50% darker
contrast=<num>    1.0 = unchanged; 1.3 = +30% contrast
gamma=<num>       Gamma correction (default 1.0)
rotate=90|180|270 Clockwise rotation
background=<hex>  Fill colour for pad fit (e.g. background=ff0000)
border=<spec>     Add border: border=5,color=0000ff
dpr=<1–3>         Device pixel ratio — multiplies w and h
anim=true|false   Preserve animation frames (GIF, WebP)
onerror=redirect  Serve original on transform failure
```

### `format=auto` behaviour

`format=auto` inspects the `Accept` header. If the browser advertises `image/avif`, Cloudflare serves AVIF. If it advertises `image/webp`, it serves WebP. Otherwise it falls back to JPEG. This is the recommended default for `<img>` elements — browsers that cannot display AVIF gracefully get JPEG.

---

## Generating srcset URLs in a Worker

```typescript
// workers/image-url-builder.ts
const ACCOUNT_HASH = "your-account-hash"; // from Images → Overview in dashboard
const BASE = `https://imagedelivery.net/${ACCOUNT_HASH}`;

interface ImageParams {
  width: number;
  height?: number;
  fit?: "cover" | "contain" | "scale-down" | "pad";
  quality?: number;
  format?: "auto" | "webp" | "avif" | "jpeg";
}

export function imageUrl(imageId: string, params: ImageParams): string {
  const parts: string[] = [`w=${params.width}`];
  if (params.height)  parts.push(`h=${params.height}`);
  if (params.fit)     parts.push(`fit=${params.fit}`);
  if (params.quality) parts.push(`quality=${params.quality}`);
  if (params.format)  parts.push(`format=${params.format}`);
  return `${BASE}/${imageId}/${parts.join(",")}`;
}

export function buildSrcset(
  imageId: string,
  widths: number[],
  baseParams: Omit<ImageParams, "width">
): string {
  return widths
    .map((w) => `${imageUrl(imageId, { ...baseParams, width: w })} ${w}w`)
    .join(", ");
}

// Example response handler
export default {
  async fetch(_req: Request, env: Env): Promise<Response> {
    const imageId = "abc123def456";
    const srcset = buildSrcset(imageId, [320, 640, 1280, 1920], {
      fit: "cover",
      format: "auto",
      quality: 85,
    });
    const html = `<img
      auto" })}"
      srcset="${srcset}"
      sizes="(max-width: 768px) 100vw, 50vw"
      loading="lazy"
      decoding="async"
    />`;
    return new Response(html, { headers: { "Content-Type": "text/html" } });
  },
};
```

---

## Signed (Private) Image Delivery

Images can be uploaded with `requireSignedURLs: true`. Delivery then requires a signed token. Generate signed URLs in a Worker using the signing key from your Images settings.

```typescript
// Generate a signed URL that expires in 1 hour
async function signImageUrl(
  imageId: string,
  variantName: string,
  signingKey: string
): Promise<string> {
  const url = `https://imagedelivery.net/${ACCOUNT_HASH}/${imageId}/${variantName}`;
  const expiry = Math.floor(Date.now() / 1000) + 3600; // 1 hour
  const signedUrl = new URL(url);
  signedUrl.searchParams.set("exp", String(expiry));

  const encoder = new TextEncoder();
  const keyData = encoder.encode(signingKey);
  const msgData = encoder.encode(signedUrl.pathname + signedUrl.search);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, msgData);
  const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  signedUrl.searchParams.set("sig", b64);
  return signedUrl.toString();
}
```

---

## Uploading Images from a Worker

```typescript
// Upload a remote image by URL (server-side fetch)
async function uploadFromUrl(
  sourceUrl: string,
  id: string,
  env: Env
): Promise<string> {
  const form = new FormData();
  form.append("url", sourceUrl);
  form.append("id", id); // custom ID — must be unique
  form.append("requireSignedURLs", "false");

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: form,
    }
  );
  const data = (await res.json()) as { result: { id: string } };
  return data.result.id;
}

// Upload raw bytes (e.g., from a multipart form body)
async function uploadBytes(
  bytes: ArrayBuffer,
  filename: string,
  env: Env
): Promise<string> {
  const form = new FormData();
  form.append("file", new Blob([bytes], { type: "image/jpeg" }), filename);
  form.append("requireSignedURLs", "false");

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: form,
    }
  );
  const data = (await res.json()) as { result: { id: string } };
  return data.result.id;
}
```

---

## Anti-patterns

- **Encoding transform params in client-side JavaScript and sending them to the browser.** If flexible variants are enabled, a user can craft arbitrary resize URLs and exhaust your transform budget. Gate flexible variants behind a Worker that validates the requested dimensions against an allowlist before issuing the delivery URL.
- **Using `fit=pad` without `background`.** The default background for padding is black, which looks wrong on white-themed sites. Always set `background=ffffff` or a brand colour.
- **Storing derived sizes separately.** Upload only the original at full resolution. Never upload pre-resized copies — that duplicates storage and misses cache benefits of the shared transform pipeline.
- **Setting `quality=100` for production delivery.** Even JPEG at q=85 is perceptually lossless for most photos. q=100 roughly triples file size with no user-visible benefit.
- **Forgetting `metadata=none`.** By default, EXIF metadata (including GPS coordinates from mobile uploads) is preserved. Always set `metadata=none` unless you have a specific need for it.

---

## Gotchas

1. **Account hash vs. zone ID.** The delivery URL uses your **account image hash** (found in Images → Overview), not your zone ID. These look similar but are different identifiers.
2. **Variant changes are not retroactively applied to cached responses.** If you update a variant's dimensions, existing CDN-cached responses at the old dimensions are served until they expire or you purge by variant URL prefix.
3. **`format=auto` requires the `Vary: Accept` header.** Cloudflare sets this automatically, but if you're fronting the delivery URL with another CDN or proxy, make sure it respects `Vary` or you risk serving AVIF to a browser that requested JPEG.
4. **The `json` format returns image metadata (dimensions, EXIF) instead of an image.** Useful for inspecting uploads, but do not accidentally serve it as an `<img>` src.
5. **Custom IDs must be URL-safe.** If you provide a custom `id` at upload time (matching a database primary key), avoid characters that require percent-encoding in the delivery URL path. Stick to `[a-zA-Z0-9_-]`.
6. **Flexible variants add `cf-` response headers that leak transform parameters to clients.** If your transforms encode business logic (e.g., watermark bypass dimensions), prefer named variants with opaque names.

---

## Verification

```bash
# List all variants on the account
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/variants" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.variants | keys'

# Fetch a variant and inspect content-type and cache status
curl -sI "https://imagedelivery.net/${ACCOUNT_HASH}/${IMAGE_ID}/thumbnail" \
  | grep -E "content-type|cf-cache-status|content-length"

# Test format=auto by spoofing Accept header
curl -sI "https://imagedelivery.net/${ACCOUNT_HASH}/${IMAGE_ID}/w=400,format=auto" \
  -H "Accept: image/avif,image/webp,*/*" \
  | grep content-type
# Expected: content-type: image/avif  (if account supports AVIF)
```

---

## Related

- `images-best-practices.md` — upload quotas, storage costs, R2 + Images hybrid patterns
- `r2-best-practices.md` — when to use R2 + Image Resizing instead of Cloudflare Images
- `cache-stale-while-revalidate-control-boundary.md` — cache behaviour for transformed images
- `workers-fetch-api-patterns.md` — fetching image APIs from within Workers
- `client-hints-adaptive-image-delivery-mobile.md` — using `DPR` and `Width` client hints

---

## Sources

- Cloudflare Images documentation: https://developers.cloudflare.com/images/
- Cloudflare Images variants: https://developers.cloudflare.com/images/manage-images/create-variants/
- Transform URL parameters: https://developers.cloudflare.com/images/transform-images/transform-via-url/
- Signed URL tokens: https://developers.cloudflare.com/images/manage-images/serve-images/serve-private-images/
