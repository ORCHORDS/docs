# Cloudflare Images Transformations from the Frontend

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You serve user-uploaded images via Cloudflare Images and need the frontend to request the right
size, format, and quality for every context — product thumbnails, avatars, hero banners — without
pre-generating every variant.

## Context
Cloudflare Images is a managed image CDN with on-the-fly transformation via URL parameters (the
`/cdn-cgi/image/` path) or via custom delivery URLs attached to an Image account. Unlike
Cloudflare Image Resizing (which transforms arbitrary origins), Cloudflare Images stores files
in Cloudflare's own object store, making uploads, access control, and variant management a
first-class API. A Pages Function or Worker generates signed variant URLs server-side; the
browser receives only the final CDN URL and never has credentials to the Images API.

---

## Architecture

```
Browser
  └── requests page from Cloudflare Pages
        └── Page HTML contains <img src="https://imagedelivery.net/ACCOUNT_HASH/IMAGE_ID/thumbnail">
              └── Cloudflare Images CDN serves pre-configured variant (thumbnail, public, etc.)

OR (flexible variants):
Browser
  └── requests /api/image-url?id=IMAGE_ID&w=400&h=300 from Pages Function
        └── Pages Function returns { url: "https://imagedelivery.net/…/w=400,h=300,fit=cover" }
              └── Browser sets img.src to that URL
```

Named variants are defined once in the Cloudflare Dashboard or via the Images API. Flexible
variants (if enabled on the account) allow arbitrary `w`, `h`, `fit`, `quality`, `format`
parameters directly in the URL.

---

## Upload via Worker (Server-Side)

```typescript
// workers/image-upload/src/index.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_IMAGES_TOKEN: string;   // Images API token stored as a Secret
  IMAGES_KV: KVNamespace;    // Maps internal resource IDs → Cloudflare image IDs
}

interface CloudflareImageUploadResponse {
  result: {
    id: string;
    filename: string;
    uploaded: string;
    variants: string[];
  };
  success: boolean;
  errors: { code: number; message: string }[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    if (url.pathname !== "/upload") {
      return new Response("Not Found", { status: 404 });
    }

    // Expect multipart/form-data with a "file" field
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    if (!file) {
      return Response.json({ error: "No file provided" }, { status: 400 });
    }

    // Validate type server-side
    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type)) {
      return Response.json({ error: "Unsupported image type" }, { status: 415 });
    }

    // Forward to Cloudflare Images API
    const uploadForm = new FormData();
    uploadForm.append("file", file, file.name);
    // Optional: tag the image with metadata
    uploadForm.append("metadata", JSON.stringify({ uploadedBy: "orchords" }));

    const cfRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/images/v1`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_IMAGES_TOKEN}` },
        body: uploadForm,
      }
    );

    const cfJson = await cfRes.json() as CloudflareImageUploadResponse;
    if (!cfJson.success) {
      return Response.json({ error: cfJson.errors[0]?.message ?? "Upload failed" }, { status: 500 });
    }

    const imageId = cfJson.result.id;

    // Store the mapping for later lookup
    const resourceId = crypto.randomUUID();
    await env.IMAGES_KV.put(`img:${resourceId}`, imageId, { expirationTtl: 60 * 60 * 24 * 365 });

    return Response.json({
      id: resourceId,
      imageId,
      variants: cfJson.result.variants,
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Flexible Variant URL Builder (Client-Side)

Named variants (thumbnail, public, avatar, etc.) should be preferred. When flexible variants are
enabled, build URLs client-side with a typed helper:

```typescript
// src/lib/cfImages.ts

const DELIVERY_BASE = "https://imagedelivery.net";
const ACCOUNT_HASH = "your_account_hash_here"; // public, not secret

type ImageFit = "scale-down" | "contain" | "cover" | "crop" | "pad";
type ImageFormat = "auto" | "webp" | "avif" | "json";
type ImageGravity = "auto" | "left" | "right" | "top" | "bottom" | "face";

interface ImageTransformOptions {
  width?: number;
  height?: number;
  fit?: ImageFit;
  quality?: number;       // 1–100
  format?: ImageFormat;
  gravity?: ImageGravity;
  dpr?: number;           // device pixel ratio 1–3
  blur?: number;          // 1–250
  sharpen?: number;       // 0–10
  brightness?: number;    // -1 to 1
  background?: string;    // hex color for pad fit
}

/**
 * Build a Cloudflare Images flexible variant URL.
 * Requires "Flexible variants" to be enabled in the Images dashboard.
 */
export function cfImageUrl(
  imageId: string,
  options: ImageTransformOptions = {}
): string {
  const params: string[] = [];

  if (options.width)      params.push(`w=${options.width}`);
  if (options.height)     params.push(`h=${options.height}`);
  if (options.fit)        params.push(`fit=${options.fit}`);
  if (options.quality)    params.push(`q=${options.quality}`);
  if (options.format)     params.push(`f=${options.format}`);
  if (options.gravity)    params.push(`g=${options.gravity}`);
  if (options.dpr)        params.push(`dpr=${options.dpr}`);
  if (options.blur)       params.push(`blur=${options.blur}`);
  if (options.sharpen)    params.push(`sharpen=${options.sharpen}`);
  if (options.brightness) params.push(`brightness=${options.brightness}`);
  if (options.background) params.push(`background=${options.background}`);

  const variant = params.length > 0 ? params.join(",") : "public";
  return `${DELIVERY_BASE}/${ACCOUNT_HASH}/${imageId}/${variant}`;
}

/** Named variant — use when flexible variants are not enabled */
export function cfImageVariant(imageId: string, variantName: string): string {
  return `${DELIVERY_BASE}/${ACCOUNT_HASH}/${imageId}/${variantName}`;
}
```

---

## React Component: Responsive Cloudflare Image

```tsx
// src/components/CfImage.tsx
import { cfImageUrl } from "../lib/cfImages";

interface CfImageProps {
  imageId: string;
  alt: string;
  widths?: number[];       // srcset breakpoints
  sizes?: string;
  className?: string;
  fit?: "cover" | "contain" | "scale-down";
  quality?: number;
  priority?: boolean;      // true = eager loading for LCP images
}

export function CfImage({
  imageId,
  alt,
  widths = [320, 640, 960, 1280],
  sizes = "100vw",
  className,
  fit = "cover",
  quality = 85,
  priority = false,
}: CfImageProps) {
  const srcSet = widths
    .map((w) => {
      const url = cfImageUrl(imageId, { width: w, fit, quality, format: "auto" });
      return `${url} ${w}w`;
    })
    .join(", ");

  const defaultSrc = cfImageUrl(imageId, {
    width: widths[widths.length - 1],
    fit,
    quality,
    format: "auto",
  });

  return (
    <img
      src={defaultSrc}
      srcSet={srcSet}
      sizes={sizes}
      alt={alt}
      className={className}
      loading={priority ? "eager" : "lazy"}
      decoding={priority ? "sync" : "async"}
      fetchPriority={priority ? "high" : "auto"}
    />
  );
}
```

```tsx
// Usage
<CfImage
  imageId="abc123-def456-ghi789"
  alt="Product hero"
  widths={[400, 800, 1200]}
  sizes="(max-width: 768px) 100vw, 50vw"
  fit="cover"
  quality={90}
  priority   // LCP image — load eagerly
/>
```

---

## Anti-patterns
- Embedding the Images API token in client-side code — it grants full upload/delete access; keep it in Worker secrets
- Building flexible variant URLs with arbitrary user input — validate width/height server-side or cap them in the URL builder
- Using flexible variants for every image when named variants suffice — named variants are pre-cached more aggressively
- Serving original (uncompressed) variants to production — always specify `quality` and `format=auto` to enable AVIF/WebP negotiation
- Skipping `width` and `height` attributes on the `<img>` — causes CLS even when the image loads from Cloudflare's fast CDN

## Gotchas
- Flexible variants must be explicitly enabled in the Cloudflare Images dashboard; they are off by default
- `format=auto` requires the request's `Accept` header to include `image/avif` or `image/webp`; verify browsers send it
- Cloudflare Images and Cloudflare Image Resizing are separate products — Image Resizing is a zone-level feature, Images is an account-level storage product
- The account hash in the delivery URL (`imagedelivery.net/HASH/...`) is public and safe to embed in client code
- Images uploaded without `requireSignedURLs = true` are publicly accessible by default; enable signed URLs for private content

## Verification
```bash
# List named variants for your Images account
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/images/v1/variants" \
  -H "Authorization: Bearer $CF_IMAGES_TOKEN" | jq '.result.variants | keys'

# Upload a test image
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/images/v1" \
  -H "Authorization: Bearer $CF_IMAGES_TOKEN" \
  -F "file=@/tmp/test.jpg" | jq '.result.id'

# Check flexible variant URL returns 200 + correct Content-Type
curl -I "https://imagedelivery.net/$ACCOUNT_HASH/$IMAGE_ID/w=400,h=300,fit=cover,f=auto" \
  -H "Accept: image/avif,image/webp,*/*"
# Expect: HTTP/2 200, Content-Type: image/avif (or image/webp)

# Verify KV mapping
wrangler kv:key get --namespace-id=$IMAGES_KV_ID "img:$RESOURCE_ID"
```

## Related
- `cloudflare-r2-presigned-upload-frontend.md`
- `wasm-cloudflare-workers-image-transform.md`
- `cloudflare-pages-og-image-generation.md`
- `image-format-selection-webp-avif.md`
- `html-srcset-responsive-images.md`

## Sources
- https://developers.cloudflare.com/images/
- https://developers.cloudflare.com/images/transform-images/
- https://developers.cloudflare.com/images/upload-images/
- https://developers.cloudflare.com/images/flexible-variants/
- https://web.dev/articles/responsive-images
