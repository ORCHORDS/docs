# SolidStart on Cloudflare with D1, Streaming SSR, and KV Sessions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to deploy a SolidStart app to Cloudflare Workers with streaming SSR, access a D1 database from server functions, and store sessions in KV. SolidStart's Cloudflare adapter is less documented than the Remix equivalent; this article covers the exact wiring needed for each feature.

## Context

- SolidStart 1.x (`@solidjs/start` + Vinxi)
- `@solidjs/start/cloudflare` adapter
- Solid.js 1.8+
- Cloudflare Workers (not Pages — the adapter targets a Worker)
- D1 binding `DB`, KV binding `SESSION_KV`
- Wrangler v3, TypeScript 5.x

---

## Section 1 — Project scaffold and adapter config

```bash
# Create SolidStart project
npx create-solid@latest my-solid-app --template with-auth
cd my-solid-app

# Install Cloudflare adapter and types
npm install @solidjs/start
npm install -D wrangler @cloudflare/workers-types vite-plugin-solid
```

```typescript
// app.config.ts
import { defineConfig } from '@solidjs/start/config';

export default defineConfig({
  server: {
    preset: 'cloudflare-module',
    rollupConfig: {
      external: ['node:async_hooks'],
    },
  },
  vite: {
    ssr: {
      target: 'webworker',
      noExternal: true,
    },
  },
});
```

```toml
# wrangler.toml
name = "my-solid-app"
main = ".output/server/index.mjs"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "solid-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[vars]
ENVIRONMENT = "production"
```

---

## Section 2 — Accessing bindings from server functions

SolidStart exposes the Worker execution context through `getRequestEvent`. Bindings live on `event.nativeEvent.context.cloudflare.env`.

```typescript
// src/lib/env.ts
import { getRequestEvent } from 'solid-js/web';

export interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
  ENVIRONMENT: string;
}

export function getEnv(): Env {
  const event = getRequestEvent();
  if (!event) throw new Error('getEnv() must be called within a request context');
  // The adapter places Cloudflare env on the native H3 event context
  return (event.nativeEvent as any).context.cloudflare.env as Env;
}

export function getWaitUntil(): (p: Promise<unknown>) => void {
  const event = getRequestEvent();
  if (!event) throw new Error('Must be called within a request context');
  return (event.nativeEvent as any).context.cloudflare.ctx.waitUntil.bind(
    (event.nativeEvent as any).context.cloudflare.ctx
  );
}
```

---

## Section 3 — Server functions hitting D1

```typescript
// src/routes/api/products.ts
import { action, query, redirect } from '@solidjs/router';
import { getEnv } from '~/lib/env';

interface Product {
  id: number;
  name: string;
  price: number;
  stock: number;
  created_at: string;
}

// query — cached GET, runs on server
export const getProducts = query(async () => {
  'use server';
  const { DB } = getEnv();
  const result = await DB.prepare(
    'SELECT id, name, price, stock, created_at FROM products ORDER BY id DESC LIMIT 50'
  ).all<Product>();
  return result.results;
}, 'products-list');

export const getProduct = query(async (id: number) => {
  'use server';
  const { DB } = getEnv();
  const row = await DB.prepare('SELECT * FROM products WHERE id = ?').bind(id).first<Product>();
  if (!row) throw new Error(`Product ${id} not found`);
  return row;
}, 'product-detail');

// action — mutation, runs on server
export const createProduct = action(async (formData: FormData) => {
  'use server';
  const { DB } = getEnv();
  const name = String(formData.get('name'));
  const price = Number(formData.get('price'));

  if (!name || isNaN(price) || price <= 0) {
    throw new Error('Invalid product data');
  }

  const result = await DB.prepare(
    'INSERT INTO products (name, price) VALUES (?, ?) RETURNING id'
  ).bind(name, price).first<{ id: number }>();

  if (!result) throw new Error('Insert failed');
  return redirect(`/products/${result.id}`);
});

export const deleteProduct = action(async (id: number) => {
  'use server';
  const { DB } = getEnv();
  await DB.prepare('DELETE FROM products WHERE id = ?').bind(id).run();
  return redirect('/products');
});
```

```typescript
// src/routes/products/index.tsx
import { createAsync, A } from '@solidjs/router';
import { For, Suspense } from 'solid-js';
import { getProducts, createProduct, deleteProduct } from '../api/products';

export default function ProductsPage() {
  const products = createAsync(() => getProducts());

  return (
    <main>
      <h1>Products</h1>

      <form action={createProduct} method="post">
        <input name="name" placeholder="Product name" required />
        <input name="price" type="number" step="0.01" placeholder="Price" required />
        <button type="submit">Add product</button>
      </form>

      <Suspense fallback={<p>Loading...</p>}>
        <ul>
          <For each={products()}>
            {(p) => (
              <li>
                <A href={`/products/${p.id}`}>{p.name}</A> — ${p.price}
                <form action={deleteProduct.with(p.id)} method="post" style="display:inline">
                  <button type="submit">Delete</button>
                </form>
              </li>
            )}
          </For>
        </ul>
      </Suspense>
    </main>
  );
}
```

---

## Section 4 — Streaming SSR

SolidStart's Cloudflare adapter supports streaming by default when using `renderStream`.

```typescript
// src/entry-server.tsx  — customise the streaming entry point
import { createHandler, renderStream } from '@solidjs/start/server';

export default createHandler(
  renderStream((event) => (
    <StartServer event={event} />
  ), {
    // Stream chunks as they arrive from Suspense boundaries
    nonce: (event) => event.nativeEvent.context.nonce,
  })
);
```

```typescript
// Wrap data-heavy sections in Suspense to allow partial streaming
// src/routes/dashboard.tsx
import { Suspense } from 'solid-js';
import { createAsync } from '@solidjs/router';
import { getHeavyDashboardData } from './api/dashboard';

export default function Dashboard() {
  // This triggers a stream chunk when resolved
  const data = createAsync(() => getHeavyDashboardData());

  return (
    <>
      <h1>Dashboard</h1>
      {/* Renders immediately */}
      <StaticHeader />

      {/* Streams in when the query resolves */}
      <Suspense fallback={<SkeletonChart />}>
        <DashboardCharts data={data()} />
      </Suspense>
    </>
  );
}
```

---

## Section 5 — KV session storage

```typescript
// src/lib/session.ts
import { useSession } from 'vinxi/http';
import { getEnv } from './env';

interface SessionData {
  userId?: string;
  role?: 'admin' | 'user';
}

export async function getSession() {
  // vinxi/http useSession uses Cloudflare KV automatically
  // when the adapter is cloudflare-module
  return useSession<SessionData>({
    password: '<redacted-secret>',
    cookie: { httpOnly: true, sameSite: 'lax', maxAge: 60 * 60 * 24 * 7 },
  });
}

export async function requireUser(): Promise<string> {
  const session = await getSession();
  const userId = session.data.userId;
  if (!userId) {
    throw redirect('/login', 302);
  }
  return userId;
}

// Login action
export const loginAction = action(async (formData: FormData) => {
  'use server';
  const { DB } = getEnv();
  const email = String(formData.get('email'));
  const password = <redacted-secret>'password'));

  const user = await DB.prepare(
    'SELECT id, role FROM users WHERE email = ? AND password_hash = ?'
  ).bind(email, hashSync(password)).first<{ id: string; role: string }>();

  if (!user) throw new Error('Invalid credentials');

  const session = await getSession();
  await session.update({ userId: user.id, role: user.role as 'admin' | 'user' });

  return redirect('/dashboard');
});

function hashSync(pw: string): string {
  // In production use a real async hash — this is illustrative only
  throw new Error('Implement with crypto.subtle.digest');
}
```

---

## Anti-patterns

- Do not call `getEnv()` at module load time — bindings are request-scoped.
- Do not use `query()` for mutations; always use `action()` to avoid caching side effects.
- Do not enable `nodejs_compat_v2` without testing — some polyfills conflict with SolidStart's SSR.
- Do not use `import.meta.env.VITE_*` for secrets — these are baked into the client bundle.
- Do not skip the `'use server'` directive — without it, the function runs in the browser and bindings are undefined.

## Gotchas

- The `cloudflare-module` preset outputs `.output/server/index.mjs` — ensure `wrangler.toml`'s `main` matches.
- `createAsync` deduplicates calls per route navigation but does not cache across navigations by default; pass a `key` to `query()` for cross-navigation caching.
- Streaming SSR only works when the client supports `ReadableStream`; Workers always support it.
- `vinxi/http` session relies on signed cookies, not KV storage directly — if you need server-side revocation use a custom KV session store.
- D1 `RETURNING` clause requires SQLite ≥ 3.35; D1 supports it.

## Verification

```bash
# Build
npm run build

# Local dev with bindings
wrangler dev --local

# Test streaming (look for Transfer-Encoding: chunked)
curl -v http://localhost:8787/dashboard 2>&1 | grep -E 'Transfer-Encoding|chunked'

# Deploy
wrangler deploy

# Tail live logs
wrangler tail --format pretty
```

## Related

- `documentation/docs/policies/frontend/workers-remix-cloudflare-pages-d1.md`
- `documentation/backend/d1-query-patterns.md`
- `documentation/backend/kv-session-storage-patterns.md`

## Sources

- https://developers.cloudflare.com/workers/frameworks/framework-guides/solidstart/
- https://start.solidjs.com/api/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
