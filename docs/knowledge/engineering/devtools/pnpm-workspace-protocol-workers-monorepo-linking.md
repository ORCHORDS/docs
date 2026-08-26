# pnpm Workspace Protocol Workers Monorepo Linking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a monorepo with shared utility packages (`packages/utils`, `packages/db`)
and several Cloudflare Workers (`workers/api`, `workers/webhook`). After running
`pnpm install` the Workers can't import the local packages — either `node_modules`
is missing the symlinks, Wrangler complains about the bundle, or the types don't resolve.

---

## Context

The `workspace:` protocol in `package.json` tells pnpm to resolve a dependency from
another workspace package instead of the npm registry. At install time pnpm creates
a symlink in `node_modules`. At publish time (or `pnpm deploy`) it replaces
`workspace:*` with the concrete resolved version. Wrangler's bundler (esbuild under
the hood) then follows the symlink and bundles the local source — which is what you
want for Workers since the runtime has no `node_modules` access.

---

## Repository layout

```
pnpm-workspace.yaml
package.json               # root
packages/
  utils/
    package.json           # name: "@acme/utils"
    src/index.ts
  db/
    package.json           # name: "@acme/db"
    src/index.ts
workers/
  api/
    package.json           # depends on @acme/utils, @acme/db
    src/index.ts
    wrangler.toml
  webhook/
    package.json
    src/index.ts
    wrangler.toml
```

---

## pnpm-workspace.yaml

```yaml
packages:
  - 'packages/*'
  - 'workers/*'
```

---

## Local package: packages/utils/package.json

```json
{
  "name": "@acme/utils",
  "version": "0.1.0",
  "private": true,
  "exports": {
    ".": {
      "import": "./src/index.ts",
      "types": "./src/index.ts"
    }
  },
  "scripts": {
    "typecheck": "tsc --noEmit"
  }
}
```

Using `src/index.ts` directly as the export avoids a build step for local packages —
esbuild (via Wrangler) handles the TypeScript transpilation at bundle time.

---

## Worker: workers/api/package.json

```json
{
  "name": "@acme/api-worker",
  "version": "0.0.0",
  "private": true,
  "dependencies": {
    "@acme/utils": "workspace:*",
    "@acme/db":    "workspace:^"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.0.0",
    "wrangler": "^4.0.0"
  }
}
```

`workspace:*` means "whatever version is in the workspace" — pnpm never checks the
registry. `workspace:^` means "at least the semver major in the workspace" — safer
when packages have real versioning.

---

## TypeScript path resolution

TypeScript does not follow pnpm symlinks automatically when `moduleResolution` is
`bundler` or `node16`. Add `paths` in the worker's `tsconfig.json`:

```json
// workers/api/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "moduleResolution": "bundler",
    "paths": {
      "@acme/utils": ["../../packages/utils/src/index.ts"],
      "@acme/db":    ["../../packages/db/src/index.ts"]
    }
  },
  "include": ["src"]
}
```

Alternatively, if every package exports `types` pointing at source (as shown above),
TypeScript resolves them without `paths` when `moduleResolution` is `bundler` — verify
with `tsc --traceResolution | grep acme`.

---

## Wrangler bundling: no extra config needed

Wrangler 4 follows symlinks created by pnpm by default:

```toml
# workers/api/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
```

Run from the worker directory:

```bash
cd workers/api
pnpm wrangler dev
```

Or from the root with the filter flag:

```bash
pnpm --filter @acme/api-worker wrangler dev
```

---

## pnpm deploy for CI

When deploying a worker in CI without the full monorepo, use `pnpm deploy` to produce
a self-contained directory with all workspace dependencies copied (not symlinked):

```bash
# In CI after `pnpm install --frozen-lockfile`
pnpm --filter @acme/api-worker deploy dist/api-worker --prod

# Then deploy from the self-contained dir
cd dist/api-worker
wrangler deploy
```

`pnpm deploy` rewrites `workspace:*` references to the resolved version and copies
the package source into `node_modules`, making the directory portable.

---

## Anti-patterns

- **Using `file:` protocol instead of `workspace:`** — `file:` creates a copy at
  install time, not a symlink; changes to the local package are invisible until
  reinstall.
- **Publishing private local packages to the registry** just to link them — defeats
  the whole point of a monorepo.
- **`"main": "dist/index.js"` without a build step** — if the `dist/` folder doesn't
  exist Wrangler (or tsc) gets an import error; point `exports` at `src/` for local-only
  packages.
- **Relying on `node_modules` symlinks inside the Workers runtime** — the runtime has
  no filesystem; you need Wrangler to bundle the dependency at build time.

---

## Gotchas

- pnpm hoists a subset of packages to the root `node_modules` and keeps the rest in
  `.pnpm/`. Local workspace packages are always symlinked into each package's
  `node_modules` — they are never hoisted. This means `require.resolve('@acme/utils')`
  from the root fails; always resolve from the package that declares the dependency.
- `wrangler deploy --minify` will follow the symlink and minify the local package
  source. If the local package has top-level `console.log` for debugging you may
  accidentally ship it.
- `workspace:^` with `pnpm publish` will replace the specifier with the concrete version
  from the package's `package.json`. If you accidentally publish a private package to
  the registry this version will be locked in the lockfile of any consumer.
- Turborepo / Nx task pipelines must list local packages in their `dependsOn` arrays
  or the build order is not guaranteed when packages produce build artifacts.

---

## Verification

```bash
# Confirm symlinks exist
ls -la workers/api/node_modules/@acme/
# Should show:  utils -> ../../../packages/utils

# Confirm TypeScript sees the types
pnpm --filter @acme/api-worker tsc --noEmit

# Confirm Wrangler bundles without error
pnpm --filter @acme/api-worker wrangler deploy --dry-run --outdir /tmp/bundle
```

---

## Related

- `pnpm-workspace-setup.md`
- `pnpm-catalogs-version-policy.md`
- `turborepo-cloudflare-workers-pipeline.md`
- `tsc-incremental-build-workers-monorepo-performance.md`
- `typescript-declaration-maps-workers-monorepo.md`

---

## Sources

- https://pnpm.io/workspaces
- https://pnpm.io/cli/deploy
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://www.typescriptlang.org/tsconfig#moduleResolution
