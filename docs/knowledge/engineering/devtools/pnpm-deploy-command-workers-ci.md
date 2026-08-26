# pnpm deploy for Isolated Worker Package Deployments in CI

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your pnpm monorepo contains multiple Cloudflare Workers packages. When deploying a single
worker to production, `wrangler deploy` runs inside the monorepo context and pulls in the
entire `node_modules` tree — including dev dependencies and unrelated workspace packages.
This bloats the bundle analysis, confuses Wrangler's dependency resolution, and makes
it hard to produce a reproducible standalone artifact for auditing or archiving. You want
`pnpm deploy` to produce a self-contained directory that holds exactly the production
dependencies for one worker, mirroring what a standalone install would produce.

## Context

`pnpm deploy` (added in pnpm v7) copies a workspace package plus its closure of
production dependencies into an output directory. The output is a portable directory
with its own `node_modules` and `package.json`, not linked to the monorepo store. It is
the pnpm equivalent of `npm pack` + `npm install --production` but workspace-aware: it
resolves `workspace:*` dependencies by copying the local package source rather than
fetching from the registry.

For Cloudflare Workers, this means you can:

1. `pnpm deploy` the worker package into a temp dir.
2. Run `wrangler deploy` from inside that dir.
3. Cache or archive the dir as a deployment artifact.

Stack: pnpm ≥ 8.x, Wrangler 3.x, Turborepo, TypeScript, GitHub Actions.

## Monorepo Structure

```
apps/
  api-worker/
    src/index.ts
    package.json
    wrangler.toml
  admin-worker/
    src/index.ts
    package.json
    wrangler.toml
packages/
  shared-utils/
    src/index.ts
    package.json
pnpm-workspace.yaml
package.json
```

`apps/api-worker/package.json`:

```json
{
  "name": "@example-org/example-repo",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*",
    "hono": "^4.0.0"
  },
  "devDependencies": {
    "wrangler": "^3.0.0",
    "@cloudflare/workers-types": "^4.0.0",
    "vitest": "^2.0.0"
  }
}
```

## Running pnpm deploy

```bash
# Deploy api-worker's production closure to a staging directory
pnpm --filter @example-org/example-repo deploy --prod /tmp/deploy/api-worker

# The output directory contains:
# /tmp/deploy/api-worker/
#   node_modules/          <- only production deps + their transitive deps
#   package.json           <- the worker's package.json
#   src/                   <- source files (not built; Wrangler builds on deploy)
#   wrangler.toml          <- copied from the package root
```

Key flags:

- `--prod` — excludes `devDependencies`. **Always use this for deployment.** Omitting it
  copies all deps including Vitest, which inflates the directory and may cause Wrangler
  to pick up unexpected modules.
- `--filter` — selects the workspace package by name. Alternatively, `cd apps/api-worker
  && pnpm deploy --prod /tmp/deploy/api-worker`.
- The output path can be relative or absolute; use absolute paths in CI to avoid
  ambiguity.

## wrangler deploy from the Output Directory

After `pnpm deploy`, run Wrangler from inside the output directory so it resolves
`node_modules` locally:

```bash
cd /tmp/deploy/api-worker
wrangler deploy --config wrangler.toml
```

If your `wrangler.toml` references the source via `main = "src/index.ts"`, Wrangler
uses esbuild to bundle `src/index.ts` and resolves imports against the local
`node_modules`. The workspace-linked `@example-org/example-repo` is now a real directory
under `node_modules`, not a symlink — this ensures consistent module resolution whether
you are in the monorepo or in the deployed artifact.

## Full CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy-api-worker.yml
name: Deploy api-worker

on:
  push:
    branches: [main]
    paths:
      - "apps/api-worker/**"
      - "packages/shared-utils/**"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Build shared packages
        run: pnpm --filter @example-org/example-repo build

      - name: pnpm deploy (production closure)
        run: |
          pnpm --filter @example-org/example-repo deploy --prod ${{ runner.temp }}/api-worker

      - name: Deploy to Cloudflare Workers
        working-directory: ${{ runner.temp }}/api-worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --config wrangler.toml

      - name: Upload deployment artifact
        uses: actions/upload-artifact@v4
        with:
          name: api-worker-deploy-${{ github.sha }}
          path: ${{ runner.temp }}/api-worker
          retention-days: 7
```

## Workspace Package Resolution

When `pnpm deploy` encounters a `workspace:*` dependency, it copies the local package
source into the output `node_modules`. If `@example-org/example-repo` has a `build` step,
the **built output** (`dist/`) must exist before `pnpm deploy` runs:

```bash
# Correct order in CI
pnpm --filter @example-org/example-repo build   # produces packages/shared-utils/dist/
pnpm --filter @example-org/example-repo deploy --prod /tmp/deploy/api-worker
# Now /tmp/deploy/api-worker/node_modules/@example-org/example-repo/dist/ exists
```

If `shared-utils` uses `exports` in its `package.json`, verify the paths are correct
after deploy:

```bash
node -e "require('/tmp/deploy/api-worker/node_modules/@example-org/example-repo')"
```

## Turborepo Integration

Add a `deploy:prod` task that gates on the build:

```json
// turbo.json
{
  "tasks": {
    "deploy:prod": {
      "dependsOn": ["build", "^build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    }
  }
}
```

`apps/api-worker/package.json`:

```json
{
  "scripts": {
    "build": "tsc --noEmit",
    "deploy:prod": "pnpm deploy --prod /tmp/deploy/api-worker && cd /tmp/deploy/api-worker && wrangler deploy"
  }
}
```

Run from the repo root:

```bash
pnpm turbo deploy:prod --filter @example-org/example-repo
```

## Anti-patterns

- **Running `wrangler deploy` from the monorepo root** — Wrangler resolves `node_modules`
  upward from the `main` entry point. In a monorepo this can include workspace symlinks
  and hoist-resolution artifacts that differ from what a standalone install would produce.
  Always deploy from the `pnpm deploy` output directory.
- **Omitting `--prod`** — Without `--prod`, `devDependencies` (Vitest, TypeScript, etc.)
  are copied into the output. Wrangler may bundle them if they appear in the module
  graph, producing a larger Worker bundle.
- **Deploying before building workspace dependencies** — `pnpm deploy` copies package
  source as-is. If `dist/` does not exist, the Worker cannot import the package.
- **Using `pnpm deploy` for Workers that use `wrangler.toml` path aliases** — Path
  aliases in `tsconfig.json` are resolved by esbuild relative to the `tsconfig.json`
  location. After `pnpm deploy`, ensure the `tsconfig.json` is either copied (it is, by
  default) or that `wrangler.toml` references it explicitly.

## Gotchas

- `pnpm deploy` does not run `prepack` or `prepare` lifecycle scripts by default in all
  versions. In pnpm ≥ 8.10, it runs `prepack` before copying. Check with
  `pnpm deploy --help` for the current behavior.
- The output directory must not exist before running `pnpm deploy` — or it must be empty.
  In CI, use `${{ runner.temp }}/api-worker` (always clean) or `rm -rf` the target first.
- `pnpm deploy` copies `wrangler.toml` only if it is listed in `files` in `package.json`
  or if the package has no `files` field (in which case all files are included). Verify
  with `pnpm pack --dry-run` what would be included.
- Wrangler's `--outdir` option and `pnpm deploy`'s `--prod` flag are orthogonal. Wrangler
  still bundles from source; `pnpm deploy` only sets up the `node_modules` closure.

## Verification

```bash
# Check what pnpm deploy produced
ls /tmp/deploy/api-worker/node_modules | sort

# Confirm devDependencies are absent
ls /tmp/deploy/api-worker/node_modules/vitest 2>/dev/null && echo "BAD: devDep present" || echo "OK"
ls /tmp/deploy/api-worker/node_modules/typescript 2>/dev/null && echo "BAD: devDep present" || echo "OK"

# Verify workspace dep was materialized
ls /tmp/deploy/api-worker/node_modules/@example-org/example-repo

# Dry-run wrangler deploy from the output dir
cd /tmp/deploy/api-worker && wrangler deploy --dry-run --outdir /tmp/bundle-check
ls -lh /tmp/bundle-check/
```

## Related

- `pnpm-workspace-setup.md`
- `pnpm-workspaces-selective-deploy-changed.md`
- `pnpm-overrides-materialization.md`
- `turborepo-cloudflare-workers-pipeline.md`
- `wrangler-config-validation-ci.md`

## Sources

- pnpm deploy docs: https://pnpm.io/cli/deploy
- pnpm workspace protocol: https://pnpm.io/workspaces
- Wrangler deploy: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
