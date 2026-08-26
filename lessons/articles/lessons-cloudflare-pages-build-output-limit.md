# Cloudflare Pages Build Output Size Limit (25MB) Causing Deploy Failure

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Next.js 14 application deployed to Cloudflare Pages via `@cloudflare/next-on-pages` began failing deploys with `Error: Script startup exceeded CPU time limit` and `Asset exceeds maximum size` errors in the Pages dashboard after adding three new npm packages (a PDF parser, a music notation library, and a date-formatting utility). The uncompressed `_worker.js` bundle had grown to 31 MB, exceeding the 25 MB Pages Worker script size limit. Deploys that had succeeded for months suddenly failed with no changes to the deployment configuration.

---

## Context

Cloudflare Pages for Next.js (via `@cloudflare/next-on-pages`) compiles all SSR routes and API routes into a single `_worker.js` file that runs as a Cloudflare Worker. Cloudflare Workers have a 10 MB compressed / 25 MB uncompressed script size limit. When new npm dependencies are added without tree-shaking validation, they can balloon the bundle significantly. Source maps, unminified vendor chunks, and side-effect-heavy packages are the most common culprits. The team had not been auditing bundle size between deploys and discovered the breach only when CI deploys began failing.

---

## What Went Wrong

```bash
# The failing deploy — Pages CI error:
# Error: Script startup exceeded CPU time limit
# Asset '.next/standalone/_worker.js' exceeds maximum size of 25MB (actual: 31.2MB)

# Checking bundle size AFTER the fact:
ls -lh .next/standalone/
# _worker.js  31M  <-- exceeds 25MB Workers limit

# next.config.js at time of failure — no optimization config
/** @type {import('next').NextConfig} */
const nextConfig = {
  // No minification config — defaults to unminified in some builds
  // No source map exclusion
  // No bundle analyzer
};

export default nextConfig;
```

```bash
# The newly added packages that pushed the bundle over the limit:
# package.json additions:
# "pdfjs-dist": "^4.0.0"      <- 8MB unminified, includes worker files
# "vexflow": "^4.2.0"          <- 3MB notation library with canvas dependencies
# "date-fns": "^3.6.0"         <- 2MB if imported without tree-shaking (import * as dateFns)

# Problematic import pattern that prevented tree-shaking:
# import * as dateFns from 'date-fns';  // imports entire library
# vs the correct:
# import { format, parseISO } from 'date-fns';  // tree-shaken
```

## Root Cause

Three compounding factors caused the bundle to exceed the 25 MB Pages limit:

1. **`pdfjs-dist`** bundles a Web Worker script (`pdf.worker.js`) inside its npm package. When imported in a Next.js SSR context, the worker script was inlined into `_worker.js` even though it is only needed in the browser. The fix is to use dynamic import with `ssr: false` for PDF rendering.

2. **`import * as dateFns from 'date-fns'`** defeated Next.js's tree-shaking pass; the entire 2 MB `date-fns` library was included instead of the ~12 KB needed for two functions.

3. **Source maps** were being generated for the production build and included in the Pages output directory. Source maps can be 2-3x the size of the source they map; the `_worker.js.map` file alone was 9 MB, and while Pages doesn't deploy `.map` files to the Worker, the build output directory check counts all files during the upload step.

## The Fix

```javascript
// next.config.js — fixed
import { execSync } from 'child_process';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 1. Enable minification (required for staying under 25MB)
  swcMinify: true,

  // 2. Exclude source maps from production builds
  productionBrowserSourceMaps: false,

  webpack: (config, { isServer, dev }) => {
    if (!dev && isServer) {
      // 3. Exclude pdfjs worker from server bundle — it's browser-only
      config.resolve.alias = {
        ...config.resolve.alias,
        'pdfjs-dist/build/pdf.worker.entry': false,
      };
    }

    // 4. Enable module concatenation (scope hoisting) for better tree-shaking
    config.optimization = {
      ...config.optimization,
      concatenateModules: true,
    };

    return config;
  },

  // 5. Mark pdfjs worker as external on server (never bundle for SSR)
  serverExternalPackages: ['pdfjs-dist'],
};

export default nextConfig;
```

```typescript
// components/PdfViewer.tsx — fix pdfjs browser-only usage
import dynamic from 'next/dynamic';

// GOOD: never import pdfjs in SSR context
const PdfViewerClient = dynamic(
  () => import('./PdfViewerClient'), // contains the pdfjs import
  {
    ssr: false, // excludes pdfjs-dist from _worker.js entirely
    loading: () => <div>Loading PDF viewer...</div>,
  }
);

export default function PdfViewer({ url }: { url: string }) {
  return <PdfViewerClient url={url} />;
}
```

```typescript
// lib/dates.ts — fix tree-shaking for date-fns
// BAD: import * as dateFns from 'date-fns';
// GOOD: named imports only
import { format, parseISO, differenceInDays } from 'date-fns';

export function formatReleaseDate(isoDate: string): string {
  return format(parseISO(isoDate), 'MMM d, yyyy');
}

export function daysUntilExpiry(isoDate: string): number {
  return differenceInDays(parseISO(isoDate), new Date());
}
```

```json
// public/_routes.json — offload static assets to Pages CDN, out of the Worker
// This reduces the Worker's surface area to SSR routes only
{
  "version": 1,
  "include": ["/api/*", "/", "/_next/image"],
  "exclude": ["/_next/static/*", "/images/*", "/fonts/*", "/favicon.ico"]
}
```

```bash
# After fix: verify bundle size before deploying
du -sh .next/standalone/*
# Target: _worker.js should be < 20MB (5MB headroom below 25MB limit)

# Check compressed size (closer to what Pages actually measures)
gzip -c .next/standalone/_worker.js | wc -c | awk '{printf "%.1f MB\n", $1/1024/1024}'
# Target: < 10MB compressed
```

## Prevention

```bash
#!/usr/bin/env bash
# scripts/check-bundle-size.sh — run in CI before deploy
set -euo pipefail

BUILD_DIR=".next/standalone"
WORKER_FILE="${BUILD_DIR}/_worker.js"
MAX_SIZE_MB=20  # 5MB headroom under the 25MB Pages limit

if [ ! -f "$WORKER_FILE" ]; then
  echo "ERROR: ${WORKER_FILE} not found — did the build succeed?"
  exit 1
fi

ACTUAL_MB=$(du -m "$WORKER_FILE" | cut -f1)
echo "_worker.js size: ${ACTUAL_MB} MB (limit: ${MAX_SIZE_MB} MB)"

if [ "$ACTUAL_MB" -gt "$MAX_SIZE_MB" ]; then
  echo "ERROR: _worker.js (${ACTUAL_MB}MB) exceeds size budget (${MAX_SIZE_MB}MB)"
  echo "Run: npx @next/bundle-analyzer to find large packages"
  exit 1
fi

echo "Bundle size OK: ${ACTUAL_MB} MB"
```

```javascript
// next.config.js: add bundle analyzer for local investigation
// Run: ANALYZE=true npm run build
import BundleAnalyzer from '@next/bundle-analyzer';

const withBundleAnalyzer = BundleAnalyzer({
  enabled: process.env.ANALYZE === 'true',
});

export default withBundleAnalyzer(nextConfig);
```

```yaml
# .github/workflows/pages-deploy.yml — add size gate to CI
name: Pages Deploy
on: [push]
jobs:
  build-and-size-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build
      - name: Check bundle size
        run: bash scripts/check-bundle-size.sh
      - name: Deploy to Pages
        run: npx wrangler pages deploy .next/standalone
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Anti-patterns

- **Adding npm packages without auditing bundle impact** — Every package added to a Pages/Workers deployment should be checked with `du -sh` or a bundle analyzer before merging.
- **`import *` from large libraries** — Namespace imports defeat tree-shaking in most bundlers; always use named imports for libraries like `date-fns`, `lodash`, `ramda`.
- **Importing browser-only libraries in SSR paths** — Libraries like `pdfjs-dist`, `canvas`, `three.js`, and `leaflet` are browser-only; importing them in SSR routes bloats the Worker bundle with irrelevant code.
- **Source maps in Pages output** — Production source maps belong in an error tracking service (Sentry, Datadog), not in the deployed artifact.
- **No bundle size gate in CI** — Without a size check, the first indication of a bundle size breach is a failed deploy — which may happen during a critical release window.

---

## Gotchas

- The 25 MB limit is for the **uncompressed** Worker script; the 10 MB limit is for the **gzip-compressed** script. Both limits apply. Build output checks usually report uncompressed size.
- `@cloudflare/next-on-pages` bundles ALL API routes and SSR pages into `_worker.js` — there is no per-route splitting in the current version; every route shares the same 25 MB budget.
- `_routes.json` in the `public/` directory controls which paths are handled by the Worker vs. served as static files from the Pages CDN — using it correctly can dramatically reduce what needs to be in the Worker.
- `wrangler pages deploy` and the Pages Git integration use the same upload endpoint and enforce the same limits; a deploy that fails in CI will also fail when triggered from the Pages dashboard.
- `serverExternalPackages` in `next.config.js` marks packages as external for Node.js SSR but does NOT help for Cloudflare Pages, which uses the Edge runtime, not Node.js. Use `ssr: false` dynamic imports for browser-only packages.
- Cloudflare Pages caches build artifacts — if bundle size is fixed but the Pages cache serves an old `_worker.js`, trigger a cache purge from the Pages dashboard or add `--no-bundle` flag to the deploy command.

---

## Verification

```bash
# Measure worker bundle size before and after fix
du -sh .next/standalone/_worker.js

# Compressed size (what Cloudflare actually measures for the 10MB limit)
gzip -c .next/standalone/_worker.js | wc -c | \
  awk '{printf "Compressed: %.2f MB\n", $1/1024/1024}'

# Identify largest dependencies in the bundle (requires @next/bundle-analyzer)
ANALYZE=true npm run build
# Opens browser with interactive treemap of bundle contents

# Check _routes.json is applied correctly — Pages should serve static assets from CDN
curl -I https://your-app.pages.dev/_next/static/chunks/main.js | grep 'cf-cache-status'
# Should show: cf-cache-status: HIT (served from Pages CDN, not Worker)

# After deploy: verify Pages deploy succeeded and worker size is within limits
npx wrangler pages deployment list --project-name your-project | head -5
```

---

## Related

- `lessons-workers-wasm-memory-limit.md`
- `lessons-workers-subrequest-fan-out-limit.md`

---

## Sources

- Cloudflare Workers Script Size Limits — https://developers.cloudflare.com/workers/platform/limits/#script-size
- Cloudflare Pages _routes.json — https://developers.cloudflare.com/pages/configuration/serving-pages/#route-matching
- @cloudflare/next-on-pages — https://github.com/cloudflare/next-on-pages
- Next.js Bundle Analyzer — https://nextjs.org/docs/app/building-your-application/optimizing/bundle-analyzer
- next.config.js serverExternalPackages — https://nextjs.org/docs/app/api-reference/next-config-js/serverExternalPackages
