# TypeScript Workers Env Interface Module Augmentation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

`wrangler types` generates a `worker-configuration.d.ts` that clobbers on every run and cannot be committed cleanly in monorepos where multiple Workers share a common types package. You want a stable, hand-maintained `Env` type that merges binding declarations from multiple sources (shared bindings, per-worker bindings, feature flags) without running a codegen step, while keeping strict TypeScript checks across all Workers.

## Context

Cloudflare Workers expose their bindings through a typed `Env` interface. The canonical pattern is the generated `worker-configuration.d.ts` from `wrangler types`, but that file is per-Worker and regenerated on every `wrangler dev` start. In large monorepos with shared infrastructure bindings (KV namespaces, service bindings, D1 databases), maintaining a hand-crafted module augmentation strategy is more stable and composable. TypeScript's declaration merging lets you split the `Env` definition across multiple files and packages, assembling a complete type at the Worker boundary.

## 1. Base Shared Bindings Package

Define infrastructure-level bindings that every Worker has access to in a shared package:

```typescript
// packages/worker-env/src/shared.d.ts
/// <reference types="@cloudflare/workers-types" />

// Module augmentation — merges with any other Env declarations
declare global {
  interface SharedEnv {
    /** KV namespace for feature flags */
    FLAGS: KVNamespace
    /** D1 database shared across all Workers */
    DB: D1Database
    /** R2 bucket for user uploads */
    UPLOADS: R2Bucket
    /** Environment name */
    ENVIRONMENT: 'development' | 'staging' | 'production'
  }
}

export {}   // make this a module so global augmentation applies
```

```jsonc
// packages/worker-env/package.json
{
  "name": "@example project/worker-env",
  "version": "0.0.0",
  "private": true,
  "types": "src/shared.d.ts",
  "exports": {
    ".": { "types": "./src/shared.d.ts" }
  }
}
```

## 2. Per-Worker Env Declaration

Each Worker extends `SharedEnv` with its own bindings:

```typescript
// workers/api/src/env.d.ts
/// <reference types="@example project/worker-env" />

/**
 * Env for the API Worker — composed from shared + per-worker bindings.
 * Passed as the Bindings generic to Hono / itty-router / plain handler.
 */
export interface Env extends SharedEnv {
  /** Service binding to the Jobs Worker */
  JOBS: Fetcher
  /** Durable Object namespace for rate limiting */
  RATE_LIMITER: DurableObjectNamespace
  /** Secret: Stripe API key */
  STRIPE_SECRET_KEY: string
}
```

```typescript
// workers/api/src/index.ts
import { Hono } from 'hono'
import type { Env } from './env'   // typed, no codegen

const app = new Hono<{ Bindings: Env }>()

app.get('/health', (c) => {
  // c.env.DB   — D1Database (from SharedEnv)
  // c.env.RATE_LIMITER  — DurableObjectNamespace (from per-worker)
  return c.json({ ok: true, env: c.env.ENVIRONMENT })
})

export default app
```

## 3. Feature-Flag Binding Augmentation

When feature flags are stored as KV JSON values, create a typed accessor layer without touching the raw `Env`:

```typescript
// packages/worker-env/src/flags.ts
import type { KVNamespace } from '@cloudflare/workers-types'

export interface FeatureFlags {
  newCheckout: boolean
  aiSuggestions: boolean
  multiRegion: boolean
}

export async function getFlags(kv: KVNamespace): Promise<FeatureFlags> {
  const raw = await kv.get('flags', 'json')
  return {
    newCheckout: false,
    aiSuggestions: false,
    multiRegion: false,
    ...(raw as Partial<FeatureFlags> | null),
  }
}
```

Usage:

```typescript
import { getFlags } from '@example project/worker-env/flags'

app.use('*', async (c, next) => {
  const flags = await getFlags(c.env.FLAGS)
  c.set('flags', flags)   // store in context for handlers
  await next()
})
```

## 4. Disabling `wrangler types` Codegen Safely

To prevent `wrangler types` from overwriting your hand-crafted declarations, configure `wrangler.toml` to skip auto-type generation in CI while keeping it available locally as a cross-check:

```toml
# wrangler.toml
[dev]
# Prevent wrangler dev from writing worker-configuration.d.ts
# We use hand-crafted declarations in src/env.d.ts
```

```bash
# package.json scripts — run wrangler types only as a manual audit tool
# "types:audit": "wrangler types --output-path /tmp/worker-configuration-audit.d.ts"
```

Add `worker-configuration.d.ts` to `.gitignore` so stale generated files never land in the repo:

```
# .gitignore
worker-configuration.d.ts
```

## 5. Validating Declarations Match Actual Bindings at Runtime

TypeScript types are erased at runtime. Add a startup validation in non-production:

```typescript
// workers/api/src/env-check.ts
export function assertEnv(env: Env): void {
  if (env.ENVIRONMENT === 'production') return

  const required: (keyof Env)[] = [
    'DB', 'FLAGS', 'UPLOADS', 'STRIPE_SECRET_KEY', 'RATE_LIMITER',
  ]
  for (const key of required) {
    if (env[key] == null) {
      throw new Error(`[env-check] Missing binding: ${key}`)
    }
  }
}
```

```typescript
// workers/api/src/index.ts
import { assertEnv } from './env-check'

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    assertEnv(env)
    return app.fetch(request, env, ctx)
  },
}
```

## 6. Monorepo tsconfig Wiring

Ensure the shared declarations are picked up without path hacks:

```jsonc
// workers/api/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "types": ["@cloudflare/workers-types"],
    "lib": ["ESNext"],
    "moduleResolution": "bundler"
  },
  "references": [
    { "path": "../../packages/worker-env" }
  ],
  "include": ["src/**/*.ts", "src/**/*.d.ts"]
}
```

```bash
# Build type declarations across the monorepo
pnpm tsc --build --verbose
```

## Anti-patterns

- **Importing runtime types from `@cloudflare/workers-types` as values.** `KVNamespace`, `D1Database`, etc. are type-only — never attempt to instantiate them.
- **Putting secrets in the `Env` interface with optional `?`.** All bound secrets should be `string`, not `string | undefined`. Use the runtime `assertEnv` check instead of nullable types to catch misconfiguration.
- **Using `any` for the `Env` generic.** `new Hono<{ Bindings: any }>()` defeats the entire pattern — always pass the concrete `Env` interface.
- **Duplicating bindings across `SharedEnv` and per-Worker `Env`.** If both declare `DB: D1Database`, TypeScript merges them, but Wrangler may complain about duplicate bindings at deploy time.

## Gotchas

- `declare global { interface SharedEnv {} }` only merges if the file is treated as a module (it must have at least one top-level `import` or `export {}`).
- `@cloudflare/workers-types` ships multiple version-pinned entry points (e.g. `@cloudflare/workers-types/2023-07-01`). Pin the version in the shared package's `/// <reference types="..." />` directive so all Workers agree on the same compat date.
- `DurableObjectNamespace` generic parameter `<T extends DurableObject>` is available in workers-types v4+; older versions use a non-generic form.
- When using `wrangler dev --remote`, bindings are real; the `assertEnv` check passes but may fail for bindings that only exist in production (e.g., an AI binding with a paid plan).

## Verification

```bash
# Full monorepo type-check
pnpm tsc --build --noEmit

# Check that the API Worker resolves Env correctly
pnpm --filter @example project/api tsc --noEmit --listFiles 2>&1 | grep env.d.ts

# Confirm no worker-configuration.d.ts files are tracked
git ls-files | grep worker-configuration
# should print nothing
```

## Related

- `wrangler-types-auto-generation-ci-pipeline.md`
- `typescript-declaration-maps-workers-monorepo.md`
- `typescript-strict-mode-guide.md`
- `hono-rpc-client-type-generation-workers.md`
- `typescript-cloudflare-workers-strict.md`

## Sources

- https://www.typescriptlang.org/docs/handbook/declaration-merging.html
- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://github.com/cloudflare/workers-types
- https://hono.dev/docs/getting-started/cloudflare-workers
