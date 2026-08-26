# frontend-bundle-optimization

**Issue:** Keep the Next.js bundle small + fast
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Next.js app's first load is 1.5 MB of JS. The user is on
slow 3G. The page takes 8 seconds to interactive. Lighthouse
score: 40.

## Root cause
**Every dependency is bundled into the initial JS.** A 100KB
library (date picker, charting lib, etc.) becomes 100KB of JS
that the user downloads before seeing the page.

**Source:** Vite + Next.js bundle analysis:
https://nextjs.org/docs/app/building-your-application/optimizing/bundle-analyzer

## Fix

### 1. Analyze the bundle
```bash
# Next.js
npx next-bundle-analyzer
# or
ANALYZE=true next build
```

This produces a treemap showing which packages take the most
space. Find the unexpected ones.

### 2. Code splitting
For a page that uses a heavy component, use dynamic import:
```ts
// ❌ Bad: bundled in the main page
import { HeavyChart } from 'heavy-chart-library';

function Dashboard() {
  return <HeavyChart data={data} />;
}

// ✅ Good: loaded only when the dashboard is visited
import dynamic from 'next/dynamic';
const HeavyChart = dynamic(() => import('heavy-chart-library').then(m => m.HeavyChart), {
  loading: () => <div>Loading chart...</div>,
  ssr: false,  // skip SSR if the chart doesn't need it
});
```

### 3. Tree shaking
For a library with named exports, import only what you need:
```ts
// ❌ Bad: imports the whole library
import * as _ from 'lodash';

// ✅ Good: imports only the function
import debounce from 'lodash/debounce';
```

Vite (used by Next.js 14) does tree shaking automatically. But
it can't shake libraries that have side effects on import.

### 4. Replace heavy libraries

| Heavy | Lighter alternative |
|---|---|
| `moment` (300KB) | `date-fns` (modular, tree-shakable) or `Intl.DateTimeFormat` |
| `lodash` (70KB) | Native ES6+ (`Array.map`, `Object.keys`, etc.) |
| `chart.js` (200KB) | `chartist` (small) or hand-rolled SVG |
| `axios` (40KB) | `fetch` (built-in) |
| `jquery` (270KB) | Vanilla JS (or React) |

### 5. Compress
Vite + Next.js do this by default (gzip + brotli). Make sure
your hosting serves the compressed files.

CF Pages: enable auto-minify in the dashboard.
- Settings → Speed → Optimization → Auto Minify: HTML, CSS, JS

### 6. Lazy load images
```html
<img  alt="..." loading="lazy" decoding="async">
```

The `loading="lazy"` defers off-screen images. The
`decoding="async"` lets the browser decode the image in
parallel with rendering.

### 7. Preconnect + preload
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preload"  as="image">
```

Preconnect warms up the connection to a third-party domain.
Preload fetches a critical resource early.

### 8. Use a CDN
CF Pages is a CDN. Your static assets are served from the
edge. Long-tail caching is automatic.

## Verification
- **Test:** `test/bundle-size.test.ts > first load JS < 200KB`
  — passes
- **Live:** Lighthouse performance score > 90
- **Audit:** Quarterly bundle analysis

## Gotchas
- **The bundle is cached, but new users get the full size.**
  Long-tail users (mobile, slow networks) feel the most pain.
- **Tree shaking doesn't work for CommonJS.** Use ESM-only
  libraries when possible.
- **Dynamic imports add latency** to the first render of the
  lazy component. Use for non-critical components only.
- **The `loading="lazy"` attribute is ignored by some older
  browsers.** Use a polyfill or accept the fallback.
- **Compression is essential** but not enough. A 1MB bundle
  compressed is 300KB. Still huge for slow networks.
- **The "first load JS" is the metric that matters.** Total
  bundle size is misleading (most code is lazy).

## Related
- `accessibility-wcag.md` (bundle size affects a11y on slow
  networks)
- `next-static-export-pages.md` (the build that produces the
  bundle)
- Next.js: https://nextjs.org/docs/app/building-your-application/optimizing/bundle-analyzer
- Web Vitals: https://web.dev/vitals/
