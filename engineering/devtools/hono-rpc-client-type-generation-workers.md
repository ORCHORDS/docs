# Hono RPC Client Type Generation for Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Hono API running on Cloudflare Workers and a frontend (or another Worker) that consumes it. You are writing `fetch('/api/users')` calls with manually typed responses, losing end-to-end type safety whenever a route shape changes. You want the client to infer request/response types directly from the server route definition with zero runtime overhead.

## Context

Hono ships a first-party RPC layer (`hono/client`) that exports `AppType` from the server and uses it to generate a fully typed `hc` client. The client uses `fetch` under the hood — no codegen step, no OpenAPI round-trip. On Cloudflare Workers the pattern works both for browser clients consuming a Worker API and for service-binding calls between Workers. The approach requires Hono v3.9+ and TypeScript 5.0+.

## 1. Structuring the Server for Type Export

Every chainable route must use `.get()`, `.post()`, etc. with typed validators. Export the `typeof app` as `AppType`.

```typescript
// workers/api/src/index.ts
import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'

const userSchema = z.object({ name: z.string(), email: z.string().email() })

const app = new Hono<{ Bindings: Env }>()
  .get('/users', async (c) => {
    const users = await c.env.DB.prepare('SELECT * FROM users').all()
    return c.json(users.results as User[])
  })
  .post('/users', zValidator('json', userSchema), async (c) => {
    const body = c.req.valid('json')
    await c.env.DB.prepare('INSERT INTO users (name, email) VALUES (?, ?)')
      .bind(body.name, body.email)
      .run()
    return c.json({ ok: true }, 201)
  })

export type AppType = typeof app
export default app
```

The key constraint: every route must be chained on a single `app` expression so TypeScript can infer the union of all route types.

## 2. Consuming the Type in a Browser Client

Install `hono` in the frontend package (types-only import, zero bundle impact when tree-shaken):

```bash
pnpm add hono
```

```typescript
// apps/web/src/lib/api.ts
import { hc } from 'hono/client'
import type { AppType } from '@example project/api'   // path alias to the Worker package

export const client = hc<AppType>('https://api.example.com')

// Fully typed — IDE autocompletes route, method, body, and response
const res = await client.users.$get()
if (res.ok) {
  const users = await res.json()   // users: User[]
}

const created = await client.users.$post({
  json: { name: 'Alice', email: 'alice@example.com' },
})
// created: Response<{ ok: boolean }, 201>
```

## 3. Service-Binding RPC Between Workers

When calling Worker A from Worker B via a service binding, pass the service binding's `fetch` as the second argument to `hc`:

```typescript
// workers/jobs/src/index.ts
import { hc } from 'hono/client'
import type { AppType } from '@example project/api'

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // env.API is a service binding to the API Worker
    const client = hc<AppType>('http://api', { fetch: env.API.fetch.bind(env.API) })
    const res = await client.users.$get()
    const users = await res.json()
    // process users...
  },
}
```

No network hop occurs — the runtime routes the call in-process.

## 4. Monorepo Workspace Type Sharing

Structure packages so the `AppType` is importable without bundling server code:

```
packages/
  api-types/
    package.json      # "main": "src/index.ts", no build step
    src/index.ts      # re-exports AppType only
workers/
  api/
    src/index.ts      # source of truth
apps/
  web/                # imports from api-types
```

```jsonc
// packages/api-types/package.json
{
  "name": "@example project/api-types",
  "version": "0.0.0",
  "private": true,
  "exports": {
    ".": "./src/index.ts"
  },
  "peerDependencies": {
    "hono": ">=4"
  }
}
```

```typescript
// packages/api-types/src/index.ts
export type { AppType } from '../../workers/api/src/index'
```

TypeScript resolves the type import at compile time; nothing ships to the browser.

## 5. Testing the RPC Client with Miniflare

Use `app.request()` in vitest tests — no real HTTP needed:

```typescript
// workers/api/src/index.test.ts
import { describe, it, expect } from 'vitest'
import { hc } from 'hono/client'
import app, { type AppType } from './index'

const client = hc<AppType>('http://localhost', {
  fetch: app.request.bind(app),
})

describe('GET /users', () => {
  it('returns an array', async () => {
    const res = await client.users.$get()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
  })
})
```

## 6. Keeping Client in Sync with CI

Add a type-check step that imports the client to catch drift early:

```yaml
# .github/workflows/typecheck.yml
- name: Type-check API client
  run: pnpm --filter @example project/web tsc --noEmit
```

Because `AppType` is a structural type, any breaking route change (renamed path, changed body schema) surfaces as a TypeScript error in the consuming package before deployment.

## Anti-patterns

- **Importing server runtime code into the client bundle.** Only import `type AppType` — never the Hono app instance itself. Use `import type` or a dedicated types-only package.
- **Using string literals for paths with `hc`.** `client.users.$get()` is type-safe; `fetch('/users')` is not. Never mix the two styles.
- **Omitting `zValidator` on POST routes.** Without a typed validator, `c.req.valid('json')` returns `unknown` and the client body type degrades to `unknown`.
- **Wrapping `app` in a middleware that hides the route types.** `app.use(logger())` is fine; `const wrapped = createMiddleware(app)` may erase the generic.

## Gotchas

- `hc` infers the base URL at the call site; it does not validate whether the Worker is actually reachable. Typos in the URL produce runtime 404s, not compile errors.
- Query parameter typing requires `.query()` inside the route definition; path parameters use `:id` syntax and appear as `{ param: { id: string } }` in the client call.
- Hono RPC does not support streaming responses (`c.body(ReadableStream)`) — those must fall back to untyped `fetch`.
- When the Worker uses `wrangler.toml` `routes`, the base URL passed to `hc` must match the production domain, not `localhost`, for service-binding calls in production.

## Verification

```bash
# Confirm zero runtime bytes added from type import
pnpm --filter @example project/web build
# Check the bundle — hono/client ships ~1 kB minified for the fetch wrapper

# Full type-check across all packages
pnpm tsc --build --verbose

# Run RPC unit tests
pnpm --filter @example project/api vitest run
```

## Related

- `hono-openapi-spec-generation.md`
- `hono-test-utils-workers-unit-testing.md`
- `typescript-workers-env-interface-module-augmentation.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`
- `vitest-workers-miniflare-testing-setup.md`

## Sources

- https://hono.dev/docs/guides/rpc
- https://hono.dev/docs/api/hono-client
- https://github.com/honojs/hono/tree/main/src/client
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
