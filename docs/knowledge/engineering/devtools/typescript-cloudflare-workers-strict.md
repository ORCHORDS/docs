# typescript-cloudflare-workers-strict

**Issue:** A Cloudflare Workers project compiles cleanly with the
default `tsconfig.json` but ships runtime crashes: bindings typed
as `any`, D1 queries returning `unknown` rows, and `env.DB` accessed
without a null-check crashing on first deploy because the binding
was not wired in `wrangler.toml`. Strict mode would have caught
all three before `wrangler deploy`.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
TypeError: Cannot read properties of undefined (reading 'prepare')
  at Object.fetch (worker.js:12)
```

The local `wrangler dev` run works because `wrangler.toml` has
`[[d1_databases]]` wired, but the staging environment `wrangler.toml`
does not. TypeScript never complained because `env` was typed `any`.

D1 query results come back as `Record<string, unknown>[]`; accessing
`row.user_id` as a number is an implicit `any` cast under loose mode.

## Context

`@cloudflare/workers-types` ships ambient type declarations for every
Workers runtime API — `KVNamespace`, `D1Database`, `R2Bucket`,
`Queue`, `DurableObjectNamespace`, and more. Without explicit strict
mode, TypeScript will not enforce the `Env` bindings interface, will
silently widen `D1Result` row types to `any`, and will not enforce
non-nullable access on bindings that could be missing at runtime.

Wrangler v4 also ships `wrangler types` — a command that reads
`wrangler.toml` and emits a `worker-configuration.d.ts` file with a
typed `Env` interface matching the declared bindings. This generated
file is the authoritative source of truth for the binding types in CI.

## tsconfig.json for Workers

```jsonc
// apps/worker/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types/2023-07-01"],

    // Strict cluster — enable ALL of these
    "strict": true,               // umbrella: enables items below
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,

    // Quality
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitReturns": true,

    // Workers-specific
    "isolatedModules": true,      // each file must be a valid ESM module
    "verbatimModuleSyntax": true, // import type vs import matters

    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

`"lib": ["ES2022"]` — deliberately omit `"DOM"`. Workers uses Web
Standard globals from `@cloudflare/workers-types`, not the DOM lib.
Mixing in `DOM` causes type conflicts on `fetch`, `Request`, `Headers`,
and `crypto` because the DOM and Workers definitions diverge.

## @cloudflare/workers-types version pin

`@cloudflare/workers-types` is versioned by compatibility date:

| Package export path          | Compatibility date |
|------------------------------|--------------------|
| `@cloudflare/workers-types`  | latest (avoid)     |
| `.../2023-07-01`             | stable 2023 APIs   |
| `.../2024-04-04`             | stable 2024 APIs   |
| `.../2025-01-01`             | 2025 APIs (R2 hints, etc.) |

Pin to the same date as `compatibility_date` in `wrangler.toml`:

```toml
# wrangler.toml
compatibility_date = "2024-04-04"
```

```jsonc
// tsconfig.json
"types": ["@cloudflare/workers-types/2024-04-04"]
```

Mismatching dates causes phantom type errors where an API that is
available in the runtime is missing in the type declarations, or vice
versa.

## Generating Env from wrangler.toml (wrangler types)

```bash
# Generate once; commit the output
npx wrangler types
# → writes worker-configuration.d.ts at project root
```

```ts
// worker-configuration.d.ts (generated — do not edit)
interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  KV_CACHE: KVNamespace;
  QUEUE_OUTBOUND: Queue<OutboundMessage>;
  API_KEY: string;   // [vars] entry
}
```

Wire the generated file into `tsconfig.json`:

```jsonc
"include": ["src/**/*.ts", "worker-configuration.d.ts"]
```

Add a CI check so the generated file never drifts from `wrangler.toml`:

```bash
# ci: regenerate and fail if diff
npx wrangler types
git diff --exit-code worker-configuration.d.ts
```

## D1 type-safe query pattern

D1's `stmt.all<T>()` is generic; give it the row type and
`noUncheckedIndexedAccess` will enforce safe access:

```ts
interface UserRow {
  id: number;
  email: string;
  created_at: string;
}

export async function getUser(
  db: D1Database,
  id: number,
): Promise<UserRow | undefined> {
  const result = await db
    .prepare("SELECT id, email, created_at FROM users WHERE id = ?")
    .bind(id)
    .first<UserRow>();
  // result is UserRow | null — strict null checks force the null guard
  return result ?? undefined;
}
```

With `noUncheckedIndexedAccess` enabled, accessing array results
without a length guard or optional chaining is a compile error:

```ts
const rows = await db.prepare("SELECT …").all<UserRow>();
// TS error without the check:
const first = rows.results[0]; // Type: UserRow | undefined
// Correct:
const first = rows.results.at(0); // UserRow | undefined — explicit
```

## Strict null checks in Worker fetch handlers

```ts
// src/index.ts
export default {
  async fetch(
    request: Request,
    env: Env,         // typed from worker-configuration.d.ts
    ctx: ExecutionContext,
  ): Promise<Response> {
    // env.DB is D1Database (not D1Database | undefined) because
    // wrangler types generated the binding as non-optional.
    // If the binding is missing at runtime, Wrangler throws before
    // this function is called — so the non-optional type is correct.

    const url = new URL(request.url);

    if (url.pathname === "/user") {
      const idParam = url.searchParams.get("id");
      if (!idParam) {
        return new Response("Missing id", { status: 400 });
      }
      const id = Number(idParam);
      if (!Number.isFinite(id)) {
        return new Response("Invalid id", { status: 400 });
      }
      const user = await getUser(env.DB, id);
      if (!user) {
        return new Response("Not found", { status: 404 });
      }
      return Response.json(user);
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

`satisfies ExportedHandler<Env>` (instead of `as ExportedHandler<Env>`)
lets TypeScript verify that `fetch` returns `Promise<Response>` while
keeping the inferred type of the object literal for editor autocomplete.

## Anti-patterns

- **`"types": ["@cloudflare/workers-types"]` without a date suffix** —
  the unversioned export tracks `latest`, which can break your types
  on package update independently of your `compatibility_date`.
- **Manually writing the `Env` interface** — it drifts from
  `wrangler.toml`; use `wrangler types` and commit the generated file.
- **Using `as D1Database` casts to satisfy the compiler** — defeats
  strict mode; if the binding is optional in some envs, model it as
  `D1Database | undefined` and add the guard.
- **`"lib": ["ES2022", "DOM"]`** — the DOM lib's `Request` and
  `Response` conflict with Workers' versions; drop `"DOM"` entirely.

## Gotchas

- `wrangler types` only reads `wrangler.toml` in the current
  directory; run it from the worker package root, not the monorepo
  root, or pass `--config apps/worker/wrangler.toml`.
- `exactOptionalPropertyTypes` is stricter than `strict: true`
  includes — it must be set explicitly, and it can break libraries
  that use optional properties loosely. Start with it off, enable
  after fixing the cascade.
- `isolatedModules: true` forbids `const enum`; replace with `enum`
  or `as const` object maps throughout.
- Vitest's `@cloudflare/vitest-pool-workers` requires matching
  `compatibility_date` between `wrangler.toml` and the Vitest pool
  config; mismatches cause the miniflare sandbox to reject bindings
  with cryptic "Unknown compatibility date" errors.

## Verification

```bash
# Type-check with zero tolerance
pnpm --filter=@org/worker exec tsc --noEmit

# Confirm Env is generated and not stale
npx wrangler types && git diff --exit-code worker-configuration.d.ts

# Confirm no implicit any escapes
grep -r "as any" apps/worker/src && exit 1 || echo "No any casts"

# Run type-aware lint
pnpm --filter=@org/worker exec eslint . \
  --rule '@typescript-eslint/no-explicit-any: error'
```

## Related

- `documentation/docs/policies/devtools/eslint-v9-flat-config-cloudflare-workers.md`
- `documentation/docs/policies/devtools/turborepo-cloudflare-workers-pipeline.md`
- `documentation/docs/policies/ai-ml/cloudflare-vectorize-patterns.md`

## Sources

- https://developers.cloudflare.com/workers/languages/typescript/
- https://github.com/cloudflare/workers-types
- https://developers.cloudflare.com/d1/worker-api/
- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://www.typescriptlang.org/tsconfig
