# Remix v2 on Cloudflare Pages with D1 and KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to deploy a Remix v2 full-stack app to Cloudflare Pages, use a D1 SQLite database for persistent data, and store sessions in KV — all without a Node.js server. The default Remix + Vite setup targets Node; wiring it to the Cloudflare runtime requires specific adapter config and `getLoadContext`.

## Context

- Remix v2.9+
- `@remix-run/cloudflare` and `@remix-run/cloudflare-pages` adapters
- Cloudflare Pages Functions (Workers runtime)
- D1 database binding `DB`
- KV namespace binding `SESSION_KV`
- Wrangler v3
- TypeScript 5.x

---

## Section 1 — Project scaffold and dependencies

```bash
# Create project with Vite + Cloudflare template
npx create-remix@latest my-app --template remix-run/remix/templates/cloudflare
cd my-app

# Install Cloudflare-specific adapters
npm install @remix-run/cloudflare @remix-run/cloudflare-pages
npm install -D wrangler @cloudflare/workers-types
```

```jsonc
// tsconfig.json — add Cloudflare types
{
  "compilerOptions": {
    "types": ["@cloudflare/workers-types", "vite/client"],
    "lib": ["ES2022"],
    "module": "ES2022",
    "moduleResolution": "bundler",
    "target": "ES2022",
    "strict": true
  }
}
```

---

## Section 2 — getLoadContext and AppLoadContext typing

The Pages adapter calls `getLoadContext` on every request. Return your bindings here so loaders/actions can read them via `context`.

```typescript
// functions/[[path]].ts  — the catch-all Pages Function
import { createPagesFunctionHandler } from '@remix-run/cloudflare-pages';
import * as build from '../build/server';

export interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
  ENVIRONMENT: string;
}

declare module '@remix-run/cloudflare' {
  interface AppLoadContext {
    env: Env;
    cf: IncomingRequestCfProperties;
    waitUntil: (promise: Promise<unknown>) => void;
  }
}

export const onRequest = createPagesFunctionHandler({
  build,
  getLoadContext({ request, context }) {
    return {
      env: context.cloudflare.env as Env,
      cf: context.cloudflare.cf,
      waitUntil: context.cloudflare.ctx.waitUntil.bind(context.cloudflare.ctx),
    };
  },
});
```

---

## Section 3 — Loader and action patterns with D1

```typescript
// app/routes/products.$id.tsx
import type { LoaderFunctionArgs, ActionFunctionArgs } from '@remix-run/cloudflare';
import { json, redirect } from '@remix-run/cloudflare';
import { useLoaderData, Form } from '@remix-run/react';

interface Product {
  id: number;
  name: string;
  price: number;
  stock: number;
}

export async function loader({ params, context }: LoaderFunctionArgs) {
  const { DB } = context.env;

  const stmt = DB.prepare('SELECT * FROM products WHERE id = ?').bind(params.id);
  const result = await stmt.first<Product>();

  if (!result) {
    throw new Response('Not Found', { status: 404 });
  }

  return json({ product: result });
}

export async function action({ request, params, context }: ActionFunctionArgs) {
  const { DB } = context.env;
  const formData = await request.formData();
  const intent = formData.get('intent');

  if (intent === 'update-stock') {
    const newStock = Number(formData.get('stock'));
    if (isNaN(newStock) || newStock < 0) {
      return json({ error: 'Invalid stock value' }, { status: 400 });
    }

    await DB.prepare('UPDATE products SET stock = ?, updated_at = ? WHERE id = ?')
      .bind(newStock, new Date().toISOString(), params.id)
      .run();

    return redirect(`/products/${params.id}`);
  }

  if (intent === 'delete') {
    await DB.prepare('DELETE FROM products WHERE id = ?').bind(params.id).run();
    return redirect('/products');
  }

  return json({ error: 'Unknown intent' }, { status: 400 });
}

export default function ProductPage() {
  const { product } = useLoaderData<typeof loader>();

  return (
    <article>
      <h1>{product.name}</h1>
      <p>Price: ${product.price}</p>
      <p>Stock: {product.stock}</p>

      <Form method="post">
        <input type="hidden" name="intent" value="update-stock" />
        <label>
          New stock:
          <input type="number" name="stock" defaultValue={product.stock} />
        </label>
        <button type="submit">Update</button>
      </Form>

      <Form method="post" onSubmit={(e) => !confirm('Delete?') && e.preventDefault()}>
        <input type="hidden" name="intent" value="delete" />
        <button type="submit">Delete product</button>
      </Form>
    </article>
  );
}
```

---

## Section 4 — KV-backed session storage

```typescript
// app/session.server.ts
import { createWorkersKVSessionStorage } from '@remix-run/cloudflare';
import type { Env } from '../functions/[[path]]';

export function createSessionStorage(env: Env) {
  return createWorkersKVSessionStorage<{ userId: string; flash?: string }>({
    kv: env.SESSION_KV,
    cookie: {
      name: '__session',
      httpOnly: true,
      path: '/',
      sameSite: 'lax',
      secrets: ['s3cr3t-change-me'],
      secure: env.ENVIRONMENT === 'production',
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
  });
}

// Usage in a loader
export async function requireUser(
  request: Request,
  env: Env
): Promise<string> {
  const sessionStorage = createSessionStorage(env);
  const session = await sessionStorage.getSession(request.headers.get('Cookie'));
  const userId = session.get('userId');

  if (!userId) {
    throw redirect('/login');
  }

  return userId;
}
```

```typescript
// app/routes/login.tsx
import type { ActionFunctionArgs } from '@remix-run/cloudflare';
import { json, redirect } from '@remix-run/cloudflare';
import { createSessionStorage } from '~/session.server';

export async function action({ request, context }: ActionFunctionArgs) {
  const { DB, SESSION_KV, ENVIRONMENT } = context.env;
  const formData = await request.formData();
  const email = String(formData.get('email'));
  const password = <redacted-secret>'password'));

  const user = await DB.prepare(
    'SELECT id FROM users WHERE email = ? AND password_hash = ?'
  ).bind(email, await hashPassword(password)).first<{ id: string }>();

  if (!user) {
    return json({ error: 'Invalid credentials' }, { status: 401 });
  }

  const sessionStorage = createSessionStorage(context.env);
  const session = await sessionStorage.getSession();
  session.set('userId', user.id);

  return redirect('/dashboard', {
    headers: { 'Set-Cookie': await sessionStorage.commitSession(session) },
  });
}

async function hashPassword(pw: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pw));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Section 5 — Wrangler and Pages config

```toml
# wrangler.toml (used for local dev via `wrangler pages dev`)
name = "my-remix-app"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".cloudflare/output"

[[d1_databases]]
binding = "DB"
database_name = "my-remix-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[vars]
ENVIRONMENT = "development"
```

```json
// package.json scripts
{
  "scripts": {
    "dev": "wrangler pages dev --compatibility-flag nodejs_compat",
    "build": "remix vite:build",
    "deploy": "npm run build && wrangler pages deploy",
    "db:migrate": "wrangler d1 execute DB --file=./schema.sql"
  }
}
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  price REAL NOT NULL,
  stock INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Anti-patterns

- Do not import Node.js builtins (`fs`, `path`, `crypto` from Node) — use the Web Crypto API (`crypto.subtle`) instead.
- Do not use `process.env` for secrets — use `context.env.MY_SECRET` from bindings/vars.
- Do not run D1 queries outside of loader/action; never store the `DB` handle in module-level state.
- Do not use `createCookieSessionStorage` without the Workers KV variant — it won't scale across edge nodes.
- Do not set `nodejs_compat_v2` if you rely on the `crypto` global — it remaps the namespace.

## Gotchas

- `getLoadContext` is only called by Pages Functions, not by `wrangler dev` targeting a worker directly.
- The `build` import in `functions/[[path]].ts` must point to the Vite server build output (`build/server/index.js`).
- D1 `.first()` returns `null` (not undefined) when no row matches — always check for null.
- KV session TTL must be set via `maxAge` in the cookie config; KV itself does not expire unless you set `expirationTtl` manually.
- `context.cloudflare.cf` is only populated in production; it is an empty object in local `wrangler pages dev`.

## Verification

```bash
# Create the D1 database
wrangler d1 create my-remix-db

# Apply schema locally
wrangler d1 execute DB --local --file=./schema.sql

# Seed a test product
wrangler d1 execute DB --local --command \
  "INSERT INTO products (name, price, stock) VALUES ('Widget', 9.99, 100)"

# Run local Pages dev server
npm run dev

# Hit the route
curl http://localhost:8788/products/1

# Deploy to Pages
npm run deploy

# Verify production
curl https://my-remix-app.pages.dev/products/1
```

## Related

- `documentation/docs/policies/frontend/workers-solid-start-cloudflare-adapter.md`
- `documentation/backend/d1-batch-writes-transactions.md`
- `documentation/backend/kv-session-storage-patterns.md`

## Sources

- https://developers.cloudflare.com/pages/framework-guides/deploy-a-remix-site/
- https://remix.run/docs/en/main/guides/vite#cloudflare
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://remix.run/docs/en/main/utils/sessions#createworkerskvSessionstorage
