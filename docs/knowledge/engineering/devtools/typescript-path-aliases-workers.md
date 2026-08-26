# TypeScript Path Aliases in Workers Projects

- Date: 2026-08-22
- Author: example.com
- Status: production

---

## Symptom / Use-case

Your Cloudflare Worker project has grown to the point where relative imports look like `../../../lib/utils` and `../../types/index`. TypeScript path aliases (the `paths` option in `tsconfig.json`) let you write `@/lib/utils` instead. However, Workers use esbuild (via Wrangler) rather than `tsc` for bundling, and getting path aliases to work requires configuring both TypeScript (for editor support and type-checking) **and** esbuild (for the actual bundle).

Typical scenarios:
- Monorepo with shared packages where cross-package imports need stable aliases
- Large single-Worker projects with a `src/` tree several levels deep
- Migrating a Node.js project to Workers where `@/*` aliases were already established
- Keeping import paths stable when refactoring directory structure

---

## Context

TypeScript path aliases are a compile-time feature. `tsc` resolves `@/lib/utils` to the correct file based on `tsconfig.json`, but `tsc` only performs type checking — it doesn't produce the bundle that Wrangler deploys. Wrangler uses **esbuild** internally, and esbuild has its own module resolution that knows nothing about `tsconfig.json`'s `paths`.

The mismatch means:
- TypeScript (in your editor and `tsc --noEmit`) resolves `@/lib/utils` correctly
- esbuild (run by `wrangler dev` / `wrangler deploy`) cannot find `@/lib/utils` and fails to build

The fix requires telling esbuild about path aliases, which can be done via:
1. **`tsconfig-paths-to-aliases` approach** — a custom esbuild plugin
2. **Wrangler's `alias` config** — Wrangler 3.x supports an `alias` table in `wrangler.toml`
3. **Vite with `@cloudflare/vite-plugin`** — Vite reads `tsconfig.json` paths natively

---

## Setting Up TypeScript Path Aliases

First, configure `tsconfig.json` to define the aliases:

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "lib": ["ESNext"],
    "types": ["@cloudflare/workers-types"],
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@lib/*": ["src/lib/*"],
      "@types/*": ["src/types/*"],
      "@config": ["src/config/index.ts"]
    }
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

With this config, TypeScript resolves:
- `@/lib/utils` → `src/lib/utils.ts`
- `@lib/auth` → `src/lib/auth.ts`
- `@types/user` → `src/types/user.ts`
- `@config` → `src/config/index.ts`

---

## Method 1: Wrangler's Built-in `alias` Config (Recommended)

Wrangler 3.x supports an `[alias]` section that passes path aliases directly to esbuild. This is the simplest approach for single-Worker projects:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[alias]
"@lib" = "./src/lib"
"@types" = "./src/types"
"@config" = "./src/config/index.ts"
```

For the wildcard `@/*` → `src/*` pattern, Wrangler's alias requires listing individual paths (wildcards aren't supported in `[alias]`). Use the wildcard in `tsconfig.json` for editor support and list the specific aliases in `wrangler.toml` for esbuild.

Alternatively, restructure to use a single `@` alias pointing at `src`:

```toml
# wrangler.toml
[alias]
"@" = "./src"
```

```typescript
// src/index.ts — this works because esbuild resolves @ → ./src
import { createRouter } from '@/router';
import { validateRequest } from '@/lib/validation';
import type { AppEnv } from '@/types/env';
```

Keep `tsconfig.json` in sync:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

---

## Method 2: Custom esbuild Plugin via Wrangler Build Config

For more control — or if you need true wildcard expansion — use a custom esbuild plugin specified via Wrangler's `build.command`:

```bash
# Install the plugin
pnpm add -D esbuild-plugin-tsconfig-paths
```

```javascript
// build.mjs
import * as esbuild from 'esbuild';
import { tsConfigPathsPlugin } from 'esbuild-plugin-tsconfig-paths';

await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  format: 'esm',
  outfile: 'dist/worker.js',
  target: 'esnext',
  platform: 'neutral',
  external: ['__STATIC_CONTENT_MANIFEST'],
  plugins: [
    tsConfigPathsPlugin({ tsconfig: './tsconfig.json' }),
  ],
  // Source maps for debugging
  sourcemap: true,
});
```

```toml
# wrangler.toml — point at the pre-built output
name = "my-worker"
main = "dist/worker.js"
compatibility_date = "2026-01-01"

[build]
command = "node build.mjs"
watch_dir = "src"
```

This approach gives you full control over esbuild but adds a build step. The `watch_dir` setting makes `wrangler dev` re-trigger the build command when files in `src/` change.

---

## Method 3: Vite + `@cloudflare/vite-plugin`

When using the Vite plugin, Vite reads `tsconfig.json`'s `compilerOptions.paths` automatically (via the `vite-tsconfig-paths` plugin):

```bash
pnpm add -D vite @cloudflare/vite-plugin vite-tsconfig-paths
```

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  plugins: [
    tsconfigPaths(),   // reads tsconfig.json paths
    cloudflare(),      // runs Worker in Miniflare
  ],
});
```

No `wrangler.toml` `[alias]` section needed — `vite-tsconfig-paths` handles it. This is the most ergonomic option for full-stack projects.

---

## Monorepo: Shared Package Aliases

In a pnpm workspace monorepo, use path aliases to import from internal packages without referencing `node_modules`:

```
apps/
  worker/
    src/index.ts
    tsconfig.json
    wrangler.toml
packages/
  shared/
    src/index.ts
    package.json
```

```json
// packages/shared/package.json
{
  "name": "@repo/shared",
  "exports": {
    ".": {
      "import": "./src/index.ts",
      "types": "./src/index.ts"
    }
  }
}
```

```json
// apps/worker/tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@repo/shared": ["../../packages/shared/src/index.ts"]
    }
  }
}
```

```toml
# apps/worker/wrangler.toml
[alias]
"@" = "./src"
"@repo/shared" = "../../packages/shared/src/index.ts"
```

This bypasses `node_modules` resolution entirely — esbuild bundles the shared package source directly into the Worker. The benefit: no need to build the shared package separately before running the Worker. The trade-off: the shared package isn't tree-shaken separately; esbuild does it as part of the Worker bundle.

---

## Type-Checking with Path Aliases

Path aliases in `tsconfig.json` make the TypeScript compiler happy in your editor, but `wrangler dev`/`wrangler deploy` don't run type checking. Add a separate `tsc --noEmit` step to your CI pipeline:

```json
// package.json
{
  "scripts": {
    "dev": "wrangler dev",
    "type-check": "tsc --noEmit",
    "build": "wrangler deploy --dry-run",
    "ci": "pnpm type-check && pnpm build"
  }
}
```

For a monorepo, run `tsc --noEmit` with project references:

```json
// apps/worker/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "references": [
    { "path": "../../packages/shared" }
  ]
}
```

```bash
# Type-check the whole monorepo respecting references
tsc --build --noEmit
```

---

## Verifying Alias Resolution

A quick way to confirm esbuild is resolving aliases correctly before a full deploy:

```bash
# Dry-run wrangler deploy — builds the bundle without deploying
wrangler deploy --dry-run --outdir=dist/

# Inspect the output for your aliased imports
grep -n "@/lib\|@repo/shared" dist/worker.js
# Should print nothing — all aliases should be resolved to their actual code

# Or use esbuild's metafile to trace the dependency graph
esbuild src/index.ts --bundle --metafile=meta.json --platform=neutral
cat meta.json | node -e "
  const m = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
  Object.keys(m.inputs).filter(k => k.includes('src/')).forEach(k => console.log(k));
"
```

---

## Anti-Patterns

**Using `paths` in `tsconfig.json` without a matching esbuild alias.** TypeScript compiles and your editor is happy, but `wrangler dev` throws `Cannot find module '@/lib/utils'` at runtime. Always keep `tsconfig.json` paths and esbuild aliases in sync.

**Aliasing to compiled `.js` output instead of source `.ts` files.** If a shared package builds to `dist/`, aliasing to the `.js` output means you need to rebuild the package on every change. Alias to `src/index.ts` instead and let esbuild bundle the TypeScript source directly.

**Deeply nesting aliases** (e.g., `@components/ui/buttons/primary`). This creates tight coupling. Prefer shallow aliases (`@components`) and let the module's internal `index.ts` control exports.

**Using barrel files (`index.ts` that re-exports everything) with path aliases.** Barrel files prevent tree-shaking. In Workers, bundle size matters — prefer direct imports: `@lib/auth` rather than `@lib` with a barrel that includes auth, validation, and everything else.

---

## Gotchas

- **Wrangler's `[alias]` keys are string-matched, not glob-expanded.** The key `"@lib"` matches the import `@lib/anything` because esbuild treats it as a prefix. But `"@/*"` as a key does not work — use `"@"` as the alias key to get the `@/*` → `src/*` behavior.

- **`baseUrl` in `tsconfig.json` affects module resolution order.** With `"baseUrl": "."`, TypeScript also resolves bare specifiers like `lib/utils` (without `@`) relative to the project root. This can silently shadow `node_modules` packages with the same name.

- **`vite-tsconfig-paths` must come before `@cloudflare/vite-plugin`** in the Vite plugins array. The Cloudflare plugin runs transformations after path resolution; reversing the order causes the Worker transformer to see unresolved aliases.

- **Aliases don't apply to `wrangler.toml`'s `main` field.** You must write a real relative path there — `main = "src/index.ts"`, not `main = "@/index.ts"`.

- **esbuild plugin order matters.** If you use multiple esbuild plugins (tsconfig-paths + a custom one), path resolution runs first. If your custom plugin runs before path resolution, it may receive unresolved alias strings.

---

## Verification

```bash
# 1. Add a path alias to tsconfig.json and wrangler.toml [alias]
# 2. Use the alias in src/index.ts:
#    import { greet } from '@lib/greeter';

# 3. Start dev server
wrangler dev

# 4. Confirm no module-not-found error in the terminal

# 5. Confirm tsc also resolves the alias
tsc --noEmit
# Expected: no errors

# 6. Dry-run build to inspect bundle
wrangler deploy --dry-run --outdir=.wrangler/tmp/
# Expected: worker.js is produced with no "unresolved" warnings
```

---

## Related

- `typescript-strict-mode-guide.md` — TypeScript strict configuration for Workers
- `typescript-cloudflare-workers-strict.md` — Workers-specific TypeScript config
- `workers-hmr-live-reload.md` — Build and reload speed optimization
- `pnpm-workspace-setup.md` — Monorepo structure for shared packages
- `turborepo-cloudflare-workers-pipeline.md` — Build pipelines with path aliases in Turborepo

---

## Sources

- TypeScript `paths` documentation: https://www.typescriptlang.org/tsconfig#paths
- Wrangler `alias` config: https://developers.cloudflare.com/workers/wrangler/configuration/#alias
- esbuild path aliasing: https://esbuild.github.io/api/#alias
- vite-tsconfig-paths plugin: https://github.com/aleclarson/vite-tsconfig-paths
- `esbuild-plugin-tsconfig-paths`: https://www.npmjs.com/package/esbuild-plugin-tsconfig-paths
