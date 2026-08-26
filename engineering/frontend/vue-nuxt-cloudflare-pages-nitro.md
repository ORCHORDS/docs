# Nuxt 3 on Cloudflare Pages via Nitro

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You are deploying a Nuxt 3 application to Cloudflare Pages and need server routes that read from a D1 database, runtime config pulled from Cloudflare env bindings, and efficient data fetching with `ofetch` caching. Local development must mirror production bindings using `wrangler pages dev`.

---

## Context
Nitro, Nuxt's server engine, ships a first-class `cloudflare-pages` preset that compiles server routes into Cloudflare Pages Functions placed under `dist/_worker.js`. Env bindings (D1, KV, R2, secrets) are forwarded by Nitro into `event.context.cloudflare.env` in server routes. Runtime config values can be mapped from those bindings in `nuxt.config.ts` so they are accessible via `useRuntimeConfig()` both server-side and client-side (public subset). `$fetch` (powered by `ofetch`) supports a `getCachedData` hook in `useAsyncData` for client-side deduplication and stale-while-revalidate patterns.

---

## Section 1 — Nuxt + Nitro Config

`nuxt.config.ts`
```typescript
import { defineNuxtConfig } from 'nuxt/config';

export default defineNuxtConfig({
  nitro: {
    preset: 'cloudflare-pages',
  },

  // Runtime config: private keys server-only, public keys exposed to client
  runtimeConfig: {
    // Populated from Cloudflare env bindings at runtime via nitro env passthrough
    dbBinding: '',          // overridden by process.env.NUXT_DB_BINDING or CF binding name
    sessionSecret: '',      // overridden by process.env.NUXT_SESSION_SECRET
    public: {
      apiBase: '/api',
    },
  },

  compatibilityDate: '2024-09-19',
});
```

`wrangler.toml`
```toml
name = "my-nuxt-app"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = "dist"

[[d1_databases]]
binding = "DB"
database_name = "nuxt-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
NUXT_SESSION_SECRET = "change-me-in-dashboard"
```

---

## Section 2 — Server Route using D1

`server/api/posts/index.get.ts`
```typescript
import type { D1Database } from '@cloudflare/workers-types';

interface Post {
  id: number;
  title: string;
  slug: string;
  published_at: string;
}

interface CloudflareEnv {
  DB: D1Database;
}

export default defineEventHandler(async (event) => {
  // Access Cloudflare bindings via Nitro's context
  const { env } = event.context.cloudflare as { env: CloudflareEnv };

  const { page = '1', limit = '20' } = getQuery(event) as Record<string, string>;
  const pageNum = Math.max(1, parseInt(page, 10));
  const limitNum = Math.min(100, parseInt(limit, 10));
  const offset = (pageNum - 1) * limitNum;

  const { results } = await env.DB.prepare(
    `SELECT id, title, slug, published_at
     FROM posts
     WHERE published_at IS NOT NULL
     ORDER BY published_at DESC
     LIMIT ? OFFSET ?`
  )
    .bind(limitNum, offset)
    .all<Post>();

  return {
    data: results,
    page: pageNum,
    limit: limitNum,
  };
});
```

`server/api/posts/[slug].get.ts`
```typescript
import type { D1Database } from '@cloudflare/workers-types';

export default defineEventHandler(async (event) => {
  const slug = getRouterParam(event, 'slug');
  if (!slug) throw createError({ statusCode: 400, message: 'Missing slug' });

  const { env } = event.context.cloudflare as { env: { DB: D1Database } };

  const post = await env.DB.prepare(
    'SELECT id, title, slug, body, published_at FROM posts WHERE slug = ? LIMIT 1'
  )
    .bind(slug)
    .first<{ id: number; title: string; slug: string; body: string; published_at: string }>();

  if (!post) throw createError({ statusCode: 404, message: 'Post not found' });

  return post;
});
```

---

## Section 3 — Composable with ofetch Caching

`composables/usePosts.ts`
```typescript
import type { Post } from '~/types';

const POST_CACHE_TTL = 60_000; // 60 s client-side stale time

export function usePosts(page: Ref<number> = ref(1)) {
  // getCachedData gives stale-while-revalidate behaviour on the client
  return useAsyncData(
    `posts-page-${page.value}`,
    () =>
      $fetch<{ data: Post[]; page: number; limit: number }>('/api/posts', {
        query: { page: page.value, limit: 20 },
      }),
    {
      watch: [page],
      getCachedData(key, nuxtApp) {
        const cached = nuxtApp.payload.data[key] ?? nuxtApp.static.data[key];
        if (!cached) return;
        const fetchedAt: number = (cached as { _fetchedAt?: number })._fetchedAt ?? 0;
        if (Date.now() - fetchedAt < POST_CACHE_TTL) return cached;
      },
      transform(data) {
        // Stamp fetch time for TTL check above
        return Object.assign(data, { _fetchedAt: Date.now() });
      },
    }
  );
}
```

`pages/blog/index.vue`
```vue
<script setup lang="ts">
const page = ref(1);
const { data, status } = usePosts(page);
</script>

<template>
  <div>
    <h1>Blog</h1>
    <p v-if="status === 'pending'">Loading…</p>
    <ul v-else>
      <li v-for="post in data?.data" :key="post.id">
        <NuxtLink :to="`/blog/${post.slug}`">{{ post.title }}</NuxtLink>
      </li>
    </ul>
    <button :disabled="page <= 1" @click="page--">Prev</button>
    <button @click="page++">Next</button>
  </div>
</template>
```

---

## Anti-patterns
- **Using `useStorage()` with the default memory driver expecting persistence** — On Cloudflare Workers, `useStorage()` defaults to in-memory; bind it explicitly to a KV namespace using `useStorage('cloudflare:KV_BINDING')` for durability.
- **Reading `process.env` in server routes for binding names** — Cloudflare bindings are not Node env vars; access them through `event.context.cloudflare.env`.
- **Running `nuxt dev` and expecting D1 to be available** — `nuxt dev` uses a local Nitro server without Cloudflare bindings; use `wrangler pages dev` for integration testing.
- **Omitting `compatibilityDate` in `nuxt.config.ts`** — Without this, Nitro's preset may fall back to an older Workers API surface that lacks D1 statement chaining.

---

## Gotchas
- Nitro bundles your server code into a single `_worker.js`; any package that uses Node-only APIs must be replaced with a Web API equivalent or excluded via `nitro.externals.exclude`.
- `event.context.cloudflare` is only populated when the app runs under the `cloudflare-pages` preset; it is `undefined` in `nuxt dev`; guard with `if (import.meta.server && event.context.cloudflare)`.
- D1 `prepare().all()` returns `{ results, success, meta }`; destructure `results` to get the array, not the raw response object.
- `wrangler pages dev dist` must point at the built `dist` directory, not the source; always run `nuxt build` first.

---

## Verification
```bash
# Install dependencies
npm install

# Build with cloudflare-pages preset
nuxt build

# Local preview with live D1 binding
wrangler pages dev dist --d1 DB=<database_id>

# Smoke-test API route
curl http://localhost:8788/api/posts?page=1

# Deploy to Cloudflare Pages
wrangler pages deploy dist --project-name my-nuxt-app
```

---

## Related
- `react-server-components-cloudflare-pages.md`
- `svelte-sveltekit-cloudflare-pages-adapter.md`
- `workers-html-streaming-rewriter-esi.md`

---

## Sources
- Nuxt Cloudflare Pages deployment — https://nitro.build/deploy/providers/cloudflare
- Cloudflare D1 bindings — https://developers.cloudflare.com/d1/
- ofetch (useFetch / useAsyncData) — https://nuxt.com/docs/api/composables/use-async-data
