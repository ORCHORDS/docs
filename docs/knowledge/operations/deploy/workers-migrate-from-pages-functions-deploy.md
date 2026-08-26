# Cloudflare Workers: Migrate from Pages Functions Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your backend logic lives in Pages Functions (`functions/` directory) and you
are hitting limitations: CPU time cap of 10 ms (vs 30 s on paid Workers), no
Cron Triggers, no Queues consumers, no Durable Objects namespaces declared in
`wrangler.toml`, and opaque bundle sizes. You need to migrate to a standalone
Worker while keeping the Pages frontend deploy untouched and avoiding a
hostname change.

## Context

Pages Functions are compiled into a Worker under the hood by Cloudflare. The
migration path replaces that auto-generated Worker with an explicitly deployed
Worker that handles the same routes, then configures the Pages project to proxy
to it via a Service Binding or by removing the `functions/` directory
altogether and routing through a custom Worker route. The safest approach uses
a Service Binding so the migration is incremental: Pages continues serving
HTML/assets, the Worker handles API routes.

---

## 1. Inventory Existing Pages Functions

```typescript
// scripts/audit-functions.ts
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir: string, base = dir): string[] {
  return readdirSync(dir).flatMap(name => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full, base) : [full.replace(base + "/", "")];
  });
}

const functions = walk("functions").filter(f => f.endsWith(".ts") || f.endsWith(".js"));
console.log("Pages Functions found:");
functions.forEach(f => console.log(" ", f));
// e.g.:
//   api/products.ts     → GET /api/products
//   api/orders/[id].ts  → GET /api/orders/:id
//   _middleware.ts      → global middleware
```

---

## 2. Translate Route Handlers to Worker fetch()

Pages Functions use a file-system router; standalone Workers use a single
`fetch` handler with manual routing (or itty-router / Hono).

```typescript
// src/index.ts  (new standalone Worker)
import { Hono } from "hono";
import { productsRoute } from "./routes/products";
import { ordersRoute }   from "./routes/orders";
import { authMiddleware } from "./middleware/auth";

const app = new Hono<{ Bindings: Env }>();

// Port _middleware.ts logic
app.use("*", authMiddleware);

// Port api/products.ts
app.route("/api/products", productsRoute);

// Port api/orders/[id].ts  (Hono uses :param syntax)
app.route("/api/orders",   ordersRoute);

export default app;

// Env interface mirrors wrangler.toml bindings
interface Env {
  DB      : D1Database;
  CACHE   : KVNamespace;
  MY_QUEUE: Queue;
}
```

---

## 3. Wrangler Config for the Standalone Worker

```toml
# wrangler.toml
name = "my-app-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[limits]
cpu_ms = 30000   # was 10 ms in Pages Functions

[[d1_databases]]
binding  = "DB"
database_name = "my-app-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id      = "yyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[[queues.producers]]
binding    = "MY_QUEUE"
queue_name = "my-app-jobs"

[triggers]
crons = ["0 * * * *"]   # available in Workers, not Pages Functions
```

---

## 4. Wire Pages to the Worker via Service Binding

Pages Functions can call a Worker via a Service Binding — this lets you migrate
one route at a time without changing DNS.

```typescript
// functions/api/[[catchall]].ts  (thin proxy, kept in Pages temporarily)
interface Env {
  API_WORKER: Fetcher;   // Service Binding to the new Worker
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  // Forward entire request to the standalone Worker
  return ctx.env.API_WORKER.fetch(ctx.request);
};
```

```toml
# pages-project wrangler.toml  (add Service Binding)
[[services]]
binding  = "API_WORKER"
service  = "my-app-api"
entrypoint = "default"
```

Deploy order matters: **deploy the Worker first**, then the Pages project.

---

## 5. Deploy Pipeline — Ordered Steps

```yaml
# .github/workflows/migrate-deploy.yml
name: Worker Migration Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - name: Deploy standalone Worker
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  deploy-pages:
    needs: deploy-worker
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - name: Deploy Pages project (with Service Binding)
        run: npx wrangler pages deploy dist --project-name=my-app
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 6. Cut Over and Remove the Pages Proxy

Once the Worker is validated, delete `functions/api/[[catchall]].ts` and add a
Worker Route to intercept API paths directly:

```typescript
// wrangler.toml addition — Worker Routes (no Pages proxy needed)
[[routes]]
pattern = "app.example.com/api/*"
zone_name = "example.com"
```

```bash
# Verify Worker Route is active
npx wrangler route list

# Remove the Pages Function proxy
rm -rf functions/api/

# Re-deploy Pages (assets only; no Functions bundle generated)
npx wrangler pages deploy dist --project-name=my-app
```

---

## Anti-patterns

- **Deleting `functions/` before the Worker is deployed** — creates a window
  where `/api/*` returns 404 from the edge with no handler registered.
- **Copying Pages Function `context.env` access patterns verbatim** — Pages
  Functions inject `env` on `context`; Workers inject it as the second argument
  to `fetch(request, env, ctx)`. Mixing them causes runtime `undefined` errors.
- **Not setting `compatibility_date`** — Pages Functions inherit the project
  compatibility date; the new Worker defaults to an older date unless explicitly
  set, causing behavioral differences.
- **Deploying Worker and Pages simultaneously in one step** — if the Worker
  deploy fails, the Pages deploy may still succeed referencing a Service Binding
  that no longer exists (or has the wrong version).

---

## Gotchas

- Pages Functions have access to `context.waitUntil()` via the `ctx` object;
  in a standalone Worker the equivalent is the third argument `ctx.waitUntil()`.
- `_middleware.ts` in Pages executes before route handlers; Hono `app.use("*")`
  runs in registration order — ensure middleware is registered before routes.
- Durable Object namespaces declared in `wrangler.toml` of a Pages project
  were managed by Cloudflare as an internal Worker; after migration, you own the
  DO namespace in the Worker's config; existing DO IDs remain valid.
- The Pages Functions CPU limit (10 ms, or 50 ms on paid) is per-invocation;
  a Worker on the Paid plan gets 30 s CPU. Validate that migrated handlers do
  not rely on previously slow paths being cut off by the CPU limit.

---

## Verification

```bash
# Confirm Worker is serving /api routes
curl -I https://app.example.com/api/products

# Compare response headers — look for CF-Worker-Status or x-powered-by differences
curl -sv https://app.example.com/api/products 2>&1 | grep -E "^< (CF|x-)"

# Check Worker analytics (not Pages analytics) for /api/* requests
npx wrangler tail my-app-api --format=pretty
```

---

## Related

- `workers-assets-deploy-static-hybrid.md`
- `workers-service-bindings-deployment-ordering.md`
- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-functions-env-var-management.md`

---

## Sources

- Cloudflare Pages Functions docs: https://developers.cloudflare.com/pages/functions/
- Workers Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Worker Routes (zone-level): https://developers.cloudflare.com/workers/configuration/routing/routes/
- Hono on Cloudflare Workers: https://hono.dev/getting-started/cloudflare-workers
