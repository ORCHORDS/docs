# Cloudflare Pages Static Asset Chunking and Code Splitting

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Pages site ships a single `app.js` bundle of 1.8 MB (uncompressed). First
Contentful Paint is 4.5 s on a mid-range mobile device. Lighthouse reports "Reduce initial
JavaScript" and "Remove unused JavaScript". Users on the homepage wait for code that is only
needed on the checkout or dashboard routes.

---

## Context

Cloudflare Pages serves static assets from Cloudflare's global edge network with automatic
long-lived cache headers (`Cache-Control: public, max-age=31536000, immutable`) applied to
any asset whose filename contains a content hash. The CDN layer is not the bottleneck — the
bottleneck is the browser: JavaScript must be downloaded, parsed, and compiled before the
page renders, and a large monolithic bundle blocks the main thread for hundreds of
milliseconds even when served from a nearby edge node.

Code splitting divides the JavaScript graph into smaller chunks that are:

- **Initial chunk** — the minimal JS required to render the first screen
- **Route chunks** — loaded lazily when the user navigates to a route
- **Vendor chunks** — third-party libraries that change rarely (long cache lifetime)
- **Async feature chunks** — heavy features (maps, rich text editors) loaded on demand

Cloudflare Pages integrates with Vite, Next.js on Pages, Astro, and any static-site
generator; the code-splitting strategy is configured in the build tool, not in Pages itself.

---

## Vite / Rollup Manual Chunks Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Split vendor libraries into a stable chunk that caches independently
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            // Group large, rarely-changing libraries into named chunks
            if (id.includes('react') || id.includes('react-dom')) {
              return 'vendor-react';
            }
            if (id.includes('@tanstack/react-query')) {
              return 'vendor-query';
            }
            if (id.includes('date-fns') || id.includes('luxon')) {
              return 'vendor-date';
            }
            // Everything else: one shared vendor chunk
            return 'vendor';
          }
        },
        // Ensure chunk filenames contain content hash for cache busting
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
    // Warn when any individual chunk exceeds 200 kB (gzipped target: ~60 kB)
    chunkSizeWarningLimit: 200,
  },
});
```

---

## Route-Based Dynamic Imports

```typescript
// src/router.tsx (React Router v6 example)
import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

// These imports create separate chunk files at build time
const Home = lazy(() => import('./routes/Home'));
const Checkout = lazy(() => import('./routes/Checkout'));
const Dashboard = lazy(() => import('./routes/Dashboard'));
const Settings = lazy(() => import('./routes/Settings'));

const router = createBrowserRouter([
  {
    path: '/',
    element: <Suspense fallback={<PageSkeleton />}><Home /></Suspense>,
  },
  {
    path: '/checkout',
    element: <Suspense fallback={<PageSkeleton />}><Checkout /></Suspense>,
  },
  {
    path: '/dashboard',
    element: <Suspense fallback={<PageSkeleton />}><Dashboard /></Suspense>,
  },
  {
    path: '/settings',
    element: <Suspense fallback={<PageSkeleton />}><Settings /></Suspense>,
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

Vite detects `import()` expressions and automatically splits the imported module (and its
unique dependency subgraph) into a separate chunk file.

---

## Preloading Critical Route Chunks

Dynamic import splits reduce initial load but add a waterfall: the user navigates → the route
chunk is requested → there is a brief flash of `<PageSkeleton>`. Mitigate with `<link
rel="modulepreload">` for the most likely next routes:

```typescript
// Preload the checkout chunk when the user hovers over the CTA
function ProductPage() {
  const preloadCheckout = () => import('./routes/Checkout');

  return (
    <button
      onMouseEnter={preloadCheckout}
      onFocus={preloadCheckout}
      onClick={() => navigate('/checkout')}
    >
      Buy Now
    </button>
  );
}
```

For server-rendered pages (Astro, Next.js on Pages), inject modulepreload link headers:

```typescript
// Cloudflare Pages Function: functions/_middleware.ts
export async function onRequest(context: EventContext<Env, string, Record<string, unknown>>) {
  const response = await context.next();

  if (response.headers.get('Content-Type')?.includes('text/html')) {
    const newResponse = new Response(response.body, response);
    // Hint the browser to preload the main app chunk
    newResponse.headers.append(
      'Link',
      '</assets/vendor-react-abc123.js>; rel="modulepreload"; as="script"',
    );
    return newResponse;
  }

  return response;
}
```

---

## Async Feature Chunks for Heavy Dependencies

```typescript
// Load a rich text editor only when the user clicks "Edit"
async function openEditor() {
  const { Editor } = await import('./components/RichTextEditor');
  // Editor and its ~400 kB dependency tree load only here
  mountEditor(Editor);
}

// Load a charting library only on the analytics dashboard
const ChartComponent = lazy(async () => {
  const { Chart } = await import('chart.js/auto');
  const { default: ChartWrapper } = await import('./components/ChartWrapper');
  // Registers Chart.js dependency into the module graph
  return { default: ChartWrapper };
});
```

---

## Cloudflare Pages Build Configuration

```toml
# wrangler.toml (for Pages projects using Wrangler)
[site]
bucket = "./dist"

# Ensure build output directory is correct
build_dir = "dist"

# Build command (adjust per framework)
build_command = "npm run build"
```

Pages automatically applies `Cache-Control: public, max-age=31536000, immutable` to assets
in `_headers` or via its automatic header injection when filenames contain a hash. Do not
override this header for hashed asset filenames — it maximises cache lifetime on Cloudflare's
edge and in browser caches.

---

## Bundle Analysis Workflow

```bash
# Vite bundle visualiser (run locally after build)
npx vite-bundle-visualizer

# Or use rollup-plugin-visualizer in vite.config.ts
# npm install -D rollup-plugin-visualizer
```

```typescript
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({
      filename: 'dist/stats.html',
      gzipSize: true,
      brotliSize: true,
      open: true, // Open in browser after build
    }),
  ],
});
```

Target metrics after splitting:
- Initial JS (all synchronously loaded chunks): < 100 kB gzipped
- Largest individual route chunk: < 50 kB gzipped
- Vendor-react chunk: ~40 kB gzipped (React 18 + ReactDOM)

---

## Anti-patterns

**One giant `manualChunks: () => 'vendor'`.** Putting *all* node_modules into a single vendor
chunk creates a monolith that invalidates on every dependency update, defeating long-term
caching. Split stable libraries (React, date utilities) from frequently updated ones.

**Dynamic importing within a render function.** `const mod = await import('./foo')` inside a
React component body re-imports on every render. Use `lazy()` + `Suspense` or import at
module scope with a deferred initialisation pattern.

**No `<Suspense>` boundary.** A `lazy()` component without `<Suspense>` throws an error on
first load. Always wrap lazy components in `<Suspense fallback={...}>`.

**Chunking below 5 kB.** Hundreds of tiny chunks add HTTP/2 stream overhead and increase
browser fetch parallelism limits. Rollup's `minSize` option (default 1 kB) coalesces tiny
modules. Do not set `manualChunks` so aggressively that you produce sub-5 kB chunks.

**Ignoring CSS code splitting.** In Vite, CSS imported inside a lazy route is automatically
split into a per-chunk CSS file and loaded only when the route chunk is requested. Do not
manually inline all CSS into the HTML `<head>` — it re-introduces the blocking problem for
styles only needed on specific routes.

---

## Gotchas

- **Shared dependencies are deduplicated by Rollup** — if both `Checkout` and `Dashboard`
  import `zod`, Rollup creates a shared chunk. This is correct behaviour; do not fight it
  by duplicating the import.

- **`import.meta.glob` is evaluated at build time.** Using Vite's glob import to load all
  route files creates static imports, not dynamic ones — you lose the code-split benefit.
  Use individual `import()` calls for lazy routes.

- **Content hash stability.** If chunk A depends on chunk B and B's content changes, A's
  hash also changes (because A embeds the import path of B, which includes B's hash). Use
  Vite's `build.modulePreload.polyfill: false` and Rollup's `experimentalMinChunkSize` to
  stabilise hashes where possible.

- **Cloudflare Pages upload limit.** Pages has a limit of 20 000 files per deployment. Very
  aggressive code splitting (one chunk per component) can approach this limit on large apps.
  Keep the total chunk count under 500 for comfort.

---

## Verification

1. Run `npm run build && npx serve dist` locally; open DevTools → Network → JS filter.
   Confirm only the initial chunks load on page load and route chunks load on navigation.
2. Run Lighthouse in Chrome DevTools; confirm "Reduce initial JavaScript" no longer appears
   or that flagged chunks are below 50 kB.
3. After deploying to Pages, inspect `cf-cache-status: HIT` on chunk files on second load.
4. Check Pages deployment log for "Total upload size" — ensure it is within limits.

---

## Related

- `workers-bundle-size-optimization-tree-shaking.md`
- `nextjs-cloudflare-pages-bundle-optimization.md`
- `pages-functions-bundle-size-optimization.md`
- `dead-code-elimination.md`
- `javascript-bundle-size.md`
- `resource-hints-preload.md`

---

## Sources

- Vite code splitting guide: https://vitejs.dev/guide/build.html#chunking-strategy
- Rollup output options: https://rollupjs.org/configuration-options/#output-manualchunks
- Cloudflare Pages headers: https://developers.cloudflare.com/pages/configuration/headers/
- Cloudflare Pages limits: https://developers.cloudflare.com/pages/platform/limits/
- web.dev code splitting: https://web.dev/articles/code-splitting-suspense
