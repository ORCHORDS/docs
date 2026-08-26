# Monorepo Deploy Pipeline with Turborepo, Wrangler & Cloudflare Pages + Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

In the example project monorepo, a change to the `api` Worker triggers a full rebuild and
redeploy of the front-end Pages app, and vice versa — even when only one
package changed. CI times balloon, and a bad deploy to one package can gate
unrelated packages that are perfectly healthy.

## Context

example project (example.com) lives in a pnpm monorepo managed by Turborepo:

```
/
├── apps/
│   ├── web/          # Cloudflare Pages (Vite + React)
│   └── api/          # Cloudflare Workers (Hono)
├── packages/
│   ├── ui/           # Shared React components
│   ├── types/        # Shared TypeScript types
│   └── auth/         # Auth utilities (used by both web and api)
└── turbo.json
```

This article describes:
1. Turborepo affected-package detection to skip unaffected deploys
2. Per-package Wrangler deploy steps in GitHub Actions
3. Coordinated Pages + Workers deploy ordering
4. Deploy artifact parity check (ensures built bundle matches committed source)

---

## Turborepo Affected-Package Detection

Turborepo's `--filter` flag with `[HEAD^1]` detects packages changed since the
last commit. In CI, compare against the base branch instead.

```bash
# Packages affected by changes in this PR vs main
pnpm turbo run build --filter="...[origin/main]" --dry=json \
  | jq '[.tasks[] | select(.taskId | endswith(":build")) | .packageName]'
```

### `turbo.json` — Deploy Pipeline Definition

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".svelte-kit/**", ".wrangler/**"]
    },
    "deploy:pages": {
      "dependsOn": ["build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CF_ACCOUNT_ID", "CF_PROJECT_NAME"]
    },
    "deploy:worker": {
      "dependsOn": ["build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CF_ACCOUNT_ID"]
    },
    "test:e2e": {
      "dependsOn": ["deploy:pages", "deploy:worker"],
      "cache": false
    }
  }
}
```

Each package's `package.json` defines the actual command:

```json
// apps/web/package.json
{
  "scripts": {
    "deploy:pages": "wrangler pages deploy dist --project-name $CF_PROJECT_NAME"
  }
}
```

```json
// apps/api/package.json
{
  "scripts": {
    "deploy:worker": "wrangler deploy --config wrangler.production.toml"
  }
}
```

---

## Per-Package Wrangler Deploy Steps

```yaml
# .github/workflows/deploy.yml
name: Monorepo Deploy

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      deploy_web: ${{ steps.affected.outputs.deploy_web }}
      deploy_api: ${{ steps.affected.outputs.deploy_api }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v3
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Detect affected packages
        id: affected
        run: |
          AFFECTED=$(pnpm turbo run build \
            --filter="...[HEAD^1]" \
            --dry=json \
            | jq -r '[.tasks[].packageName] | unique[]')

          echo "Affected packages:"
          echo "$AFFECTED"

          echo "deploy_web=$(echo "$AFFECTED" | grep -q '^web$' && echo true || echo false)" \
            >> "$GITHUB_OUTPUT"
          echo "deploy_api=$(echo "$AFFECTED" | grep -q '^api$' && echo true || echo false)" \
            >> "$GITHUB_OUTPUT"

  deploy-api:
    needs: detect-changes
    if: needs.detect-changes.outputs.deploy_api == 'true'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run build --filter=api
      - name: Parity check
        run: bash scripts/deploy-artifact-parity.sh apps/api/dist
      - name: Deploy Worker
        run: pnpm turbo run deploy:worker --filter=api
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

  deploy-web:
    needs: [detect-changes, deploy-api]
    if: |
      always() &&
      needs.detect-changes.outputs.deploy_web == 'true' &&
      (needs.deploy-api.result == 'success' || needs.deploy-api.result == 'skipped')
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run build --filter=web
      - name: Parity check
        run: bash scripts/deploy-artifact-parity.sh apps/web/dist
      - name: Deploy Pages
        run: pnpm turbo run deploy:pages --filter=web
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_PROJECT_NAME: example project-app
```

---

## Pages + Workers Coordinated Deploy Ordering

Deploy the API Worker first, then the web front-end. This ensures the front-end
never ships to users before the API endpoints it calls are live.

```
Dependency graph for a full deploy:

  [packages/types:build]
        ↓
  [packages/auth:build]  [packages/ui:build]
        ↓                       ↓
  [apps/api:build]       [apps/web:build]
        ↓                       ↓
  [apps/api:deploy:worker]       |
                    ↓            ↓
               [apps/web:deploy:pages]
                         ↓
               [test:e2e] (smoke gate)
```

Turborepo enforces this via `dependsOn`. The `deploy:pages` task in `apps/web`
must declare a dependency on the API deploy completing:

```json
// apps/web/turbo.json (package-level override)
{
  "tasks": {
    "deploy:pages": {
      "dependsOn": ["api#deploy:worker", "build"]
    }
  }
}
```

---

## Deploy Artifact Parity Check

Ensures the built `dist/` directory matches what the source code at `HEAD`
would produce — catches stale cached artifacts or tampered bundles.

```bash
#!/usr/bin/env bash
# scripts/deploy-artifact-parity.sh
set -euo pipefail

DIST_DIR=$1

if [[ ! -d "$DIST_DIR" ]]; then
  echo "ERROR: dist directory not found: $DIST_DIR"
  exit 1
fi

# Compute deterministic hash of all built files
ACTUAL_HASH=$(find "$DIST_DIR" -type f | sort | xargs sha256sum | sha256sum | awk '{print $1}')

# Re-build in a clean temp directory and compute expected hash
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cp -r . "$TMPDIR/repo"
(cd "$TMPDIR/repo" && pnpm install --frozen-lockfile && pnpm turbo run build --filter="$(basename "$(dirname "$DIST_DIR")")")

EXPECTED_DIR="$TMPDIR/repo/$DIST_DIR"
EXPECTED_HASH=$(find "$EXPECTED_DIR" -type f | sort | xargs sha256sum | sha256sum | awk '{print $1}')

if [[ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]]; then
  echo "PARITY FAIL: built artifact does not match clean build from HEAD"
  echo "  Actual:   $ACTUAL_HASH"
  echo "  Expected: $EXPECTED_HASH"
  exit 1
fi

echo "Parity OK: $DIST_DIR matches clean build ($ACTUAL_HASH)"
```

### Parity Check Results Table

| Check                              | Pass condition                   | Action on fail     |
|------------------------------------|----------------------------------|--------------------|
| File count matches                 | `find dist/ | wc -l` equal       | Abort deploy       |
| SHA-256 of all files equal         | Deterministic hash matches       | Abort deploy       |
| Source map present                 | `*.map` files exist in dist      | Warning only       |
| Bundle size within 10% of baseline | Size delta < 10%                 | Alert + manual gate|

---

## Turborepo Remote Cache

Enable remote cache to avoid rebuilding unchanged packages across CI runs.

```bash
# Authenticate with Turborepo remote cache (Vercel or self-hosted)
npx turbo login
npx turbo link

# Or pass token directly in CI
pnpm turbo run build --token="$TURBO_TOKEN" --team="example project"
```

```yaml
# .github/workflows/deploy.yml (add to env)
env:
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: example project
```

With remote cache, a build that has already run for the same file hash is
skipped entirely — `cache hit`. In a typical PR that only modifies `apps/api`,
`packages/ui` and `apps/web` will be cache hits.

---

## Anti-patterns

- **Deploying both Pages and Workers in parallel** — if the Worker deploy
  fails, the web app may still ship pointing to a broken API. Always deploy
  API before web.
- **Using `--filter=...` without `fetch-depth: 0` in actions/checkout** — git
  history is needed for `[HEAD^1]` comparisons; a shallow clone returns all
  packages as affected.
- **Skipping the parity check in production deploys** — Turborepo's build cache
  can serve stale artifacts if cache keys are misconfigured. The parity check
  catches this.
- **Putting `CLOUDFLARE_API_TOKEN` in `turbo.json` `env`** — this causes Turbo
  to include the token value in cache key computation. It is safe to list it in
  `env` for cache busting, but never log it.
- **Running `turbo deploy` without `cache: false`** — deploy tasks are always
  side-effectful and must not be cached. Mark them `"cache": false`.

---

## Gotchas

- Turborepo's `--filter="...[HEAD^1]"` syntax includes dependents of changed
  packages. A change to `packages/auth` will flag both `apps/api` and `apps/web`
  as affected — this is correct because both depend on `auth`.
- The `deploy:worker` and `deploy:pages` tasks will never be cached (per
  `"cache": false`), but their upstream `build` tasks are cached. The net
  effect is: rebuilds are fast (cached), but deploys always re-run.
- `wrangler pages deploy` outputs the deployment URL to stderr, not stdout.
  Capture with `2>&1` or parse from the API.
- Turborepo remote cache is opt-in per run. If `TURBO_TOKEN` is missing in CI,
  the build succeeds but runs in full each time — check CI logs for
  `WARN: No remote caching enabled`.

---

## Verification

```bash
# Dry-run to see which packages would deploy
pnpm turbo run deploy:worker deploy:pages --filter="...[HEAD^1]" --dry

# Verify remote cache hits in CI logs
# Look for: "cache hit, replaying logs" in turbo output

# Confirm artifact hash parity locally
bash scripts/deploy-artifact-parity.sh apps/api/dist
bash scripts/deploy-artifact-parity.sh apps/web/dist

# Check Cloudflare deployment status for both
wrangler deployments list --name example project-api
wrangler pages deployment list --project-name example project-app
```

---

## Related

- `cloudflare-workers-deploy-pipeline.md`
- `cloudflare-pages-preview-deployments.md`
- `deploy-artifact-build-parity-ci-gate.md`
- `wrangler-deploy-github-actions-workers.md`
- `environment-parity-staging-production.md`

## Sources

- Turborepo filtering — https://turbo.build/repo/docs/crafting-your-repository/running-tasks#using-filters
- Turborepo remote caching — https://turbo.build/repo/docs/core-concepts/remote-caching
- Wrangler Pages deploy — https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- pnpm workspaces — https://pnpm.io/workspaces
