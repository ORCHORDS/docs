# React 19 Resource Loading: preload, preinit, and prefetchDNS

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Critical fonts, scripts, and stylesheets load late because your React app renders `<link>` and `<script>` tags deep inside components, far from `<head>`. LCP suffers because the browser discovers these resources too late during HTML parsing.

## Context
React 19 added a first-party resource-loading API (`react-dom`) that hoists hints directly into `<head>` during server-side rendering, regardless of where in the component tree they are called. Unlike manual `<link rel="preload">` tags, these hints are deduplicated automatically and can be called inside any component, including Server Components, without prop-drilling the resource URL up to a layout. They are especially effective when combined with Cloudflare Pages/Workers SSR, where the edge sends HTTP `Early Hints (103)` before the full HTML response.

## Core API Surface

```typescript
// All imports from 'react-dom' — no separate package needed in React 19
import {
  prefetchDNS,
  preconnect,
  preload,
  preloadModule,
  preinit,
  preinitModule,
} from 'react-dom';

// DNS prefetch only — lowest cost, no connection kept open
prefetchDNS('https://fonts.gstatic.com');

// Open a TCP+TLS connection (no resource fetched yet)
preconnect('https://cdn.example.com', { crossOrigin: 'anonymous' });

// Fetch and cache a resource — does NOT execute scripts or apply stylesheets
preload('https://cdn.example.com/hero.webp', { as: 'image', fetchPriority: 'high' });
preload('/fonts/inter-var.woff2', { as: 'font', crossOrigin: 'anonymous' });

// Fetch AND execute/apply — for scripts and stylesheets that must run before paint
preinit('https://cdn.example.com/analytics.js', { as: 'script' });
preinit('/styles/critical.css', { as: 'style', precedence: 'high' });

// ES module variants
preloadModule('/js/chart-worker.js', { as: 'script' });
preinitModule('/js/main.js', { as: 'script', crossOrigin: 'anonymous' });
```

## Usage in Server Components

```tsx
// app/page.tsx  (Next.js App Router / Cloudflare Pages with Workers SSR)
import { preload, preconnect, prefetchDNS } from 'react-dom';

export default async function HomePage() {
  // Called at render time — React batches and deduplicates into <head>
  prefetchDNS('https://api.example.com');
  preconnect('https://images.example.com', { crossOrigin: 'use-credentials' });
  preload('/fonts/inter-var.woff2', {
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  });

  const data = await fetch('https://api.example.com/hero', {
    next: { revalidate: 3600 },
  }).then((r) => r.json() as Promise<{ headline: string; imageUrl: string }>);

  return (
    <main>
      <h1>{data.headline}</h1>
      <img src={data.imageUrl} alt="Hero" width={1200} height={630} />
    </main>
  );
}
```

## Dynamic Resource Hints Based on Route Data

```tsx
// app/product/[id]/page.tsx
import { preload } from 'react-dom';

interface Product {
  id: string;
  name: string;
  imageUrl: string;
  videoUrl?: string;
}

export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await fetch(`https://api.example.com/products/${params.id}`).then(
    (r) => r.json() as Promise<Product>
  );

  // Preload the above-the-fold product image BEFORE the component renders
  preload(product.imageUrl, { as: 'image', fetchPriority: 'high' });

  // Conditionally preload video — only if the product has one
  if (product.videoUrl) {
    preload(product.videoUrl, { as: 'video' });
  }

  return (
    <article>
      <h1>{product.name}</h1>
      <img src={product.imageUrl} alt={product.name} />
      {product.videoUrl && <video src={product.videoUrl} controls />}
    </article>
  );
}
```

## Cloudflare Workers: Early Hints Integration

```typescript
// workers/ssr-handler.ts
// Cloudflare Pages Functions / Workers SSR — send 103 Early Hints
// before streaming the React HTML to further reduce resource discovery latency

export default {
  async fetch(request: Request): Promise<Response> {
    // Send 103 Early Hints for critical assets
    // This is sent immediately while the Worker processes the request
    const earlyHints = new Response(null, {
      status: 103,
      headers: {
        Link: [
          '</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin=anonymous',
          '</styles/critical.css>; rel=preload; as=style',
          '<https://api.example.com>; rel=preconnect',
        ].join(', '),
      },
    });

    // Cloudflare automatically sends 103 when the response is returned to the edge;
    // your fetch handler returns 103 and the edge buffers it while awaiting the 200.
    // (Actual usage depends on Pages Functions early hints support — see docs.)

    const html = await renderReactApp(request);
    return new Response(html, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=0, must-revalidate',
      },
    });
  },
} satisfies ExportedHandler;

async function renderReactApp(_request: Request): Promise<string> {
  // Placeholder — integrate with your React SSR pipeline
  return '<!doctype html><html>...</html>';
}
```

## Stylesheet Precedence Ordering

```tsx
// React 19 stylesheet precedence controls insertion order in <head>
// Lower precedence values are inserted earlier (applied first, lower specificity wins last)
import { preinit } from 'react-dom';

function ThemeProvider({ theme }: { theme: 'light' | 'dark' }) {
  // Base styles load first
  preinit('/styles/base.css', { as: 'style', precedence: 'low' });
  // Component styles override base
  preinit('/styles/components.css', { as: 'style', precedence: 'medium' });
  // Theme tokens override components
  preinit(`/styles/theme-${theme}.css`, { as: 'style', precedence: 'high' });

  return <>{/* children */}</>;
}
```

## Anti-patterns
- Calling `preload`/`preinit` inside `useEffect` — these only work at render time (server and client initial render); effects run after paint, defeating the purpose
- Using `preinit` for large third-party scripts that are not render-blocking — prefer `preload` + deferred execution to avoid blocking the main thread
- Preloading every image on the page — limit `preload` to LCP candidates and above-the-fold resources; over-preloading competes with critical resources for bandwidth
- Mixing `preinit` with `<link>` tags for the same stylesheet — React deduplicates `preinit` calls but not `<link>` tags; you'll get duplicate requests
- Ignoring `precedence` on `preinit` stylesheets — without it, React inserts them in render order which may not match your cascade intent

## Gotchas
- `preload` and `preinit` are deduplicated by URL — calling them multiple times with the same URL (even from different components) is safe and results in one `<link>` tag
- These APIs are no-ops in the browser if called after the initial render (`document.head` is already fully populated); they're most valuable in SSR/RSC pipelines
- `crossOrigin: 'anonymous'` is required for font preloads to match browser cache entries — a mismatch causes the browser to download the font twice
- `fetchPriority: 'high'` on `preload` affects the browser's internal priority queue, but the actual boost depends on the browser's loading scheduler
- Cloudflare Pages currently supports HTTP 103 Early Hints via a response header — the Worker must return the 103 before streaming begins for hints to fire before the HTML

## Verification
```bash
# Confirm <link> tags appear in <head> before any component-rendered content
curl -s https://your-site.pages.dev | grep -E '<link rel="preload"'

# Lighthouse: check LCP timing and "Eliminate render-blocking resources"
npx lighthouse https://your-site.pages.dev --only-audits=uses-rel-preload,render-blocking-resources

# WebPageTest waterfall: preloaded resources should start fetching < 100 ms after HTML starts parsing
```

## Related
- [HTML Performance Resource Hints](html-performance-resource-hints.md)
- [Font Loading Optimization](font-loading-optimization.md)
- [HTML Web Vitals LCP](html-web-vitals-lcp.md)
- [React 19 Server Components Streaming SSR](react-19-server-components-streaming-ssr.md)
- [Next.js Font Optimization](next-js-font-optimization.md)

## Sources
- https://react.dev/reference/react-dom#resource-preloading-apis
- https://developers.cloudflare.com/pages/configuration/early-hints/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/103
- https://web.dev/articles/fetch-priority
