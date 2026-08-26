# TypeScript Path Aliases in Workers Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a monorepo with shared utilities in `packages/shared/` and multiple Cloudflare Workers in `apps/*/`. Imports like `../../packages/shared/utils` are brittle. You want `@shared/utils` and `@types/models` to resolve correctly in TypeScript, Vitest, and production Wrangler builds — but Wrangler bundles with esbuild, not tsc, and esbuild does not read `tsconfig.json` `paths` natively.

## Context

TypeScript `paths` in `tsconfig.json` are a compile-time hint for the type checker and editors. They are **not** module resolution logic at runtime. Each bundler and test runner needs its own configuration to honour them:

- **tsc** (`--noEmit`): reads `paths` natively.
- **Vitest**: needs `vite-tsconfig-paths` plugin or a `resolve.alias` map.
- **Wrangler / esbuild**: needs an esbuild `alias` mapping passed via `wrangler.toml`'s `[build]` section or a custom esbuild plugin.

Getting all three to agree is the main challenge.

## Monorepo Layout and tsconfig Setup

```
monorepo/
├── tsconfig.base.json          # shared compiler options + paths
├── packages/
│   └── shared/
│       ├── package.json        # name: "@repo/shared"
│       ├── src/
│       │   ├── utils.ts
│       │   └── models.ts
│       └── tsconfig.json
└── apps/
    └── api-worker/
        ├── wrangler.toml
        ├── tsconfig.json       # extends base
        ├── vitest.config.ts
        └── src/
            └── index.ts
```

```jsonc
// tsconfig.base.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "baseUrl": ".",
    "paths": {
      "@shared/*": ["packages/shared/src/*"],
      "@types/*":  ["packages/shared/src/types/*"]
    }
  }
}

// apps/api-worker/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "baseUrl": "../.."          // resolve paths relative to monorepo root
  },
  "include": ["src", "../../worker-configuration.d.ts"]
}
```

## Wrangler / esbuild Path Resolution

```toml
# apps/api-worker/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[build]
# 1. Type-check with tsc (reads tsconfig paths, catches type errors)
# 2. Wrangler then bundles with its own esbuild — paths are resolved via alias below
command = "npx tsc --noEmit -p tsconfig.json"

[build.upload]
format = "modules"

# esbuild alias map — mirrors tsconfig.json paths
# Wrangler passes these to esbuild as alias entries
[esbuild]
alias = { "@shared" = "../../packages/shared/src", "@types" = "../../packages/shared/src/types" }
```

```typescript
// apps/api-worker/src/index.ts
import { formatDate } from '@shared/utils';     // resolves via esbuild alias
import type { User } from '@types/models';      // resolved by tsc for type checking

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const now = formatDate(new Date());
    return Response.json({ time: now });
  },
};
```

## Vitest Path Resolution

```typescript
// apps/api-worker/vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineWorkersConfig({
  plugins: [
    // Reads tsconfig.json paths and registers them as Vite aliases
    // Works for both the test runner process and the worker pool
    tsconfigPaths({ root: '../..' }),
  ],
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

```bash
npm install -D vite-tsconfig-paths
```

## Alternative: Explicit Vite Alias (Without `vite-tsconfig-paths`)

```typescript
// vitest.config.ts — manual alias map instead of the plugin
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';
import path from 'node:path';

const root = path.resolve(__dirname, '../..');

export default defineWorkersConfig({
  resolve: {
    alias: {
      '@shared': path.join(root, 'packages/shared/src'),
      '@types':  path.join(root, 'packages/shared/src/types'),
    },
  },
  test: {
    poolOptions: {
      workers: { wrangler: { configPath: './wrangler.toml' } },
    },
  },
});
```

## The esbuild vs. tsc Bundling Gotcha

Wrangler uses **esbuild** for bundling, not tsc. This means:

1. `tsconfig.json` `paths` have **no effect** on what esbuild resolves at bundle time.
2. tsc `--noEmit` in the `[build] command` only type-checks; it does not produce output files that esbuild reads.
3. esbuild resolves modules using its own `alias` config (passed via `wrangler.toml`'s `[esbuild]` section) or a custom esbuild plugin.

```bash
# If you forget to add esbuild alias, you get this at wrangler deploy time:
# Could not resolve "@shared/utils"
# All imports of @shared/* fail at bundle time even if tsc passes

# The fix — every path alias in tsconfig.json must have a matching entry in wrangler.toml:
# tsconfig.json:   "@shared/*": ["packages/shared/src/*"]
# wrangler.toml:   alias = { "@shared" = "../../packages/shared/src" }
# Note: esbuild alias is a prefix match, not a glob — omit the /*
```

## CI Workflow

```yaml
# .github/workflows/ci.yml (excerpt)
- name: Type-check all Workers
  run: |
    for app in apps/*/; do
      echo "Checking $app"
      npx tsc --noEmit -p "$app/tsconfig.json"
    done

- name: Test api-worker
  working-directory: apps/api-worker
  run: npx vitest run

- name: Deploy api-worker
  working-directory: apps/api-worker
  run: npx wrangler deploy --env production
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns

- **Relying on `tsconfig.json` `paths` alone for Wrangler builds.** tsc path aliases are invisible to esbuild. The bundle will fail with "Could not resolve" errors.
- **Using `ts-loader` or Babel to transpile before Wrangler.** Wrangler expects to own the esbuild step. Pre-transpiling produces non-standard output that confuses Wrangler's asset handling.
- **Putting absolute machine paths in `wrangler.toml` `[esbuild] alias`.** Use paths relative to the `wrangler.toml` file location. Absolute paths break on CI and on other developers' machines.
- **Mixing `moduleResolution: "node"` and `moduleResolution: "bundler"`.** Use `"bundler"` across the monorepo for Workers. `"node"` does not support the `.js` extension-less import style Workers use.

## Gotchas

- esbuild alias is a **prefix substitution**, not a glob. `"@shared" = "../../packages/shared/src"` means `@shared/utils` becomes `../../packages/shared/src/utils`. Adding the trailing slash in the alias key (`"@shared/"`) is not required but does not hurt.
- If `packages/shared/` has its own `package.json` with an `exports` field, esbuild's `alias` may be ignored in favour of the `exports` map. Either remove `exports` from the shared package or add the package name to esbuild's `alias` instead of the path alias: `"@repo/shared" = "../../packages/shared/src"`.
- `vite-tsconfig-paths` reads the first `tsconfig.json` it finds walking up from the Vitest config. Pass `root` explicitly when the monorepo root `tsconfig.base.json` is above `apps/api-worker/`.
- When running `wrangler types` in a monorepo, run it from the Worker's directory, not the monorepo root, so it reads the correct `wrangler.toml` and writes `worker-configuration.d.ts` beside it.

## Verification

```bash
# Confirm tsc resolves paths
cd apps/api-worker
npx tsc --noEmit --traceResolution 2>&1 | grep '@shared'
# Should show: ======== Resolving module '@shared/utils' ... ========
#              Resolution result: packages/shared/src/utils.ts

# Confirm esbuild resolves paths (dry-run bundle)
npx wrangler deploy --dry-run --outdir dist
grep -r 'formatDate' dist/  # function should appear in the bundled output

# Run Vitest to confirm alias works in tests
npx vitest run --reporter=verbose
```

## Related

- `vitest-workers-env-type-generation.md` — Vitest + Workers setup that coexists with path aliases
- `wrangler-dev-external-api-mock-proxy.md` — local dev configuration in the same monorepo
- `wrangler-secret-bulk-import-workers.md` — deploying secrets for Workers in a monorepo

## Sources

- https://developers.cloudflare.com/workers/wrangler/configuration/#bundling
- https://esbuild.github.io/api/#alias
- https://github.com/aleclarson/vite-tsconfig-paths
- https://www.typescriptlang.org/tsconfig#paths
