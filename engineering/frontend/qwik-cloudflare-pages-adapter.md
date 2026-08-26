# Qwik Framework Cloudflare Pages Adapter

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Deploying a Qwik City application to Cloudflare Pages requires an edge-compatible adapter that outputs both static assets and a Worker function for SSR routes. Without the adapter, the default Node.js build target produces `Buffer` and `process.env` references that crash in the Workers runtime. The `@builder.io/qwik-city/adapters/cloudflare-pages` adapter handles serialisation, routing, and environment variable forwarding automatically.

## Context

Qwik's resumability model means the framework ships zero JavaScript by default and only downloads interaction handlers on demand. This pairs well with Cloudflare Pages: static assets are served from the CDN edge while dynamic routes are handled by a Pages Function (Workers). The adapter generates a `_worker.js` entry in the output directory which Pages picks up automatically. Qwik's symbol chunking strategy produces hundreds of tiny `.js` files; Cloudflare's CDN caches each chunk independently, so cache hit rates are extremely high after the first visitor warms the edge.

## Adapter Configuration

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import { qwikVite } from "@builder.io/qwik/optimizer";
import { qwikCity } from "@builder.io/qwik-city/vite";
import { cloudflarePagesAdapter } from "@builder.io/qwik-city/adapters/cloudflare-pages/vite";

export default defineConfig(() => {
  return {
    plugins: [
      qwikCity(),
      qwikVite(),
      // The adapter must be last; it rewrites the output manifest
      cloudflarePagesAdapter(),
    ],
    preview: {
      headers: {
        // Immutable caching for Qwik symbol chunks (content-hashed filenames)
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    },
  };
});
```

## Environment Variables and Bindings

```typescript
// src/routes/layout.tsx
import { component$, Slot } from "@builder.io/qwik";
import { routeLoader$ } from "@builder.io/qwik-city";

// routeLoader$ runs on the edge; env bindings are available via platform
export const useConfig = routeLoader$(async ({ platform }) => {
  // platform.env contains Cloudflare bindings declared in wrangler.toml
  const env = platform.env as {
    API_BASE_URL: string;
    PRODUCTS_KV: KVNamespace;
  };

  const rawConfig = await env.PRODUCTS_KV.get("site-config", {
    type: "json",
  });

  return {
    apiBase: env.API_BASE_URL,
    config: rawConfig ?? {},
  };
});

export default component$(() => {
  const config = useConfig();

  return (
    <>
      <header>
        <span data-testid="api-base">{config.value.apiBase}</span>
      </header>
      <main>
        <Slot />
      </main>
    </>
  );
});
```

## SSR Route with KV Data Fetching

```typescript
// src/routes/products/index.tsx
import { component$ } from "@builder.io/qwik";
import { routeLoader$, type DocumentHead } from "@builder.io/qwik-city";

interface Product {
  id: string;
  name: string;
  price: number;
}

export const useProducts = routeLoader$(async ({ platform, status }) => {
  const env = platform.env as { PRODUCTS_KV: KVNamespace };

  try {
    const data = await env.PRODUCTS_KV.get<Product[]>("products:list", {
      type: "json",
    });
    return data ?? [];
  } catch {
    status(500);
    return [] as Product[];
  }
});

export default component$(() => {
  const products = useProducts();

  return (
    <section class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 p-6">
      {products.value.map((product) => (
        <article
          key={product.id}
          class="rounded-xl border p-4 shadow-sm hover:shadow-md transition-shadow"
        >
          <h2 class="text-lg font-semibold">{product.name}</h2>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            {new Intl.NumberFormat("en-US", {
              style: "currency",
              currency: "USD",
            }).format(product.price)}
          </p>
        </article>
      ))}
    </section>
  );
});

export const head: DocumentHead = {
  title: "Products",
};
```

## Cloudflare Pages Config and Wrangler Bindings

```toml
# wrangler.toml  (used by `wrangler pages dev` for local preview)
name = "my-qwik-app"
compatibility_date = "2025-03-01"

[[kv_namespaces]]
binding = "PRODUCTS_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[vars]
API_BASE_URL = "https://api.example.com"
```

```jsonc
// package.json scripts
{
  "scripts": {
    "build": "qwik build",
    "build.types": "tsc --noEmit",
    "deploy": "npm run build && wrangler pages deploy dist",
    "preview": "wrangler pages dev dist"
  }
}
```

## Anti-patterns

- Importing Node.js built-ins (`fs`, `path`, `crypto`) inside `routeLoader$` or `routeAction$` — the Workers runtime does not provide them; use the Web Crypto API and `platform.env` bindings instead.
- Disabling Qwik's symbol chunking to reduce file count — chunking is what enables resumability; a monolithic bundle defeats the framework's purpose and breaks lazy hydration.
- Using `process.env.VAR` to read secrets — in Workers, only `platform.env.VAR` (from the `Env` bindings object) is available; `process.env` is undefined at runtime.

## Gotchas

- Qwik serialises component state into the HTML as `<script type="qwik/json">`; if a `routeLoader$` returns a value that cannot be JSON-serialised (e.g. a `Date` object or a class instance), the page will throw a hydration error at runtime. Always return plain objects.
- The adapter expects the build output at `dist/`; if you rename the output directory in `vite.config.ts`, also update the `wrangler pages deploy` path.

## Verification

```bash
# Build the project
npm run build

# Confirm the adapter generated the Pages worker entry
ls dist/_worker.js

# Preview locally against real KV bindings
npx wrangler pages dev dist --kv PRODUCTS_KV

# Run Qwik's built-in e2e suite
npx playwright test
```

## Related

- `frontend/astro-cloudflare-adapter-ssr-hybrid.md`
- `frontend/sveltekit-cloudflare-pages-adapter.md`
- `frontend/react-suspense-cloudflare-pages-ssr-edge.md`

## Sources

- https://qwik.dev/docs/deployments/cloudflare-pages/
- https://developers.cloudflare.com/pages/functions/
- https://qwik.dev/docs/route-loader/
