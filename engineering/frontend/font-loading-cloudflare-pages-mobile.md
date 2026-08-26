# Font Loading on Cloudflare Pages — Mobile FOUT & R2 Self-Hosted Fonts

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Text renders in the system fallback font for 300-800 ms on mobile connections, then
flashes to the brand typeface (FOUT — Flash of Unstyled Text). On slow 4G, the flash
is visible to users even after the page reaches LCP. Google Fonts loads from a third-party
origin, adding a DNS + TLS round-trip on every cold visit.

## Context

example project (example.com) uses Next.js 14 `output: 'export'` deployed on Cloudflare Pages.
The app is mobile-first; fonts not delivered from the same edge PoP as HTML cause
extra RTTs. Moving fonts to Cloudflare R2 (served via a Worker or Pages static asset)
eliminates the third-party origin and enables aggressive edge caching via `_headers`.

---

## font-display Values Compared

| Value | FOUT | FOIT | When to Use |
|---|---|---|---|
| `auto` | Browser default | Browser default | Never intentional |
| `block` | No | Yes — invisible up to 3 s | Icon fonts only |
| `swap` | Yes — immediate fallback | No | Body text, headings |
| `fallback` | 100 ms block, then swap | 100 ms invisible | Good for headings |
| `optional` | Never swaps | Drops font if not cached | Non-critical decorative |

For example project's body copy use `swap`; for headings use `fallback` to limit FOUT duration.

---

## Self-Hosting Fonts on R2

### 1. Upload to R2

```bash
# Convert TTF → WOFF2 before uploading (pyftsubset or fonttools)
pip install fonttools brotli
pyftsubset Inter-Regular.ttf \
  --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6" \
  --flavor=woff2 \
  --output-file=inter-regular-latin.woff2

# Upload via Wrangler
npx wrangler r2 object put example project-fonts/inter-regular-latin.woff2 \
  --file inter-regular-latin.woff2 \
  --content-type "font/woff2"
```

### 2. Serve R2 assets via a Worker (or Pages Function)

```ts
// functions/fonts/[[path]].ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  FONTS_BUCKET: R2Bucket;
}

export const onRequest: PagesFunction<Env> = async ({ params, env }) => {
  const key = (params.path as string[]).join('/');
  const obj = await env.FONTS_BUCKET.get(key);
  if (!obj) return new Response('Not found', { status: 404 });

  return new Response(obj.body, {
    headers: {
      'Content-Type': obj.httpMetadata?.contentType ?? 'font/woff2',
      // Fonts are immutable — cache at edge and browser for 1 year
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Access-Control-Allow-Origin': 'https://example.com',
    },
  });
};
```

---

## Cloudflare Pages `_headers` Cache Rules

```
# public/_headers

# Self-hosted WOFF2 fonts — immutable, 1-year TTL
/fonts/*.woff2
  Cache-Control: public, max-age=31536000, immutable
  Access-Control-Allow-Origin: https://example.com

# Fallback for WOFF (legacy)
/fonts/*.woff
  Cache-Control: public, max-age=31536000, immutable
  Access-Control-Allow-Origin: https://example.com

# CSS with font-face declarations — short TTL so changes propagate
/fonts/fonts.css
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
```

---

## @font-face Declaration

```css
/* public/fonts/fonts.css */

/* Subset: Latin + Latin Extended */
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-regular-latin.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
  /* Size-adjust shifts the fallback metric to match Inter */
  size-adjust: 100.06%;
  ascent-override: 90%;
  descent-override: 22.43%;
  line-gap-override: 0%;
}

@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-bold-latin.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: fallback;
  size-adjust: 100.06%;
  ascent-override: 90%;
  descent-override: 22.43%;
}
```

The `size-adjust`, `ascent-override`, and `descent-override` descriptors shrink the
layout shift caused by the fallback font having different metrics (reduces CLS).

---

## Preload Hints in Next.js

### App Router — layout.tsx

```tsx
// app/layout.tsx
import type { Metadata } from 'next';

export const metadata: Metadata = {
  // next/head does not support <link rel="preload"> in App Router;
  // use the `links` metadata key or a custom component.
};

// Custom Head component that injects preload link
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Preload only the critical-path font weight */}
        <link
          rel="preload"

          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link rel="stylesheet"  />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

### Why `crossOrigin="anonymous"` matters

Fonts are fetched with CORS. Without `crossOrigin`, the preloaded font sits in the
preload cache under a different cache key than the actual font fetch, so the browser
fetches twice. Always set `crossOrigin="anonymous"` on font preloads.

---

## next/font vs Self-Hosted

| Approach | FOUT Risk | Third-Party Origin | Edge Cache Control | CLS Risk |
|---|---|---|---|---|
| `next/font/google` (server mode) | Low (inlined) | No (proxied at build) | Limited | Low |
| `next/font/google` (static export) | Not supported | — | — | — |
| `next/font/local` | Low | No | Full control | Low |
| Manual `@font-face` + R2 | Medium | No | Full control | Medium |

`next/font` with `output: 'export'` falls back to `next/font/local`. Point it at the
same WOFF2 files uploaded to R2 and copied into `/public/fonts/` for local dev.

```ts
// lib/fonts.ts
import localFont from 'next/font/local';

export const inter = localFont({
  src: [
    { path: '../public/fonts/inter-regular-latin.woff2', weight: '400' },
    { path: '../public/fonts/inter-bold-latin.woff2',   weight: '700' },
  ],
  display: 'swap',
  variable: '--font-inter',
});
```

---

## Anti-patterns

- **Loading Google Fonts via `<link>` in `_document`** — third-party DNS RTT on mobile.
- **No `crossOrigin` on font preload** — double fetch, wastes bandwidth.
- **`font-display: block` on body text** — invisible text for up to 3 s on slow connections.
- **Not subsetting fonts** — full Inter WOFF2 is ~300 KB; Latin subset is ~25 KB.
- **Using `preconnect` to `fonts.googleapis.com` then self-hosting** — preconnect has no effect if the domain is never fetched.

---

## Gotchas

- Cloudflare Pages `_headers` rules require exact path matching with glob support;
  `/*.woff2` matches only top-level, not subdirectories. Use `/fonts/*.woff2`.
- R2 public buckets do not set `Cache-Control` by default — the Pages Function or
  Worker must set it explicitly.
- `size-adjust` and `ascent-override` are supported in all modern browsers but not IE.
  They are ignored gracefully on unsupported browsers.
- `next/font/local` with `output: 'export'` copies fonts into `/_next/static/media/`
  with content-hashed filenames. Ensure `_headers` also covers `/_next/static/media/*.woff2`.

---

## Verification

```bash
# 1. Check preload link in HTML output
grep -r "preload" out/index.html

# 2. Verify CORS header on font file
curl -I -H "Origin: https://example.com" \
  https://example.com/fonts/inter-regular-latin.woff2 \
  | grep -E "access-control|cache-control|content-type"

# 3. WebPageTest — filmstrip to observe FOUT on throttled 4G
# Metric: First Contentful Paint vs. Web Font loaded time

# 4. Lighthouse CLS score — should be <0.1 with metric overrides applied
npx lighthouse https://example.com --form-factor mobile \
  --only-audits=cumulative-layout-shift

# 5. Confirm immutable cache header on WOFF2
curl -sI https://example.com/fonts/inter-regular-latin.woff2 \
  | grep cache-control
# Expected: cache-control: public, max-age=31536000, immutable
```

---

## Related

- `font-loading-optimization.md`
- `next-js-font-optimization.md`
- `variable-fonts-loading-strategy.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `nextjs-static-export-cloudflare-pages-routing.md`
- `html-web-vitals-cls.md`

## Sources

- Cloudflare R2 — https://developers.cloudflare.com/r2/
- CSS font-display — https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display
- Cloudflare Pages _headers — https://developers.cloudflare.com/pages/configuration/headers/
- next/font/local — https://nextjs.org/docs/app/api-reference/components/font#local-fonts
- Font metric overrides — https://developer.chrome.com/blog/font-fallbacks/
