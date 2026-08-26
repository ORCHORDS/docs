# Responsive Image Optimisation Pipeline for Mobile via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Mobile devices on slow connections receive the same large desktop images, hurting LCP scores and burning data budgets. You need an edge pipeline that automatically resizes, converts to modern formats (WebP/AVIF), and caches derivatives — without managing an image server.

## Context

Cloudflare Workers can invoke Cloudflare Image Resizing (a Cloudflare Pro/Business feature) by making a subrequest to the same zone with the `cf.image` option set. The Worker acts as a smart proxy:

1. Reads `Accept` and `Save-Data` headers to determine optimal format and quality.
2. Detects approximate device class from the `User-Agent` and `Viewport-Width` hint.
3. Calls Image Resizing to produce the derivative.
4. Stores the derivative in R2 for future cache hits.
5. Returns appropriate `Vary` and `Cache-Control` headers.

## Solution

### 1. Wrangler Bindings

```toml
[[r2_buckets]]
binding = "IMAGE_CACHE"
bucket_name = "orchords-image-derivatives"

[vars]
ORIGIN_HOST = "assets.example.com"  # where originals live

# Ensure Image Resizing is enabled on the zone (Cloudflare dashboard → Speed → Optimization)
```

### 2. TypeScript Types

```typescript
// src/types.ts
export interface Env {
  IMAGE_CACHE: R2Bucket;
  ORIGIN_HOST: string;
}

export interface ImageRequest {
  src:     string;   // path to original, e.g. /uploads/hero.jpg
  width?:  number;
  height?: number;
  quality?: number;
  format?: 'webp' | 'avif' | 'jpeg' | 'png';
}

export interface DeviceProfile {
  width:   number;  // target render width in CSS pixels
  dpr:     number;  // device pixel ratio
  quality: number;  // 1-100
  format:  'avif' | 'webp' | 'jpeg';
  saveData: boolean;
}
```

### 3. Accept Header Format Negotiation

```typescript
// src/format.ts
export function negotiateFormat(
  acceptHeader: string | null,
  saveData: boolean,
): 'avif' | 'webp' | 'jpeg' {
  if (!acceptHeader) return 'jpeg';

  // AVIF preferred where supported; fallback to WebP, then JPEG
  if (acceptHeader.includes('image/avif')) {
    // Save-Data: AVIF quality can compensate; still prefer it
    return 'avif';
  }
  if (acceptHeader.includes('image/webp')) return 'webp';
  return 'jpeg';
}
```

### 4. Device Detection from Headers

```typescript
// src/device.ts
export function detectDeviceProfile(
  request: Request,
  saveData: boolean,
): DeviceProfile {
  // Client Hints (Chrome 84+, Edge 84+)
  const viewportWidth = parseInt(request.headers.get('Sec-CH-Viewport-Width') ?? '0', 10);
  const dpr           = parseFloat(request.headers.get('Sec-CH-DPR') ?? '1');
  const rtt           = parseInt(request.headers.get('Sec-CH-RTT') ?? '0', 10);

  // Fallback: UA sniff for rough device class
  const ua       = request.headers.get('User-Agent') ?? '';
  const isMobile = /Mobile|Android|iPhone|iPad/i.test(ua);

  // Determine target render width
  let targetWidth = viewportWidth > 0 ? viewportWidth : (isMobile ? 390 : 1280);
  const effectiveDpr = dpr > 0 ? Math.min(dpr, 3) : 1;
  let physicalWidth  = Math.round(targetWidth * effectiveDpr);

  // Save-Data: halve resolution
  let quality = saveData ? 45 : (rtt > 300 ? 60 : 80);
  if (saveData) physicalWidth = Math.round(physicalWidth / 2);

  const acceptHeader = request.headers.get('Accept') ?? '';
  const format       = negotiateFormat(acceptHeader, saveData);

  return { width: physicalWidth, dpr: effectiveDpr, quality, format, saveData };
}

import { negotiateFormat } from './format';
import type { DeviceProfile } from './types';
```

### 5. R2 Cache Key Generation

```typescript
// src/cache.ts
export function derivativeCacheKey(
  src: string,
  width: number,
  format: string,
  quality: number,
): string {
  // Normalise path
  const clean = src.startsWith('/') ? src.slice(1) : src;
  return `derivatives/${clean}/${width}w_q${quality}.${format}`;
}
```

### 6. Cloudflare Image Resizing Subrequest

```typescript
// src/resize.ts
import type { Env, DeviceProfile } from './types';

export async function resizeViaCloudflare(
  originUrl: string,
  profile: DeviceProfile,
  env: Env,
): Promise<Response> {
  // Cloudflare Image Resizing: pass cf.image options on a fetch subrequest
  // The subrequest must target a URL on the same zone
  const response = await fetch(originUrl, {
    cf: {
      image: {
        width:   profile.width,
        quality: profile.quality,
        format:  profile.format,
        fit:     'scale-down',
        metadata:'none',   // strip EXIF for privacy + size
      } as RequestInitCfPropertiesImage,
    } as RequestInitCfProperties,
  });

  if (!response.ok) {
    throw new Error(`Image resizing failed: ${response.status} ${originUrl}`);
  }

  return response;
}

// Augment types for Cloudflare-specific cf options (not in standard TS lib)
declare interface RequestInitCfPropertiesImage {
  width?:    number;
  height?:   number;
  quality?:  number;
  format?:   'avif' | 'webp' | 'jpeg' | 'png' | 'baseline-jpeg';
  fit?:      'scale-down' | 'contain' | 'cover' | 'crop' | 'pad';
  metadata?: 'keep' | 'copyright' | 'none';
}
declare interface RequestInitCfProperties {
  image?: RequestInitCfPropertiesImage;
  cacheEverything?: boolean;
  cacheTtl?: number;
}
```

### 7. Worker Entry Point with R2 Caching

```typescript
// src/index.ts
import type { Env } from './types';
import { detectDeviceProfile } from './device';
import { derivativeCacheKey } from './cache';
import { resizeViaCloudflare } from './resize';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'GET') {
      return new Response('Method not allowed', { status: 405 });
    }

    const url      = new URL(request.url);
    const src      = url.searchParams.get('src');
    if (!src) return new Response('Missing src', { status: 400 });

    const saveData = request.headers.get('Save-Data') === 'on';
    const profile  = detectDeviceProfile(request, saveData);
    const cacheKey = derivativeCacheKey(src, profile.width, profile.format, profile.quality);

    // 1. Try R2 derivative cache
    const cached = await env.IMAGE_CACHE.get(cacheKey);
    if (cached) {
      const headers = new Headers();
      cached.writeHttpMetadata(headers);
      headers.set('Cache-Control', 'public, max-age=2592000, immutable'); // 30 days
      headers.set('X-Cache', 'HIT');
      return new Response(cached.body, { headers });
    }

    // 2. Fetch from origin via Image Resizing
    const originUrl  = `https://${env.ORIGIN_HOST}${src}`;
    let resized: Response;
    try {
      resized = await resizeViaCloudflare(originUrl, profile, env);
    } catch (err) {
      // Fallback: pass-through original
      console.error('Resize error:', err);
      return fetch(originUrl);
    }

    // 3. Store derivative in R2 (stream body to R2 and clone for response)
    const [bodyForR2, bodyForClient] = resized.body!.tee();
    const contentType = resized.headers.get('Content-Type') ?? `image/${profile.format}`;

    // Store in R2 asynchronously — don't await so the client gets the response ASAP
    const r2Put = env.IMAGE_CACHE.put(cacheKey, bodyForR2, {
      httpMetadata: {
        contentType,
        cacheControl: 'public, max-age=2592000, immutable',
      },
    });

    // 4. Build srcset hint header for HTML-level usage
    const srcsetHint = buildSrcsetHint(src, profile);

    const responseHeaders = new Headers({
      'Content-Type':  contentType,
      'Cache-Control': 'public, max-age=2592000, immutable',
      'Vary':          'Accept, Save-Data, Sec-CH-Viewport-Width, Sec-CH-DPR',
      'X-Cache':       'MISS',
      'X-Srcset-Hint': srcsetHint,
    });

    // Await R2 write in background via waitUntil if ExecutionContext is available
    // (add ctx: ExecutionContext to handler params for production use)
    r2Put.catch(err => console.error('R2 write failed:', err));

    return new Response(bodyForClient, { headers: responseHeaders });
  },
};

function buildSrcsetHint(src: string, profile: DeviceProfile): string {
  const widths = [320, 640, 960, 1280, 1920].filter(w => w <= profile.width * 1.5);
  return widths
    .map(w => `/image?src=${encodeURIComponent(src)}&w=${w} ${w}w`)
    .join(', ');
}
```

### 8. HTML `<img>` Integration

```html
<!-- Use the Worker as an image proxy -->
<img

  srcset="
    /image?src=/uploads/hero.jpg&w=320  320w,
    /image?src=/uploads/hero.jpg&w=640  640w,
    /image?src=/uploads/hero.jpg&w=960  960w,
    /image?src=/uploads/hero.jpg&w=1280 1280w
  "
  sizes="(max-width: 600px) 100vw, 50vw"
  loading="lazy"
  decoding="async"
  width="1280"
  height="720"
  alt="Hero image"
/>
```

## Implementation Details

- **R2 as derivative cache**: R2 zero-egress-fee storage makes it cost-effective to cache hundreds of derivatives per original. The cache key encodes width, quality, and format so variants never collide.
- **`tee()` pattern**: `ReadableStream.tee()` splits the resized body into two branches — one written to R2, one streamed to the client — without buffering the entire image in memory.
- **Client Hints**: Send `Accept-CH: Sec-CH-DPR, Sec-CH-Viewport-Width` in a response header (or a `<meta http-equiv>` tag) on the first page load so browsers include these headers on subsequent requests.
- **Save-Data header**: Browsers in Chrome for Android will set `Save-Data: on` when the user enables Data Saver. Halving physical resolution and dropping quality to 45 reduces payload by ~75%.
- **AVIF quality**: AVIF at quality 55 is perceptually equivalent to JPEG at quality 80 and typically 50% smaller.
- **Immutable cache**: Setting `immutable` on derivative URLs is safe because the cache key encodes the quality and width — any parameter change produces a new key.

## Anti-patterns

- **Do not** use `cache.match` / `cache.put` (Cache API) for derivatives — the CF Cache is shared with HTML pages and subject to cache eviction. R2 provides guaranteed, cost-effective storage.
- **Do not** serve the same image URL for both retina and non-retina without DPR negotiation. The `Vary` header must include `Sec-CH-DPR` when DPR-based sizing is used.
- **Do not** pass unsanitised user-supplied `src` query params to the origin fetch. Validate the path against an allowlist prefix (e.g., `/uploads/`).
- **Do not** await the R2 write on the critical path — use `ExecutionContext.waitUntil(r2Put)` to write after the response is sent.

## Gotchas

- Cloudflare Image Resizing is only available on Pro plans and above. On Workers Free, the `cf.image` option is silently ignored and the original is returned.
- `tee()` on a `Response.body` consumes the original stream. If Image Resizing returns an error, `body` may be `null` — guard with `resized.body!.tee()`.
- AVIF encoding is CPU-intensive; Cloudflare's Image Resizing offloads this to a dedicated pipeline, but the first request for an AVIF derivative is noticeably slower than WebP.
- The `Vary` header must list every header that influences the response. Missing a dimension (e.g., `Save-Data`) causes CDN nodes to serve a high-quality image to low-data users after the first cache population.

## Verification

1. `curl -H 'Accept: image/avif,image/webp' -H 'Sec-CH-Viewport-Width: 390' -H 'Sec-CH-DPR: 3' -I https://your-worker.example.com/image?src=/uploads/hero.jpg`
   — Confirm `Content-Type: image/avif` and `X-Cache: MISS`.
2. Repeat the same `curl` — confirm `X-Cache: HIT` and response is served from R2.
3. Add `-H 'Save-Data: on'` — confirm quality drops and width halves.
4. Run Lighthouse on a page using the proxy — check LCP and image audit scores.
5. In R2 console or via `wrangler r2 object list orchords-image-derivatives`, confirm derivative keys are present.

## Related

- `workers-app-manifest-dynamic-pwa.md` — manifest icon pipeline uses same R2 caching pattern
- Cloudflare Image Resizing docs: https://developers.cloudflare.com/images/image-resizing/
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/

## Sources

- Cloudflare Image Resizing — Workers integration guide
- Client Hints specification — WICG
- Save-Data header — Network Information API
- WebP / AVIF format comparisons — Google web.dev
- R2 Workers Binding API — Cloudflare documentation
