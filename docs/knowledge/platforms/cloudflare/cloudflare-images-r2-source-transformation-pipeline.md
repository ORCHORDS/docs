# Cloudflare Images R2 Source Transformation Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You store original high-resolution images in R2 and want to serve transformed variants
(resize, crop, format conversion, quality tuning) through Cloudflare Images without
duplicating files or maintaining a separate origin server. Image resizing happens at
the edge on every cache miss; transformed variants are cached and never hit R2 again.

Separately, you want Workers to generate dynamic signed transformation URLs so clients
cannot request arbitrary crops that drain your Images quota.

---

## Context

Cloudflare Images supports **R2 buckets as a source** via the "Custom origin" feature
(Images → Source → R2). When configured, the Images service fetches the original from
R2 on first request for a new transformation, caches the result, and serves subsequent
requests from cache.

Architecture for example project:

```
Client  →  Cloudflare CDN  →  Cloudflare Images  →  R2 (private bucket)
                ↑                    ↑
         cache HIT (served)    cache MISS (fetch + transform + cache)
```

Key numbers (2026):
- R2 Class A ops (Images fetching originals): ~$4.50/million
- Images transformations: ~$0.50/1 000 unique transformations
- Transformed variants are cached globally; cache hit does not bill a transformation
- Maximum source image resolution: 100 MP
- Maximum output dimension: 12 288 px on any side

---

## Configuring R2 as Images Source

R2 bucket must be in the same Cloudflare account. Configuration is per-zone:

```bash
# Enable Images R2 source via Cloudflare API
curl -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/cloudflare_images" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": {
      "r2_bucket": "example project-media-originals",
      "serve_path_prefix": "/img/"
    }
  }'
```

Once set, a request to:

```
https://example.com/cdn-cgi/image/width=800,format=webp/img/users/avatar-42.png
```

causes Images to:
1. Strip `/cdn-cgi/image/<options>` prefix
2. Fetch `img/users/avatar-42.png` from the R2 bucket `example project-media-originals`
3. Apply `width=800,format=webp` transformation
4. Cache the result with the transformation params as part of the cache key

---

## Worker: Signing Transformation URLs

Clients must not be able to request arbitrary transformation parameters. Sign the
allowed set with HMAC-SHA256 and validate in a Worker sitting in front of the
`/cdn-cgi/image/` path.

```typescript
// src/workers/image-signer.ts
const ALLOWED_WIDTHS = new Set([320, 640, 800, 1200, 1920]);
const ALLOWED_FORMATS = new Set(['webp', 'avif', 'jpeg']);

export interface ImageSignParams {
  width: number;
  format: string;
  r2Key: string;       // e.g. "users/avatar-42.png"
  expiresAt: number;   // Unix seconds
}

export async function signImageUrl(
  params: ImageSignParams,
  secret: string,
): Promise<string> {
  const message = `${params.width}:${params.format}:${params.r2Key}:${params.expiresAt}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');

  const opts = `width=${params.width},format=${params.format}`;
  return `/cdn-cgi/image/${opts}/img/${params.r2Key}?sig=${b64}&exp=${params.expiresAt}`;
}

export async function verifyImageRequest(
  req: Request,
  secret: string,
): Promise<boolean> {
  const url = new URL(req.url);
  const sig = url.searchParams.get('sig');
  const expStr = url.searchParams.get('exp');
  if (!sig || !expStr) return false;

  const exp = parseInt(expStr, 10);
  if (isNaN(exp) || Date.now() / 1000 > exp) return false;

  // Extract params from URL path: /cdn-cgi/image/<opts>/img/<r2key>
  const match = url.pathname.match(/^\/cdn-cgi\/image\/([^/]+)\/img\/(.+)$/);
  if (!match) return false;

  const optStr = match[1]; // e.g. "width=800,format=webp"
  const r2Key = match[2];

  const widthMatch = optStr.match(/width=(\d+)/);
  const formatMatch = optStr.match(/format=(\w+)/);
  if (!widthMatch || !formatMatch) return false;

  const width = parseInt(widthMatch[1], 10);
  const format = formatMatch[1];

  // Enforce allow-lists before HMAC check
  if (!ALLOWED_WIDTHS.has(width) || !ALLOWED_FORMATS.has(format)) return false;

  const message = `${width}:${format}:${r2Key}:${exp}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  const sigBytes = Uint8Array.from(
    atob(sig.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0),
  );
  return crypto.subtle.verify('HMAC', key, sigBytes, new TextEncoder().encode(message));
}
```

---

## Worker: Enforcing Signed URL at the Edge

```typescript
// src/workers/image-gateway.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Only intercept /cdn-cgi/image/ paths
    if (!url.pathname.startsWith('/cdn-cgi/image/')) {
      return fetch(req);
    }

    const valid = await verifyImageRequest(req, env.IMAGE_SIGNING_SECRET);
    if (!valid) {
      return new Response('Forbidden: invalid or expired image signature', {
        status: 403,
        headers: { 'Cache-Control': 'no-store' },
      });
    }

    // Strip signature params before forwarding to Cloudflare Images
    url.searchParams.delete('sig');
    url.searchParams.delete('exp');

    const cleanReq = new Request(url.toString(), {
      method: req.method,
      headers: req.headers,
    });

    return fetch(cleanReq);
  },
};
```

---

## Worker: Generating Image URLs for API Responses

```typescript
// src/lib/image-urls.ts
import { signImageUrl } from './image-signer';

export async function avatarUrl(
  userId: string,
  r2Key: string,
  env: Env,
): Promise<Record<string, string>> {
  const expiresAt = Math.floor(Date.now() / 1000) + 3600; // 1 hour

  const [small, medium, large] = await Promise.all([
    signImageUrl({ width: 320, format: 'webp', r2Key, expiresAt }, env.IMAGE_SIGNING_SECRET),
    signImageUrl({ width: 640, format: 'webp', r2Key, expiresAt }, env.IMAGE_SIGNING_SECRET),
    signImageUrl({ width: 1200, format: 'webp', r2Key, expiresAt }, env.IMAGE_SIGNING_SECRET),
  ]);

  return { small, medium, large };
}
```

---

## Uploading Originals to R2

```typescript
// src/workers/upload-handler.ts
export async function handleAvatarUpload(req: Request, env: Env): Promise<Response> {
  const formData = await req.formData();
  const file = formData.get('file') as File | null;
  if (!file) return new Response('Missing file', { status: 400 });

  const userId = req.headers.get('X-User-Id');
  if (!userId) return new Response('Unauthenticated', { status: 401 });

  // Store original at a stable, namespaced key
  const r2Key = `users/${userId}/avatar-original.${file.type.split('/')[1] ?? 'jpg'}`;

  await env.MEDIA_BUCKET.put(r2Key, file.stream(), {
    httpMetadata: {
      contentType: file.type,
      cacheControl: 'private, max-age=0',
    },
    customMetadata: { uploadedBy: userId, uploadedAt: new Date().toISOString() },
  });

  // Purge any cached transformed variants for this key
  await purgeImageVariants(r2Key, env);

  const urls = await avatarUrl(userId, r2Key, env);
  return Response.json({ r2Key, urls });
}

async function purgeImageVariants(r2Key: string, env: Env): Promise<void> {
  // Purge cached image variants via Cache API (zone-level)
  const widths = [320, 640, 800, 1200, 1920];
  const formats = ['webp', 'avif', 'jpeg'];
  const cache = caches.default;

  await Promise.all(
    widths.flatMap(w =>
      formats.map(f =>
        cache.delete(
          new Request(
            `https://${env.HOSTNAME}/cdn-cgi/image/width=${w},format=${f}/img/${r2Key}`,
          ),
        ),
      ),
    ),
  );
}
```

---

## Anti-patterns

- **Pointing the R2 source at a public bucket** — Images fetches internally; the bucket
  does not need to be public. Keeping it private prevents hotlinking of originals.
- **Allowing clients to construct transformation URLs directly** — without signing, a
  client can request every combination of width/quality, exhausting your Images quota.
- **Storing processed thumbnails in R2 manually** — Cloudflare Images caches transformed
  variants globally. Storing thumbs in R2 yourself duplicates work and costs more.
- **Not purging cached variants after upload** — if a user updates their avatar, old
  transformed variants stay cached until TTL expires unless explicitly purged.
- **Using `fit=cover` with uncontrolled aspect ratios** — always pass both `width` and
  `height` or use `fit=scale-down` to avoid unexpected crops.

---

## Gotchas

- The R2 source key path must exactly match the suffix after `/img/` in the CDN URL —
  URL encoding differences between `%20` and `+` cause 404 from the Images origin fetch.
- Images does not currently support R2 object versioning — it fetches the latest version
  of the key; use key namespacing (e.g. include a hash) to bust caches explicitly.
- `Cache-Control: private` on the R2 object's `httpMetadata` does NOT prevent Images
  from caching the transformed output — Images ignores the source object's cache headers.
- The transformation result TTL defaults to the zone's edge cache TTL, not the R2
  object TTL. Set explicit Cache Rules on `/cdn-cgi/image/*` paths.
- `format=auto` is not available when the URL is constructed manually; use
  `format=webp` or `format=avif` explicitly and serve via `<picture>` tags.

---

## Verification

```bash
# Confirm Images is serving from R2 (check CF-Cache-Status and cf-resized headers)
curl -sI "https://example.com/cdn-cgi/image/width=640,format=webp/img/users/avatar-42.png" \
  | grep -E "CF-Cache-Status|cf-resized|content-type"

# Expected:
# CF-Cache-Status: MISS  (first request)
# cf-resized: internal=ok/webp q=85
# content-type: image/webp

# Second request should show HIT:
# CF-Cache-Status: HIT
```

```typescript
// Unit test for signer
import { signImageUrl, verifyImageRequest } from './image-signer';
import { describe, it, expect } from 'vitest';

describe('image signing', () => {
  it('verifies a freshly signed URL', async () => {
    const params = {
      width: 640, format: 'webp',
      r2Key: 'users/42/avatar.jpg',
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
    };
    const path = await signImageUrl(params, 'test-secret');
    const req = new Request(`https://example.com${path}`);
    expect(await verifyImageRequest(req, 'test-secret')).toBe(true);
  });

  it('rejects an expired URL', async () => {
    const params = {
      width: 640, format: 'webp',
      r2Key: 'users/42/avatar.jpg',
      expiresAt: Math.floor(Date.now() / 1000) - 1, // past
    };
    const path = await signImageUrl(params, 'test-secret');
    const req = new Request(`https://example.com${path}`);
    expect(await verifyImageRequest(req, 'test-secret')).toBe(false);
  });
});
```

---

## Related

- `cloudflare-images-flexible-variants-workers.md`
- `cloudflare-images-transform-urls-variants.md`
- `r2-best-practices.md`
- `r2-signed-urls.md`
- `r2-presigned-url-cors-mobile-upload.md`
- `images-best-practices.md`

---

## Sources

- https://developers.cloudflare.com/images/upload-images/use-r2-as-source/
- https://developers.cloudflare.com/images/transform-images/
- https://developers.cloudflare.com/images/transform-images/transform-via-url/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tag/
