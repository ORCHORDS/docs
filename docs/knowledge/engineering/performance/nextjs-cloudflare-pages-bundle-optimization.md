# Next.js Bundle Optimization on Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Next.js site deployed to Cloudflare Pages ships a 1.2 MB first-load JS bundle.  On 4G mobile (10 Mbps, 60 ms RTT) the parse-and-execute cost alone adds 3–5 s to TTI.  Lighthouse flags "Reduce unused JavaScript" and "Avoid enormous network payloads" but the recommended fixes (code splitting, tree shaking) are vague.  You need a systematic, Pages-specific approach: which chunks to split, which packages to replace or remove, and how to verify the result with field data rather than lab scores alone.

## Context

Cloudflare Pages serves Next.js output via the `@cloudflare/next-on-pages` adapter, which compiles route handlers as individual Workers scripts and static assets as R2-backed objects.  The constraint differs from Vercel: each Workers script has a **1 MB compressed size limit** (10 MB uncompressed before the bundler gzips) and a **10 ms CPU time budget** per request (soft; 50 ms burst).  Bundle size affects both the asset download time (network) and Worker script cold-start time (parse cost).

Mobile broadband vs desktop distinction:
- 4G mobile median throughput: 8–15 Mbps with 40–80 ms RTT.
- Home broadband: 50–200 Mbps with 8–20 ms RTT.
- A 200 KB JS chunk costs 160–200 ms on 4G vs 8–32 ms on broadband — 5–20× difference.
- V8 parse time on a Snapdragon 695 (mid-range 2024 Android) is roughly 1 ms/KB, so a 600 KB chunk takes 600 ms just to parse — before any network.

## Section 1 — Identifying Bundle Bloat

**Step 1: generate the bundle analysis report**

```bash
# next.config.js must have bundleAnalyzer enabled
ANALYZE=true npx next build
```

`next.config.js`:
```javascript
const withBundleAnalyzer = require('@next/bundle-analyzer')({
  enabled: process.env.ANALYZE === 'true',
});

module.exports = withBundleAnalyzer({
  experimental: {
    optimizePackageImports: [
      'lucide-react', 'date-fns', 'lodash-es', '@radix-ui/react-icons',
    ],
  },
});
```

`@next/bundle-analyzer` opens two treemaps: client and server.  Focus on the **client** treemap.  Look for:
- Any single module > 50 KB gzipped (common offenders: `moment`, `lodash`, `recharts`, `@mui/material`)
- Duplicated packages (multiple semver versions of the same package)
- `node_modules` code in page-specific chunks that should be in `_app` or a shared chunk

**Step 2: generate a size regression baseline**

```bash
npx bundlesize --config .bundlesizerc.json
```

`.bundlesizerc.json`:
```json
{
  "files": [
    { "path": ".next/static/chunks/pages/_app-*.js",    "maxSize": "120 kB" },
    { "path": ".next/static/chunks/framework-*.js",     "maxSize": "50 kB"  },
    { "path": ".next/static/chunks/main-*.js",          "maxSize": "40 kB"  },
    { "path": ".next/static/chunks/pages/index-*.js",   "maxSize": "30 kB"  }
  ]
}
```

Add `bundlesize` to your CI (Cloudflare Pages deploy hook or GitHub Actions pre-deploy step) so every PR surfaces regressions before they reach production.

## Section 2 — Code Splitting Strategies for Pages

**Dynamic imports for below-fold components:**

```javascript
// app/page.tsx
import dynamic from 'next/dynamic';

// Heavy chart only needed when user scrolls to "Analytics" section
const AnalyticsChart = dynamic(
  () => import('@/components/AnalyticsChart'),
  {
    loading: () => <div className="chart-skeleton" />,
    ssr: false,   // chart uses DOM APIs; disable server render
  }
);

// Modal dialog — not needed on first paint
const PricingModal = dynamic(() => import('@/components/PricingModal'));
```

Expected impact: each dynamically imported component's chunk is only downloaded when the component is about to render.  On mobile where network is slow, lazy-loading a 80 KB chart saves 640 ms download time on 4G before the user even sees the fold where it lives.

**Route-level splitting is automatic in Next.js App Router** — each `page.tsx` gets its own chunk.  But shared components imported by many pages end up in a large shared chunk.  Control this with `splitChunks`:

```javascript
// next.config.js
module.exports = {
  webpack(config, { isServer }) {
    if (!isServer) {
      config.optimization.splitChunks = {
        ...config.optimization.splitChunks,
        cacheGroups: {
          // Move UI library into its own chunk, cached separately
          radix: {
            test: /[\\/]node_modules[\\/]@radix-ui[\\/]/,
            name: 'radix-ui',
            chunks: 'all',
            priority: 30,
          },
          // Keep date-fns locale data separate
          dateFns: {
            test: /[\\/]node_modules[\\/]date-fns[\\/]/,
            name: 'date-fns',
            chunks: 'all',
            priority: 20,
          },
        },
      };
    }
    return config;
  },
};
```

## Section 3 — Package Replacements and Tree-shaking

**High-impact swaps (ordered by typical bundle savings):**

| Replace | With | Savings (gzipped) |
|---------|------|-------------------|
| `moment` (72 KB) | `date-fns` tree-shaken | 55 KB |
| `lodash` (24 KB) | native ES or `lodash-es` with `optimizePackageImports` | 18 KB |
| `axios` (12 KB) | `fetch` polyfill or `ky` (3 KB) | 9 KB |
| `react-icons` all icons | Named imports from `react-icons/fa6` | 40 KB |
| `@mui/material` full | Shadcn/ui (zero runtime) | 80 KB |

**Enable `optimizePackageImports`** in `next.config.js` for any icon library, date library, or component library that uses barrel files:

```javascript
module.exports = {
  experimental: {
    optimizePackageImports: [
      'lucide-react',
      'date-fns',
      'lodash-es',
      '@heroicons/react',
    ],
  },
};
```

This causes Next.js to rewrite barrel imports (e.g., `import { Calendar, User } from 'lucide-react'`) into direct file imports so the bundler can tree-shake unreferenced icons.  Without this, the full icon set (~800 KB) is included.

**Verify tree-shaking is working:**

```bash
# Check if moment locale data is being pulled in (it shouldn't be if you use date-fns)
cat .next/static/chunks/*.js | grep -c 'moment/locale'
# Should return 0
```

## Section 4 — Cloudflare Pages–Specific Tuning

**Workers script size constraint:**
Each API route compiled by `@cloudflare/next-on-pages` runs as a separate Worker.  The 1 MB compressed limit means server-side code that imports heavy dependencies will fail to deploy.  Keep server components lean:

```javascript
// app/api/products/route.ts
// BAD — imports a 200 KB library server-side unnecessarily
import { parse } from 'some-heavy-parser';

// GOOD — use a lighter alternative or inline the specific function
import { parseProductSlug } from '@/lib/slug'; // 200 bytes
```

**Cache static assets with immutable headers:**
In `_headers` (Pages static config):

```
/static/*
  Cache-Control: public, max-age=31536000, immutable

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable
```

Immutable caching means returning mobile users on 4G skip the re-validation round-trip entirely (saves 40–80 ms RTT per cached chunk).

**Pages `_headers` for font preloading:**

```
/
  Link: </_next/static/fonts/Inter-Regular.woff2>; rel=preload; as=font; crossorigin=anonymous
```

Instructs CF edge to inject a `Link` preload header, triggering browser preload from the HTML parse phase rather than waiting for CSS to be parsed.  On 4G this saves 150–400 ms on font LCP.

**Prefetch next route with speculation rules:**

```html
<!-- in app/layout.tsx -->
<script type="speculationrules" dangerouslySetInnerHTML={{ __html: JSON.stringify({
  prefetch: [{ source: 'list', urls: ['/checkout', '/account'] }],
  prerender: [{ source: 'list', urls: ['/products'] }],
}) }} />
```

Chrome on Android 13+ supports prerendering.  The products page JS chunk is parsed and executed before the user taps — turning a 2 s navigation into < 200 ms.

## Anti-patterns

- **Importing entire UI library in `_app.tsx`** — puts all component code in the shared chunk downloaded on every page.  Import only globally needed wrappers (toast provider, theme provider) and lazy-load the rest.
- **Using `ssr: false` on above-fold components** — delays rendering by waiting for JS hydration.  Only disable SSR for components that are genuinely below fold or use browser-only APIs.
- **Skipping the bundle analyzer** — bundle regressions are invisible without measurement.  A single dependency update can add 50 KB silently.
- **Setting `Cache-Control: no-store` on `/_next/static/`** — destroys repeat-visit performance.  Next.js content-hashes all static filenames; immutable caching is always safe for `/_next/static/`.
- **Large server actions with shared heavy imports** — Server Actions run as Worker scripts on Pages.  An action that imports `pdfkit` (3 MB) will exceed the Worker script size limit.

## Gotchas

- `@cloudflare/next-on-pages` does not support all Next.js features (notably `next/image` built-in optimization requires the Image Resizing API add-on to be enabled on the zone).
- `optimizePackageImports` only rewrites static barrel imports — dynamic imports (`import(pkg)`) are not rewritten.
- Pages does not support Edge Runtime `next export` output.  Verify your `next.config.js` sets `output: 'edge'` or omits output entirely (defaults to Node-compatible, compiled to Workers by the adapter).
- Bundle analyzer reports pre-compression sizes.  Gzipped sizes are typically 25–40 % of reported.  Always check `.next/analyze/*.json` for true transferred sizes.

## Verification

1. Run `ANALYZE=true npx next build` and confirm no single chunk exceeds 200 KB gzipped.
2. Deploy to Pages preview environment, open DevTools Network (throttled to Fast 4G), reload.  Verify total JS transferred < 300 KB for the landing page.
3. Run Lighthouse mobile (no throttle override) — score ≥ 90 TBT and ≥ 85 Speed Index are achievable with these optimizations on typical content sites.
4. Check the Analytics Engine RUM data (see `analytics-engine-rum-web-vitals.md`) for INP improvement on `blob5 = 'mobile'` after deployment.

## Related

- `bundle-analysis-workflows.md` — generic bundle analysis workflow
- `bundle-size-budgets.md` — enforcing size limits in CI
- `code-splitting-strategies.md` — framework-agnostic splitting patterns
- `cloudflare-image-resizing-mobile-webp-avif.md` — complementary image optimization
- `early-hints-103-cloudflare-pages-mobile.md` — Pages-native LCP improvement
- `workers-cpu-time-optimization.md` — keeping Worker CPU within budget

## Sources

- Next.js bundle analyzer: https://nextjs.org/docs/app/building-your-application/optimizing/bundle-analyzer
- Cloudflare next-on-pages adapter: https://developers.cloudflare.com/pages/framework-guides/nextjs/
- next.config.js optimizePackageImports: https://nextjs.org/docs/app/api-reference/config/next-config-js/optimizePackageImports
- Cloudflare Pages _headers file: https://developers.cloudflare.com/pages/configuration/headers/
- Speculation Rules API: https://developer.chrome.com/docs/web-platform/prerender-pages
