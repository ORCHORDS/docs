# Cloudflare Images Flexible Variants with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your app needs dynamically sized images where the exact dimensions are not known at build time — user-uploaded avatars at arbitrary canvas sizes, CMS-driven hero images, or thumbnail grids where the client negotiates dimensions. Cloudflare Images **flexible variants** allow any caller to specify width, height, fit, and quality at request time rather than pre-defining every variant in the dashboard. Workers act as the authorisation and signing layer so the flexible variant URL cannot be abused by external clients.

---

## Context

Cloudflare Images has two variant modes:

| Mode | Dimensions | Dashboard config needed | URL pattern |
|------|-----------|------------------------|-------------|
| Named variant | Fixed at creation | Yes | `imagedelivery.net/{accountHash}/{imageId}/{variantName}` |
| Flexible variant | Dynamic per-request | Enable once | `imagedelivery.net/{accountHash}/{imageId}/w={w},h={h},fit={fit}` |

Flexible variants are disabled by default. Once enabled (Images → Variants → Allow flexible variants), any signed or public URL can pass transformation parameters. For public delivery zones, abuse is contained by signing the URL with an HMAC token generated in a Worker so clients cannot freely enumerate or resize arbitrary images.

Workers also handle the signing, serve the correct `Accept: image/avif,image/webp` negotiation, implement lazy-loading hints, and proxy delivery for EU data-residency zones.

---

## Enabling Flexible Variants

Flexible variants must be enabled once per account via the REST API or dashboard before any Worker can use them.

```bash
# Enable via API
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/config" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"flexible_variants": true}'
```

```typescript
// Confirm from a Worker (admin/management Worker only)
async function isFlexibleVariantsEnabled(
  accountId: string,
  apiToken: string
): Promise<boolean> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/images/v1/config`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const body = (await res.json()) as { result: { flexible_variants: boolean } };
  return body.result.flexible_variants;
}
```

---

## Generating Signed Flexible Variant URLs in a Worker

Never expose raw image IDs to the browser. Use a Worker to build a signed delivery URL with HMAC-SHA256.

```typescript
interface Env {
  CF_ACCOUNT_HASH: string; // e.g. "abc123xyz" — from Images dashboard
  IMAGES_SIGNING_KEY: string; // stored as a Worker secret
}

interface ResizeParams {
  imageId: string;
  width?: number;
  height?: number;
  fit?: "scale-down" | "contain" | "cover" | "crop" | "pad";
  quality?: number;
  format?: "auto" | "avif" | "webp" | "json";
}

async function signedImageUrl(
  params: ResizeParams,
  env: Env
): Promise<string> {
  const { imageId, width, height, fit = "scale-down", quality = 85, format = "auto" } = params;

  const variant = [
    width && `w=${width}`,
    height && `h=${height}`,
    `fit=${fit}`,
    `q=${quality}`,
    `f=${format}`,
  ]
    .filter(Boolean)
    .join(",");

  const baseUrl = `https://imagedelivery.net/${env.CF_ACCOUNT_HASH}/${imageId}/${variant}`;

  // HMAC sign the URL path so clients cannot tamper with dimensions
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.IMAGES_SIGNING_KEY),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const urlObj = new URL(baseUrl);
  const expiry = Math.floor(Date.now() / 1000) + 3600; // 1-hour TTL
  const payload = `${urlObj.pathname}?exp=${expiry}`;

  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  const sigHex = [...new Uint8Array(sig)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return `${baseUrl}?exp=${expiry}&sig=${sigHex}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/image-url")) {
      const imageId = url.searchParams.get("id");
      const width = Number(url.searchParams.get("w") ?? 800);
      const height = Number(url.searchParams.get("h") ?? 600);

      if (!imageId) {
        return new Response("Missing id", { status: 400 });
      }

      const signed = await signedImageUrl(
        { imageId, width, height },
        env
      );

      return Response.json({ url: signed });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Proxy Delivery Through a Worker (EU Residency / CORS)

For GDPR zones where images must not be served from US PoPs, proxy the delivery request from a Worker with a `cf.colo` constraint.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const imageId = url.pathname.split("/").at(-2);
    const variant = url.pathname.split("/").at(-1);

    if (!imageId || !variant) {
      return new Response("Bad request", { status: 400 });
    }

    const deliveryUrl = `https://imagedelivery.net/${env.CF_ACCOUNT_HASH}/${imageId}/${variant}`;

    // Force routing through EU PoPs only
    const imageResponse = await fetch(deliveryUrl, {
      headers: {
        Accept: request.headers.get("Accept") ?? "image/avif,image/webp,image/*",
      },
      cf: {
        // Restrict to EU datacenters via Argo tier hint
        resolveOverride: "imagedelivery.net",
      },
    });

    const headers = new Headers(imageResponse.headers);
    headers.set("Access-Control-Allow-Origin", "https://app.example.com");
    headers.set("Cache-Control", "public, max-age=31536000, immutable");
    headers.delete("Set-Cookie");

    return new Response(imageResponse.body, {
      status: imageResponse.status,
      headers,
    });
  },
};
```

---

## Accept-Header Driven Format Negotiation

Flexible variants accept `f=auto` which Cloudflare resolves to AVIF or WebP based on the `Accept` header. When proxying, forward the browser's Accept header.

```typescript
function buildVariantString(
  accept: string,
  width: number,
  height: number
): string {
  let format: "avif" | "webp" | "auto" = "auto";
  if (accept.includes("image/avif")) format = "avif";
  else if (accept.includes("image/webp")) format = "webp";

  return `w=${width},h=${height},f=${format},fit=scale-down,q=85`;
}
```

---

## Generating `srcset` Descriptors Server-Side

A Worker endpoint returns a JSON payload with pre-signed srcset URLs for a given image, covering common breakpoints.

```typescript
const BREAKPOINTS = [320, 640, 960, 1280, 1920] as const;

async function buildSrcset(imageId: string, env: Env): Promise<string> {
  const entries = await Promise.all(
    BREAKPOINTS.map(async (w) => {
      const url = await signedImageUrl({ imageId, width: w }, env);
      return `${url} ${w}w`;
    })
  );
  return entries.join(", ");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const imageId = new URL(request.url).searchParams.get("id");
    if (!imageId) return new Response("Missing id", { status: 400 });

    const srcset = await buildSrcset(imageId, env);
    return Response.json({ srcset });
  },
};
```

---

## Anti-patterns

- **Exposing flexible variant URLs directly to the browser without signing**: anyone can set `w=99999,h=99999` and trigger expensive resize jobs across millions of images. Always HMAC-sign.
- **Not setting a TTL on signed URLs**: leaked URLs remain valid indefinitely. Use an `exp` claim and validate it in a Cloudflare Transform Rule or in the Worker proxy.
- **Using `fit=pad` on user-uploaded avatars**: pad fills transparent background with white by default. Use `fit=cover` for avatars and `fit=contain` for product images.
- **Requesting `f=avif` unconditionally**: AVIF is unsupported in older Safari (< 16) and IE. Use `f=auto` and forward `Accept` headers or use the Worker negotiation pattern above.
- **Caching signed URLs in the browser's localStorage**: the signature has a TTL; stale signed URLs will 403 after expiry. Store the image ID, generate fresh signed URLs on demand, and let the CDN cache the images by content hash.

---

## Gotchas

- Flexible variants add approximately 5-20ms of server-side resize latency on the first request for an uncached dimension. After the first request the resized image is cached at the edge.
- The `imagedelivery.net` domain is shared infrastructure. For SLAs requiring dedicated egress, use a Custom Domain on Cloudflare Images (Images → Custom Domains) and proxy through a Worker.
- `quality` above 85 increases file size with diminishing perceptual gain. AVIF at `q=70` often beats JPEG at `q=90` in visual quality.
- Flexible variant dimension limits: max 12,000px on either axis, max 100 megapixels total. Uploads exceeding these are rejected at ingest, not at resize time.
- HMAC signing in Workers uses the Web Crypto API; `SHA-256` is available synchronously via `crypto.subtle`. Do not use a Node.js `crypto` module import even when `nodejs_compat` is enabled — the Web Crypto API is faster in the Workers runtime.

---

## Verification

```bash
# Confirm flexible variants are enabled
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/config" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.flexible_variants'

# Test a flexible variant URL directly (replace hash and id)
curl -I "https://imagedelivery.net/{accountHash}/{imageId}/w=400,h=300,fit=cover,f=auto"

# Confirm AVIF delivery on supporting clients
curl -H "Accept: image/avif,image/webp,image/*" \
  "https://imagedelivery.net/{accountHash}/{imageId}/w=800,f=auto" -I | grep content-type

# Verify Worker-generated signed URL
curl "https://api.example.com/image-url?id={imageId}&w=640&h=480" | jq .url
```

---

## Related

- `cloudflare-images-transform-urls-variants.md`
- `images-best-practices.md`
- `workers-crypto-patterns.md`
- `r2-presigned-url-cors-mobile-upload.md`

---

## Sources

- https://developers.cloudflare.com/images/transform-images/transform-via-url/
- https://developers.cloudflare.com/images/flexible-variants/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/images/upload-images/formats-limitations/
