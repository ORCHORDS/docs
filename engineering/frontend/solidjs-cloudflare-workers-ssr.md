# SolidJS Cloudflare Workers SSR

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

SolidStart applications deployed to Cloudflare Workers fail at runtime when using the default Node.js server preset because SolidJS's streaming SSR relies on `ReadableStream` and the Fetch API, which the Workers runtime natively provides. The solution is to use SolidStart's `cloudflare-pages` adapter, which generates a Workers-compatible entry without Node.js polyfills and wires `server$()` functions to the edge runtime. Teams migrating from a Node/Vercel deployment to Cloudflare gain sub-10ms TTFB from the edge with no changes to component code.

## Context

SolidJS uses fine-grained reactivity rather than a virtual DOM — signals propagate changes directly to the DOM without diffing. This has an important implication for SSR: the server renders HTML synchronously from signal values, and the client "hydrates" by attaching the existing DOM nodes to new signals without re-running render functions. The Workers runtime is an ideal host because SolidStart's streaming renderer produces a WHATWG `ReadableStream` natively. The `@solidjs/start` package (SolidStart v1) ships a `cloudflare-pages` preset that compiles routes to a `_worker.js` Pages Function and places static assets in the build output.

## SolidStart Config with Cloudflare Preset

```typescript
// app.config.ts
import { defineConfig } from "@solidjs/start/config";

export default defineConfig({
  server: {
    preset: "cloudflare-pages",
    // Rollup input options passed through to the worker bundle
    rollupConfig: {
      external: [],
    },
  },
  // SolidStart uses Vinxi under the hood; pass Vite options here
  vite: {
    build: {
      target: "esnext",
    },
  },
});
```

## Typed Environment Bindings via Middleware

```typescript
// src/middleware.ts
import { createMiddleware } from "@solidjs/start/middleware";

export interface CloudflareEnv {
  PRODUCTS_KV: KVNamespace;
  DB: D1Database;
  API_SECRET: string;
}

// Attach bindings to the request event so any server$ function can use them
export default createMiddleware({
  onRequest: [
    (event) => {
      const cf = event.nativeEvent.context?.cloudflare as
        | { env: CloudflareEnv }
        | undefined;

      if (cf) {
        // Store on locals so server$ functions can import from "~/lib/env"
        event.locals.env = cf.env;
      }
    },
  ],
});
```

```typescript
// src/lib/env.ts
import { getRequestEvent } from "solid-js/web";
import type { CloudflareEnv } from "~/middleware";

export function useEnv(): CloudflareEnv {
  const event = getRequestEvent();
  if (!event?.locals.env) {
    throw new Error("Cloudflare env not available outside request context");
  }
  return event.locals.env as CloudflareEnv;
}
```

## Route with Server-Side Data Fetching

```typescript
// src/routes/products.tsx
import { For, Suspense } from "solid-js";
import { createAsync, cache } from "@solidjs/router";
import { useEnv } from "~/lib/env";

interface Product {
  id: number;
  name: string;
  price: number;
}

// cache() deduplicates calls within a single SSR render pass
const getProducts = cache(async (): Promise<Product[]> => {
  "use server";
  const env = useEnv();
  const { results } = await env.DB.prepare(
    "SELECT id, name, price FROM products ORDER BY name"
  ).all<Product>();
  return results;
}, "products");

export const route = {
  // Preload runs during navigation to start the fetch early
  preload: () => getProducts(),
};

export default function ProductsPage() {
  const products = createAsync(() => getProducts());

  return (
    <main class="container mx-auto px-4 py-8">
      <h1 class="mb-6 text-3xl font-bold">Products</h1>
      <Suspense fallback={<p class="animate-pulse">Loading…</p>}>
        <ul class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <For each={products()}>
            {(product) => (
              <li class="rounded-xl border p-4 shadow-sm">
                <h2 class="font-semibold">{product.name}</h2>
                <p class="mt-1 text-2xl font-bold tabular-nums">
                  {new Intl.NumberFormat("en-US", {
                    style: "currency",
                    currency: "USD",
                  }).format(product.price)}
                </p>
              </li>
            )}
          </For>
        </ul>
      </Suspense>
    </main>
  );
}
```

## Fine-Grained Reactivity Pattern with Signals

```typescript
// src/components/StockCounter.tsx
import { createSignal, createEffect } from "solid-js";
import { server$ } from "@solidjs/start/server";

// server$ compiles to a fetch call on the client and runs on the edge
const updateStock = server$(async (productId: number, delta: number) => {
  "use server";
  const env = useEnv();
  const result = await env.DB.prepare(
    "UPDATE products SET stock = stock + ?1 WHERE id = ?2 RETURNING stock"
  )
    .bind(delta, productId)
    .first<{ stock: number }>();
  return result?.stock ?? 0;
});

export function StockCounter(props: { productId: number; initialStock: number }) {
  // SolidJS signal — no re-renders, just fine-grained DOM updates
  const [stock, setStock] = createSignal(props.initialStock);
  const [pending, setPending] = createSignal(false);

  const adjust = async (delta: number) => {
    setPending(true);
    const newStock = await updateStock(props.productId, delta);
    setStock(newStock);
    setPending(false);
  };

  return (
    <div class="flex items-center gap-3">
      <button
        onClick={() => adjust(-1)}
        disabled={pending() || stock() <= 0}
        class="rounded bg-red-500 px-3 py-1 text-white disabled:opacity-40"
      >
        -
      </button>
      <span class="w-12 text-center tabular-nums">{stock()}</span>
      <button
        onClick={() => adjust(1)}
        disabled={pending()}
        class="rounded bg-green-500 px-3 py-1 text-white disabled:opacity-40"
      >
        +
      </button>
    </div>
  );
}
```

## Anti-patterns

- Calling `createSignal` or `createStore` at module scope outside a component or reactive root — SolidJS's ownership model requires signals to be created inside a tracking context, otherwise they will never be cleaned up and can cause memory leaks in long-lived Worker instances.
- Using `useServer` or Node.js `http` imports inside `"use server"` functions — the Workers runtime provides only Web APIs; use `fetch`, `Request`, `Response`, and `crypto` from the global scope.
- Wrapping every leaf element in `<Suspense>` — SolidJS streaming works best with a single top-level `<Suspense>` boundary per route; excessive boundaries fragment the stream and increase TTFB.

## Gotchas

- SolidJS's `<For>` component requires a stable `key` equivalent — it tracks items by reference identity of the array. Replacing the entire products array (e.g. after a mutation) re-creates all DOM nodes; use `reconcile` from `solid-js/store` to diff in place.
- The `cloudflare-pages` preset sets `compatibility_date` in the generated `wrangler.toml`; after upgrading SolidStart, verify the date is still valid against Cloudflare's compatibility matrix.

## Verification

```bash
# Build for Cloudflare Pages
npx solidstart build

# Confirm worker entry was emitted
ls .output/server/_worker.js

# Run local preview with Wrangler
npx wrangler pages dev .output/public

# Type-check the server$ functions separately (they run in a different bundle)
npx tsc --project tsconfig.json --noEmit
```

## Related

- `frontend/signals-fine-grained-reactivity.md`
- `frontend/streaming-html-workers-react-rendertopipeablestream.md`
- `frontend/remix-cloudflare-workers-adapter.md`

## Sources

- https://docs.solidjs.com/solid-start/reference/server/use-server
- https://developers.cloudflare.com/pages/framework-guides/deploy-a-solidstart-site/
- https://docs.solidjs.com/concepts/reactivity
