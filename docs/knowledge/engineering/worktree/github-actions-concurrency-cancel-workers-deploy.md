# GitHub Actions Concurrency Groups for Cloudflare Workers Deployments

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Two engineers push commits to `main` within seconds of each other. Both CI runs reach the
Wrangler deploy step and execute concurrently. The second run deploys an older build over
the first because Cloudflare's Workers API processes the second upload a few hundred
milliseconds after the first. The result is a stale version serving production traffic
until someone notices and re-triggers the pipeline. You need a mechanism to serialize
Workers deployments without blocking unrelated CI steps.

## Context

GitHub Actions `concurrency` groups let you declare that only one run of a given key
may be active at a time. When a newer run arrives for the same key, you can either
queue it (`cancel-in-progress: false`) or cancel the older run immediately
(`cancel-in-progress: true`). For Workers deployments the correct default is to cancel
the in-progress run so the latest commit always wins, but for D1 migrations the correct
default is to queue so migrations run in order. Mixing both concerns in one job is the
most common mistake.

Concurrency groups are scoped to a workflow file + key string. They do not cross
repositories, do not prevent Wrangler CLI calls made outside GitHub Actions from
interfering, and do not replace Cloudflare-side version ordering guarantees.

## Serializing Production Deploys: Cancel In-Progress

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]

# One deploy active at a time per environment; newer run cancels the old one.
concurrency:
  group: deploy-${{ github.ref_name }}-${{ vars.CLOUDFLARE_WORKER_NAME }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
      - uses: actions/upload-artifact@v4
        with:
          name: worker-dist
          path: dist/

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - uses: actions/download-artifact@v4
        with:
          name: worker-dist
          path: dist/
      - env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy --env production
```

## Queueing Migrations: No Cancel

```yaml
# .github/workflows/migrate.yml
name: D1 Migrations

on:
  push:
    branches: [main]
    paths:
      - "migrations/**"

# Migrations must run in order — never cancel an in-progress migration.
concurrency:
  group: d1-migrate-${{ github.ref_name }}
  cancel-in-progress: false          # queue; do not cancel

jobs:
  migrate:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm wrangler d1 migrations apply --env production DB_PROD
```

## Per-PR Preview Environment Concurrency

```yaml
# .github/workflows/preview.yml
name: PR Preview Deploy

on:
  pull_request:
    types: [opened, synchronize]

# One preview deploy per PR at a time; cancel old runs for the same PR.
concurrency:
  group: preview-pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          PREVIEW_NAME="pr-${{ github.event.pull_request.number }}-worker"
          pnpm wrangler deploy \
            --name "$PREVIEW_NAME" \
            --env preview
```

## Concurrency Group Key Design Patterns

```yaml
# Pattern 1 — per-environment, per-worker (most granular)
concurrency:
  group: deploy-${{ matrix.env }}-${{ matrix.worker }}
  cancel-in-progress: true

# Pattern 2 — per-branch (useful when branch = environment mapping)
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true

# Pattern 3 — global serializer across all deploys to the same account
# (useful for small teams; too slow for large monorepos)
concurrency:
  group: cloudflare-deploy-${{ vars.CF_ACCOUNT_ID }}
  cancel-in-progress: false

# Pattern 4 — workflow-level group, covering ALL jobs in the file
# Place at the top-level of the YAML (not inside a job)
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## Detecting Cancellation in Cleanup Steps

```yaml
# Ensure cleanup always runs even when the workflow is cancelled
jobs:
  deploy:
    runs-on: ubuntu-latest
    concurrency:
      group: deploy-${{ github.ref_name }}
      cancel-in-progress: true
    steps:
      - uses: actions/checkout@v4
      - id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy --env production

      - name: Notify on cancellation
        if: cancelled()
        run: |
          echo "Deploy was cancelled by a newer run. Commit: $GITHUB_SHA"
          # Post a Slack webhook, update a status page, etc.
```

```typescript
// scripts/check-active-deploy.ts
// Use the GitHub API to verify no deploy is in progress before a manual trigger
import { Octokit } from "@octokit/rest";

async function hasActiveDeployRun(
  owner: string,
  repo: string,
  workflowFile: string
): Promise<boolean> {
  const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
  const runs = await octokit.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: workflowFile,
    status: "in_progress",
    per_page: 5,
  });
  return runs.data.total_count > 0;
}

const active = await hasActiveDeployRun("orchords", "my-repo", "deploy.yml");
if (active) {
  console.error("A deploy is already in progress. Wait or cancel it first.");
  process.exit(1);
}
```

## Anti-patterns

- Using the same concurrency group for build and deploy jobs. The build job is safe to
  run in parallel; only the deploy step needs serialization. Sharing the group cancels
  builds that were nearly finished, wasting compute.
- Setting `cancel-in-progress: true` on migration workflows. A cancelled D1 migration
  may leave the schema in a half-applied state. Always use `false` for migrations.
- Using `${{ github.sha }}` in the concurrency key. This makes every run unique,
  disabling concurrency protection entirely.
- Relying on concurrency groups as the sole mechanism to prevent double-deploys. If
  a developer triggers `wrangler deploy` locally while CI is also deploying, the
  concurrency group does not help. Use Wrangler's `--versions` split workflow or a
  deployment lock in Cloudflare KV for truly mutual exclusion.

## Gotchas

- When a run is cancelled mid-job, subsequent jobs that `needs:` the cancelled job are
  also skipped. Structure workflows so the deploy job is the only one that needs
  serialization, not the entire pipeline.
- The concurrency group key is evaluated at workflow parse time. Dynamic expressions
  like `${{ github.event.pull_request.number }}` are available, but context variables
  that are only set inside job steps are not.
- GitHub counts a queued run (waiting for a concurrency group) against your concurrency
  quota. On free plans with many PRs this can exhaust the concurrent job limit faster
  than expected.

## Verification

```bash
# Via GitHub CLI — list in-progress runs for the deploy workflow
gh run list --workflow deploy.yml --status in_progress --repo example-org/example-repo

# Check the concurrency group currently holding the lock
gh api /repos/example-org/example-repo/actions/runs \
  --jq '.workflow_runs[] | select(.status=="in_progress") | {id,head_sha,name}'
```

## Related

- `github-actions-wrangler-deploy-pipeline.md`
- `canary-deployment-strategy.md`
- `workers-d1-migration-ci-pipeline.md`
- `monorepo-wrangler-selective-deploy.md`
- `wrangler-version-upload-deploy-split-workflow.md`

## Sources

- GitHub Actions concurrency docs: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
- Cloudflare Workers deploy API ordering: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
