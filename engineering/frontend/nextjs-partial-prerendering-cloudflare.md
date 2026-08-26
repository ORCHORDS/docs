# Next.js App Router Partial Prerendering with Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You have a Next.js App Router page where most of the layout is static (header, navigation, product
grid shell) but a small section depends on dynamic data (personalised recommendations, cart count,
A/B variant). The page currently opts into dynamic rendering for the whole route — every request
hits the origin, TTFB is high, and LCP suffers. You want to serve the static shell instantly from
Cloudflare's CDN while streaming in only the dynamic parts.

## Context

Partial Prerendering (PPR) was introduced experimentally in Next.js 14 and stabilised in Next.js
15 (released late 2024). It is the first mechanism that lets a single Next.js route be
*simultaneously* static and dynamic at the granularity of React Suspense boundaries.

How it works at build time:

1. Next.js renders the page at build time. Everything outside a `<Suspense>` boundary is
   pre-rendered to a static HTML shell.
2. Suspense fallbacks for dynamic segments are included in the static HTML.
3. The static shell is placed in Cloudflare Pages' CDN cache.

How it works at request time:

1. The browser receives the static HTML shell from Cloudflare edge cache immediately (no server
   round-trip for the shell).
2. The dynamic segments are streamed via a server-rendered response from Cloudflare Pages
   Functions (the Next.js server runtime).
3. The browser hydrates the static shell first, then applies the streamed dynamic content.

This gives you CDN-speed initial page loads (no server RTT for the shell) + fresh dynamic content,
without sacrificing interactivity.

## Enabling PPR in Next.js 15

In `next.config.ts`:

```typescript
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  experimental: {
    ppr: true,             // 'incremental' to opt-in per-route; true for all routes
  },
};

export default nextConfig;
```

With `ppr: 'incremental'`, opt a specific route in with:

```typescript
// app/products/[id]/page.tsx
export const experimental_ppr = true;
```

## Structuring a PPR-Enabled Route

The static/dynamic boundary is defined by `<Suspense>`. Anything that calls `cookies()`,
`headers()`, `searchParams`, or `fetch` with `cache: 'no-store'` inside a Suspense boundary
becomes a dynamic island:

```typescript
// app/shop/page.tsx
import { Suspense } from 'react';
import { ProductGrid } from '@/components/product-grid';   // static
import { CartBadge } from '@/components/cart-badge';       // dynamic
import { Recommendations } from '@/components/recs';       // dynamic

export default function ShopPage() {
  return (
    <main>
      {/* Static — pre-rendered at build, served from Cloudflare CDN */}
      <header className="site-header">
        <Logo />
        <nav>...</nav>
        <Suspense fallback={<CartBadgeSkeleton />}>
          {/* Dynamic — streamed from Pages Functions */}
          <CartBadge />
        </Suspense>
      </header>

      {/* Static shell */}
      <ProductGrid />

      {/* Dynamic island */}
      <Suspense fallback={<RecommendationsSkeleton />}>
        <Recommendations />
      </Suspense>
    </main>
  );
}
```

`CartBadge` reads a cookie; `Recommendations` calls an uncached API. Both are inside Suspense
and become dynamic. The rest renders at build time.

## Cloudflare Pages Deployment

The `@cloudflare/next-on-pages` adapter handles PPR routes automatically as of version 1.13+.

```bash
npm install -D @cloudflare/next-on-pages
```

`wrangler.toml`:

```toml
name = "my-shop"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[pages_build_output_dir]
path = ".vercel/output/static"
```

`package.json` build command:

```json
{
  "scripts": {
    "build": "next build && npx @cloudflare/next-on-pages",
    "pages:dev": "npx wrangler pages dev .vercel/output/static"
  }
}
```

When `next-on-pages` processes a PPR route:
- The static HTML shell is placed in `_worker.js`'s static asset manifest (served by Cloudflare
  CDN with `Cache-Control: s-maxage=31536000`).
- The dynamic rendering function becomes a Pages Function triggered for the same route path.
- Cloudflare's routing layer serves the static shell from cache, then continues streaming the
  dynamic parts from the Function.

## Cache Headers for the Static Shell

The PPR static shell gets aggressive cache headers automatically. Verify them:

```bash
curl -I https://yoursite.pages.dev/shop
# CF-Cache-Status: HIT
# Cache-Control: public, max-age=0, s-maxage=31536000, stale-while-revalidate
```

`CF-Cache-Status: HIT` for the initial HTML is the goal. Dynamic streaming continues behind a
separate HTTP/2 or HTTP/3 stream.

For cache invalidation, Pages Functions can call the Cloudflare Cache API after a product update:

```typescript
// app/api/revalidate/route.ts
import { revalidatePath } from 'next/cache';
import { NextRequest } from 'next/server';

export async function POST(req: NextRequest) {
  const { path } = await req.json();
  revalidatePath(path);
  return Response.json({ revalidated: true });
}
```

## Dynamic Components: What Can Live in a PPR Island

Any component that uses:
- `cookies()` — reads request cookies
- `headers()` — reads request headers
- `searchParams` (from page props) — reads URL query params
- `fetch()` with `{ cache: 'no-store' }` or `{ next: { revalidate: 0 } }`
- `unstable_noStore()` — explicitly opts out of caching

All of the above force the component into dynamic rendering. Without Suspense wrapping them, they
force the *entire route* into dynamic rendering (defeating PPR).

## Server Actions in PPR Pages

Server actions (`"use server"`) work normally with PPR. They are separate POST requests and are
not part of the static shell. However, a server action triggered from a dynamic island must not
call `revalidatePath` in a way that invalidates the PPR static shell unless a rebuild is
acceptable.

Preferred pattern: server actions call an edge cache purge:

```typescript
'use server';
import { revalidatePath } from 'next/cache';

export async function updateCart(productId: string) {
  await db.cart.add(productId);
  // Only revalidate the dynamic cart segment, not the full page shell
  revalidatePath('/shop', 'layout');
}
```

## Anti-patterns

**Placing dynamic data fetches outside Suspense**: If `CartBadge` uses `cookies()` but is not
wrapped in `<Suspense>`, Next.js falls back to fully dynamic rendering for the whole route. The
Suspense boundary is the boundary — not the component itself.

**Using `export const dynamic = 'force-dynamic'` on a PPR route**: This disables PPR for the
route entirely. Remove it; let PPR handle the dynamic/static split via Suspense.

**Fetching the same data in both static and dynamic components**: The static shell is rendered at
build time; it cannot share runtime state with dynamic islands. Pass props down into the Suspense
boundary, not shared in-request state.

**Not testing in Cloudflare's local dev**: Run `npm run pages:dev` and verify `CF-Cache-Status`
headers. The Vite/webpack dev server (`next dev`) does not simulate CDN caching or PPR streaming.

**Relying on PPR for auth-gated pages**: PPR serves the static shell from cache to *all* users
before auth is checked. If the shell contains any sensitive structure (e.g., a username in the
header), it leaks to unauthenticated users. Put auth checks inside dynamic islands.

## Gotchas

- `next-on-pages` version 1.13+ is required for PPR. Earlier versions do not understand the dual
  static-plus-dynamic output format and will produce incorrect routing.
- The Suspense fallback in the static shell is rendered at build time. If the fallback references
  any runtime state (cookies, date), it will be stale. Keep fallbacks purely structural
  (skeletons, spinners).
- The `experimental_ppr` flag in route files is a string export, not a boolean:
  `export const experimental_ppr = true` — using a runtime value (`const x = condition; export
  const experimental_ppr = x`) causes a build error.
- PPR is incompatible with `export const runtime = 'edge'` on the same route. PPR requires the
  Node.js Pages Functions runtime for the dynamic streaming portion. On Cloudflare, this means
  `nodejs_compat` must be enabled.
- Streaming from Cloudflare Pages Functions has a 30-second function timeout. Long-running dynamic
  segments must complete within that window or the connection closes.

## Verification

1. Build locally: `npm run build`. Look for `○ (PPR)` next to route paths in the build output
   summary. Routes marked `●` (dynamic) are not PPR-enabled.
2. Deploy to Pages preview: `npm run pages:dev`. Make a GET request and inspect the response. The
   static shell arrives immediately; dynamic content streams in within the same response body.
3. Check `CF-Cache-Status: HIT` on second request to the same path (static shell).
4. Open React DevTools Profiler and verify that dynamic islands mount after the static shell
   hydrates — they should appear as deferred hydration events.
5. Verify `searchParams`-dependent content changes when query params change without a full rebuild.

## Related

- `nextjs-isr-vs-cloudflare-pages-static-export.md`
- `next-js-app-router-patterns.md`
- `next-js-caching-strategy.md`
- `react-suspense-cloudflare-pages-ssr-edge.md`
- `react-19-server-components-streaming-ssr.md`
- `react-server-actions.md`

## Sources

- Next.js PPR docs: https://nextjs.org/docs/app/api-reference/next-config-js/ppr
- `@cloudflare/next-on-pages`: https://github.com/cloudflare/next-on-pages
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Next.js 15 changelog: https://nextjs.org/blog/next-15
