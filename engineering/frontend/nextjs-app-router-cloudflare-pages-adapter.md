# Next.js App Router on Cloudflare Pages with @cloudflare/next-on-pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to deploy a Next.js 14+ App Router project to Cloudflare Pages. The default Node.js runtime is not available on Cloudflare's edge, so you need the `@cloudflare/next-on-pages` adapter to compile your app into a Cloudflare Workers-compatible bundle. Bindings such as D1, KV, and R2 cannot be accessed via `process.env`—they require a different API.

## Context

Cloudflare Pages runs on the Workers runtime, not Node.js. The `@cloudflare/next-on-pages` package transforms the Next.js build output into a format that can execute inside a Worker. Route Handlers and Server Components must use `getRequestContext().env` to reach Cloudflare bindings. The compatibility flag `nodejs_compat` must be enabled so that Node.js built-ins that *are* polyfilled (like `crypto`, `Buffer`, `stream`) work correctly.

## Build Setup and wrangler.toml Configuration

```toml
# wrangler.toml
name = "my-nextjs-app"
pages_build_output_dir = ".vercel/output/static"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[r2_buckets]]
binding = "ASSETS_BUCKET"
bucket_name = "my-assets"

[vars]
NEXT_PUBLIC_API_URL = "https://api.example.com"
APP_ENV = "production"
```

```jsonc
// package.json (relevant scripts)
{
  "scripts": {
    "build": "npx @cloudflare/next-on-pages",
    "preview": "npx wrangler pages dev",
    "deploy": "npx wrangler pages deploy"
  }
}
```

```typescript
// app/api/items/route.ts  — Route Handler accessing D1 and KV
import { getRequestContext } from '@cloudflare/next-on-pages';
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge'; // required for next-on-pages

export async function GET(request: NextRequest) {
  const { env } = getRequestContext();

  // D1 query
  const { results } = await env.DB.prepare(
    'SELECT id, name, created_at FROM items ORDER BY created_at DESC LIMIT 50'
  ).all();

  // KV cache check
  const cached = await env.CACHE.get('items:list');
  if (cached) {
    return NextResponse.json(JSON.parse(cached), {
      headers: { 'X-Cache': 'HIT' },
    });
  }

  await env.CACHE.put('items:list', JSON.stringify(results), {
    expirationTtl: 60,
  });

  return NextResponse.json(results, { headers: { 'X-Cache': 'MISS' } });
}

export async function POST(request: NextRequest) {
  const { env } = getRequestContext();
  const body = await request.json() as { name: string };

  if (!body.name || typeof body.name !== 'string') {
    return NextResponse.json({ error: 'name is required' }, { status: 400 });
  }

  const result = await env.DB.prepare(
    'INSERT INTO items (name, created_at) VALUES (?, ?) RETURNING id'
  )
    .bind(body.name, new Date().toISOString())
    .first<{ id: number }>();

  // Invalidate KV cache after write
  await env.CACHE.delete('items:list');

  return NextResponse.json({ id: result?.id }, { status: 201 });
}
```

```typescript
// app/items/page.tsx — Server Component reading from D1
import { getRequestContext } from '@cloudflare/next-on-pages';

export const runtime = 'edge';

interface Item {
  id: number;
  name: string;
  created_at: string;
}

export default async function ItemsPage() {
  const { env } = getRequestContext();

  const { results } = await env.DB.prepare(
    'SELECT id, name, created_at FROM items ORDER BY created_at DESC'
  ).all<Item>();

  return (
    <ul>
      {results.map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  );
}
```

## Accessing process.env vs getRequestContext().env

`process.env` works **only** for `[vars]` defined in `wrangler.toml` and for `NEXT_PUBLIC_*` values baked in at build time. It does **not** expose D1, KV, R2, or other binding objects—those are runtime handles that exist only inside the Worker request context. Always call `getRequestContext().env` inside a Route Handler or async Server Component when you need a binding.

| What you need | How to access |
|---|---|
| Static string var (`APP_ENV`) | `process.env.APP_ENV` |
| D1 database handle | `getRequestContext().env.DB` |
| KV namespace handle | `getRequestContext().env.CACHE` |
| R2 bucket handle | `getRequestContext().env.ASSETS_BUCKET` |

## Compatibility Flags and nodejs_compat

Add `compatibility_flags = ["nodejs_compat"]` in `wrangler.toml`. Without it, imports of Node.js built-ins like `crypto` or `buffer` throw at runtime. This flag enables Workers' polyfill layer. It does **not** give you a full Node.js environment—APIs such as `fs`, `child_process`, `net`, and `http` are not available and will throw if called.

## Anti-patterns

- Calling `getRequestContext()` outside of a request (e.g., at module top-level during build). It throws because there is no request context at build time.
- Using `process.env.DB` and expecting a binding object—it returns `undefined`.
- Omitting `export const runtime = 'edge'` on Route Handlers—the adapter will warn and the handler may be skipped.
- Importing Node.js-only packages (e.g., `sharp`, `bcrypt` native modules) that have no Workers polyfill.

## Gotchas

- `@cloudflare/next-on-pages` lags slightly behind Next.js releases; check the compatibility matrix before upgrading Next.js.
- Middleware runs at the edge but has its own context—access bindings there via `request.cf` and the `getRequestContext` export from the adapter.
- Local `wrangler pages dev` requires you to run `npx @cloudflare/next-on-pages` first; it does not watch and rebuild automatically.
- `generateStaticParams` works but statically generated pages are served as static assets, not through Workers, so they cannot call `getRequestContext()`.

## Verification

```bash
# Build
npx @cloudflare/next-on-pages

# Local preview with bindings from wrangler.toml
npx wrangler pages dev --d1=DB --kv=CACHE

# Deploy
npx wrangler pages deploy

# Smoke test a Route Handler
curl -s https://my-nextjs-app.pages.dev/api/items | jq .
```

## Related

- `tanstack-query-workers-optimistic-mutations.md`
- `qwik-cloudflare-pages-resumability.md`
- `htmx-cloudflare-workers-hypermedia.md`

## Sources

- https://developers.cloudflare.com/pages/framework-guides/nextjs/ssr/
- https://github.com/cloudflare/next-on-pages
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
