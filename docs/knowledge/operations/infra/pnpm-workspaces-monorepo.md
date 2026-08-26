# pnpm-workspaces-monorepo

**Issue:** pnpm workspace structure for Next.js + CF Pages Functions monorepo
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have `apps/web` (Next.js) and `functions` (CF Pages
Functions) in a monorepo. `pnpm install` works. `pnpm dev`
inside `apps/web` works. But `wrangler pages dev` from the root
can't find the function dependencies.

## Root cause
pnpm uses symlinks for workspace packages. The `.bin/` directory
of a workspace package is symlinked to the workspace root. When
CF Pages / wrangler bundles from `functions/`, it follows the
symlinks and may or may not bundle the deps correctly depending
on the bundler version.

**Source:** pnpm workspaces docs:
https://pnpm.io/workspaces

> "pnpm creates a non-flat node_modules directory by default
> ... which means that dependencies of dependencies are not
> hoisted to the top level."

This is intentional (saves disk space, prevents phantom deps),
but breaks tools that assume flat `node_modules`.

## Fix
For a Next.js + CF Functions monorepo:

### `package.json` (root)
```json
{
  "name": "monorepo",
  "private": true,
  "packageManager": "pnpm@9.0.0",
  "workspaces": [
    "apps/*",
    "functions",
    "packages/*"
  ],
  "scripts": {
    "dev": "pnpm --filter web dev",
    "build": "pnpm --filter web build",
    "deploy": "pnpm --filter web deploy",
    "lint": "pnpm -r --parallel lint",
    "test": "pnpm -r --parallel test",
    "typecheck": "pnpm -r --parallel typecheck"
  }
}
```

### `functions/package.json` (CF Pages Functions)
```json
{
  "name": "functions",
  "private": true,
  "type": "module",
  "dependencies": {
    "shared-lib": "workspace:*"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.0.0",
    "wrangler": "^4.0.0"
  }
}
```

### `wrangler.toml`
```toml
name = "example project-pages"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

# Pages Functions output: functions/dist
pages_build_output_dir = "apps/web/out"

# Workers (separate from Pages): functions/dist-worker
# [build]
# command = "pnpm --filter functions build"
```

### `apps/web/package.json` (Next.js)
```json
{
  "name": "web",
  "private": true,
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.0.0",
    "shared-lib": "workspace:*"
  },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "deploy": "bash scripts/deploy.sh"
  }
}
```

## Common pitfalls

### 1. esbuild postinstall race
On `pnpm install`, esbuild's postinstall script downloads the
platform binary. With parallel installs, the symlink gets
stomped. Fix: `pnpm rebuild esbuild` after install.

### 2. Phantom dependencies
A package can `import` something that's not in its `dependencies`
because the dependency was hoisted in a flat `node_modules`.
With pnpm, it fails. Fix: add the missing dep to the package's
`dependencies` explicitly.

### 3. TypeScript paths
For shared types, use `paths` in `tsconfig.json`:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@shared/*": ["packages/shared/src/*"]
    }
  }
}
```

But this doesn't work for runtime. For runtime, use a real
workspace dep + the `exports` field in the package's
`package.json`:
```json
{
  "name": "shared-lib",
  "exports": {
    ".": "./src/index.ts",
    "./types": "./src/types.ts"
  }
}
```

### 4. wrangler + workspace deps
`wrangler` runs in the `functions/` directory but needs to see
the root `node_modules`. Use `--persist-to` for local dev state,
and `--external` for deps that shouldn't be bundled.

## Verification
- **Test:** `pnpm install` from root succeeds
- **Test:** `pnpm --filter functions dev` runs the Functions
  server
- **Test:** `pnpm --filter web dev` runs the Next.js dev server
- **Live:** `pnpm run deploy` builds + deploys both web and
  functions

## Gotchas
- **Use `workspace:*` for cross-workspace deps** (not the
  specific version). pnpm resolves the actual version at install.
- **Each workspace has its own `node_modules/.pnpm/`** — don't
  share. Pnpm manages the cross-links.
- **For CI, use `pnpm install --frozen-lockfile`** to fail fast
  on lockfile drift.
- **For monorepo-wide lint, use `pnpm -r --parallel lint`** to
  run lint in all packages concurrently.

## Related
- pnpm docs: https://pnpm.io/workspaces
- pnpm + CF Pages: https://developers.cloudflare.com/pages/framework-guides/
- esbuild postinstall issue: https://github.com/evanw/esbuild/issues/2927
