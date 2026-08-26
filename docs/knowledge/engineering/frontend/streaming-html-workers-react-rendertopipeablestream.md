# Streaming HTML with Cloudflare Workers and React 18 renderToPipeableStream

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Your React app has slow data-fetching components that block the entire HTML response until all data is ready, making Time to First Byte (TTFB) high and the page feel slow. You want the browser to receive and render the shell—header, navigation, above-the-fold layout—immediately, while deferred sections stream in as their data resolves. You are running on Cloudflare Workers (or Pages Functions), not Node.js, so the standard `renderToPipeableStream` Node.js stream adapter cannot be used directly.

---

## Context

React 18 introduced two server rendering APIs:

- `renderToPipeableStream` — designed for Node.js Writable streams.
- `renderToReadableStream` — designed for the **Web Streams API** (`ReadableStream`), which is what Cloudflare Workers natively expose.

Cloudflare Workers support the Web Streams API (`ReadableStream`, `TransformStream`, `WritableStream`) without any polyfills. `renderToReadableStream` produces a `ReadableStream<Uint8Array>` that can be passed directly into a `new Response(stream)`. Combined with React `<Suspense>` boundaries, this lets your Worker flush the HTML shell immediately and stream `<script>` chunks that hydrate deferred sections as their data arrives—exactly like Next.js App Router's streaming SSR, but running in your own Worker code.

---

## 1. Project Setup

```bash
# Worker with React SSR
npm create cloudflare@latest streaming-ssr -- --type=none
cd streaming-ssr
npm install react react-dom @types/react @types/react-dom
npm install --save-dev wrangler typescript
```

```toml
# wrangler.toml
name = "streaming-ssr"
main = "src/index.tsx"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[build]
command = "npm run build"
```

```json
// tsconfig.json (relevant keys)
{
  "compilerOptions": {
    "jsx": "react-jsx",
    "lib": ["ES2022", "WebWorker"],
    "module": "ESNext",
    "target": "ES2022"
  }
}
```

---

## 2. Streaming Worker Entry Point

```tsx
// src/index.tsx
import { renderToReadableStream } from 'react-dom/server';
import { App } from './components/App';

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Pass request context to the React tree via a simple prop / context
    const stream = await renderToReadableStream(
      <App url={url} />,
      {
        bootstrapScripts: ['/static/client.js'],
        onError(error: unknown) {
          console.error('SSR render error:', error);
        },
      },
    );

    // allReady resolves when ALL Suspense boundaries have resolved.
    // For crawlers / social previews, wait for full render before sending.
    const userAgent = request.headers.get('user-agent') ?? '';
    if (isBot(userAgent)) {
      await stream.allReady;
    }

    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        // No content-length: response is chunked/streamed
        'Transfer-Encoding': 'chunked',
        // Allow Workers to start streaming before it finishes reading upstream
        'X-Content-Type-Options': 'nosniff',
      },
    });
  },
};

function isBot(ua: string): boolean {
  return /Googlebot|Bingbot|Slurp|DuckDuckBot|facebookexternalhit|Twitterbot/i.test(ua);
}
```

---

## 3. App Shell with Suspense Boundaries

```tsx
// src/components/App.tsx
import { Suspense } from 'react';
import { Header } from './Header';
import { HeroSection } from './HeroSection';
import { ProductList } from './ProductList';
import { RecommendedItems } from './RecommendedItems';

interface AppProps {
  url: URL;
}

export function App({ url }: AppProps) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Streaming SSR Demo</title>
        <link rel="stylesheet"  />
      </head>
      <body>
        {/* Shell — renders immediately, no async deps */}
        <Header />

        {/* Above-the-fold hero — also synchronous */}
        <HeroSection />

        {/* Product list suspends on async data */}
        <Suspense fallback={<ProductListSkeleton />}>
          <ProductList category={url.searchParams.get('category') ?? 'all'} />
        </Suspense>

        {/* Recommendations stream in last */}
        <Suspense fallback={<RecommendationsSkeleton />}>
          <RecommendedItems />
        </Suspense>
      </body>
    </html>
  );
}

function ProductListSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading products" className="grid grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-48 bg-gray-200 animate-pulse rounded" />
      ))}
    </div>
  );
}

function RecommendationsSkeleton() {
  return <div aria-busy="true" className="h-32 bg-gray-100 animate-pulse rounded mt-8" />;
}
```

---

## 4. Data Fetching inside Suspense Components

React's server-side Suspense requires components to throw a Promise (or use a framework's `use()` / data router). The cleanest approach in a raw Worker context is a simple `use()` wrapper with a per-request cache to avoid duplicate fetches:

```typescript
// src/lib/serverFetch.ts
// A request-scoped in-memory cache: one Map per Worker invocation.
const cache = new Map<string, Promise<unknown>>();

export function createFetchCache() {
  return {
    fetch<T>(url: string, init?: RequestInit): T {
      if (!cache.has(url)) {
        cache.set(url, globalThis.fetch(url, init).then((r) => r.json()));
      }
      // React will call the component multiple times; throw the promise each time
      // until it resolves.
      const promise = cache.get(url)!;
      // @ts-expect-error — internal React use() mechanism
      throw promise;
    },
    clear() { cache.clear(); },
  };
}
```

Or, using React 19's `use()` with a pre-fetched promise:

```tsx
// src/components/ProductList.tsx
import { use } from 'react';

async function fetchProducts(category: string): Promise<Product[]> {
  const res = await fetch(`https://api.example.com/products?category=${category}`, {
    // cf: { cacheTtl: 60 }  — uncomment when running inside a Worker fetch handler
  });
  if (!res.ok) throw new Error('Failed to load products');
  return res.json();
}

// Pre-fetch during render — React will suspend until the promise resolves
const productsCache = new Map<string, Promise<Product[]>>();

function getProducts(category: string): Promise<Product[]> {
  if (!productsCache.has(category)) {
    productsCache.set(category, fetchProducts(category));
  }
  return productsCache.get(category)!;
}

interface ProductListProps {
  category: string;
}

export function ProductList({ category }: ProductListProps) {
  // `use()` suspends the component until the promise resolves
  const products = use(getProducts(category));

  return (
    <ul className="grid grid-cols-3 gap-4">
      {products.map((product) => (
        <li key={product.id} className="border rounded p-4">
          <img src={product.imageUrl} alt={product.name} loading="lazy" />
          <h3 className="font-semibold mt-2">{product.name}</h3>
          <p className="text-gray-600">${product.price}</p>
        </li>
      ))}
    </ul>
  );
}
```

---

## 5. Client Hydration

```tsx
// src/client.tsx  (bundled separately for the browser)
import { hydrateRoot } from 'react-dom/client';
import { App } from './components/App';

const url = new URL(location.href);
hydrateRoot(document, <App url={url} />);
```

The `bootstrapScripts` option in `renderToReadableStream` injects `<script >` before `</body>`. React hydrates incrementally—each Suspense boundary re-hydrates as its streamed content arrives—so interactive regions are not blocked by slow sections.

---

## 6. Error Handling in Suspended Boundaries

```tsx
// src/components/ErrorBoundary.tsx
import { Component, type ReactNode } from 'react';

interface Props { children: ReactNode; fallback: ReactNode; }
interface State { hasError: boolean; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError() { return { hasError: true }; }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
```

Wrap each Suspense with an error boundary so a failing data fetch degrades gracefully:

```tsx
<ErrorBoundary fallback={<p>Failed to load products. <a href="">Retry</a></p>}>
  <Suspense fallback={<ProductListSkeleton />}>
    <ProductList category={category} />
  </Suspense>
</ErrorBoundary>
```

---

## 7. Measuring Streaming Performance

```bash
# Confirm streaming: Connection stays open during render
curl -N -v https://streaming-ssr.your-subdomain.workers.dev/ 2>&1 | head -30
# Look for "Transfer-Encoding: chunked" in response headers

# Measure TTFB with curl
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" \
  https://streaming-ssr.your-subdomain.workers.dev/

# WebPageTest trace will show shell HTML arriving first,
# then Suspense chunks arriving as data resolves
```

---

## Anti-Patterns

- **Using `renderToPipeableStream` in a Worker** — It requires Node.js `stream.Writable`. Workers have no Node.js streams without a compatibility shim. Use `renderToReadableStream` which is designed for the Web Streams API.
- **Putting `await stream.allReady` before every response** — This defeats streaming: the entire React tree must resolve before any bytes are sent. Only await `allReady` for bots; send `stream` immediately for browser clients.
- **Suspense boundaries wrapping entire page routes** — A single top-level Suspense means nothing streams until all data is ready. Place boundaries around individual slow sections so the shell arrives instantly.
- **Fetching data in `useEffect` after hydration** — This causes a visible cascade: shell renders on server, hydrates on client, then data loads client-side. Fetch on the server and pass data through Suspense / `use()` instead.
- **Using `renderToString` with streaming intent** — `renderToString` is synchronous and buffers the entire tree; it has no Suspense streaming support. Migrate to `renderToReadableStream`.

---

## Gotchas

- **`use()` cache scope**: The per-request `productsCache` Map in the example above leaks across requests in a long-lived Worker isolate. Reset it at the start of each `fetch()` handler invocation, or scope the cache inside the render call.
- **`bootstrapScripts` path**: The path must be an absolute path from the root (`/static/client.js`), not relative. If your static assets are served from a different origin or R2 bucket, use `bootstrapScriptContent` with an inline bootstrap instead.
- **Hydration mismatches**: The server-rendered HTML must match what `hydrateRoot` expects. If your component reads `window` or `navigator` during render it will produce different output between server and client. Guard with `typeof window !== 'undefined'`.
- **Cloudflare's response buffering**: Cloudflare's CDN may buffer streamed responses for cache inspection. Set `Cache-Control: no-store` or use a Cache API bypass rule for SSR routes to prevent buffering from negating your streaming TTFB gains.
- **`onError` and `onShellError` distinction**: `onError` fires for errors inside Suspense boundaries (the shell still sends). `onShellError` fires when the synchronous shell itself throws—at that point the stream is broken and you must send a fallback response. Handle both separately.

---

## Verification

```bash
# 1. Shell arrives before Suspense content resolves
curl -N https://your-app.workers.dev/ | head -c 500
# Should show <header>, <nav>, etc. before product list HTML

# 2. Bots get fully-rendered HTML
curl -A "Googlebot" -s https://your-app.workers.dev/ | grep 'product-name'
# Should find product names (allReady was awaited)

# 3. Browser clients get chunked response
curl -I https://your-app.workers.dev/
# Expect: Transfer-Encoding: chunked  (or no Content-Length)

# 4. Wrangler tail for SSR errors
wrangler tail streaming-ssr --format pretty | grep 'SSR render error'
```

---

## Related

- `react-19-server-components-streaming-ssr.md`
- `react-suspense-boundaries.md`
- `react-suspense-cloudflare-pages-ssr-edge.md`
- `nextjs-partial-prerendering-cloudflare.md`
- `server-sent-events-streaming-ui.md`

---

## Sources

- `renderToReadableStream` — https://react.dev/reference/react-dom/server/renderToReadableStream
- Cloudflare Workers Web Streams — https://developers.cloudflare.com/workers/runtime-apis/streams/
- React Suspense for data fetching — https://react.dev/reference/react/Suspense
- `use()` RFC — https://github.com/reactjs/rfcs/pull/229
