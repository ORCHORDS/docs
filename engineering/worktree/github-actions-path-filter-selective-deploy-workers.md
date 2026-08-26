# Selective Cloudflare Workers Deployment with GitHub Actions Path Filters

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo holds five Cloudflare Worker packages. Every commit to `main` triggers a workflow that deploys all five, even when only one file changed. Build minutes balloon, deploy risk increases, and Wrangler rate limits become a concern. You want each Worker to deploy **only when its own files changed**.

## Context

[`dorny/paths-filter`](https://github.com/dorny/paths-filter) is a GitHub Action that compares the current commit's diff against configurable glob patterns and emits boolean outputs and a JSON changes array. Combined with job `needs:` and `if:` conditions, you can build a DAG where each deploy job runs only when its package was touched.

For very large teams a dynamic matrix approach (one job, N packages) is more maintainable than N static jobs — this article covers both.

---

## Static Per-Worker Jobs (Simple, Up to ~5 Workers)

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches:
      - main

jobs:
  # ── 1. Detect which packages changed ──────────────────────────────────────
  changes:
    name: Detect Changes
    runs-on: ubuntu-latest
    outputs:
      api:        ${{ steps.filter.outputs.api }}
      auth:       ${{ steps.filter.outputs.auth }}
      webhooks:   ${{ steps.filter.outputs.webhooks }}

    steps:
      - uses: actions/checkout@v4

      - name: Path filter
        id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            api:
              - 'packages/api/**'
              - 'packages/shared/**'   # shared lib change → redeploy api too
            auth:
              - 'packages/auth/**'
              - 'packages/shared/**'
            webhooks:
              - 'packages/webhooks/**'
              - 'packages/shared/**'

  # ── 2. Per-Worker deploy jobs, gated on changes output ────────────────────
  deploy-api:
    name: Deploy api-worker
    needs: changes
    if: needs.changes.outputs.api == 'true'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: Deploy
        working-directory: packages/api
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  deploy-auth:
    name: Deploy auth-worker
    needs: changes
    if: needs.changes.outputs.auth == 'true'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: Deploy
        working-directory: packages/auth
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  deploy-webhooks:
    name: Deploy webhooks-worker
    needs: changes
    if: needs.changes.outputs.webhooks == 'true'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: Deploy
        working-directory: packages/webhooks
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Dynamic Matrix (Scales to Many Workers)

```yaml
# .github/workflows/deploy-matrix.yml
name: Deploy Workers (Matrix)

on:
  push:
    branches: [main]

jobs:
  changes:
    name: Detect Changes
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.filter.outputs.changes }}

    steps:
      - uses: actions/checkout@v4

      - name: Path filter
        id: filter
        uses: dorny/paths-filter@v3
        with:
          # When list-files is not set, the `changes` output is a JSON array
          # of filter names whose patterns matched — e.g. ["api","webhooks"]
          list-files: none
          filters: |
            api:      ['packages/api/**', 'packages/shared/**']
            auth:     ['packages/auth/**', 'packages/shared/**']
            webhooks: ['packages/webhooks/**', 'packages/shared/**']
            mailer:   ['packages/mailer/**', 'packages/shared/**']

  deploy:
    name: Deploy ${{ matrix.worker }}
    needs: changes
    if: ${{ needs.changes.outputs.matrix != '[]' }}
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        worker: ${{ fromJson(needs.changes.outputs.matrix) }}

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: Deploy
        working-directory: packages/${{ matrix.worker }}
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## TypeScript: Generating Filter Config from package.json

For monorepos with many packages, generate the filter list programmatically:

```typescript
// scripts/gen-path-filters.ts
import { execSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';

const packagesDir = path.resolve('packages');
const workerDirs = fs.readdirSync(packagesDir).filter((d) => {
  const pkg = path.join(packagesDir, d, 'package.json');
  if (!fs.existsSync(pkg)) return false;
  const json = JSON.parse(fs.readFileSync(pkg, 'utf8'));
  // Only include packages with a wrangler.toml
  return fs.existsSync(path.join(packagesDir, d, 'wrangler.toml'));
});

const filters = workerDirs
  .map((d) => `  ${d}: ['packages/${d}/**', 'packages/shared/**']`)
  .join('\n');

console.log(`filters: |\n${filters}`);
// Pipe this into .github/workflows/deploy-matrix.yml via a pre-commit hook or CI step
```

---

## Anti-patterns

- **Deploying all Workers on every push** — the canonical anti-pattern this article solves. Even a `wrangler.toml` change in one package should not redeploy siblings.
- **Missing `packages/shared/**` in filter patterns** — if a shared utility package changes and downstream Workers are not re-deployed, production runs stale code against updated types.
- **Using `paths:` trigger on the workflow** — the `on.push.paths` filter skips the workflow entirely if no matching file changed, preventing the `changes` job from running at all. This means required status checks fail. Use `dorny/paths-filter` inside the workflow instead, so the workflow always runs but individual jobs are skipped.
- **`fail-fast: true` on the matrix** — a single Worker deploy failure should not cancel other Workers. Always set `fail-fast: false`.

---

## Gotchas

- `dorny/paths-filter` compares against the **merge base** for PRs and the **previous commit** for push events. On the first push to a new branch with no history, all filters return `true`. This is usually the desired behaviour for new branches.
- The `changes` output from `paths-filter` is a JSON string (`"[\"api\",\"webhooks\"]"`) — wrap it with `fromJson()` in the matrix `include` expression.
- If all filter outputs are `false`, the `matrix` output is `'[]'`. Check `matrix != '[]'` in the `if:` condition to avoid a matrix expansion error on an empty array.
- GitHub caches workflow files for the current SHA. A change to `deploy.yml` itself does not appear in the path filter diff; it takes effect on the next commit.

---

## Verification

```bash
# Manually test filter logic against a specific commit range
gh api repos/example-org/example-repo/compare/HEAD~1...HEAD --jq '.files[].filename'

# Check which jobs ran (and which were skipped) for a workflow run
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
# {"name": "Deploy api-worker", "conclusion": "success"}
# {"name": "Deploy auth-worker", "conclusion": "skipped"}
# {"name": "Deploy webhooks-worker", "conclusion": "skipped"}
```

---

## Related

- `changesets-monorepo-workers-package-versioning.md`
- `lefthook-pre-commit-workers-monorepo.md`
- `git-sparse-checkout-workers-monorepo-ci.md`
- [dorny/paths-filter documentation](https://github.com/dorny/paths-filter)

## Sources

- `dorny/paths-filter` README (2024)
- GitHub Actions documentation — expressions and contexts (2026)
- Cloudflare Workers Wrangler CLI documentation (2026)
- example.com internal runbook: "Selective CI deploys" (2025)
