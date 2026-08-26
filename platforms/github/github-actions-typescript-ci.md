# github-actions-typescript-ci

**Issue:** GitHub Actions CI for TypeScript + Cloudflare Pages Functions — type check, lint, deploy
**Date:** 2026-08-11
**Status:** documented

## Minimal CI workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, 'fix/**', 'feat/**']
  pull_request:
    branches: [main]

jobs:
  typecheck:
    name: TypeScript
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      - run: npx tsc -p tsconfig.functions.json --noEmit
      - run: npx tsc -p tsconfig.json --noEmit

  lint:
    name: ESLint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      - run: npx eslint . --ext .ts,.tsx --max-warnings 0

  deploy-preview:
    name: Deploy Preview
    runs-on: ubuntu-latest
    needs: [typecheck, lint]
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      - run: npm run build
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy dist --project-name=my-app --branch=${{ github.head_ref }}
```

## Lock file check

Prevent PRs from modifying `package-lock.json` without updating `package.json`:

```yaml
  lockfile-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      # Verify lock file is consistent — fails if package-lock.json is stale
      - run: |
          if ! git diff --exit-code package-lock.json; then
            echo "package-lock.json is out of sync with package.json"
            exit 1
          fi
```

## tsconfig.functions.json pattern

A separate tsconfig for Functions prevents the `@cloudflare/workers-types` globals from
polluting the frontend TypeScript config:

```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "types": ["@cloudflare/workers-types"],
    "lib": ["ES2022"],
    "target": "ES2022",
    "moduleResolution": "bundler",
    "noEmit": true,
    "strict": true
  },
  "include": ["functions/**/*.ts"]
}
```

The root `tsconfig.json` includes frontend files only — no `@cloudflare/workers-types`,
so `D1Database` etc. are not available in React/frontend code (intentional).

## Wrangler action version

Use the official `cloudflare/wrangler-action@v3` — it wraps `wrangler` CLI:

```yaml
- uses: cloudflare/wrangler-action@v3
  with:
    apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
    command: pages deploy dist --project-name=my-app
```

For main branch deploys (production), omit `--branch` — Cloudflare Pages treats the
configured "production branch" deployments as production (promoted automatically).

## Cache key for node_modules

Speed up CI by caching `node_modules`:

```yaml
- uses: actions/cache@v4
  id: node-cache
  with:
    path: node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('package-lock.json') }}
- run: npm ci
  if: steps.node-cache.outputs.cache-hit != 'true'
```

Note: `actions/setup-node` with `cache: 'npm'` caches the npm registry cache (~/.npm),
not node_modules. The manual cache above is more aggressive — it restores node_modules
directly and skips `npm ci` on cache hit.

## D1 migrations in CI

Run D1 migrations against a local SQLite file for testing:

```yaml
- run: |
    for f in migrations/*.sql; do
      wrangler d1 execute my-app-local --local --file="$f"
    done
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

For staging, run against the real D1 database:
```yaml
- run: wrangler d1 execute my-app-staging --remote --file=migrations/latest.sql
```

## Gotchas

- **`npm ci` vs `npm install`**: Always use `npm ci` in CI — it fails if lock file is out of sync, producing a hard error instead of silently updating deps.
- **`--noEmit` for type check**: Never run `tsc` without `--noEmit` in CI unless you want to emit JS — it's slower and leaves artifacts.
- **`--max-warnings 0` for ESLint**: Zero tolerance for warnings in CI. Fix warnings before they accumulate.
- **Wrangler needs CLOUDFLARE_API_TOKEN**: Store as a GitHub Actions secret, never in code. The token needs Pages:Write and Workers:Write scopes.
- **Pages preview URL**: `wrangler pages deploy` with `--branch=PR-branch` creates a preview URL. The URL is output to stdout — capture with `id: deploy` and `${{ steps.deploy.outputs.url }}` if needed in PR comments.
- **Node version**: Use `'22'` (LTS). Cloudflare Workers target ES2022 but Node is for build tools only — match your local version.

## Related

- `workers-types-migration.md`
- `wrangler-toml-reference.md`
- `pages-functions-env-types.md`
- `codex-review-merge-gate.md`
- `branch-protection-and-codeowners.md`
