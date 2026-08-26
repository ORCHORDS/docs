# Type-Safe Workers Bindings with `wrangler types`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker accesses KV namespaces, D1 databases, R2 buckets, and Durable Objects through the `env` parameter, but the `Env` interface is written by hand and drifts from `wrangler.toml` bindings. Accessing a renamed binding produces a runtime `undefined` error rather than a compile-time TypeScript error. You want the type definitions to be generated automatically from the authoritative source — `wrangler.toml`.

---

## Context

`wrangler types` (available since Wrangler 3.x) reads `wrangler.toml` and emits a `worker-configuration.d.ts` ambient declaration file that contains an `Env` interface reflecting every binding. Re-running it after changing `wrangler.toml` instantly surfaces type mismatches across the codebase.

The `@cloudflare/workers-types` package provides the underlying runtime types (`KVNamespace`, `D1Database`, `R2Bucket`, `DurableObjectNamespace`, etc.) that the generated file references. Both must be present for the generated declarations to resolve correctly.

Generated output example:
```typescript
// worker-configuration.d.ts (auto-generated — do not edit)
interface Env {
  USERS_KV: KVNamespace;
  DB: D1Database;
  ASSETS: R2Bucket;
  RATE_LIMITER: DurableObjectNamespace;
  ENVIRONMENT: string;            // [vars]
  API_SECRET: string;             // [secrets] (type only; value not generated)
}
```

---

## Solution

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"

[[kv_namespaces]]
binding = "USERS_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "my-assets"

[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiter"
```

```bash
# Install the workers-types package that backs the generated declarations
npm install --save-dev @cloudflare/workers-types

# Generate worker-configuration.d.ts
npx wrangler types

# Regenerate and immediately run type-check
npx wrangler types && npx tsc --noEmit
```

```typescript
// src/index.ts — consume generated Env without any hand-written interface
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/user') {
      return handleUser(request, env);
    }

    if (url.pathname === '/asset') {
      return handleAsset(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function handleUser(request: Request, env: Env): Promise<Response> {
  const userId = new URL(request.url).searchParams.get('id');
  if (!userId) return new Response('Missing id', { status: 400 });

  // env.USERS_KV is typed as KVNamespace — full autocompletion
  const raw = await env.USERS_KV.get(userId, 'json');
  if (!raw) return new Response('Not found', { status: 404 });

  return Response.json(raw);
}

async function handleAsset(request: Request, env: Env): Promise<Response> {
  const key = new URL(request.url).searchParams.get('key') ?? '';
  // env.ASSETS is typed as R2Bucket
  const object = await env.ASSETS.get(key);
  if (!object) return new Response('Not found', { status: 404 });

  return new Response(object.body, {
    headers: { 'Content-Type': object.httpMetadata?.contentType ?? 'application/octet-stream' },
  });
}
```

```typescript
// src/env.ts — extend generated Env with helper methods (do not re-declare Env)
// Use module augmentation so wrangler types regeneration doesn't overwrite extensions

// Augment the global Env with a typed helper wrapper
export interface AppEnv extends Env {
  /** Convenience: get a user record with automatic JSON parse */
  getUser(id: string): Promise<UserRecord | null>;
}

export interface UserRecord {
  id: string;
  email: string;
  createdAt: string;
}

/** Factory: wraps the raw Env with higher-level methods. */
export function wrapEnv(env: Env): AppEnv {
  return {
    ...env,
    async getUser(id: string): Promise<UserRecord | null> {
      return env.USERS_KV.get<UserRecord>(id, 'json');
    },
  };
}
```

```typescript
// src/db.ts — typed D1 queries using generated Env
import type { UserRecord } from './env';

export async function insertUser(
  db: D1Database,
  user: Omit<UserRecord, 'createdAt'>,
): Promise<UserRecord> {
  const now = new Date().toISOString();
  await db
    .prepare('INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)')
    .bind(user.id, user.email, now)
    .run();
  return { ...user, createdAt: now };
}

export async function getUser(db: D1Database, id: string): Promise<UserRecord | null> {
  const row = await db
    .prepare('SELECT id, email, created_at AS createdAt FROM users WHERE id = ?')
    .bind(id)
    .first<UserRecord>();
  return row ?? null;
}
```

```json
// tsconfig.json — reference generated types and workers-types
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "strict": true,
    "types": ["@cloudflare/workers-types"],
    "lib": ["ES2022"]
  },
  "include": ["src", "worker-configuration.d.ts"]
}
```

```yaml
# .github/workflows/typecheck.yml — regenerate types in CI then run tsc
name: Type check
on: [push, pull_request]
jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
      - run: npm ci
      - name: Regenerate wrangler types
        run: npx wrangler types
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      - name: TypeScript check
        run: npx tsc --noEmit
      - name: Assert no diff in generated types
        run: |
          git diff --exit-code worker-configuration.d.ts || (
            echo "worker-configuration.d.ts is out of date. Run: npx wrangler types"
            exit 1
          )
```

```json
// package.json scripts
{
  "scripts": {
    "types:gen": "wrangler types",
    "types:check": "wrangler types && tsc --noEmit",
    "predev": "wrangler types"
  }
}
```

---

## Implementation Details

- **Output path** — by default `wrangler types` writes to `./worker-configuration.d.ts` in the project root. Pass `--output-path src/types/env.d.ts` to customise.
- **`satisfies ExportedHandler<Env>`** — using `satisfies` instead of a type annotation preserves the concrete type of the default export for testing, while still enforcing the `Env` shape.
- **Secret bindings** — `wrangler types` generates `string` for secrets defined in `[secrets]`. The actual values are never emitted.
- **Service bindings** — typed as `Fetcher`; you can extend the generated interface with a typed wrapper using module augmentation (see `src/env.ts` pattern above).
- **Multiple environments** — run `wrangler types --env staging` to generate types for a specific `[env.staging]` block.

---

## Anti-patterns

- **Hand-editing `worker-configuration.d.ts`** — it is regenerated on every `wrangler types` run. Put customisations in a separate augmentation file.
- **Committing stale generated types** — the CI diff check above catches this. Make regeneration part of the dev `predev` script.
- **Using `any` for `env`** — defeats the entire purpose. Even in test helpers, pass `Partial<Env>` cast rather than `any`.
- **Mixing `@cloudflare/workers-types` versions** — ensure the version in `package.json` matches the `compatibility_date` in `wrangler.toml` to avoid type/runtime mismatches.

---

## Gotchas

- `wrangler types` requires a valid `wrangler.toml` in the current directory. Run it from the project root or pass `--config path/to/wrangler.toml`.
- If `@cloudflare/workers-types` is missing, the generated file will have unresolved references. TypeScript will error on `KVNamespace`, `D1Database`, etc.
- Durable Object bindings require the class to be exported from the same Worker entry point; the generated type is `DurableObjectNamespace` regardless of the class shape.
- `wrangler types` does **not** generate types for Workflows or Queues prior to Wrangler 3.60 — update Wrangler if these bindings are missing.

---

## Verification

```bash
# Confirm file is generated
npx wrangler types && ls -lh worker-configuration.d.ts

# Confirm TypeScript resolves Env correctly
npx tsc --noEmit 2>&1 | grep -c 'error' || echo 'No errors'

# Intentionally rename a binding in wrangler.toml and confirm tsc catches it
# (Expect: error TS2339: Property 'OLD_BINDING' does not exist on type 'Env')
```

---

## Related

- `documentation/docs/policies/devtools/wrangler-dev-workflow.md`
- `documentation/docs/policies/devtools/workers-vitest-d1-fixtures.md`
- `documentation/docs/policies/devtools/vitest-unit-testing.md`

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://developers.cloudflare.com/workers/languages/typescript/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/wrangler
