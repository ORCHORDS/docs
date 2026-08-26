# GitHub Actions CI/CD Pipeline for Cloudflare Workers + Pages Monorepo

Date:   2026-08-22
Author: example.com
Status: stable

## Symptom

Deployments go out manually from developer laptops, D1 migrations run out
of order, Pages and Worker deployments desync, and there is no smoke test
confirming the live environment is healthy after a deploy. A broken deploy
is discovered by users, not the team.

## Context

A full CI pipeline for a Cloudflare Workers + Pages monorepo needs several
ordered stages: static analysis, test execution, build artifact creation,
database migration, Worker deployment, Pages deployment, and post-deploy
verification. GitHub Actions job-level `needs` dependencies enforce the
ordering; environment-level protection rules add human gates for production.

This article assumes pnpm workspaces, Turborepo for caching, a D1 database,
a `worker/` directory, and a `frontend/` directory with a Next.js app
deployed to Cloudflare Pages.

---

## 1. Workflow Trigger Strategy

```yaml
# .github/workflows/ci.yml
name: CI / Deploy

on:
  push:
    branches: [main, 'release/**']
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

Key decisions:
- Cancel in-progress runs on PR pushes (new commit supersedes the old).
- Never cancel runs on `main`; let all stages finish for auditability.
- `release/**` branches also get the full pipeline so release PRs are
  validated before merge.

---

## 2. Job Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                     CI / Deploy pipeline                        │
│                                                                 │
│   lint ──────┐                                                  │
│              ├──► build ──► migrate ──► deploy-worker ──►       │
│   test ──────┘                     │                   │        │
│                                    └──► deploy-pages ──►        │
│                                                         │        │
│                                                    smoke-test   │
└─────────────────────────────────────────────────────────────────┘
```

Jobs and their `needs` declarations:

```
┌──────────────┬──────────────────────────────┬──────────────────┐
│ Job          │ needs                        │ Condition        │
├──────────────┼──────────────────────────────┼──────────────────┤
│ lint         │ —                            │ always           │
│ test         │ —                            │ always           │
│ build        │ lint, test                   │ always           │
│ migrate      │ build                        │ main branch only │
│ deploy-worker│ migrate                      │ main branch only │
│ deploy-pages │ migrate                      │ main branch only │
│ smoke-test   │ deploy-worker, deploy-pages  │ main branch only │
└──────────────┴──────────────────────────────┴──────────────────┘
```

---

## 3. Lint and Test Jobs

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec turbo run lint typecheck --filter='[HEAD^1]'

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec turbo run test --filter='[HEAD^1]'
        env:
          # Miniflare needs no real token for local D1 emulation.
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

Using Turborepo's `--filter='[HEAD^1]'` runs only tasks in packages that
changed since the previous commit, cutting CI time on large monorepos.

---

## 4. Build Job with Artifact Upload

```yaml
  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec turbo run build

      - name: Upload Worker bundle
        uses: actions/upload-artifact@v4
        with:
          name: worker-bundle
          path: worker/dist/
          retention-days: 3

      - name: Upload Pages build
        uses: actions/upload-artifact@v4
        with:
          name: pages-build
          path: frontend/.next/
          retention-days: 3
```

---

## 5. D1 Migration Job

```yaml
  migrate:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production   # Requires a manual approval gate if configured.
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile

      - name: Apply D1 migrations (production)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm exec wrangler d1 migrations apply PROD_DB \
            --env production \
            --remote
```

The `--remote` flag applies migrations to the real D1 database. Omit it
for a dry-run against the local SQLite emulation file.

---

## 6. Wrangler Deploy Job

```yaml
  deploy-worker:
    needs: migrate
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: worker-bundle, path: worker/dist/ }
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile

      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm exec wrangler deploy \
            --config worker/wrangler.toml \
            --env production \
            --var RELEASE_SHA:"${{ github.sha }}"
```

---

## 7. Pages Deploy Job

```yaml
  deploy-pages:
    needs: migrate
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: pages-build, path: frontend/.next/ }
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile

      - name: Deploy Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm exec wrangler pages deploy frontend/.next/standalone \
            --project-name=my-project \
            --branch=main \
            --commit-hash="${{ github.sha }}"
```

---

## 8. Smoke Test Job

```yaml
  smoke-test:
    needs: [deploy-worker, deploy-pages]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile

      - name: Run Playwright smoke suite
        env:
          BASE_URL: https://my-project.pages.dev
          API_URL:  https://api.my-project.workers.dev
        run: pnpm exec playwright test --project=chromium tests/smoke/

      - name: Health-check Worker
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            https://api.my-project.workers.dev/health)
          [ "$STATUS" = "200" ] || (echo "Worker unhealthy: $STATUS" && exit 1)
```

---

## Anti-patterns

- Deploying the Worker and running migrations in the same job. If the
  migration fails mid-deploy, the Worker may be live against a partially
  migrated schema.
- Uploading `node_modules/` as a build artifact. Upload only the compiled
  output (e.g. `worker/dist/`) to keep artifact sizes small.
- Using `if: always()` on `deploy-worker` without understanding that it
  will deploy even when tests fail.
- Storing `CF_API_TOKEN` as a plain Actions variable instead of a secret.
  Secrets are redacted in logs; variables are not.
- Running Playwright in the same job as the deploy, which prolongs the
  critical path. Keep smoke tests in a dedicated final job.

---

## Gotchas

- Wrangler requires `CLOUDFLARE_ACCOUNT_ID` for Pages deploys but NOT for
  Workers deploys (account is inferred from the API token). Set it anyway
  to avoid confusion when scripts are reused.
- `wrangler pages deploy` does NOT create D1 bindings automatically. The
  Pages project must have the binding configured in the dashboard or via
  `wrangler pages project` commands before the first deploy.
- Turborepo remote caching requires `TURBO_TOKEN` and `TURBO_TEAM` secrets
  to share cache across CI runs. Without them each run rebuilds from scratch.
- GitHub's `cancel-in-progress` on `main` should always be false. Cancelling
  a production deploy mid-flight can leave the Worker and Pages in
  mismatched states.

---

## Verification

```bash
# Trigger the pipeline manually on a branch:
gh workflow run ci.yml --ref my-branch

# Watch live logs:
gh run watch

# Check the last workflow run status:
gh run list --workflow=ci.yml --limit=5

# Verify D1 migration was applied:
pnpm exec wrangler d1 migrations list PROD_DB --env production --remote
```

---

## Related

- documentation/categories/worktree/conventional-commits-automated-changelog.md
- documentation/categories/worktree/pr-readiness-checklist-workers-projects.md
- documentation/categories/worktree/monorepo-workspace-cloudflare-workers.md
- documentation/categories/worktree/git-branching-cloudflare-preview-environments.md

---

## Source URLs

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- https://developers.cloudflare.com/d1/migrations/
- https://turbo.build/repo/docs/crafting-your-repository/running-tasks#filter-by-changed-packages
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idneeds
