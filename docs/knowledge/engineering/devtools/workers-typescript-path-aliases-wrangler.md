# TypeScript Path Aliases (`@/lib/*`) with Wrangler Builds

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers monorepo grows to dozens of source files and relative imports like `../../../lib/db/client` become unmaintainable. You want `@/lib/db/client` path aliases that work consistently in `wrangler build`, `wrangler dev`, Vitest, and VS Code IntelliSense — without diverging configurations that work in some tools but break in others.

---

## Context

TypeScript `paths` in `tsconfig.json` are a compile-time remapping that `tsc` understands but does not emit resolution logic into JavaScript. Wrangler uses esbuild under the hood; esbuild has native path-alias support via its `alias` option, configurable through a Wrangler esbuild plugin. Vitest (also esbuild-backed) accepts `resolve.alias` in `vitest.config.ts`. VS Code reads `tsconfig.json` `paths` for IntelliSense. Aligning all three requires setting paths in exactly one canonical place and deriving the others from it — the pattern below uses `tsconfig.json` as the source of truth.

---

## Section 1 — tsconfig.json and wrangler.toml

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    },
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true
  },
  "include": ["src/**/*.ts"]
}
```

```toml
# wrangler.toml
name = "my-worker"
main = "src/worker.ts"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]

# Wrangler passes these options directly to esbuild
[build]
command = ""

# esbuild alias support via wrangler's build.esbuild_options (Wrangler ≥ 3.78)
[build.esbuild_options]
# Alias is applied during bundle — must match tsconfig paths without the "/*"
alias = { "@" = "./src" }
```

---

## Section 2 — Vitest config and alias resolution helper

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

export default defineConfig({
  resolve: {
    alias: {
      // Mirror tsconfig paths — keep in sync with wrangler.toml [build.esbuild_options]
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'miniflare',
    environmentOptions: {
      compatibilityDate: '2025-08-01',
      compatibilityFlags: ['nodejs_compat'],
    },
  },
});
```

```typescript
// scripts/check-aliases.ts — run with `npx tsx scripts/check-aliases.ts`
// Reads tsconfig paths and verifies each maps to an existing directory.
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';

const tsconfig = JSON.parse(
  readFileSync(resolve(process.cwd(), 'tsconfig.json'), 'utf-8')
) as { compilerOptions?: { paths?: Record<string, string[]>; baseUrl?: string } };

const paths = tsconfig.compilerOptions?.paths ?? {};
const baseUrl = tsconfig.compilerOptions?.baseUrl ?? '.';

let allOk = true;
for (const [alias, targets] of Object.entries(paths)) {
  for (const target of targets) {
    // Strip trailing /*
    const dir = resolve(process.cwd(), baseUrl, target.replace(/\/\*$/, ''));
    const exists = existsSync(dir);
    console.log(`${exists ? '✓' : '✗'} ${alias} → ${dir}`);
    if (!exists) allOk = false;
  }
}

process.exit(allOk ? 0 : 1);
```

```typescript
// Example usage in src/worker.ts — imports resolve via the alias
import type { Env } from '@/types/env';
import { getUserById } from '@/db/queries';
import { jsonError } from '@/lib/response';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const id = Number(url.searchParams.get('id'));

    if (!id) return jsonError(400, 'Missing id');

    const user = await getUserById(env.DB, id);
    if (!user) return jsonError(404, 'Not found');

    return Response.json(user);
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — VS Code workspace settings and circular dependency check

```jsonc
// .vscode/settings.json
{
  // Tell VS Code's TS server which tsconfig to use for path resolution
  "typescript.tsdk": "node_modules/typescript/lib",
  "typescript.preferences.importModuleSpecifier": "non-relative",
  // If using a monorepo with multiple tsconfigs:
  "typescript.tsserver.experimental.enableProjectDiagnostics": true
}
```

```bash
# Detect circular dependencies — madge reads the compiled JS via esbuild
npx madge --circular --extensions ts \
  --ts-config tsconfig.json \
  src/worker.ts

# If madge doesn't resolve aliases, pass the webpack alias config
npx madge --circular --extensions ts \
  --webpack-config <(echo '{"resolve":{"alias":{"@":"./src"}}}') \
  src/

# Type-check (verifies aliases round-trip through tsc)
npx tsc --noEmit

# Vitest resolves aliases via vitest.config.ts — run tests to confirm
npx vitest run
```

---

## Anti-patterns

- **Defining aliases only in `tsconfig.json` `paths`** — TypeScript uses them for type-checking only; esbuild (used by Wrangler) ignores `tsconfig.json` paths entirely during bundling. You must also set `[build.esbuild_options] alias` in `wrangler.toml`.
- **Using deep nested aliases like `@/lib/db/v2/internal`** — defeats the readability purpose; keep aliases at one level (`@/lib`, `@/types`, `@/utils`) and use normal relative imports below that.
- **Forgetting to update `vitest.config.ts` when adding a new alias** — Vitest will silently pass tests if the aliased module is never imported in tests, hiding the misconfiguration until a new test is written.

---

## Gotchas

- `[build.esbuild_options]` in `wrangler.toml` requires Wrangler **3.78+**; earlier versions require a custom `build.command` that invokes esbuild with `--alias:@=./src`.
- `moduleResolution: "Bundler"` in `tsconfig.json` is required for `paths` to work correctly with esbuild-style resolution; `"NodeNext"` or `"Node16"` requires explicit `.js` extensions on relative imports which conflicts with the alias pattern.
- Circular dependencies are **not** detected by `tsc --noEmit`; use `madge` or `eslint-plugin-import`'s `no-cycle` rule to catch them, since they can cause `undefined` at runtime when modules initialise in the wrong order.
- VS Code must be restarted (or TS server restarted via the command palette: `TypeScript: Restart TS server`) after changing `tsconfig.json` `paths` for IntelliSense to pick up the new aliases.

---

## Verification

```bash
# Confirm tsconfig paths resolve to real directories
npx tsx scripts/check-aliases.ts

# Confirm tsc resolves the aliases
npx tsc --noEmit

# Confirm Wrangler bundles without resolution errors
npx wrangler deploy --dry-run --outdir dist/
ls dist/

# Confirm Vitest resolves the aliases
npx vitest run --reporter verbose

# Confirm no circular deps
npx madge --circular --extensions ts src/
```

---

## Related

- `workers-vitest-type-coverage-report.md`
- `workers-custom-eslint-no-await-in-loop.md`

---

## Sources

- TypeScript path mapping — https://www.typescriptlang.org/tsconfig#paths
- Wrangler esbuild_options — https://developers.cloudflare.com/workers/wrangler/configuration/#build
- esbuild path aliases — https://esbuild.github.io/api/#alias
- Vitest resolve.alias — https://vitest.dev/config/#resolve-alias
- madge circular dependency detection — https://github.com/pahen/madge
