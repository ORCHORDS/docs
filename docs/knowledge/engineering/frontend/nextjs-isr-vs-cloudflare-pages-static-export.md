# Next.js ISR vs Cloudflare Pages Static Export Trade-offs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You're deploying a Next.js application to Cloudflare Pages and need to choose between:
- `output: 'export'` (fully static, no server runtime)
- ISR via `revalidate` (requires the `@cloudflare/next-on-pages` adapter and a Workers
  runtime)

The wrong choice leads to either stale content on high-traffic pages, or unnecessary Workers
invocations (and associated billing) for content that could be fully static.

---

## Context

Cloudflare Pages supports two deployment modes for Next.js:

| Mode | Adapter | Runtime | Cost driver |
|------|---------|---------|-------------|
| Static export (`output: 'export'`) | none | None (pure CDN) | Bandwidth only |
| Full / hybrid SSR + ISR | `@cloudflare/next-on-pages` | Workers (edge) | Requests + CPU |

**Static export** pre-renders every page at build time and uploads the output as static
assets. Zero server execution at request time. No revalidation — every content change
requires a new deploy.

**ISR on Pages** uses `next-on-pages` to compile each route into a Worker function. The
Worker checks a KV namespace (or the Workers Cache API) for a cached response; if missing or
expired it re-renders and stores it. This approximates Vercel's ISR behaviour but with
meaningful differences.

---

## Section 1 — Static Export: Configuration and Routing

```js
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  // Cloudflare Pages serves files from /out by default
  // No trailing slash needed for Pages Functions interop
  trailingSlash: false,
  images: {
    // Static export has no Image Optimization server
    unoptimized: true,
  },
};

module.exports = nextConfig;
```

Pages routing quirk: Cloudflare Pages maps `/about` → `/about.html` automatically. But deep
dynamic segments like `/products/[id]` require `generateStaticParams` — without it the build
fails.

```tsx
// app/products/[id]/page.tsx
export async function generateStaticParams() {
  const products = await fetchAllProductIds(); // runs at build time only
  return products.map((id) => ({ id: String(id) }));
}

export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await fetchProduct(params.id);
  return <ProductDetail product={product} />;
}
```

If the product catalogue is large (> 10 000 SKUs), static export becomes impractical. Each
product page is an HTML file; build time scales linearly and deploy size can exceed Pages'
25 000-file limit.

---

## Section 2 — ISR on Cloudflare Pages with next-on-pages

Install the adapter:

```bash
npm install -D @cloudflare/next-on-pages
```

```js
// next.config.js  (ISR mode — no output:'export')
/** @type {import('next').NextConfig} */
const nextConfig = {
  // no `output` key — let next-on-pages handle it
};

module.exports = nextConfig;
```

```toml
# wrangler.toml
name = "my-app"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".vercel/output/static"

[[kv_namespaces]]
binding = "NEXT_CACHE_WORKERS_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Route with ISR:

```tsx
// app/products/[id]/page.tsx
export const revalidate = 3600; // 1 hour

export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await fetchProduct(params.id);  // runs in Worker at edge
  return <ProductDetail product={product} />;
}
```

The first request after a cold start (or after `revalidate` seconds) will hit the Worker and
re-render. Subsequent requests within the TTL are served from KV cache.

---

## Section 3 — Decision Matrix

### Choose static export when:
- Content changes only on deploy (marketing site, docs, blog)
- Page count is bounded (< 5 000 routes)
- You need zero Workers execution cost
- You want maximum CDN hit rate — Pages caches static assets at every PoP by default
- Mobile performance is critical: no cold-start latency, TTFB is purely CDN (~10–30 ms)

### Choose ISR when:
- Content changes between deploys and full rebuilds are too slow
- Dynamic personalisation on some routes (header auth, geo-targeting via `geo` in Workers)
- Product pages exceed the Pages 25 000-file limit
- You need `generateStaticParams` fallback (`dynamicParams = true`) for unknown slugs
- Real-time stock/pricing must be at most N minutes stale

### Hybrid approach (recommended for large catalogues):

```
Static export for:   /  /about  /contact  /blog/[slug]  (bounded, rarely changes)
ISR for:             /products/[id]  /search  /account/* (dynamic, unbounded)
```

This isn't directly possible in a single Next.js project with `output: 'export'` (which
applies globally). The workaround is **two separate Next.js projects** deployed to the same
Pages project under different path prefixes using Pages' `_routes.json`:

```json
// _routes.json (in the static output root)
{
  "version": 1,
  "include": ["/*"],
  "exclude": ["/products/*", "/search"]
}
```

Routes not excluded are served as static. Excluded routes fall through to a Worker function
(your ISR Next.js app) deployed as a Pages Function.

---

## Section 4 — Performance Characteristics at Mobile Scale

**Static export:**
- TTFB: 10–30 ms globally (pure CDN edge)
- LCP: dominated by image loading, not server render
- No cold start — no Worker is ever invoked
- Safe for `<meta viewport>` and `dvh` units — rendered at build time, no hydration race

**ISR cold start (first request after TTL):**
- Workers cold start on Pages: ~5–50 ms (typically 5–15 ms with `nodejs_compat`)
- React render time: ~20–100 ms for typical page
- KV read latency: ~10–30 ms (co-located PoP cache hit) or ~50–100 ms (miss)
- Total worst-case TTFB on mobile: ~150–200 ms — still fast, but measurable

**ISR warm (KV cache hit):**
- Workers executes but returns KV value instantly
- TTFB: ~30–80 ms

For mobile users on 4G with an RTT of 50–80 ms, the difference between 20 ms (static) and
80 ms (ISR warm) is negligible vs. the connection overhead. Cold starts are the concern;
mitigate with:

```tsx
// Ensure the KV cache is always warm via a cron Worker that pings critical routes
// wrangler.toml
[[triggers]]
crons = ["*/15 * * * *"]  // every 15 min
```

---

## Anti-patterns

- **Using ISR for every route by default** — Workers are billed per invocation. A marketing
  site with 10 000 monthly visitors on ISR costs the same as one with 10 000 000 if cached;
  but static export costs nothing beyond bandwidth.
- **`revalidate = 0` (always re-render)** — this is SSR, not ISR, and removes all caching
  benefit. Use `revalidate = 0` only on routes that genuinely require per-request fresh data
  (e.g., account pages behind auth).
- **Static export + `next/image` without `unoptimized: true`** — the Image component will
  generate `/_next/image` URLs that require a server; on a pure static deploy these 404.
- **Ignoring the 25 000-file limit** — Cloudflare Pages hard-caps at 25 000 files per
  deployment. A large static export that exceeds this will be truncated silently.
- **`generateStaticParams` without `dynamicParams = false`** — on static export, an unknown
  slug would normally fall back to SSR; with `output: 'export'` it throws a build error
  instead. Set `export const dynamicParams = false` explicitly.

---

## Gotchas

- `next-on-pages` does **not** support all Next.js features. Check the compatibility matrix
  at https://opennext.js.org/cloudflare before choosing ISR. Notable gaps as of 2026:
  `next/headers` in certain edge contexts, `unstable_cache` with custom tags, and some
  middleware patterns.
- The KV namespace for ISR cache must be created before deploying. An unbound `NEXT_CACHE_WORKERS_KV`
  causes the Worker to throw `ReferenceError` on first render.
- Static export strips all server-only code. `cookies()`, `headers()`, `redirect()` from
  `next/headers` are unavailable — accessing them throws at **build time**.
- On Cloudflare Pages, the `_headers` file controls HTTP headers for static assets. Use it
  to add `Cache-Control: public, max-age=31536000, immutable` for hashed JS/CSS chunks and
  `Cache-Control: no-store` for HTML files (so ISR revalidation is visible to CDN).

---

## Verification

Static export:
```bash
npx next build
# should see "output: export" in build log
ls out/  # HTML files for every static route
wrangler pages deploy out/ --project-name my-app
```

ISR:
```bash
npx @cloudflare/next-on-pages
wrangler pages deploy .vercel/output/static --project-name my-app
```

After ISR deploy, hit a product page twice. First response headers should show
`CF-Cache-Status: MISS`; second should show `CF-Cache-Status: HIT` (or `DYNAMIC` if served
from KV without Cloudflare caching the Worker response directly).

---

## Related

- `nextjs-static-export-cloudflare-pages-routing.md`
- `next-js-caching-strategy.md`
- `next-js-data-fetching.md`
- `pwa-service-worker-cloudflare-pages.md`
- `service-worker-caching-cloudflare-cdn-conflict.md`

---

## Sources

- Cloudflare next-on-pages docs: https://developers.cloudflare.com/pages/framework-guides/nextjs/ssr/
- OpenNext Cloudflare adapter: https://opennext.js.org/cloudflare
- Next.js static exports: https://nextjs.org/docs/app/building-your-application/deploying/static-exports
- Cloudflare Pages limits: https://developers.cloudflare.com/pages/platform/limits/
