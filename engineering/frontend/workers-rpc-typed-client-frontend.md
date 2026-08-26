# Workers RPC with Service Bindings for Type-Safe Frontend-to-Worker Calls

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Pages Functions calling internal Worker services via `fetch()` lose all type safety:
the request body is `unknown`, the response type must be manually asserted, and any
schema mismatch is caught only at runtime. Workers RPC — available when a Worker
extends `WorkerEntrypoint` — replaces HTTP-over-service-binding with direct
method calls that are typed end-to-end. The caller receives the return value of the
Worker method directly, with no `Response.json()` boilerplate, no status code checks,
and full TypeScript inference through the binding.

---

## Context

Workers RPC was introduced alongside the `WorkerEntrypoint` and `DurableObject`
class APIs. A Worker that extends `WorkerEntrypoint` exposes its public async methods
as callable RPC stubs when bound to another Worker or Pages Functions environment via
a service binding. The RPC call crosses the Worker boundary with near-zero overhead
(no HTTP parsing, no TCP round-trip) — both Workers run in the same Cloudflare PoP
and share a direct inter-isolate channel.

RPC stubs support:
- Primitive return types (string, number, boolean, null)
- Plain objects and arrays (serialised via structured clone)
- `ReadableStream`, `Request`, `Response` (zero-copy where possible)
- Stub chaining (returning another `RpcTarget` for further calls)

---

## Worker Service: Defining RPC Methods

```typescript
// packages/catalog-worker/src/index.ts
import { WorkerEntrypoint } from 'cloudflare:workers';

export interface Product {
  id: string;
  name: string;
  price: number;
  stock: number;
}

export interface SearchResult {
  products: Product[];
  total: number;
  cursor?: string;
}

// Extend WorkerEntrypoint — public methods become RPC-callable
export default class CatalogWorker extends WorkerEntrypoint<Env> {
  /** Full-text product search backed by Vectorize + D1 */
  async searchProducts(
    query: string,
    opts: { limit?: number; cursor?: string } = {}
  ): Promise<SearchResult> {
    const { limit = 20, cursor } = opts;

    const rows = await this.env.DB.prepare(
      `SELECT id, name, price, stock
         FROM products
        WHERE name LIKE ?1
        LIMIT ?2`
    )
      .bind(`%${query}%`, limit)
      .all<Product>();

    return { products: rows.results, total: rows.results.length };
  }

  /** Single product lookup */
  async getProduct(id: string): Promise<Product | null> {
    const row = await this.env.DB.prepare(
      'SELECT * FROM products WHERE id = ?1'
    )
      .bind(id)
      .first<Product>();
    return row ?? null;
  }
}
```

The Worker's `wrangler.toml` requires no special RPC configuration — exporting a
`WorkerEntrypoint` subclass as the default export is sufficient.

---

## Binding the Service in Pages Functions (wrangler.toml)

```toml
# apps/storefront/wrangler.toml
name = "storefront-pages"
pages_build_output_dir = "dist"
compatibility_date = "2025-01-01"

[[services]]
binding   = "CATALOG"
service   = "catalog-worker"
entrypoint = "default"   # matches the `export default class CatalogWorker`
```

The `entrypoint` field must match the exported name of the `WorkerEntrypoint` class.

---

## Calling RPC Methods from Pages Functions

```typescript
// apps/storefront/functions/api/products/search.ts
import type CatalogWorker from '../../../packages/catalog-worker/src/index';

type Env = {
  CATALOG: Service<CatalogWorker>;   // typed stub via Service<T>
};

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const url = new URL(ctx.request.url);
  const query = url.searchParams.get('q') ?? '';
  const limit = Number(url.searchParams.get('limit') ?? '20');

  // Direct method call — no fetch(), no JSON.parse(), fully typed
  const result = await ctx.env.CATALOG.searchProducts(query, { limit });

  return Response.json(result);
};
```

TypeScript infers `result` as `SearchResult` without any manual assertion. If
`searchProducts` signature changes in the Worker, the Pages function emits a
compile error immediately.

---

## Sharing Types Across the Monorepo

The `Service<T>` generic requires the Worker class type to be importable. Structure
the monorepo so the type-only import is possible without pulling in Worker runtime
code:

```
packages/
  catalog-worker/
    src/
      index.ts          ← WorkerEntrypoint implementation
      types.ts          ← exported Product, SearchResult interfaces (no runtime deps)
apps/
  storefront/
    functions/
      api/products/search.ts
    tsconfig.json
```

```typescript
// packages/catalog-worker/src/types.ts
export interface Product { id: string; name: string; price: number; stock: number; }
export interface SearchResult { products: Product[]; total: number; cursor?: string; }
```

```typescript
// apps/storefront/functions/api/products/search.ts
import type { SearchResult } from 'catalog-worker/types';  // type-only, no runtime

// Use the interface directly instead of importing the class
// when the monorepo layout makes class import circular
```

---

## Returning Streams from RPC Methods

RPC supports `ReadableStream` return values for large payloads. The stream is
transferred zero-copy between isolates:

```typescript
// In CatalogWorker
async exportProducts(): Promise<ReadableStream<Uint8Array>> {
  const { readable, writable } = new TransformStream<Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  // Pipe D1 cursor rows into the stream asynchronously
  this.ctx.waitUntil(
    (async () => {
      const stmt = this.env.DB.prepare('SELECT * FROM products');
      const cursor = stmt.cursor<Product>();
      for await (const row of cursor) {
        await writer.write(encoder.encode(JSON.stringify(row) + '\n'));
      }
      await writer.close();
    })()
  );

  return readable;
}
```

```typescript
// Pages Function consuming the stream
const stream = await ctx.env.CATALOG.exportProducts();
return new Response(stream, {
  headers: { 'Content-Type': 'application/x-ndjson' },
});
```

---

## Local Development with Wrangler

RPC bindings work in `wrangler dev` when both Workers are running. Use
`--port` flags to run them simultaneously and declare the service binding
in the Pages Functions `wrangler.toml`:

```bash
# Terminal 1: start the catalog worker
cd packages/catalog-worker && wrangler dev --port 8787

# Terminal 2: start the Pages Functions dev server
cd apps/storefront && wrangler pages dev dist --port 8788
```

Wrangler resolves local service bindings by matching the `service` name to a
running local Worker instance. The RPC call goes through `127.0.0.1` during
development with the same API surface as production.

---

## Anti-patterns

- **Using `fetch()` to call a Worker that could be bound as a service**: HTTP
  fetch across service boundaries adds JSON parsing overhead and loses type safety.
  Prefer `Service<T>` + RPC when both Workers are in the same Cloudflare account.
- **Passing non-structured-cloneable objects**: Functions, Promises, class instances
  with prototype methods, and DOM objects cannot cross RPC boundaries. Serialize
  them to plain objects first.
- **Importing the Worker class at runtime in the Pages Functions bundle**: The
  `import type` keyword is essential. Importing the runtime class pulls in Worker-
  specific globals (`cloudflare:workers`) that do not exist in the Pages Functions
  build target.
- **Relying on RPC for public-facing APIs**: RPC is for internal service-to-service
  calls. Public API endpoints should still use HTTP `fetch()` to allow for
  rate limiting, auth middleware, and CDN caching.

---

## Gotchas

- `Service<T>` is available in `@cloudflare/workers-types` version 4.20240725.0
  and later. Older versions expose `Fetcher` without the generic parameter.
- RPC calls from Pages Functions count against the Pages Functions request limit,
  not the bound Worker's request limit — but CPU time in the callee counts against
  the callee's CPU limit.
- `WorkerEntrypoint` methods must be `async`. Synchronous public methods are not
  exposed as RPC stubs.
- Structured clone does not support `undefined` object property values — they are
  dropped. Use `null` for optional absent values in RPC return types.
- The `entrypoint` field in the service binding defaults to `"default"` if omitted,
  which matches `export default class`. Named exports require an explicit entrypoint.

---

## Verification

1. Add a `console.log` inside `CatalogWorker.searchProducts`.
2. Call the Pages Function endpoint with `curl 'http://localhost:8788/api/products/search?q=shirt'`.
3. Confirm the log appears in the **catalog-worker** terminal (not the Pages terminal),
   proving the RPC crossed the service boundary.
4. Introduce a type error in the Pages Function (e.g., pass `limit: 'twenty'`) and
   confirm `tsc` catches it without running the code.

---

## Related

- `hono-cloudflare-workers-frontend-api.md` — Hono on Workers for HTTP APIs
- `remix-cloudflare-workers-adapter.md` — Remix with Worker service bindings
- `websocket-durable-objects-realtime-ui.md` — Durable Objects RPC for realtime

---

## Sources

- Workers RPC documentation: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- WorkerEntrypoint API: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/rpc/
- Service bindings overview: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- `@cloudflare/workers-types` changelog: https://github.com/cloudflare/workers-types/releases
