# Turborepo --affected Flag for Selective Cloudflare Workers Deployment

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo contains ten Cloudflare Workers packages but a typical PR only touches one or two. Running `wrangler deploy` for all Workers on every commit wastes CI minutes and risks deploying untested packages. You need a way to deploy only the Workers that were actually affected by the current change, including transitive dependencies.

## Context

Turborepo's `--affected` flag compares the current file tree against a base ref and computes which packages have changed, then propagates that signal through the `dependsOn` graph so downstream packages are also included. For service-binding scenarios — where `worker-b` depends on `worker-a` — a change in `worker-a` must trigger a redeploy of `worker-b` as well. The `--dry=json` output can be parsed by a subsequent GitHub Actions step to build a dynamic matrix, combining Turbo's change detection with the parallel-deploy pattern.

## Pipeline Configuration

Define the deploy pipeline in `turbo.json` with explicit ordering for service bindings:

```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".wrangler/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"]
    },
    "test": {
      "dependsOn": ["build"]
    },
    "deploy": {
      "dependsOn": ["build", "test", "^deploy"],
      "cache": false,
      "outputs": []
    }
  }
}
```

`"^deploy"` means a package's deploy task waits until all its `dependencies` (in `package.json`) have deployed first — critical for service bindings where `worker-b` calls `worker-a` via its binding.

## Running Affected Deploys Locally

```bash
# Deploy only packages changed since the previous commit
turbo run deploy --affected --from=HEAD~1

# Deploy only packages changed since the main branch diverged
turbo run deploy --affected --from=origin/main

# Preview what would run without executing
turbo run deploy --affected --from=HEAD~1 --dry=json | \
  jq '.tasks[] | {package: .package, task: .task, reason: .dependencies}'

# Force-include a specific package even if not detected as changed
turbo run deploy --filter=packages/api-gateway... --affected --from=HEAD~1
```

## GitHub Actions with Dynamic Matrix from --dry=json

```yaml
# .github/workflows/deploy-affected.yml
name: Deploy Affected Workers

on:
  push:
    branches: [main]

concurrency:
  group: deploy-affected-${{ github.ref }}
  cancel-in-progress: false

jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.affected.outputs.matrix }}
      empty: ${{ steps.affected.outputs.empty }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v3
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - id: affected
        run: |
          BASE="origin/main"
          if [ "${{ github.event_name }}" = "push" ]; then
            BASE="${{ github.event.before }}"
          fi

          PACKAGES=$(pnpm exec turbo run deploy \
            --affected --from="$BASE" --dry=json 2>/dev/null \
            | jq -c '[.tasks[] | select(.task=="deploy") | .package]')

          if [ "$PACKAGES" = "[]" ] || [ -z "$PACKAGES" ]; then
            echo "empty=true"  >> "$GITHUB_OUTPUT"
            echo "matrix={\"package\":[]}" >> "$GITHUB_OUTPUT"
          else
            echo "empty=false" >> "$GITHUB_OUTPUT"
            echo "matrix={\"package\":$PACKAGES}" >> "$GITHUB_OUTPUT"
          fi

  deploy:
    needs: plan
    if: needs.plan.outputs.empty == 'false'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.plan.outputs.matrix) }}
      fail-fast: true
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v3
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Deploy ${{ matrix.package }}
        working-directory: ${{ matrix.package }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm exec wrangler deploy --env production
```

## Shared Library Change Cascades

When a shared library (`packages/shared-utils`) changes, all Workers that depend on it must redeploy. Turborepo handles this automatically through the `dependsOn` graph:

```json
// packages/auth-worker/package.json
{
  "dependencies": {
    "@repo/shared-utils": "workspace:*"
  }
}
```

With this in place, `--affected` from a change in `shared-utils` will include `auth-worker` in the deploy set. Verify the cascade:

```bash
# Touch the shared library and preview the cascade
touch packages/shared-utils/src/index.ts
git add -N packages/shared-utils/src/index.ts
turbo run deploy --affected --from=HEAD --dry=json | \
  jq '[.tasks[] | select(.task=="deploy") | .package]'
# ["packages/shared-utils", "packages/auth-worker", "packages/api-gateway"]
```

## Caching Deploy Tasks Safely

Deploy tasks generally must not be cached (Cloudflare's state is external), but build tasks can and should be:

```json
// turbo.json — deploy is never cached; build is
{
  "pipeline": {
    "build": {
      "cache": true,
      "outputs": ["dist/**"]
    },
    "deploy": {
      "cache": false,
      "dependsOn": ["build"]
    }
  }
}
```

Using `cache: false` on deploy means Turbo always re-runs it for affected packages, even if source files are unchanged — correct behaviour for an external side-effect task.

## Anti-patterns

- **Using `--affected` without `--from`** — defaults to comparing against `HEAD`, which is always empty diff; always specify a meaningful base.
- **Caching deploy tasks** — if a deploy is cache-hit, Turbo skips it silently; a Worker code change that was already built but not re-deployed will go live silently on the next manual run.
- **Omitting `^deploy` in `dependsOn` for service-bound Workers** — Worker B can deploy before Worker A finishes, causing a service-binding resolution failure in production.
- **Parsing Turbo JSON output with string tools instead of jq** — package names may contain slashes or special characters that break naive grep/awk parsing.

## Gotchas

- `--affected` uses git diff under the hood; unstaged or untracked files are not included in the comparison.
- `github.event.before` is `0000000000000000000000000000000000000000` on the first push to a new branch; fall back to `origin/main` in that case.
- Turbo `--dry=json` output schema may change across Turbo major versions; pin `turbo` in `devDependencies` and test upgrades in a separate branch.
- Service binding configuration in `wrangler.toml` must reference the Worker's `name`, not its package path; keep `name` stable across renames.
- `--affected` in Turbo 2.x requires the `--from` flag; earlier versions used `--since`.

## Verification

```bash
# Confirm Turbo detects the right packages after a targeted change
git diff --name-only HEAD~1 HEAD
turbo run deploy --affected --from=HEAD~1 --dry=json | \
  jq '[.tasks[] | select(.task=="deploy") | .package]'

# Verify service binding order is respected
turbo run deploy --affected --from=HEAD~1 --dry=json | \
  jq '.tasks[] | {package, dependsOn: .dependencies}'

# Check Turbo cache status after a no-change run
turbo run build --affected --from=HEAD~1 --summarize
cat .turbo/runs/*.json | jq '.tasks[] | {package, cacheState}'
```

## Related

- `git-worktree-ci-matrix-parallel-workers-deploy.md`
- `pnpm-recursive-exec-workers-monorepo-build.md`

## Sources

- Turborepo --affected documentation — https://turbo.build/repo/docs/reference/run#--affected
- Turborepo pipeline dependsOn — https://turbo.build/repo/docs/reference/configuration#dependson
- Cloudflare service bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Turbo dry run JSON schema — https://turbo.build/repo/docs/reference/run#--dryjson
