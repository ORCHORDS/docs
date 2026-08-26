# Turborepo Affected Workers Selective Deploy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project monorepo has 8+ Cloudflare Workers. Every CI push deploys all of them with `wrangler deploy --config` in a loop, taking 12+ minutes even when only one Worker changed. You want to deploy only the Workers whose source files (or upstream packages) were modified since the last successful deploy, using Turborepo's task graph to detect affected packages.

## Context

Turborepo's `--filter` flag supports a `[<from-ref>...<to-ref>]` git range syntax that emits only the packages affected by commits in that range, including transitive dependents. Combined with a `deploy` task defined in `turbo.json`, you get a graph-aware selective deploy: if `packages/db-utils` changes, Turborepo automatically includes every Worker that depends on it. The pattern requires Turborepo v2.0+ and that each Worker is a separate workspace package with a `deploy` script.

## 1. Workspace Package Structure

Each Worker must be an isolated pnpm workspace package with its own `package.json` and `wrangler.toml`:

```
workers/
  api/
    package.json      # name: "@example project/worker-api"
    wrangler.toml
    src/index.ts
  jobs/
    package.json      # name: "@example project/worker-jobs"
    wrangler.toml
    src/index.ts
  assets/
    package.json      # name: "@example project/worker-assets"
    wrangler.toml
    src/index.ts
packages/
  db-utils/
    package.json      # name: "@example project/db-utils"
    src/index.ts
```

```jsonc
// workers/api/package.json
{
  "name": "@example project/worker-api",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "build":   "wrangler deploy --dry-run --outdir dist",
    "deploy":  "wrangler deploy",
    "dev":     "wrangler dev",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@example project/db-utils": "workspace:*"
  }
}
```

The `deploy` script is intentionally thin — Turborepo orchestrates sequencing and caching.

## 2. Turborepo Task Graph for Deploy

Define `deploy` as a pipeline task that depends on `build` completing successfully:

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"]
    },
    "deploy": {
      "dependsOn": ["build", "typecheck"],
      "cache": false,
      "env": [
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ENVIRONMENT"
      ]
    },
    "deploy:staging": {
      "dependsOn": ["build", "typecheck"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    }
  }
}
```

`"cache": false` is mandatory for `deploy` — deployment is a side effect, not a reproducible output.

## 3. Detecting Affected Packages in CI

Use Turborepo's `--filter` with a git SHA range to run `deploy` only on changed packages:

```bash
# In GitHub Actions, BASE_SHA is the last successful deploy commit
turbo run deploy \
  --filter="...[${BASE_SHA}...HEAD]" \
  --concurrency=3
```

The `...` prefix means "this package and all packages that depend on it" — so changing `@example project/db-utils` automatically triggers deploy for `@example project/worker-api` and `@example project/worker-jobs` if they depend on it.

Store the last successful deploy SHA in a persistent store:

```bash
# After successful deploy, store the SHA
echo "$GITHUB_SHA" > .last-deploy-sha
# Or use a Cloudflare KV / R2 object for cross-runner persistence
```

## 4. GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # for OIDC if using Workers secrets federation

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0    # full history for git range filtering

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Restore Turborepo remote cache
        uses: actions/cache@v4
        with:
          path: .turbo
          key: turbo-${{ github.sha }}
          restore-keys: turbo-

      - name: Get last successful deploy SHA
        id: last-sha
        run: |
          # Fetch from R2 or fallback to merge-base with main
          SHA=$(curl -sf \
            "https://api.example.com/internal/last-deploy-sha" \
            -H "Authorization: Bearer ${{ secrets.INTERNAL_TOKEN }}" \
            || git merge-base origin/main HEAD^1)
          echo "sha=${SHA}" >> "$GITHUB_OUTPUT"

      - name: Deploy affected Workers
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          ENVIRONMENT: production
        run: |
          BASE="${{ steps.last-sha.outputs.sha }}"
          echo "Deploying packages changed since ${BASE}"
          pnpm turbo run deploy \
            --filter="...[${BASE}...HEAD]" \
            --concurrency=3 \
            --log-order=grouped

      - name: Record successful deploy SHA
        if: success()
        run: |
          curl -sf -X POST \
            "https://api.example.com/internal/last-deploy-sha" \
            -H "Authorization: Bearer ${{ secrets.INTERNAL_TOKEN }}" \
            -d "$GITHUB_SHA"
```

## 5. Fallback: Force-Deploy All Workers

When the base SHA is unavailable (first deploy, corrupted state), deploy everything:

```bash
# deploy-all.sh
#!/usr/bin/env bash
set -euo pipefail

echo "Running full deploy of all Workers"
pnpm turbo run deploy \
  --filter="@example project/worker-*" \
  --concurrency=2
```

Add this as a manual GitHub Actions workflow trigger:

```yaml
on:
  workflow_dispatch:
    inputs:
      force_all:
        description: 'Deploy all Workers regardless of changes'
        type: boolean
        default: false
```

```yaml
- name: Deploy
  run: |
    if [ "${{ inputs.force_all }}" = "true" ]; then
      pnpm turbo run deploy --filter="@example project/worker-*" --concurrency=2
    else
      pnpm turbo run deploy --filter="...[${BASE}...HEAD]" --concurrency=3
    fi
```

## 6. Verifying the Filter Before Deploying

Dry-run the filter to see which packages would be affected before running real deploys:

```bash
# List affected packages without running tasks
pnpm turbo run deploy \
  --filter="...[origin/main...HEAD]" \
  --dry-run=json \
  | jq '.packages[]'
```

Use this in PR previews to annotate which Workers would be deployed.

## Anti-patterns

- **Setting `"cache": true` on the `deploy` task.** Turborepo would skip deploys for unchanged packages using a cached result — but cached results mean "the task was run before," not "the Worker is deployed." Deploy must always re-execute.
- **Using `--filter` without `...` prefix.** `--filter="[SHA...HEAD]"` only matches packages with direct changes; `--filter="...[SHA...HEAD]"` matches them AND their dependents. Omitting `...` will miss Workers that depend on changed shared packages.
- **Deploying Workers in parallel with `--concurrency=10`.** Wrangler deploys hit the Cloudflare API which rate-limits at account level. Keep concurrency at 2-3.
- **Storing the last-deploy SHA only in the runner's filesystem.** CI runners are ephemeral; always persist the SHA to an external store (R2, KV, GitHub environment variable, or a git tag).

## Gotchas

- `fetch-depth: 0` is required in `actions/checkout` for `git merge-base` and SHA range calculations to work. Shallow clones break git range filters.
- Turborepo's `--filter` uses package names, not directory paths. Ensure `package.json` `name` fields are unique and match what you reference in filters.
- If a Worker has no `build` output (e.g., it uses `wrangler deploy` directly without a separate build step), the `deploy` task's `dependsOn: ["build"]` may fail. Either add a no-op `build` script or adjust `dependsOn` per package.
- Wrangler `2.x` vs `3.x` deploy command flags differ. Pin wrangler in the root `package.json` and use `pnpm.overrides` to prevent workers from pulling a different version.

## Verification

```bash
# Preview affected packages for current branch vs main
pnpm turbo run deploy \
  --filter="...[origin/main...HEAD]" \
  --dry-run=json | jq -r '.packages[]'

# Time a selective deploy (should be much faster than full deploy)
time pnpm turbo run deploy --filter="...[HEAD^...HEAD]" --concurrency=3

# Confirm only changed worker was deployed
wrangler deployments list --name api-worker | head -5
```

## Related

- `turborepo-cloudflare-workers-pipeline.md`
- `turborepo-setup.md`
- `turborepo-remote-cache-cloudflare-r2.md`
- `pnpm-workspaces-selective-deploy-changed.md`
- `changeset-versioning-monorepo-release.md`

## Sources

- https://turbo.build/repo/docs/crafting-your-repository/running-tasks#using-filters-to-select-packages
- https://turbo.build/repo/docs/reference/run#--filter-string
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/nicolo-ribaudo/changesets-turbo-selective
