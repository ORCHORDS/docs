# Multi-Worker Local Dev with Wrangler Service Bindings

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You have two or more Cloudflare Workers that communicate via service bindings, and you want both workers running locally during development so you can test cross-worker calls without deploying to Cloudflare.

## Context
Wrangler v3+ supports `wrangler dev` in multi-worker mode: a `services` array in `wrangler.toml` declares a dependency on another Worker by name, and Wrangler starts both in the same local `workerd` process. The calling Worker can invoke the callee via the service binding just like in production. This is invaluable for testing auth gateways calling downstream APIs, or a public-facing router dispatching to internal service Workers.

## Project Structure

```
monorepo/
├── packages/
│   ├── api-gateway/
│   │   ├── src/index.ts
│   │   └── wrangler.toml
│   └── users-service/
│       ├── src/index.ts
│       └── wrangler.toml
└── package.json
```

## wrangler.toml Configuration

Configure the downstream service Worker first. It has no service bindings of its own:

```toml
# packages/users-service/wrangler.toml
name = "users-service"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[d1_databases]]
binding = "DB"
database_name = "users-db"
database_id = "00000000-0000-0000-0000-000000000001"
```

Configure the gateway Worker to bind the downstream by name:

```toml
# packages/api-gateway/wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[services]]
binding = "USERS_SERVICE"
service = "users-service"   # Must match `name` in the callee's wrangler.toml
```

## TypeScript Types for Service Bindings

Generate types with `wrangler types` or declare them manually:

```typescript
// packages/api-gateway/src/types.d.ts
export interface Env {
  USERS_SERVICE: Fetcher;  // The service binding type
  API_SECRET: string;
}
```

```typescript
// packages/users-service/src/types.d.ts
export interface Env {
  DB: D1Database;
}
```

## Implementing the Downstream Worker

```typescript
// packages/users-service/src/index.ts
import { Hono } from "hono";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

app.get("/users/:id", async (c) => {
  const { id } = c.req.param();
  const user = await c.env.DB.prepare(
    "SELECT id, email, name FROM users WHERE id = ?"
  )
    .bind(id)
    .first<{ id: string; email: string; name: string }>();

  if (!user) return c.json({ error: "Not found" }, 404);
  return c.json(user);
});

app.post("/users", async (c) => {
  const { email, name } = await c.req.json<{ email: string; name: string }>();
  const id = crypto.randomUUID();
  await c.env.DB.prepare(
    "INSERT INTO users (id, email, name) VALUES (?, ?, ?)"
  )
    .bind(id, email, name)
    .run();
  return c.json({ id }, 201);
});

export default app;
```

## Calling the Service Binding from the Gateway

```typescript
// packages/api-gateway/src/index.ts
import { Hono } from "hono";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

// Authenticate, then proxy to the downstream service
app.use("*", async (c, next) => {
  const secret = <redacted-secret>"X-API-Secret");
  if (secret !== c.env.API_SECRET) {
    return c.json({ error: "Unauthorized" }, 401);
  }
  await next();
});

app.get("/users/:id", async (c) => {
  const { id } = c.req.param();
  // Service binding call: routed inside workerd, no real HTTP
  const response = await c.env.USERS_SERVICE.fetch(
    new Request(`https://users-service/users/${id}`)
  );
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
});

app.post("/users", async (c) => {
  const body = await c.req.json();
  const response = await c.env.USERS_SERVICE.fetch(
    new Request("https://users-service/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
  return new Response(response.body, { status: response.status });
});

export default app;
```

## Running Both Workers Locally

Start the downstream service first in one terminal, then the gateway in another:

```bash
# Terminal 1 — downstream service (no --port needed if gateway starts it)
cd packages/users-service
pnpm wrangler dev --local --port 8686

# Terminal 2 — gateway; Wrangler discovers users-service via the services[] binding
cd packages/api-gateway
pnpm wrangler dev --local --port 8787
```

Alternatively, use a `Procfile` with `concurrently` or `just`:

```bash
# justfile
dev:
  concurrently \
    "cd packages/users-service && wrangler dev --local --port 8686" \
    "cd packages/api-gateway   && wrangler dev --local --port 8787"
```

Wrangler v3 auto-discovers the callee when both share the same local session (same terminal group). If auto-discovery fails, explicitly set `experimental_services` in `miniflare` options.

## TypeScript Path Setup for Shared Types

```json
// packages/api-gateway/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "paths": {
      "@repo/users-service-types": ["../users-service/src/types.d.ts"]
    }
  }
}
```

## Anti-patterns
- Using a real `https://` URL in service binding `fetch()` calls; use an arbitrary non-routable hostname like `https://users-service/` — the URL host is irrelevant for service bindings.
- Deploying both workers to verify changes during development; the local multi-worker mode avoids the deploy roundtrip entirely.
- Declaring the same D1 `database_id` in both `wrangler.toml` files; only the worker that owns the binding should declare it — the gateway accesses D1 only via the service binding.
- Starting both workers on the same port; each must have a distinct `--port`.
- Forgetting to set `nodejs_compat` in both workers when using Node-compat APIs on either side of the binding.

## Gotchas
- Service binding calls do not go through the public internet even locally; they are synchronous in-process calls in `workerd`, so network mocking tools like MSW on the Node.js side won't intercept them.
- The `Fetcher` type is only available in `@cloudflare/workers-types`; ensure it's installed and referenced in `tsconfig.json`.
- `wrangler dev` for the callee must be running before the gateway starts its first request; a race condition at startup may cause `503 Service Unavailable` on the first request.
- Workers in a multi-worker local setup share CPU resources; CPU-intensive callee work can cause timeout-like behavior in the calling worker during heavy load.
- Custom domains configured in `wrangler.toml` are ignored in local dev; service bindings use the worker name for routing.

## Verification
```bash
# Confirm the gateway proxies through to the service
curl -s -H "X-API-Secret: dev-secret" http://localhost:8787/users/test-id
# Expect: {"error":"Not found"} with status 404 (real D1 lookup)

# Check both dev servers appear in wrangler output
wrangler dev --local --port 8787 2>&1 | grep "Service binding"
```

## Related
- `/documentation/docs/policies/devtools/wrangler-dev-local-d1-r2-kv.md`
- `/documentation/docs/policies/devtools/vitest-pool-workers-cloudflare-test-api.md`
- `/documentation/docs/policies/devtools/turborepo-cloudflare-workers-pipeline.md`
- `/documentation/docs/policies/devtools/pnpm-workspace-setup.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/wrangler/configuration/#services
- https://developers.cloudflare.com/workers/testing/local-development/
