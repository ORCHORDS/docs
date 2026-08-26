# Nx Affected-Deploy Workflow for Workers Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Nx monorepo contains ten or more Cloudflare Workers packages and every CI run deploys all of them, wasting time and Cloudflare deploy slots. You want to deploy only the Workers whose source has actually changed since the last merge to `main`.

---

## Context

Nx's affected computation uses the git diff between a base SHA and a head SHA to determine which projects have changed, then walks the project dependency graph to include anything transitively impacted. `nx affected --target=deploy` runs `wrangler deploy` only for those projects. Each Workers package in the monorepo has its own `project.json` defining a `deploy` target that shells out to `wrangler deploy`. In CI the base is typically `origin/main` and the head is the current commit. `nx run-many --parallel` controls how many deploys execute concurrently, which is important to stay within Cloudflare's API rate limits.

---

## Section 1 — Per-Package Nx and Wrangler Configuration

```json
// packages/payments-worker/project.json
{
  "name": "payments-worker",
  "$schema": "../../node_modules/nx/schemas/project-schema.json",
  "projectType": "application",
  "sourceRoot": "packages/payments-worker/src",
  "targets": {
    "build": {
      "executor": "@nx/esbuild:esbuild",
      "options": {
        "outputPath": "dist/packages/payments-worker",
        "main": "packages/payments-worker/src/index.ts",
        "tsConfig": "packages/payments-worker/tsconfig.json",
        "format": ["esm"]
      }
    },
    "typecheck": {
      "executor": "nx:run-commands",
      "options": {
        "command": "tsc --noEmit",
        "cwd": "packages/payments-worker"
      }
    },
    "deploy": {
      "executor": "nx:run-commands",
      "dependsOn": ["build", "typecheck"],
      "options": {
        "command": "npx wrangler deploy",
        "cwd": "packages/payments-worker"
      }
    },
    "dev": {
      "executor": "nx:run-commands",
      "options": {
        "command": "npx wrangler dev --port 8788",
        "cwd": "packages/payments-worker"
      }
    }
  },
  "implicitDependencies": ["shared-utils", "shared-types"]
}
```

```toml
# packages/payments-worker/wrangler.toml
name = "payments-worker"
main = "../../dist/packages/payments-worker/index.js"
compatibility_date = "2025-01-01"
node_compat = true

[vars]
ENVIRONMENT = "production"

[[kv_namespaces]]
binding = "SESSIONS_KV"
id = "abc123"

[[d1_databases]]
binding = "PAYMENTS_DB"
database_name = "payments"
database_id = "def456"
```

```json
// nx.json (repo root)
{
  "$schema": "./node_modules/nx/schemas/nx-schema.json",
  "defaultBase": "main",
  "namedInputs": {
    "default": ["{projectRoot}/**/*", "sharedGlobals"],
    "sharedGlobals": ["{workspaceRoot}/nx.json", "{workspaceRoot}/package-lock.json"]
  },
  "targetDefaults": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["default"],
      "cache": true
    },
    "deploy": {
      "dependsOn": ["build"],
      "cache": false
    }
  }
}
```

---

## Section 2 — Running Affected Deploy Locally and in CI

```bash
# Show which projects are affected since main (dry run)
nx affected --target=deploy --base=main --head=HEAD --dry-run

# Deploy only affected Workers
nx affected --target=deploy --base=main --head=HEAD

# Control parallelism — deploy at most 3 Workers concurrently
nx affected --target=deploy --base=main --head=HEAD --parallel=3

# Run affected deploy for a specific environment by passing wrangler flags
nx affected --target=deploy \
  --base=main --head=HEAD \
  --parallel=2 \
  -- --env staging

# Deploy ALL packages (override affected, useful for initial setup)
nx run-many --target=deploy --all --parallel=2

# List all projects in the repo
nx show projects

# Show the dependency graph
nx graph
```

---

## Section 3 — CI Integration with GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

jobs:
  affected-deploy:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      NX_CLOUD_AUTH_TOKEN: ${{ secrets.NX_CLOUD_AUTH_TOKEN }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Required for nx affected git base comparison

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Set NX base and head SHAs
        uses: nrwl/nx-set-shas@v4
        # Sets NX_BASE and NX_HEAD env vars automatically from PR/push context

      - name: Deploy affected Workers
        run: |
          npx nx affected \
            --target=deploy \
            --base=$NX_BASE \
            --head=$NX_HEAD \
            --parallel=3 \
            --no-bail

      - name: Notify on failure
        if: failure()
        run: echo "One or more Workers failed to deploy — check logs above."
```

---

## Anti-patterns

- **Using `--all` in production CI** — `nx run-many --target=deploy --all` ignores the affected computation entirely and deploys every Worker on every push. Only use `--all` for initial bootstrapping or forced full deploys.
- **Setting `cache: true` on the `deploy` target** — Deployments are side effects; caching them means a Worker won't re-deploy when the cache is hit even if the previous deploy failed. Always set `cache: false` on deploy targets.
- **Omitting `fetch-depth: 0` in checkout** — A shallow clone means Nx cannot compute the git diff back to `origin/main`, causing `affected` to fall back to deploying everything.
- **High `--parallel` values** — Cloudflare's Workers API has rate limits. Setting `--parallel` above 5 risks rate-limit errors during large deploys. Keep it at 2–3 for safety.
- **Missing `implicitDependencies` on shared packages** — If `shared-utils` changes but `payments-worker` doesn't list it as an implicit dependency, Nx won't mark `payments-worker` as affected.

---

## Gotchas

- `nrwl/nx-set-shas` sets `NX_BASE` and `NX_HEAD` automatically based on GitHub context (PR base, push before-SHA). Use it instead of hardcoding SHAs.
- `nx affected` computes the set at invocation time — if you invoke it twice in one CI run, ensure inputs haven't changed between invocations.
- `wrangler deploy` inside an Nx target inherits the working directory from `project.json`'s `cwd` option. The `wrangler.toml` must be in that directory.
- Nx caches task results in `.nx/cache` locally. In CI, restore this directory from cache (e.g., actions/cache) to speed up build steps that precede deploy.
- Changing `nx.json` `namedInputs` or `targetDefaults` invalidates all Nx cache entries — do this deliberately during repo maintenance windows.

---

## Verification

```bash
# Show what would be affected right now
nx affected --target=deploy --base=origin/main --dry-run

# Verify a specific project's deploy target config
nx show project payments-worker --json | jq '.targets.deploy'

# Confirm the deploy ran for the expected set of projects
nx affected --target=deploy --base=origin/main 2>&1 | grep -E '(Running|Skipping)'

# Check deployed Workers via wrangler
npx wrangler deployments list --name payments-worker
```

---

## Related

- `turborepo-workers-monorepo-build-cache.md`
- `git-worktree-parallel-feature-development.md`

---

## Sources

- Nx Affected Documentation — https://nx.dev/ci/features/affected
- Nrwl nx-set-shas Action — https://github.com/nrwl/nx-set-shas
- Wrangler Deploy Reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
