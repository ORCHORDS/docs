# React Server Components with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to use React Server Components (RSC) with a Cloudflare Workers backend but the standard Node.js streaming APIs (`ReactDOMServer.renderToPipeableStream`) are not available in the Workers runtime. You need a setup where the RSC payload endpoint runs on Workers, HTML is streamed via `renderToReadableStream`, and everything is served from a Pages Function without hitting cold-start size limits.

## Context

React 18 introduced two separate rendering paths: the HTML stream (consumed by browsers) and the RSC flight format (consumed by client components for hydration). Cloudflare Workers supports the Web Streams API natively, so `react-dom/server.edge` — which exposes `renderToReadableStream` — works out of the box. The flight format can be generated with `react-server-dom-webpack/server.edge` (or the Vite variant) and cached in KV for repeated requests. `AsyncLocalStorage` fills the role of Node.js's CLS for per-request context such as auth tokens and D1 database handles.

## RSC Payload Endpoint on Workers

```typescript
// functions/rsc.ts  (Pages Function)
import { renderToReadableStream } from 'react-dom/server.edge';
import { renderToReadableStream as renderFlightStream } from 'react-server-dom-webpack/server.edge';
import { AsyncLocalStorage } from 'node:async_hooks';
import { App } from '../src/App.server';

export const requestStorage = new AsyncLocalStorage<{
  db: D1Database;
  user: string | null;
}>();

interface Env {
  DB: D1Database;
  RSC_CACHE: KVNamespace;
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env } = ctx;
  const url = new URL(request.url);

  // Serve flight format for RSC-aware clients
  if (request.headers.get('accept') === 'text/x-component') {
    const cacheKey = `rsc:${url.pathname}`;
    const cached = await env.RSC_CACHE.get(cacheKey, 'stream');
    if (cached) {
      return new Response(cached, {
        headers: { 'content-type': 'text/x-component' },
      });
    }

    const { readable, writable } = new TransformStream();
    const user = await resolveUser(request);

    requestStorage.run({ db: env.DB, user }, () => {
      const flightStream = renderFlightStream(
        // @ts-expect-error RSC element type
        App({ url: url.pathname }),
        { signal: request.signal }
      );
      flightStream.pipeTo(writable);
    });

    // Cache for 60 s (skip for authenticated pages)
    if (!user) {
      const [forCache, forResponse] = readable.tee();
      ctx.waitUntil(
        env.RSC_CACHE.put(cacheKey, forCache, { expirationTtl: 60 })
      );
      return new Response(forResponse, {
        headers: { 'content-type': 'text/x-component' },
      });
    }

    return new Response(readable, {
      headers: { 'content-type': 'text/x-component' },
    });
  }

  // Serve full HTML stream for initial page load
  const user = await resolveUser(request);
  const stream = await requestStorage.run({ db: env.DB, user }, () =>
    renderToReadableStream(
      // @ts-expect-error RSC element type
      App({ url: url.pathname }),
      { signal: request.signal, bootstrapModules: ['/client.js'] }
    )
  );

  return new Response(stream, {
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
};

async function resolveUser(req: Request): Promise<string | null> {
  const cookie = req.headers.get('cookie') ?? '';
  const token = cookie.match(/session=([^;]+)/)?.[1];
  return token ?? null;
}
```

## D1 Data Fetching in Server Components

```typescript
// src/components/PostList.server.tsx
import { requestStorage } from '../../functions/rsc';

interface Post {
  id: number;
  title: string;
  slug: string;
}

export async function PostList() {
  const ctx = requestStorage.getStore();
  if (!ctx) throw new Error('PostList rendered outside request context');

  const result = await ctx.db
    .prepare('SELECT id, title, slug FROM posts ORDER BY created_at DESC LIMIT 20')
    .all<Post>();

  return (
    <ul className="post-list">
      {result.results.map((post) => (
        <li key={post.id}>
          <a href={`/posts/${post.slug}`}>{post.title}</a>
        </li>
      ))}
    </ul>
  );
}
```

## RSC Flight Format Caching Strategy in KV

Cache the flight stream keyed by pathname and a short TTL. Use `readable.tee()` to split the stream: one branch goes to KV via `ctx.waitUntil`, the other is returned immediately to the client. Authenticated responses must bypass the cache entirely — use a `Set-Cookie` presence check or a resolved user guard before teeing.

For cache invalidation on content updates, write a Durable Object or use a KV namespace with a version prefix derived from a `content-hash` stored alongside your D1 rows. Purge matching KV keys inside the same D1 transaction using a post-write Worker trigger.

## Wrangler Configuration

```jsonc
// wrangler.jsonc
{
  "name": "my-rsc-app",
  "compatibility_date": "2025-09-01",
  "compatibility_flags": ["nodejs_compat"],
  "d1_databases": [
    { "binding": "DB", "database_name": "app-db", "database_id": "<uuid>" }
  ],
  "kv_namespaces": [
    { "binding": "RSC_CACHE", "id": "<kv-id>" }
  ]
}
```

## Anti-patterns

- **Using `renderToPipeableStream`** — it depends on Node.js streams and throws in the Workers runtime; always use `renderToReadableStream` from `react-dom/server.edge`.
- **Storing DB handles in module-level globals** — concurrent requests share the same module instance; use `AsyncLocalStorage` to scope per-request state.
- **Caching authenticated RSC payloads in KV** — leaks user-specific data across sessions; gate caching on the absence of a resolved user.
- **Forgetting `compatibility_flags: ["nodejs_compat"]`** — `AsyncLocalStorage` from `node:async_hooks` requires this flag; without it the import fails silently in some bundler setups.

## Gotchas

- `react-server-dom-webpack` must be aliased to its `.edge` exports in your Vite/Rollup config; the default CJS build will not work in Workers.
- `renderToReadableStream` resolves after the shell renders; Suspense boundaries stream lazily — ensure your `waitUntil` budget accounts for slow D1 queries.
- KV `put` with a `ReadableStream` value requires the Workers runtime to fully consume the stream; a teed stream that is never consumed will stall the response.
- Pages Functions have a 25 MB compressed size limit; bundle React Server internals separately and load via dynamic import if you approach the limit.

## Verification

```bash
# Local dev with wrangler pages dev
npx wrangler pages dev ./dist --d1=DB --kv=RSC_CACHE

# Check flight format header
curl -H 'accept: text/x-component' http://localhost:8788/ | head -5

# Confirm KV caching after first request
npx wrangler kv key list --namespace-id=<kv-id> --prefix=rsc:

# Deploy to Pages
npx wrangler pages deploy ./dist --project-name=my-rsc-app
```

## Related

- `vite-cloudflare-pages-build-optimization.md`
- `web-components-shadow-dom-workers-api.md`

## Sources

- React Server Components RFC — https://github.com/reactjs/rfcs/blob/main/text/0188-server-components.md
- Cloudflare Workers Node.js compat — https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- react-dom server edge exports — https://react.dev/reference/react-dom/server
