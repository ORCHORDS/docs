# Nuxt Cloudflare Module Integration

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Deploying a Nuxt 3 application to Cloudflare Pages with full SSR requires the `@nuxthub/core` module (or the legacy `nitro cloudflare-pages` preset) to produce a Workers-compatible output. Out of the box Nuxt targets Node.js, so naive deployments fail with runtime errors about missing `http` and `stream` modules. The Cloudflare module rewires Nitro's server engine to use Workers-native APIs and exposes KV, R2, D1, and AI bindings through Nuxt's `useRuntimeConfig` and `hubKV()` composables.

## Context

Nuxt 3 uses Nitro as its server engine, and Nitro ships first-class support for the `cloudflare-pages` output preset. The `@nuxthub/core` module builds on top of this preset and adds typed binding helpers, local development proxies via `wrangler`, and a deployment CLI (`nuxthub deploy`). For teams already using Cloudflare infrastructure (KV, D1, R2), the module eliminates the boilerplate of manually accessing `event.context.cloudflare.env`. The key deployment artefact is a `.output/` directory containing a static `public/` tree and a `server/` directory with the Worker entry.

## Nuxt Config with Cloudflare Module

```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxthub/core"],

  hub: {
    // Enable the bindings you actually use; false = not provisioned
    kv: true,
    database: true, // D1
    blob: true, // R2
  },

  nitro: {
    preset: "cloudflare-pages",
    // Inline the Cloudflare compatibility flags
    cloudflare: {
      deployConfig: true,
      nodeCompat: true,
    },
  },

  runtimeConfig: {
    // Server-only secrets — exposed as CF env vars in production
    apiSecret: "",
    public: {
      // Client-accessible values
      apiBase: "/api",
    },
  },

  compatibilityDate: "2025-09-01",
});
```

## Server Route with KV and D1 Bindings

```typescript
// server/api/products/index.get.ts
import { hubKV, hubDatabase } from "@nuxthub/core";

interface Product {
  id: number;
  name: string;
  price: number;
  stock: number;
}

export default defineEventHandler(async (event) => {
  // hubKV() returns a typed KV namespace accessor
  const kv = hubKV();
  const cacheKey = "products:all";

  // Check KV cache first
  const cached = await kv.getItem<Product[]>(cacheKey);
  if (cached) {
    setHeader(event, "X-Cache", "HIT");
    return cached;
  }

  // Fall back to D1
  const db = hubDatabase();
  const { results } = await db
    .prepare("SELECT id, name, price, stock FROM products ORDER BY name LIMIT 100")
    .all<Product>();

  // Cache for 60 seconds
  await kv.setItem(cacheKey, results, { ttl: 60 });

  setHeader(event, "X-Cache", "MISS");
  return results;
});
```

## Vue Page Component with useFetch

```vue
<!-- pages/products.vue -->
<script setup lang="ts">
interface Product {
  id: number
  name: string
  price: number
  stock: number
}

const { data: products, status } = await useFetch<Product[]>('/api/products', {
  // Nuxt deduplicates identical requests during SSR
  key: 'products-list',
  // Transform on the client after hydration
  transform: (raw) =>
    raw.map((p) => ({
      ...p,
      formattedPrice: new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
      }).format(p.price),
    })),
})
</script>

<template>
  <main class="container mx-auto px-4 py-8">
    <h1 class="mb-6 text-3xl font-bold">Products</h1>

    <div v-if="status === 'pending'" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="i in 6"
        :key="i"
        class="h-32 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
      />
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <article
        v-for="product in products"
        :key="product.id"
        class="rounded-xl border p-4 shadow-sm"
      >
        <h2 class="font-semibold">{{ product.name }}</h2>
        <p class="mt-1 text-2xl font-bold tabular-nums">
          {{ product.formattedPrice }}
        </p>
        <span
          :class="product.stock < 10 ? 'text-red-600' : 'text-green-600'"
          class="text-sm"
        >
          {{ product.stock }} in stock
        </span>
      </article>
    </div>
  </main>
</template>
```

## D1 Database Migration via NuxtHub CLI

```typescript
// server/database/migrations/0001_create_products.sql
// (NuxtHub reads .sql files from server/database/migrations/)

// Triggered with: npx nuxthub database migrations apply

/*
CREATE TABLE IF NOT EXISTS products (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  name    TEXT    NOT NULL,
  price   REAL    NOT NULL DEFAULT 0,
  stock   INTEGER NOT NULL DEFAULT 0,
  created INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_products_name ON products(name);
*/
```

```typescript
// server/api/admin/seed.post.ts  (protected seeding endpoint)
import { hubDatabase } from "@nuxthub/core";

export default defineEventHandler(async (event) => {
  // Require a secret header in production
  const secret = <redacted-secret> "X-Seed-Secret");
  if (secret !== useRuntimeConfig().apiSecret) {
    throw createError({ statusCode: 401, message: "Unauthorized" });
  }

  const db = hubDatabase();
  const stmt = db.prepare(
    "INSERT INTO products (name, price, stock) VALUES (?, ?, ?)"
  );

  const batch = [
    stmt.bind("Widget A", 29.99, 150),
    stmt.bind("Widget B", 49.99, 75),
    stmt.bind("Widget C", 9.99, 300),
  ];

  await db.batch(batch);
  return { seeded: batch.length };
});
```

## Anti-patterns

- Using `process.env` to access secrets in server routes — Nuxt on Workers exposes them through `useRuntimeConfig()` which reads from `event.context.cloudflare.env` at runtime; `process.env` is absent.
- Setting `ssr: false` in `nuxt.config.ts` to avoid adapter issues — this converts the app to a pure SPA and loses all Cloudflare edge SSR benefits; fix the adapter config instead.
- Importing Nuxt server composables (`hubKV`, `hubDatabase`) in Vue component `<script setup>` — these are server-only and will throw a build error if bundled into the client chunk.

## Gotchas

- `@nuxthub/core` version must be aligned with the NuxtHub platform version; a mismatch causes silent 500 errors from the binding proxy. Pin versions and run `npx nuxthub check` to verify.
- Local development with `nuxt dev` does not use Wrangler; D1 and KV calls are proxied to NuxtHub's remote preview environment unless you run `nuxt dev --remote` or manually start `wrangler pages dev .output/public`.

## Verification

```bash
# Build for Cloudflare Pages
npx nuxi build --preset cloudflare-pages

# Preview locally with Wrangler (uses .output/public + _worker.js)
npx wrangler pages dev .output/public

# Apply D1 migrations to the preview environment
npx nuxthub database migrations apply --env preview

# Deploy to production
npx nuxthub deploy
```

## Related

- `frontend/remix-cloudflare-workers-adapter.md`
- `frontend/astro-cloudflare-adapter-ssr-hybrid.md`
- `frontend/feature-flags-cloudflare-workers-kv-edge-config.md`

## Sources

- https://hub.nuxt.com/docs/getting-started/installation
- https://nitro.unjs.io/deploy/providers/cloudflare
- https://developers.cloudflare.com/d1/
