# TanStack Start + Cloudflare Workers Deployment

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case:** You want to deploy a TanStack Start (full-stack React framework built on TanStack Router) application on Cloudflare Workers, taking advantage of edge SSR, KV caching, D1 data access, and Workers-native server functions — without the Node.js runtime.

**Context:** TanStack Start 1.x (stable as of early 2026) uses Vinxi/Nitro under the hood. Nitro ships a `cloudflare-pages` and `cloudflare-module` preset that compiles the app to a Workers-compatible ES module. Server functions (`createServerFn`) become Workers fetch handlers, and the router's loader system maps cleanly to the edge request lifecycle.

---

## Project Setup and Cloudflare Preset

```bash
npx create-tsrouter-app@latest my-app --framework start --bundler vite
cd my-app
npm install
```

```typescript
// app.config.ts  (TanStack Start config via Vinxi)
import { defineConfig } from '@tanstack/start/config';

export default defineConfig({
  server: {
    preset: 'cloudflare-pages',    // or 'cloudflare-module' for Workers
    rollupConfig: {
      external: ['node:async_hooks'],  // polyfill-safe exclusion
    },
  },
  vite: {
    define: {
      // Ensure no Node.js globals leak into the Workers bundle
      'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV ?? 'production'),
    },
  },
});
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "my-tanstack-app"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".output/public"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id     = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Accessing CF Bindings in Server Functions

```typescript
// app/server/context.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface CFEnv {
  DB:    D1Database;
  CACHE: KVNamespace;
}

// TanStack Start exposes the raw request event via `getEvent()`
import { getEvent } from 'vinxi/http';

export function getCFEnv(): CFEnv {
  const event = getEvent();
  // Nitro stores the CF env on the H3 event context
  return (event.context.cloudflare?.env ?? {}) as CFEnv;
}
```

## Server Function with D1 Query

```typescript
// app/server/posts.ts
import { createServerFn } from '@tanstack/start';
import { z } from 'zod';
import { getCFEnv } from './context';

const PostSchema = z.object({
  id:    z.number(),
  slug:  z.string(),
  title: z.string(),
  body:  z.string(),
});

export const getPosts = createServerFn({ method: 'GET' }).handler(async () => {
  const { DB, CACHE } = getCFEnv();

  const cached = await CACHE.get('posts:all', 'json');
  if (cached) return cached as z.infer<typeof PostSchema>[];

  const { results } = await DB.prepare(
    'SELECT id, slug, title, body FROM posts ORDER BY id DESC LIMIT 50'
  ).all<z.infer<typeof PostSchema>>();

  await CACHE.put('posts:all', JSON.stringify(results), { expirationTtl: 60 });
  return results;
});

export const createPost = createServerFn({ method: 'POST' })
  .validator(z.object({ slug: z.string(), title: z.string(), body: z.string() }))
  .handler(async ({ data }) => {
    const { DB, CACHE } = getCFEnv();
    const [post] = await DB.prepare(
      'INSERT INTO posts (slug, title, body) VALUES (?, ?, ?) RETURNING *'
    ).bind(data.slug, data.title, data.body).all();
    await CACHE.delete('posts:all');   // invalidate list cache
    return post;
  });
```

## Route Loader Integration

```typescript
// app/routes/posts.tsx
import { createFileRoute } from '@tanstack/react-router';
import { getPosts } from '../server/posts';

export const Route = createFileRoute('/posts')({
  loader: () => getPosts(),
  component: PostsPage,
});

function PostsPage() {
  const posts = Route.useLoaderData();
  return (
    <ul>
      {posts.map((p) => (
        <li key={p.id}>{p.title}</li>
      ))}
    </ul>
  );
}
```

## Mutation with `useServerFn`

```typescript
// app/components/NewPostForm.tsx
import { useServerFn } from '@tanstack/start';
import { createPost } from '../server/posts';
import { useRouter } from '@tanstack/react-router';

export function NewPostForm() {
  const router = useRouter();
  const submit = useServerFn(createPost);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    await submit({
      data: {
        slug:  fd.get('slug') as string,
        title: fd.get('title') as string,
        body:  fd.get('body') as string,
      },
    });
    router.invalidate();   // re-run loaders to show new post
  }

  return (
    <form onSubmit={handleSubmit}>
      <input name="slug"  placeholder="slug"  required />
      <input name="title" placeholder="title" required />
      <textarea name="body" required />
      <button type="submit">Create</button>
    </form>
  );
}
```

## Build and Deploy

```bash
# Build for Cloudflare Pages
npm run build

# Preview locally with CF bindings via wrangler
npx wrangler pages dev .output/public --d1=DB --kv=CACHE

# Deploy
npx wrangler pages deploy .output/public
```

## Anti-patterns

- **Using `process.env` for secrets** at runtime — CF Workers use `env` bindings; environment variables must be set in `wrangler.toml` or the Pages dashboard, not `.env` files (those only work for Vite build-time substitution).
- **Importing Node.js built-ins** (`fs`, `path`, `crypto`) directly inside server functions — use `node:crypto` with `nodejs_compat` flag and ensure Nitro's rollup config excludes them as externals.
- **Fetching data inside the component** instead of the loader — loaders run on the edge and benefit from KV caching; moving data fetching client-side defeats edge SSR.
- **Forgetting `router.invalidate()`** after mutations — TanStack Router caches loader data aggressively; explicit invalidation is required to see updates.

## Gotchas

- `event.context.cloudflare?.env` is only populated when running via `wrangler pages dev` or deployed to Pages; it is `undefined` in `vite dev` mode without a special proxy.
- The `cloudflare-pages` preset outputs an `_worker.js` bundle; do not manually edit it — it's regenerated on every build.
- TanStack Start uses React 19 under the hood; ensure peer deps align (`react@^19`, `react-dom@^19`).
- Server function RPC serialization uses `devalue`; complex objects (class instances, `Map`, `Set`) serialize correctly but `Date` objects become strings — parse explicitly.
- Workers CPU time limit (10 ms free / 30 ms paid default) applies per-request; batch D1 queries with `db.batch()` to stay within budget.

## Verification

```bash
# Type-check
npx tsc --noEmit

# Build + inspect bundle size
npm run build && ls -lh .output/server/*.js

# Smoke-test against local wrangler
curl http://localhost:8788/posts
```

## Related

- `react-router-v7-patterns.md`
- `react-query-patterns.md`
- `hono-cloudflare-workers-frontend-api.md`
- `remix-cloudflare-workers-adapter.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`

## Sources

- TanStack Start docs: https://tanstack.com/start/latest/docs/framework/react/overview
- Nitro Cloudflare preset: https://nitro.unjs.io/deploy/providers/cloudflare
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Cloudflare D1: https://developers.cloudflare.com/d1/
