# turborepo-cloudflare-workers-pipeline

**Issue:** A monorepo with Cloudflare Workers and Pages packages runs
all tasks on every commit because `turbo.json` has no pipeline
declared — every invocation is `turbo run build` with no dependency
graph, no caching, and no affected-files filtering. The deploy task
also runs even when only tests changed, burning Cloudflare deploy
minutes on no-op uploads.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
turbo run deploy
  • Packages in scope: web, worker, packages/shared
  • Running deploy in 3 packages
  [web]    deploying…  (even though only worker/src changed)
  [worker] deploying…
```

`turbo run build` takes 4 min on the initial run and 4 min on the
second run with no changes — nothing is cached. `wrangler deploy`
fires unconditionally because no `dependsOn` chain gates it on a
successful build. Remote cache is unconfigured, so CI always starts
cold.

## Context

Turborepo models the monorepo task graph as a directed acyclic graph
(DAG) whose edges are `dependsOn` relationships declared in
`turbo.json`. Cloudflare Workers projects add two wrinkles: the
`deploy` task invokes `wrangler deploy` and is side-effectful (it
must never be cached), and the `worker` package's build output is a
single bundled `.js` file that Wrangler consumes, not a tree of
files like a Next.js app. Both patterns need explicit config to work
correctly with Turborepo's cache model.

## Pipeline task dependency graph

The canonical ordering for a Workers + Pages monorepo is:

```
typecheck ──►  test  ──►  build  ──►  deploy
                              │
                         (lint runs in parallel with test,
                          both depend on typecheck)
              lint ──────────►
```

```jsonc
// turbo.json (root)
{
  "$schema": "https://turbo.build/schema.json",
  "globalEnv": ["NODE_ENV", "CF_ACCOUNT_ID"],
  "tasks": {
    "typecheck": {
      "dependsOn": ["^typecheck"],
      "outputs": []
    },
    "lint": {
      "dependsOn": ["typecheck"],
      "outputs": []
    },
    "test": {
      "dependsOn": ["typecheck"],
      "outputs": ["coverage/**"],
      "inputs": ["src/**", "test/**", "vitest.config.*"]
    },
    "build": {
      "dependsOn": ["^build", "typecheck"],
      "outputs": [".next/**", "dist/**", ".wrangler/tmp/**"]
    },
    "deploy": {
      "dependsOn": ["build", "test", "lint"],
      "cache": false,
      "inputs": []
    }
  }
}
```

Key decisions:
- `"cache": false` on `deploy` — Wrangler uploads are idempotent
  on the platform side but never safe to skip locally; Turborepo
  must always execute this task.
- `"^build"` on `build` — upstream packages (e.g. `packages/shared`)
  must finish building before `apps/worker` or `apps/web` build.
- `"inputs"` on `test` — limits cache invalidation to source and
  test files; changing only `README.md` reuses the test cache.

## Remote cache setup with Cloudflare R2

Turborepo's remote cache protocol is compatible with any S3-style
endpoint. Use R2 to keep cache in the same account as the Workers.

```bash
# Install the self-hosted remote cache adapter
pnpm add -D @ducktors/turborepo-remote-cache

# In wrangler.toml for the cache Worker (separate mini-worker):
[vars]
TURBO_TOKEN = "generate-a-secret-and-store-in-CF-secret"
```

```jsonc
// turbo.json additions
{
  "remoteCache": {
    "enabled": true,
    "preflight": false
  }
}
```

Environment variables for CI (GitHub Actions / Cloudflare Pages build):

| Variable         | Value                               |
|------------------|-------------------------------------|
| `TURBO_API`      | `https://turbo-cache.your.workers.dev` |
| `TURBO_TOKEN`    | (Cloudflare secret)                 |
| `TURBO_TEAM`     | `team_yourorg`                      |
| `TURBO_REMOTE_ONLY` | `true` (CI never uses local cache)|

With R2 remote cache, a full cold build that takes 3 min locally
replays in ~8 s on the second CI run when only tests changed —
`build` hits remote cache; only `test` re-runs.

## Affected-files filtering

Turborepo computes affected packages via `turbo run --filter` using
git to find changed files. For Cloudflare Workers the most useful
patterns are:

```bash
# Run only tasks in packages changed since main
turbo run build --filter=...[origin/main]

# Run deploy only for the worker, regardless of what changed
turbo run deploy --filter=@org/worker

# Run everything that depends on shared package
turbo run build --filter=...@org/shared...
```

```jsonc
// Per-package turbo.json override (apps/worker/turbo.json)
{
  "tasks": {
    "build": {
      "inputs": [
        "src/**/*.ts",
        "wrangler.toml",
        "../../packages/shared/src/**/*.ts"
      ],
      "outputs": ["dist/**", ".wrangler/tmp/**"]
    }
  }
}
```

The per-package `inputs` override is the most precise cache key:
the Worker's build cache is only invalidated when its own source,
its `wrangler.toml`, or the shared library source changes — not when
the Next.js app's CSS changes.

## CI pipeline integration

```yaml
# .github/workflows/ci.yml
- name: Turbo build + test
  env:
    TURBO_API: ${{ vars.TURBO_API }}
    TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
    TURBO_TEAM: ${{ vars.TURBO_TEAM }}
  run: |
    turbo run typecheck lint test build \
      --filter=...[origin/main] \
      --parallel

- name: Deploy (main branch only)
  if: github.ref == 'refs/heads/main'
  run: turbo run deploy --filter=...[origin/main~1]
```

The deploy step uses `[origin/main~1]` (compare to the previous
commit on main) so that every merge to main deploys exactly the
changed packages and nothing more.

## Anti-patterns

- **`cache: true` on `deploy`** — Turborepo will skip the Wrangler
  upload on cache hit, silently leaving a stale Worker version live.
- **No `^build` on `build`** — shared packages may not have rebuilt
  before the Worker bundles them; the build succeeds but with stale
  shared code.
- **Storing `TURBO_TOKEN` in the repo** — rotate it immediately; use
  Cloudflare Workers Secrets or GitHub Actions secrets.
- **Globbing `**` in `inputs`** — negates the affected-files speedup;
  every task re-runs on any file change anywhere in the package.
- **Running `turbo run deploy` on every PR** — use `--filter` and
  a branch guard; unreviewed PRs should not touch production Workers.

## Gotchas

- Turborepo hashes the task's `inputs` set; if `wrangler.toml` is not
  in `inputs`, changing `[vars]` or `[[routes]]` will not invalidate
  the build cache even though the deployed Worker would differ.
- `.wrangler/tmp/` is Wrangler's intermediate build directory; it must
  be in `outputs` or Turborepo cannot restore it for the deploy task
  that depends on build.
- `globalEnv` entries are included in every task's cache key; add
  `NODE_ENV` and any `CF_*` vars that affect build output here,
  otherwise debug and production builds share a cache bucket.
- Turborepo v2's remote cache protocol changed the auth header format;
  older self-hosted adapters must be updated to `>=2.0` of the adapter
  package or cache writes silently 401.

## Verification

```bash
# First run: all tasks execute
turbo run build test --filter=...  --dry=json | jq '.tasks[].cache'
# Second run with no changes: all tasks should be "HIT"
turbo run build test --filter=...
# Expected output: "cache hit, replaying output" for build + test

# Confirm deploy is never cached
turbo run deploy --dry=json | jq '.tasks[] | select(.taskId | contains("deploy")) | .cache'
# Expected: false
```

- CI: compare `Duration` in Turbo summary between run 1 (cold) and
  run 2 (warm) on the same commit — warm must be <30 s for a typical
  Workers project.
- Inspect R2 bucket: artifacts appear under `{TURBO_TEAM}/{hash}`.

## Related

- `documentation/categories/devtools/eslint-v9-flat-config-cloudflare-workers.md`
- `documentation/categories/devtools/typescript-cloudflare-workers-strict.md`
- `documentation/categories/devtools/pnpm-overrides-materialization.md`
- `documentation/categories/devtools/changesets-versioning.md`

## Sources

- https://turbo.build/repo/docs/reference/configuration
- https://turbo.build/repo/docs/crafting-your-repository/caching
- https://developers.cloudflare.com/r2/
- https://github.com/ducktors/turborepo-remote-cache
- https://turbo.build/repo/docs/crafting-your-repository/running-tasks#using-filters
