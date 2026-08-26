# Million.js React Optimization on Cloudflare Workers SSR

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

React apps served via Cloudflare Workers SSR suffer from slow hydration and large reconciler overhead when rendering dense data tables or lists. Million.js replaces React's virtual DOM diffing with a block-based compiler optimisation that dramatically reduces reconciler work. Integrating it into a Workers SSR pipeline requires careful handling of the compiler plugin, edge-compatible builds, and streaming output.

## Context

Million.js works by statically analysing JSX at build time and emitting "block" components that bypass the standard React reconciler for stable subtrees. In a Cloudflare Workers SSR context (using `react-dom/server`'s `renderToReadableStream`) the compiler must run during the Vite/webpack build step that targets the worker bundle. The runtime overhead added by Million's block wrapper is negligible on the edge, while the CPU savings during re-renders on the client side are significant. The key constraint is that `million/react` must be imported from the edge-compatible CJS/ESM bundle; the default package entry is safe for Workers because it contains no Node-specific APIs.

## Installing and Configuring the Compiler Plugin

```typescript
// vite.config.ts  (worker + client shared config)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import million from "million/compiler";

export default defineConfig({
  plugins: [
    // million must come BEFORE the React plugin
    million.vite({
      // auto mode wraps eligible components automatically
      auto: true,
      // exclude components that use context or refs heavily
      filter: {
        exclude: ["**/node_modules/**", "**/src/editor/**"],
      },
    }),
    react(),
  ],
  build: {
    rollupOptions: {
      // separate worker entry from client entry
      input: {
        client: "src/client.tsx",
        worker: "src/worker.ts",
      },
    },
  },
});
```

## Worker SSR Entry with Streaming

```typescript
// src/worker.ts
import { renderToReadableStream } from "react-dom/server";
import { createElement } from "react";
import App from "./App";

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Pass route info to the app so it can render the correct page
    const stream = await renderToReadableStream(
      createElement(App, { pathname: url.pathname }),
      {
        bootstrapScripts: ["/client.js"],
        onError(error: unknown) {
          console.error("SSR error:", error);
        },
      }
    );

    // Let the browser start painting immediately
    await stream.allReady;

    return new Response(stream, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        // Cloudflare will compress automatically
        "Cache-Control": "public, max-age=0, must-revalidate",
      },
    });
  },
};
```

## Block Components for Data-Heavy Lists

```typescript
// src/components/ProductTable.tsx
import { block } from "million/react";
import React from "react";

interface Product {
  id: string;
  name: string;
  price: number;
  stock: number;
}

// block() wraps the component at build time; the compiler emits
// a static template with only the changing values as "holes"
const ProductRow = block(function ProductRow({ product }: { product: Product }) {
  return (
    <tr key={product.id}>
      <td className="px-4 py-2 font-mono text-sm">{product.id}</td>
      <td className="px-4 py-2">{product.name}</td>
      <td className="px-4 py-2 tabular-nums">
        {new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
        }).format(product.price)}
      </td>
      <td
        className={`px-4 py-2 ${product.stock < 10 ? "text-red-600" : "text-green-600"}`}
      >
        {product.stock}
      </td>
    </tr>
  );
});

export function ProductTable({ products }: { products: Product[] }) {
  return (
    <table className="w-full border-collapse text-left">
      <thead>
        <tr>
          <th className="border-b px-4 py-2">ID</th>
          <th className="border-b px-4 py-2">Name</th>
          <th className="border-b px-4 py-2">Price</th>
          <th className="border-b px-4 py-2">Stock</th>
        </tr>
      </thead>
      <tbody>
        {products.map((p) => (
          <ProductRow key={p.id} product={p} />
        ))}
      </tbody>
    </table>
  );
}
```

## Fetching Data at the Edge Before SSR

```typescript
// src/worker.ts  (extended with KV data fetch)
import { renderToReadableStream } from "react-dom/server";
import { createElement } from "react";
import App from "./App";

export interface Env {
  PRODUCT_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Fetch from KV before streaming so SSR has data synchronously
    const raw = await env.PRODUCT_KV.get("products:all", { type: "json" });
    const products = (raw as { id: string; name: string; price: number; stock: number }[]) ?? [];

    const stream = await renderToReadableStream(
      createElement(App, { pathname: url.pathname, products }),
      { bootstrapScripts: ["/client.js"] }
    );

    await stream.allReady;

    return new Response(stream, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  },
};
```

## Anti-patterns

- Wrapping components that consume React context with `block()` — Million's static template cannot track context changes and will silently serve stale values.
- Placing the Million compiler plugin **after** the React plugin in the Vite config; it must transform JSX before the React transform runs.
- Using `renderToPipeableStream` (Node streams API) in a Workers environment — always use `renderToReadableStream` which returns a WHATWG `ReadableStream`.

## Gotchas

- Million's `auto` mode skips components that contain hooks with dynamic dependencies; inspect the build output with `MILLION_DEBUG=1` to confirm which components were actually wrapped.
- The `block()` call must wrap a named function expression, not an arrow function, otherwise the compiler cannot extract a stable template name and falls back to standard React rendering.

## Verification

```bash
# Build and preview locally with Wrangler
npx wrangler pages dev dist --compatibility-date=2025-01-01

# Confirm block components appear in the bundle
grep -r "million" dist/worker.js | head -5

# Measure reconciler call count in browser devtools
# React DevTools Profiler > Flamegraph: blocks show as single commit entries
```

## Related

- `frontend/react-19-server-components-streaming-ssr.md`
- `frontend/streaming-html-workers-react-rendertopipeablestream.md`
- `frontend/react-suspense-cloudflare-pages-ssr-edge.md`

## Sources

- https://million.dev/docs
- https://developers.cloudflare.com/workers/runtime-apis/streams/readable-stream/
- https://react.dev/reference/react-dom/server/renderToReadableStream
