# Next.js Image Optimization on Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

`next/image` throws `Error: No "loader" prop or "loaderFile"` at build time, or images
are served as unresized full-resolution PNGs on mobile, wrecking LCP scores. The default
`/_next/image` route does not exist on a static export.

## Context

Next.js 14 with `output: 'export'` produces a fully static site — no Node.js server,
no built-in image optimisation endpoint. Cloudflare Pages does not execute Node.js
functions by default, so the built-in `/_next/image` optimiser is unavailable.
example project (example.com) targets mobile-first and ships large hero images; unoptimised delivery
causes 3-4 MB payloads on cellular connections.

Two viable paths exist:
1. Cloudflare Image Resizing (IR) — a Cloudflare feature that rewrites image URLs
   through Cloudflare's edge workers and returns WebP/AVIF on the fly.
2. A custom Pages Function that proxies image requests to IR.

---

## Static Export Constraints

| Feature | Node.js Server | Static Export (`output: 'export'`) |
|---|---|---|
| `/_next/image` route | Available | **Not available** |
| Built-in WebP/AVIF | Yes | No |
| `sizes` attribute | Respected | Passed through but not used for resizing |
| `placeholder="blur"` | Yes | Yes (base64 inline, not remote) |
| `unoptimized` prop | Works | Required without a custom loader |

Setting `images.unoptimized: true` silences the build error but disables all resizing.
Use it only in local dev or as a last resort.

---

## Cloudflare Image Resizing as Custom Loader

### next.config.js

```js
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: {
    loader: 'custom',
    loaderFile: './src/lib/cfImageLoader.ts',
    // Enumerate every remote hostname images can come from
    remotePatterns: [
      { protocol: 'https', hostname: 'assets.example.com' },
      { protocol: 'https', hostname: 'r2.example.com' },
    ],
  },
};

module.exports = nextConfig;
```

### Custom loader — src/lib/cfImageLoader.ts

```ts
import type { ImageLoaderProps } from 'next/image';

/**
 * Routes all next/image requests through Cloudflare Image Resizing.
 * CF IR is a Cloudflare Pro+ feature; the URL format is:
 *   /cdn-cgi/image/<options>/<original-url>
 */
export default function cfImageLoader({
  src,
  width,
  quality,
}: ImageLoaderProps): string {
  // During SSG / local dev: return the original URL unchanged
  if (process.env.NODE_ENV === 'development') return src;

  const q = quality ?? 75;
  const origin =
    typeof window !== 'undefined'
      ? window.location.origin
      : 'https://example.com';

  // Absolute URLs pass straight through; relative paths get the origin prepended
  const absoluteSrc = src.startsWith('http') ? src : `${origin}${src}`;

  return `/cdn-cgi/image/format=auto,width=${width},quality=${q}/${absoluteSrc}`;
}
```

### format=auto negotiation

`format=auto` instructs CF IR to inspect the `Accept` header and return:
- **AVIF** for Chrome 85+, Firefox 93+, Safari 16.4+
- **WebP** for most other modern browsers
- **JPEG/PNG** fallback for legacy clients

---

## `_next/image` Routing on Cloudflare Pages

### Option A — Redirect rule in `_redirects`

```
# public/_redirects
/cdn-cgi/image/*  /cdn-cgi/image/:splat  200
```

No entry needed — Cloudflare handles `/cdn-cgi/image/*` natively at the edge when
Image Resizing is enabled on the zone. No Pages Function required.

### Option B — Pages Function fallback (if IR is unavailable)

```ts
// functions/cdn-cgi/image/[[path]].ts
import type { PagesFunction } from '@cloudflare/workers-types';

export const onRequest: PagesFunction = async (context) => {
  // Proxy to the Cloudflare IR endpoint; requires Workers Unbound billing
  const url = new URL(context.request.url);
  const response = await fetch(url.toString(), {
    cf: { image: { format: 'auto' } },
  } as RequestInit);
  return response;
};
```

---

## Mobile WebP/AVIF Delivery

```tsx
// components/HeroImage.tsx
import Image from 'next/image';

export function HeroImage() {
  return (
    <Image
      src="https://assets.example.com/hero.jpg"
      alt="example project hero"
      width={1200}
      height={630}
      // Tell the browser what size slot this image fills at each breakpoint
      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 80vw, 1200px"
      priority   // Hero is above the fold — preload it
      quality={80}
    />
  );
}
```

The loader converts the above to srcset entries like:

```
/cdn-cgi/image/format=auto,width=640,quality=80/https://assets.example.com/hero.jpg 640w,
/cdn-cgi/image/format=auto,width=828,quality=80/https://assets.example.com/hero.jpg 828w,
/cdn-cgi/image/format=auto,width=1080,quality=80/https://assets.example.com/hero.jpg 1080w,
```

Mobile devices with a 390 px viewport and 2× DPR will fetch the 828 w variant.

---

## Recommended `deviceSizes` / `imageSizes`

```js
// next.config.js — tune to your real breakpoints
images: {
  deviceSizes: [390, 414, 768, 1024, 1280, 1920],
  imageSizes:  [16, 32, 48, 64, 96, 128, 256],
}
```

---

## Anti-patterns

- **`unoptimized: true` in production** — silences the error but ships full-res images.
- **Using `fill` without a positioned parent** — causes layout shift (CLS spike).
- **Omitting `sizes`** — browser defaults to `100vw` and fetches the largest srcset candidate.
- **Hardcoding `quality={100}`** — CF IR still encodes; 100 disables lossy gains.
- **Using `placeholder="blur"` with remote images without `blurDataURL`** — build error.

---

## Gotchas

- Cloudflare Image Resizing requires the **Pro plan** or higher on the zone. On Pages
  Free, `/cdn-cgi/image/*` returns the original image unchanged — not an error.
- IR caches resized variants in Cloudflare's cache; purging original assets does not
  automatically purge resized copies. Use Cache-Tag purging or `cf-cache-status: BYPASS`.
- The custom loader runs **at render time**, not at build time. Passing a dynamic `src`
  (user-uploaded content) works fine.
- `next/image` with `output: 'export'` still emits `<img>` with `srcset`; it does NOT
  emit `<picture>` with `<source type="image/avif">`. AVIF negotiation relies entirely
  on the `Accept` header handled by CF IR.

---

## Verification

```bash
# 1. Build the static export
npm run build   # produces /out directory

# 2. Preview locally with Wrangler (respects Pages Functions)
npx wrangler pages dev out --port 8788

# 3. Check that the loader URL appears in the rendered HTML
curl -s http://localhost:8788 | grep cdn-cgi/image

# 4. Confirm format negotiation (production only — IR not active locally)
curl -I -H "Accept: image/avif,image/webp" \
  "https://example.com/cdn-cgi/image/format=auto,width=828,quality=80/https://assets.example.com/hero.jpg" \
  | grep content-type
# Expected: content-type: image/avif

# 5. Lighthouse mobile audit — LCP should improve >40% vs unoptimised
npx lighthouse https://example.com --form-factor mobile --only-categories performance
```

---

## Related

- `nextjs-static-export-cloudflare-pages-routing.md`
- `image-format-selection-webp-avif.md`
- `html-srcset-responsive-images.md`
- `html-lazy-loading-images.md`
- `html-web-vitals-lcp.md`
- `build-time-env-baking-chunk-hash.md`

## Sources

- Cloudflare Image Resizing docs — https://developers.cloudflare.com/images/image-resizing/
- Next.js custom loader API — https://nextjs.org/docs/app/api-reference/components/image#loaderfile
- Next.js static export — https://nextjs.org/docs/app/building-your-application/deploying/static-exports
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
