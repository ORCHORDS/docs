# Angular Universal SSR on Cloudflare Pages with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have an Angular 17+ application and want to run server-side rendering on Cloudflare Pages Functions using the Workers runtime. The default Angular SSR builder targets Node.js; adapting it to the Workers runtime requires replacing Node-specific APIs and wiring D1 through the Pages `platform` binding context.

## Context

- Angular 17+ with `@angular/ssr` (replaces the old `@nguniversal/express-engine`)
- `@angular/build:application` builder with SSR enabled
- Cloudflare Pages Functions (Workers runtime, `nodejs_compat`)
- `@cloudflare/workers-types` for D1, KV
- D1 binding `DB`, KV binding `KV_CACHE`
- Wrangler v3, TypeScript 5.x

---

## Section 1 — Angular SSR project setup

```bash
# New Angular project with SSR
npx @angular/cli@latest new my-angular-app --ssr
cd my-angular-app

# Or add SSR to existing project
ng add @angular/ssr

# Install Cloudflare types
npm install -D @cloudflare/workers-types wrangler
```

```json
// angular.json — verify SSR is enabled under "build"
{
  "projects": {
    "my-angular-app": {
      "architect": {
        "build": {
          "builder": "@angular/build:application",
          "options": {
            "outputPath": "dist/my-angular-app",
            "server": "src/main.server.ts",
            "prerender": false,
            "ssr": {
              "entry": "src/server.ts"
            }
          }
        }
      }
    }
  }
}
```

---

## Section 2 — Workers-compatible server entry

Replace the default Express-based `server.ts` with a Fetch API handler.

```typescript
// src/server.ts  — Workers fetch handler, NOT Express
import { APP_BASE_HREF } from '@angular/common';
import { CommonEngine } from '@angular/ssr/node'; // we replace this below
import { renderApplication } from '@angular/platform-server';
import bootstrap from './main.server';

export interface Env {
  DB: D1Database;
  KV_CACHE: KVNamespace;
  ASSETS: Fetcher; // Pages static asset binding
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Serve static assets through Pages ASSETS binding
    // This is faster than SSR for .js/.css/.png files
    const isAsset = /\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|map)$/i.test(url.pathname);
    if (isAsset) {
      return env.ASSETS.fetch(request);
    }

    try {
      const html = await renderApplication(bootstrap, {
        document: await getDocument(env, url),
        url: url.pathname + url.search,
        platformProviders: [
          { provide: APP_BASE_HREF, useValue: '/' },
          // Inject Cloudflare bindings into the Angular DI tree
          { provide: CLOUDFLARE_ENV, useValue: env },
          { provide: EXECUTION_CTX, useValue: ctx },
        ],
      });

      return new Response(html, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    } catch (err) {
      console.error('SSR error', err);
      // Fallback to client-side rendering
      return env.ASSETS.fetch(new Request(new URL('/index.html', request.url), request));
    }
  },
};

async function getDocument(env: Env, url: URL): Promise<string> {
  // Serve the Angular index.html shell from Pages ASSETS
  const resp = await env.ASSETS.fetch(new Request(new URL('/index.html', url.origin)));
  return resp.text();
}
```

```typescript
// src/tokens.ts — DI tokens for Cloudflare bindings
import { InjectionToken } from '@angular/core';
import type { Env } from './server';

export const CLOUDFLARE_ENV = new InjectionToken<Env>('CLOUDFLARE_ENV');
export const EXECUTION_CTX = new InjectionToken<ExecutionContext>('EXECUTION_CTX');
```

---

## Section 3 — D1 service via platform binding

```typescript
// src/app/services/product.service.ts
import { Injectable, Inject, PLATFORM_ID } from '@angular/core';
import { isPlatformServer } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Observable, from } from 'rxjs';
import { CLOUDFLARE_ENV } from '../../tokens';
import type { Env } from '../../server';

export interface Product {
  id: number;
  name: string;
  price: number;
  stock: number;
}

@Injectable({ providedIn: 'root' })
export class ProductService {
  constructor(
    private http: HttpClient,
    @Inject(PLATFORM_ID) private platformId: object,
    @Inject(CLOUDFLARE_ENV) private env: Env
  ) {}

  getProducts(): Observable<Product[]> {
    if (isPlatformServer(this.platformId)) {
      // Direct D1 access during SSR
      return from(this.fetchFromD1());
    }
    // Client-side: hit our own API route
    return this.http.get<Product[]>('/api/products');
  }

  private async fetchFromD1(): Promise<Product[]> {
    const result = await this.env.DB
      .prepare('SELECT id, name, price, stock FROM products ORDER BY id DESC LIMIT 50')
      .all<Product>();
    return result.results;
  }

  getProduct(id: number): Observable<Product> {
    if (isPlatformServer(this.platformId)) {
      return from(
        this.env.DB
          .prepare('SELECT * FROM products WHERE id = ?')
          .bind(id)
          .first<Product>()
          .then((r) => {
            if (!r) throw new Error(`Product ${id} not found`);
            return r;
          })
      );
    }
    return this.http.get<Product>(`/api/products/${id}`);
  }
}
```

---

## Section 4 — API route via Pages Function

For client-side data fetching, expose a JSON API through a dedicated Pages Function.

```typescript
// functions/api/products.ts
import type { Env } from '../../src/server';

export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  const result = await env.DB
    .prepare('SELECT id, name, price, stock FROM products ORDER BY id DESC')
    .all();

  return Response.json(result.results, {
    headers: { 'Cache-Control': 'public, max-age=30, stale-while-revalidate=60' },
  });
};

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const body = await request.json<{ name: string; price: number }>();

  if (!body.name || !body.price || body.price <= 0) {
    return Response.json({ error: 'Invalid input' }, { status: 400 });
  }

  const result = await env.DB
    .prepare('INSERT INTO products (name, price, stock) VALUES (?, ?, 0) RETURNING id')
    .bind(body.name, body.price)
    .first<{ id: number }>();

  if (!result) return Response.json({ error: 'Insert failed' }, { status: 500 });

  return Response.json({ id: result.id }, { status: 201 });
};
```

```typescript
// functions/api/products/[id].ts
import type { Env } from '../../../src/server';

export const onRequestGet: PagesFunction<Env> = async ({ params, env }) => {
  const id = Number(params.id);
  if (isNaN(id)) return Response.json({ error: 'Invalid id' }, { status: 400 });

  const row = await env.DB
    .prepare('SELECT * FROM products WHERE id = ?')
    .bind(id)
    .first();

  if (!row) return Response.json({ error: 'Not found' }, { status: 404 });
  return Response.json(row);
};
```

---

## Section 5 — Wrangler and Pages config

```toml
# wrangler.toml
name = "my-angular-app"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]
# For Pages, SSR entry is defined in _worker.js or via build output
# Local dev:
pages_build_output_dir = "dist/my-angular-app/browser"

[[d1_databases]]
binding = "DB"
database_name = "angular-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "KV_CACHE"
id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

```json
// package.json
{
  "scripts": {
    "build": "ng build",
    "dev": "wrangler pages dev dist/my-angular-app/browser",
    "deploy": "ng build && wrangler pages deploy dist/my-angular-app/browser",
    "db:migrate": "wrangler d1 execute DB --file=./schema.sql"
  }
}
```

---

## Anti-patterns

- Do not use `TransferState` with server-only data that includes secrets — it is serialised into the HTML and sent to the client.
- Do not call D1 from Angular lifecycle hooks like `ngOnInit` without guarding with `isPlatformServer` — client builds do not have D1.
- Do not use `zone.js` async wrappers around `await` D1 calls — they are incompatible with the Workers microtask queue in some edge cases; use RxJS `from()` instead.
- Do not rely on `localStorage` in SSR paths — it does not exist in the Workers runtime.
- Do not set `prerender: true` for routes that fetch live D1 data — prerendering freezes data at build time.

## Gotchas

- Angular's `HttpClient` in SSR does not automatically use the Workers `fetch`; ensure `provideHttpClient(withFetch())` is in `app.config.server.ts`.
- The `CLOUDFLARE_ENV` token must be provided in `platformProviders` (in `renderApplication`), not `providers` in `app.config.ts`, or DI will fail on the server.
- Pages Functions file-system routing applies to `functions/` — ensure your SSR catch-all does not shadow API routes by ordering them correctly.
- `@angular/ssr/node` imports Node-specific code; import from `@angular/platform-server` directly for the Workers-compatible `renderApplication`.
- TypeScript strict mode will flag `(event.nativeEvent as any)` — define proper interfaces or use `unknown` casts carefully.

## Verification

```bash
# Build Angular app
ng build --configuration production

# Apply D1 schema
wrangler d1 execute DB --local --file=./schema.sql

# Start Pages dev
wrangler pages dev dist/my-angular-app/browser --local

# Test SSR (should return full HTML with product data)
curl -s http://localhost:8788/ | grep '<app-root'

# Test API route
curl http://localhost:8788/api/products

# Deploy
npm run deploy
```

## Related

- `documentation/categories/frontend/workers-remix-cloudflare-pages-d1.md`
- `documentation/backend/d1-batch-writes-transactions.md`

## Sources

- https://developers.cloudflare.com/pages/framework-guides/deploy-an-angular-site/
- https://angular.dev/guide/ssr
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/pages/functions/
