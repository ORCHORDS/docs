# Vite Build Configuration Optimized for Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Vite build produces large JavaScript bundles that exceed the Cloudflare Pages 25 MB per-file asset limit, or your CI pipeline fails because a single chunk includes all vendor code. You need chunk splitting, vendor isolation, lazy-loaded routes, and stable asset fingerprinting that survives repeated deployments without busting the CDN cache unnecessarily.

## Context

Cloudflare Pages serves static assets from its global edge network with automatic content-addressed URLs when you use hashed filenames. However, Pages enforces a 25 MB compressed limit per file and a 20,000-file project limit. Vite's default Rollup output places everything in a handful of large chunks; with `rollupOptions.output.manualChunks` you can isolate vendor libraries, split route chunks, and control fingerprinting. The `vite-plugin-cloudflare` package adds first-class Pages support including `import.meta.env.CF_PAGES` injection and Workers build integration.

## Vite Configuration

```typescript
// vite.config.ts
import { defineConfig, splitVendorChunkPlugin } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    cloudflare(),
    // Only generate bundle analysis in CI
    process.env.ANALYZE === '1' &&
      visualizer({ filename: 'dist/stats.html', gzipSize: true }),
  ],
  build: {
    target: 'es2022',
    // Warn at 500 kB, error above Pages' effective threshold
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        // Stable fingerprint: content hash only, no entry name prefix
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        manualChunks(id) {
          // Isolate heavyweight vendor libraries
          if (id.includes('node_modules/react') ||
              id.includes('node_modules/react-dom') ||
              id.includes('node_modules/scheduler')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/@tanstack')) {
            return 'vendor-tanstack';
          }
          if (id.includes('node_modules/')) {
            return 'vendor-misc';
          }
        },
      },
    },
  },
  // Expose CF_PAGES at build time for runtime guards
  define: {
    'import.meta.env.CF_PAGES': JSON.stringify(
      process.env.CF_PAGES ?? '0'
    ),
    'import.meta.env.CF_PAGES_BRANCH': JSON.stringify(
      process.env.CF_PAGES_BRANCH ?? ''
    ),
  },
}));
```

## Dynamic Import Lazy Routes

```typescript
// src/router.tsx
import { createBrowserRouter } from 'react-router-dom';

export const router = createBrowserRouter([
  {
    path: '/',
    lazy: () => import('./pages/Home').then((m) => ({ Component: m.default })),
  },
  {
    path: '/dashboard',
    lazy: () =>
      import('./pages/Dashboard').then((m) => ({ Component: m.default })),
  },
  {
    path: '/settings',
    lazy: () =>
      import('./pages/Settings').then((m) => ({ Component: m.default })),
  },
]);
```

Each `lazy` entry becomes its own Rollup chunk with a content hash. Only the current route chunk is fetched; the router prefetches adjacent routes on `<Link>` hover via React Router's built-in prefetch behavior.

## `import.meta.env.CF_PAGES` Runtime Guards

```typescript
// src/lib/analytics.ts
export function initAnalytics() {
  // Skip analytics on local dev and preview branches
  if (import.meta.env.CF_PAGES !== '1') {
    console.debug('[analytics] skipped — not a Pages production build');
    return;
  }
  if (import.meta.env.CF_PAGES_BRANCH !== 'main') {
    console.debug('[analytics] skipped — preview branch');
    return;
  }
  // Production-only analytics bootstrap
  window._analytics?.init({ project: 'my-app' });
}
```

## CI Asset Fingerprinting

```yaml
# .github/workflows/pages.yml
name: Deploy to Cloudflare Pages
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      # Generate bundle analysis on main
      - run: ANALYZE=1 npm run build
        env:
          CF_PAGES: '1'
          CF_PAGES_BRANCH: ${{ github.ref_name }}
      # Fail CI if any single asset exceeds 20 MB (compressed headroom)
      - name: Check asset sizes
        run: |
          find dist/assets -name '*.js' | while read f; do
            size=$(gzip -c "$f" | wc -c)
            if [ "$size" -gt 20971520 ]; then
              echo "FAIL: $f compressed size ${size} bytes exceeds limit"
              exit 1
            fi
          done
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: pages deploy dist --project-name=my-app
```

## Anti-patterns

- **Single monolithic chunk** — omitting `manualChunks` results in all vendor code in one entry file; a React + Tanstack bundle easily hits 3–4 MB uncompressed.
- **Using `splitVendorChunkPlugin` alone** — it creates only one `vendor` chunk; explicit `manualChunks` gives finer control and avoids re-bundling unchanged libraries on every deploy.
- **Hardcoding `CF_PAGES=true` in `.env`** — this leaks production guards into local dev; always inject via CI environment variables and `define`.
- **Non-hashed asset names** — without content hashes, CDN edges cache stale JS after a deploy; always use `[hash]` in `chunkFileNames`.

## Gotchas

- `vite-plugin-cloudflare` requires Wrangler 3.x and a `wrangler.jsonc` at the project root; missing it causes the plugin to silently skip Workers integration.
- `manualChunks` is called for every module ID including CSS; guard with `id.includes('node_modules/')` to avoid misclassifying source files.
- Cloudflare Pages counts each hashed filename as a distinct file; 10 deploys of a 2,000-file project can approach the 20,000-file limit — use `wrangler pages project purge` periodically.
- `import.meta.env` substitution happens at build time via `define`; accessing it at runtime in a Worker (SSR) context will show the literal string `import.meta.env.CF_PAGES` unless you also inject it in your Workers bundle.

## Verification

```bash
# Build and inspect chunk sizes
npm run build
du -sh dist/assets/*.js | sort -h

# Confirm content hashes are present
ls dist/assets/ | grep -E '[a-f0-9]{8}'

# Check gzip sizes
for f in dist/assets/*.js; do printf "%s\t%s\n" "$(gzip -c $f | wc -c)" "$f"; done | sort -n

# Dry-run Pages deployment
npx wrangler pages deploy dist --project-name=my-app --dry-run
```

## Related

- `react-server-components-cloudflare-workers.md`
- `view-transitions-api-cloudflare-pages.md`

## Sources

- Vite Rollup Options — https://vitejs.dev/config/build-options.html#build-rollupoptions
- Cloudflare Vite Plugin — https://github.com/cloudflare/workers-sdk/tree/main/packages/vite-plugin-cloudflare
- Cloudflare Pages Limits — https://developers.cloudflare.com/pages/platform/limits/
