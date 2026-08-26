# React Server Components on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to ship a Next.js App Router application to Cloudflare Pages using React Server Components, with streaming `Suspense` boundaries, server actions backed by D1, and a Workers Cache API integration via `cache()`. Your cold-start budget is tight and you need true edge rendering without a Node.js origin.

---

## Context
`@cloudflare/next-on-pages` compiles each Next.js route into an individual Cloudflare Pages Function that runs on the V8 isolate runtime. React's streaming renderer pipes chunks to the edge response without buffering the whole HTML document. Server Actions are routed through the same function boundary and can reach D1 via the `env` binding injected into `getRequestContext()`. The Workers Cache API is used to back Next.js `cache()` calls so RSC payloads survive across requests within the same PoP. You must set `export const runtime = 'edge'` on every RSC route; the Node.js runtime is unavailable on Pages.

---

## Section 1 — Project Config

`next.config.ts`
```typescript
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Required for @cloudflare/next-on-pages
  experimental: {
    // Server Actions are stable in Next 14+
  },
};

export default nextConfig;
```

`wrangler.toml`
```toml
name = "my-rsc-app"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".vercel/output/static"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

`package.json` scripts (relevant)
```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build && npx @cloudflare/next-on-pages",
    "preview": "wrangler pages dev",
    "deploy": "wrangler pages deploy"
  }
}
```

---

## Section 2 — Server Component with Suspense Streaming

`app/products/page.tsx`
```typescript
import { Suspense } from 'react';
import { getRequestContext } from '@cloudflare/next-on-pages';
import { cache } from 'react';

export const runtime = 'edge';

// cache() is memoised per-request; combine with Workers Cache for cross-request caching
const getProducts = cache(async (): Promise<Product[]> => {
  const cacheKey = new Request('https://cache.internal/products');
  const cfCache = await caches.open('products-v1');
  const cached = await cfCache.match(cacheKey);
  if (cached) return cached.json() as Promise<Product[]>;

  const { env } = getRequestContext();
  const { results } = await env.DB.prepare(
    'SELECT id, name, price_cents FROM products ORDER BY created_at DESC LIMIT 50'
  ).all<Product>();

  const response = new Response(JSON.stringify(results), {
    headers: { 'Cache-Control': 'public, max-age=60' },
  });
  await cfCache.put(cacheKey, response);
  return results;
});

async function ProductList() {
  const products = await getProducts();
  return (
    <ul className="product-grid">
      {products.map((p) => (
        <li key={p.id}>
          {p.name} — ${(p.price_cents / 100).toFixed(2)}
        </li>
      ))}
    </ul>
  );
}

export default function ProductsPage() {
  return (
    <main>
      <h1>Products</h1>
      <Suspense fallback={<p>Loading products…</p>}>
        <ProductList />
      </Suspense>
    </main>
  );
}

interface Product {
  id: number;
  name: string;
  price_cents: number;
}
```

---

## Section 3 — Server Action backed by D1

`app/products/actions.ts`
```typescript
'use server';

import { getRequestContext } from '@cloudflare/next-on-pages';
import { revalidatePath } from 'next/cache';

export async function createProduct(formData: FormData): Promise<{ error?: string }> {
  const name = formData.get('name');
  const priceStr = formData.get('price');

  if (typeof name !== 'string' || name.trim().length === 0) {
    return { error: 'Name is required' };
  }
  const priceCents = Math.round(parseFloat(priceStr as string) * 100);
  if (isNaN(priceCents) || priceCents < 0) {
    return { error: 'Invalid price' };
  }

  const { env } = getRequestContext();
  await env.DB.prepare(
    'INSERT INTO products (name, price_cents, created_at) VALUES (?, ?, ?)'
  )
    .bind(name.trim(), priceCents, new Date().toISOString())
    .run();

  // Bust the Workers Cache for the product list
  const cfCache = await caches.open('products-v1');
  await cfCache.delete(new Request('https://cache.internal/products'));

  revalidatePath('/products');
  return {};
}
```

`app/products/new/page.tsx`
```typescript
'use client';

import { useActionState } from 'react';
import { createProduct } from '../actions';

export const runtime = 'edge';

export default function NewProductPage() {
  const [state, action, isPending] = useActionState(createProduct, {});

  return (
    <form action={action}>
      {state.error && <p className="error">{state.error}</p>}
      <label>
        Name
        <input name="name" required />
      </label>
      <label>
        Price (USD)
        <input name="price" type="number" step="0.01" min="0" required />
      </label>
      <button type="submit" disabled={isPending}>
        {isPending ? 'Saving…' : 'Create product'}
      </button>
    </form>
  );
}
```

---

## Anti-patterns
- **`export const runtime = 'nodejs'`** — The Node.js runtime is unavailable on Cloudflare Pages; every route must use `'edge'`.
- **Importing Node built-ins directly** — `fs`, `path`, `crypto` (Node flavour) will fail; use the Web Crypto API or Workers-compatible equivalents.
- **Using `unstable_cache` without a Workers Cache fallback** — `unstable_cache` persists only in memory within a single isolate; pair it with `caches.open()` for cross-request persistence.
- **Large D1 result sets without pagination** — D1 has a 10 MB response cap per query; always add `LIMIT`/`OFFSET`.

---

## Gotchas
- `@cloudflare/next-on-pages` requires the `nodejs_compat` compatibility flag in `wrangler.toml` even though you use the edge runtime; without it certain polyfills fail at build time.
- `getRequestContext()` throws outside of a request context (e.g. in global module scope); always call it inside an async function that is triggered by a request.
- Streaming requires the response to be chunked; ensure no middleware or proxy between Cloudflare Pages and the browser buffers the response body.
- D1 bindings are not available during `next build`; use `wrangler pages dev` for local iteration that injects real bindings.

---

## Verification
```bash
# Install adapter
npm install --save-dev @cloudflare/next-on-pages

# Build and bundle
next build && npx @cloudflare/next-on-pages

# Local preview with D1 binding
wrangler pages dev --d1 DB=<database_id>

# Deploy
wrangler pages deploy .vercel/output/static --project-name my-rsc-app

# Confirm streaming: look for Transfer-Encoding: chunked
curl -I https://my-rsc-app.pages.dev/products
```

---

## Related
- `svelte-sveltekit-cloudflare-pages-adapter.md`
- `vue-nuxt-cloudflare-pages-nitro.md`
- `cloudflare-pages-middleware-auth-redirect.md`

---

## Sources
- `@cloudflare/next-on-pages` docs — https://developers.cloudflare.com/pages/framework-guides/nextjs/
- Next.js App Router — https://nextjs.org/docs/app
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Workers Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
