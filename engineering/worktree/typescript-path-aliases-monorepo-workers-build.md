# TypeScript Path Aliases in Monorepo Cloudflare Workers Builds

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You add `"@repo/utils": ["../../packages/utils/src"]` to a Worker package's
`tsconfig.json` so imports like `import { hash } from "@repo/utils"` resolve cleanly
during development. TypeScript IDE support works fine, but when you run `wrangler deploy`
or `wrangler dev`, the bundler (esbuild inside Wrangler) cannot resolve `@repo/utils`
and throws `Cannot resolve module "@repo/utils"`. The same breakage appears in Vitest
tests that import the alias.

## Context

TypeScript path aliases are a compiler-level indirection. `tsc` rewrites them during
emit, but Wrangler uses esbuild directly for bundling and does not read `tsconfig.json`
path mappings by default. Similarly, Vitest needs explicit alias configuration in
`vitest.config.ts` to mirror the TypeScript paths. In a pnpm workspace monorepo the
correct long-term solution is to use the `workspace:*` protocol so packages are real
packages with their own `package.json` and `exports` field — esbuild then resolves them
via `node_modules` without any alias magic. Path aliases remain useful as a fallback for
packages that are not yet publishable or for internal type-only imports.

## Option A (Preferred): Workspace Packages via pnpm + package.json exports

```jsonc
// packages/utils/package.json
{
  "name": "@repo/utils",
  "version": "0.0.0",
  "private": true,
  "main": "./src/index.ts",          // For bundlers that understand TS directly
  "types": "./src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"    // esbuild resolves this; no path alias needed
    }
  }
}
```

```jsonc
// apps/worker-payments/package.json
{
  "dependencies": {
    "@repo/utils": "workspace:*"     // pnpm symlinks into node_modules/@repo/utils
  }
}
```

```typescript
// apps/worker-payments/src/index.ts
// No alias needed — resolves via node_modules symlink
import { hash } from "@repo/utils";
```

```toml
# wrangler.toml — no extra config; esbuild follows the node_modules symlink
name = "worker-payments"
main = "src/index.ts"
compatibility_date = "2026-01-01"
```

## Option B: esbuild Alias Plugin via wrangler.toml

```toml
# wrangler.toml — alias block supported since Wrangler 3.22
[alias]
"@repo/utils" = "../../packages/utils/src"
"@repo/types" = "../../packages/types/src"
```

```bash
# Confirm alias resolution at bundle time
pnpm wrangler deploy --dry-run --outdir dist/
# esbuild will inline packages/utils/src into the dist bundle
```

## Option C: tsconfig-paths for Vitest

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-plugin-tsconfig-paths";

export default defineConfig({
  plugins: [
    tsconfigPaths(),   // reads compilerOptions.paths from the nearest tsconfig.json
  ],
  test: {
    environment: "miniflare",
    environmentOptions: {
      compatibilityDate: "2026-01-01",
    },
  },
});
```

```jsonc
// apps/worker-payments/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "paths": {
      "@repo/utils": ["../../packages/utils/src"],
      "@repo/utils/*": ["../../packages/utils/src/*"]
    }
  }
}
```

```jsonc
// tsconfig.base.json (monorepo root)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true
  }
}
```

## TypeScript Project References for Type-Checking Without Bundling

```jsonc
// apps/worker-payments/tsconfig.json — with project references
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "composite": true,
    "outDir": ".tsbuild",
    "rootDir": "src"
  },
  "references": [
    { "path": "../../packages/utils" },
    { "path": "../../packages/types" }
  ]
}
```

```bash
# Type-check the whole graph without emitting (use in CI pre-deploy gate)
pnpm tsc --build --noEmit apps/worker-payments/tsconfig.json

# Incremental check (only changed packages)
pnpm tsc --build --incremental apps/worker-payments/tsconfig.json
```

## Enforcing Alias Consistency Across the Monorepo

```typescript
// scripts/check-alias-parity.ts
// Ensures every tsconfig path alias has a matching wrangler.toml [alias] entry
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import TOML from "@iarna/toml";

const tsconfigPath = resolve("apps/worker-payments/tsconfig.json");
const wranglerPath = resolve("apps/worker-payments/wrangler.toml");

const tsconfig = JSON.parse(readFileSync(tsconfigPath, "utf-8"));
const wrangler = TOML.parse(readFileSync(wranglerPath, "utf-8")) as Record<
  string,
  unknown
>;

const tsPaths = Object.keys(tsconfig.compilerOptions?.paths ?? {}).map((p) =>
  p.replace(/\/\*$/, "")
);
const wranglerAliases = Object.keys(
  (wrangler["alias"] as Record<string, string>) ?? {}
);

const missing = tsPaths.filter((p) => !wranglerAliases.includes(p));
if (missing.length > 0) {
  console.error(
    "Missing wrangler.toml [alias] entries for TS paths:\n" +
      missing.map((p) => `  ${p}`).join("\n")
  );
  process.exit(1);
}
console.log("All TS path aliases have matching wrangler.toml alias entries.");
```

```yaml
# Add to CI pre-deploy gate
- name: Check alias parity
  run: pnpm tsx scripts/check-alias-parity.ts
```

## Anti-patterns

- Relying only on `tsconfig.json` `paths` and expecting Wrangler/esbuild to honour them.
  esbuild does not read `compilerOptions.paths`. The alias must be declared separately in
  `wrangler.toml`'s `[alias]` block or resolved via `node_modules`.
- Using absolute host paths in `tsconfig.paths` (e.g., `/path/to/project).
  These break on other developers' machines and in CI. Always use paths relative to the
  `tsconfig.json` file.
- Adding `paths` to the monorepo root `tsconfig.base.json`. Root-level path aliases are
  inherited by all packages but point to the wrong relative directory from each package's
  perspective. Define paths per-package.
- Setting `moduleResolution: "node"` in 2026. Use `"bundler"` for Worker packages. `"node"`
  does not resolve `exports` fields in `package.json`, breaking workspace packages that use
  conditional exports.

## Gotchas

- `wrangler.toml [alias]` paths are resolved relative to the `wrangler.toml` file, not
  the project root. Double-check relative path depth when your Worker package is nested
  more than one level below the monorepo root.
- `vite-plugin-tsconfig-paths` reads the nearest `tsconfig.json` by walking up from the
  config file. If `vitest.config.ts` is at the monorepo root but the paths are defined in
  a package-level `tsconfig.json`, the plugin will not find them. Set `root` explicitly or
  point `tsconfigPaths({ root: __dirname })` to the correct config.
- TypeScript project references require every referenced package to have `"composite": true`
  and define `outDir` and `rootDir`. Forgetting this on any one package in the graph causes
  `tsc --build` to fail with a cryptic "referenced project must have composite enabled" error.
- After adding a new workspace package, run `pnpm install` to create the symlink in
  `node_modules`. Until the symlink exists, both esbuild and the TypeScript language server
  will report the package as unresolved even though the source files are present.

## Verification

```bash
# Confirm esbuild resolves the alias correctly
pnpm wrangler deploy --dry-run --outdir dist/ 2>&1 | grep -E "error|warning|alias"

# Confirm tsc sees no path resolution errors
pnpm tsc --noEmit --project apps/worker-payments/tsconfig.json

# Confirm the workspace symlink exists
ls -la node_modules/@repo/utils
# → should point to ../../packages/utils (symlink)

# Run Vitest with alias to confirm test resolution
pnpm vitest run --project apps/worker-payments
```

## Related

- `monorepo-pnpm-turborepo-2026.md`
- `pnpm-workspace-protocol-version-resolution.md`
- `cloudflare-workers-vitest-miniflare-testing.md`
- `monorepo-package-boundary-enforcement-workers.md`
- `pnpm-workspace-git-worktree-isolation.md`

## Sources

- Wrangler alias config: https://developers.cloudflare.com/workers/wrangler/configuration/#alias
- pnpm workspace protocol: https://pnpm.io/workspaces#workspace-protocol-workspace
- TypeScript project references: https://www.typescriptlang.org/docs/handbook/project-references.html
- vite-plugin-tsconfig-paths: https://github.com/aleclarson/vite-tsconfig-paths
