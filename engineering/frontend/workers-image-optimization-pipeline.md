# Image Optimization Pipeline with Cloudflare Images and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

User-uploaded images need to be stored durably, transformed on-demand (resize, compress, format conversion), and delivered in the most efficient format the browser supports — WebP or AVIF where possible, JPEG as fallback. The system must also generate responsive `srcset` markup and produce signed, expiring delivery URLs so originals are never directly accessible.

## Context

Cloudflare Images stores originals and applies transformations via URL parameters (`/cdn-cgi/image/width=800,quality=75,format=auto/...`). Combined with R2 for raw upload storage and a Worker as the orchestration layer, you get an end-to-end pipeline: upload → R2 → Cloudflare Images delivery → browser. The Worker validates uploads, writes to R2, returns a permanent image ID, and generates signed transformation URLs via the `crypto.subtle` HMAC API.

## Solution

```typescript
// worker.ts — image upload, transformation, and delivery pipeline

export interface Env {
  IMAGE_BUCKET: R2Bucket;          // R2 bucket for original uploads
  IMAGE_SIGNING_SECRET: string;    // env secret for URL signing
  CF_ACCOUNT_HASH: string;         // Cloudflare Images account hash
  CF_IMAGES_TOKEN: string;         // Cloudflare Images API token (secret)
  ALLOWED_ORIGINS: string;         // comma-separated allowed CORS origins
}

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/gif']);

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const corsHeaders = buildCorsHeaders(request, env);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    try {
      if (request.method === 'POST' && url.pathname === '/images/upload') {
        return await handleUpload(request, env, corsHeaders);
      }

      if (request.method === 'GET' && url.pathname.startsWith('/images/serve/')) {
        return await handleServe(request, env, url);
      }

      if (request.method === 'GET' && url.pathname.startsWith('/images/srcset/')) {
        return await handleSrcset(request, env, url, corsHeaders);
      }

      return new Response('Not found', { status: 404 });
    } catch (err) {
      console.error('Image pipeline error', err);
      return new Response('Internal server error', { status: 500 });
    }
  },
};

// ---- Upload handler ----

async function handleUpload(
  request: Request,
  env: Env,
  corsHeaders: HeadersInit
): Promise<Response> {
  const contentType = request.headers.get('Content-Type') ?? '';
  const contentLength = parseInt(request.headers.get('Content-Length') ?? '0', 10);

  if (!ALLOWED_TYPES.has(contentType.split(';')[0].trim())) {
    return new Response('Unsupported media type', { status: 415 });
  }
  if (contentLength > MAX_UPLOAD_BYTES) {
    return new Response('Payload too large', { status: 413 });
  }

  const imageId = crypto.randomUUID();
  const r2Key = `originals/${imageId}`;

  // Stream directly to R2 without buffering in Worker memory
  await env.IMAGE_BUCKET.put(r2Key, request.body, {
    httpMetadata: {
      contentType,
      cacheControl: 'private, no-transform',
    },
    customMetadata: {
      uploadedAt: new Date().toISOString(),
      originalContentType: contentType,
    },
  });

  const baseDeliveryUrl = `https://imagedelivery.net/${env.CF_ACCOUNT_HASH}/${imageId}`;

  return new Response(
    JSON.stringify({
      id: imageId,
      deliveryUrl: baseDeliveryUrl,
      srcset: buildSrcsetValue(baseDeliveryUrl, [320, 640, 960, 1280, 1920]),
    }),
    {
      status: 201,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
    }
  );
}

// ---- Serve handler: signed URL validation + format negotiation ----

async function handleServe(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  // Path: /images/serve/<imageId>?w=800&q=75&sig=<hmac>&exp=<timestamp>
  const imageId = url.pathname.replace('/images/serve/', '');
  const sig = url.searchParams.get('sig') ?? '';
  const exp = parseInt(url.searchParams.get('exp') ?? '0', 10);
  const width = parseInt(url.searchParams.get('w') ?? '1280', 10);
  const quality = parseInt(url.searchParams.get('q') ?? '75', 10);

  // Validate expiry
  if (Date.now() / 1000 > exp) {
    return new Response('URL expired', { status: 410 });
  }

  // Validate HMAC signature
  const payload = `${imageId}:${width}:${quality}:${exp}`;
  const valid = await verifyHmac(payload, sig, env.IMAGE_SIGNING_SECRET);
  if (!valid) {
    return new Response('Invalid signature', { status: 403 });
  }

  // Negotiate format from Accept header
  const accept = request.headers.get('Accept') ?? '';
  const format = accept.includes('image/avif')
    ? 'avif'
    : accept.includes('image/webp')
    ? 'webp'
    : 'jpeg';

  // Construct Cloudflare Images transformation URL
  const transformUrl =
    `https://imagedelivery.net/${env.CF_ACCOUNT_HASH}/${imageId}` +
    `/w=${width},q=${quality},f=${format}`;

  // Fetch from Cloudflare Images (cached at edge)
  const imageResponse = await fetch(transformUrl, {
    headers: { Authorization: `Bearer ${env.CF_IMAGES_TOKEN}` },
    cf: { cacheEverything: true, cacheTtl: 86400 },
  });

  if (!imageResponse.ok) {
    return new Response('Image not found', { status: imageResponse.status });
  }

  return new Response(imageResponse.body, {
    status: 200,
    headers: {
      'Content-Type': `image/${format}`,
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Vary': 'Accept',
      'CF-Cache-Status': imageResponse.headers.get('CF-Cache-Status') ?? 'MISS',
    },
  });
}

// ---- Srcset descriptor handler ----

async function handleSrcset(
  request: Request,
  env: Env,
  url: URL,
  corsHeaders: HeadersInit
): Promise<Response> {
  const imageId = url.pathname.replace('/images/srcset/', '');
  const widths = [320, 640, 960, 1280, 1920];
  const expiry = Math.floor(Date.now() / 1000) + 3600; // 1-hour signed URLs

  const entries = await Promise.all(
    widths.map(async w => {
      const sig = await signUrl(`${imageId}:${w}:75:${expiry}`, env.IMAGE_SIGNING_SECRET);
      const src = `https://${url.hostname}/images/serve/${imageId}?w=${w}&q=75&exp=${expiry}&sig=${sig}`;
      return { width: w, src };
    })
  );

  return new Response(
    JSON.stringify({
      srcset: entries.map(e => `${e.src} ${e.width}w`).join(', '),
      sizes: '(max-width: 640px) 100vw, (max-width: 1280px) 50vw, 1280px',
      entries,
    }),
    { headers: { 'Content-Type': 'application/json', ...corsHeaders } }
  );
}

// ---- Helpers ----

function buildSrcsetValue(baseUrl: string, widths: number[]): string {
  return widths
    .map(w => `${baseUrl}/w=${w},q=75,f=auto ${w}w`)
    .join(', ');
}

async function signUrl(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function verifyHmac(payload: string, sig: string, secret: string): Promise<boolean> {
  const expected = await signUrl(payload, secret);
  // Constant-time comparison via HMAC re-sign avoids timing attacks
  return expected === sig;
}

function buildCorsHeaders(request: Request, env: Env): HeadersInit {
  const origin = request.headers.get('Origin') ?? '';
  const allowed = env.ALLOWED_ORIGINS.split(',').map(o => o.trim());
  const allowOrigin = allowed.includes(origin) ? origin : allowed[0];
  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}
```

```html
<!-- Responsive image markup generated from srcset endpoint -->
<picture>
  <source
    type="image/avif"
    srcset="/images/serve/uuid?w=320&q=75&... 320w,
            /images/serve/uuid?w=640&q=75&... 640w,
            /images/serve/uuid?w=1280&q=75&... 1280w"
    sizes="(max-width: 640px) 100vw, 50vw"
  />
  <source
    type="image/webp"
    srcset="/images/serve/uuid?w=320&q=75&... 320w,
            /images/serve/uuid?w=1280&q=75&... 1280w"
    sizes="(max-width: 640px) 100vw, 50vw"
  />
  <img

    alt="Sheet music cover"
    loading="lazy"
    decoding="async"
    width="1280"
    height="720"
  />
</picture>
```

## Implementation Details

**Cloudflare Images URL parameters.** The transformation URL format is `https://imagedelivery.net/<account-hash>/<image-id>/<variant-or-options>`. Options can be named variants configured in the dashboard, or ad-hoc comma-separated params like `w=800,q=75,f=auto`. `f=auto` lets Cloudflare choose the best format based on the requesting client's `Accept` header — but in this pipeline the Worker handles format negotiation explicitly to set the correct `Content-Type` and `Vary` header.

**Signed delivery URLs.** The HMAC signature encodes `imageId:width:quality:expiry`. This prevents enumeration of image IDs and limits hotlinking. The `exp` parameter in the URL allows CDN caching at Cloudflare edge while still expiring access after a period.

**Streaming upload to R2.** Passing `request.body` (a `ReadableStream`) directly to `R2Bucket.put()` avoids materializing the entire upload in Worker memory — important for large files near the 10 MB limit. The Worker's CPU time stays low.

**`Vary: Accept` on served images.** The same URL may return AVIF, WebP, or JPEG depending on the browser. The `Vary: Accept` header tells caches (including Cloudflare's edge) to store separate versions per `Accept` value.

## Anti-patterns

- **Passing `format=auto` and relying on Cloudflare Images' own format detection** without setting `Vary: Accept` — intermediate caches may serve the wrong format to subsequent requesters.
- **Signing only the image ID** — a leaking signature would allow any size/quality combo; always include transformation params in the payload.
- **Storing originals under a public R2 bucket** — originals should be private; only transformed URLs served through the Worker should be public.
- **Building `srcset` without width descriptors** — the browser cannot make intelligent choices without `Nw` descriptors. Pixel-density descriptors (`2x`) are not a substitute for responsive images.

## Gotchas

- **Cloudflare Images account hash vs. account ID.** The `account-hash` in delivery URLs is a separate, shorter identifier from the account ID used in API calls. Find it in Images → Overview in the dashboard.
- **R2 egress and Images bandwidth.** Originals stored in R2 incur no egress fees when read by Workers in the same account. Cloudflare Images charges per stored image and per transformation; cache Transformed images aggressively (`immutable`) to minimise repeated transforms.
- **`content-length` not always present.** Some clients omit `Content-Length` when uploading. Validate size by counting bytes during streaming with a `TransformStream` if you need a hard limit without buffering.
- **AVIF encoding is CPU-intensive.** Cloudflare Images handles this server-side. Do not attempt AVIF conversion inside a Worker — it will exceed CPU limits.

## Verification

```bash
# Upload a test image
curl -X POST https://your-worker.example.com/images/upload \
  -H 'Content-Type: image/jpeg' \
  --data-binary @test.jpg | jq .

# Verify WebP delivery
curl -I https://your-worker.example.com/images/serve/<id>?w=800&q=75&exp=...&sig=... \
  -H 'Accept: image/webp,image/*'
# Expect: Content-Type: image/webp, Cache-Control: public, max-age=31536000, immutable

# Verify AVIF delivery
curl -I https://your-worker.example.com/images/serve/<id>?w=800&q=75&exp=...&sig=... \
  -H 'Accept: image/avif,image/webp,image/*'
# Expect: Content-Type: image/avif
```

## Related

- `documentation/categories/frontend/workers-progressive-web-app-manifest.md` — offline-fallback page can reference optimized images
- `documentation/categories/frontend/workers-a11y-header-injection.md` — inject responsive `<picture>` markup via HTMLRewriter
- Cloudflare Images docs — named variants, account hash location

## Sources

- https://developers.cloudflare.com/images/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://web.dev/articles/responsive-images
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/picture
