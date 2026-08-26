# Wrangler Version Upload/Deploy Split Workflow

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want safer, auditable Cloudflare Workers rollouts: upload a build artifact once, then
promote it across environments without rebuilding. You also need the ability to hold a
version for manual approval before it reaches production traffic, or to roll back
instantaneously by re-pointing a deployment without recompiling.

## Context

Wrangler 3.x introduced a two-phase release model:
`wrangler versions upload` compiles and stores a Worker version in Cloudflare's registry
without routing any traffic to it. `wrangler versions deploy` (or `wrangler deploy
--versions`) then atomically shifts the traffic split to one or more stored versions.
This decoupling lets CI pipelines upload once on every push, let QA verify the stored
artifact, and allow a human gate before production traffic shifts—without ever touching
source code again after the upload step.

The pattern also enables percentage-based gradual rollouts: send 10% of requests to the
new version, observe error rates, then ramp to 100% or roll back to 0% without a
redeploy.

## Uploading a Version Without Deploying

```bash
# In CI — runs on every push to main, no traffic impact
wrangler versions upload \
  --name my-worker \
  --env production \
  --message "feat(payments): idempotency key v2 (#412)"

# Capture the version ID for downstream jobs
VERSION_ID=$(wrangler versions list --name my-worker --env production \
  --json | jq -r '.[0].id')
echo "VERSION_ID=$VERSION_ID" >> "$GITHUB_ENV"
```

```yaml
# .github/workflows/upload.yml
jobs:
  upload:
    runs-on: ubuntu-latest
    outputs:
      version_id: ${{ steps.upload.outputs.version_id }}
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - id: upload
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm wrangler versions upload --name my-worker --env production
          ID=$(pnpm wrangler versions list --name my-worker --env production \
            --json | jq -r '.[0].id')
          echo "version_id=$ID" >> "$GITHUB_OUTPUT"
```

## Promoting a Stored Version to Production

```yaml
# .github/workflows/promote.yml  — triggered manually or after approval gate
on:
  workflow_dispatch:
    inputs:
      version_id:
        description: "Wrangler version ID to promote"
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production          # requires manual approval in GitHub Environments
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm wrangler versions deploy \
            "${{ github.event.inputs.version_id }}" \
            --name my-worker \
            --env production \
            --percentage 100
```

## Gradual Traffic Split During Rollout

```bash
# Step 1 — canary: 10% of requests go to the new version
wrangler versions deploy "$NEW_ID" \
  --name my-worker \
  --env production \
  --percentage 10 \
  --version "$OLD_ID:90"

# Step 2 — ramp after 15-minute soak (run from a separate CI job or cron)
wrangler versions deploy "$NEW_ID" \
  --name my-worker \
  --env production \
  --percentage 50 \
  --version "$OLD_ID:50"

# Step 3 — full promotion
wrangler versions deploy "$NEW_ID" \
  --name my-worker \
  --env production \
  --percentage 100
```

## Instant Rollback Without Rebuild

```bash
# List the two most recent versions
VERSIONS=$(wrangler versions list --name my-worker --env production --json)
PREV_ID=$(echo "$VERSIONS" | jq -r '.[1].id')

# Repoint 100% of traffic to the previous version — no compile step
wrangler versions deploy "$PREV_ID" \
  --name my-worker \
  --env production \
  --percentage 100
```

```typescript
// scripts/rollback.ts — typed helper for runbook automation
import { execSync } from "node:child_process";

function rollback(workerName: string, env: "staging" | "production"): void {
  const raw = execSync(
    `wrangler versions list --name ${workerName} --env ${env} --json`,
    { encoding: "utf-8" }
  );
  const versions: Array<{ id: string; created_on: string }> = JSON.parse(raw);
  if (versions.length < 2) throw new Error("No previous version to roll back to");
  const prevId = versions[1].id;
  execSync(
    `wrangler versions deploy ${prevId} --name ${workerName} --env ${env} --percentage 100`,
    { stdio: "inherit" }
  );
  console.log(`Rolled back ${workerName}/${env} to version ${prevId}`);
}

rollback("my-worker", "production");
```

## Chaining Upload and Promote Across Environments

```yaml
# Upload once, promote staging → production sequentially
jobs:
  upload:
    outputs:
      version_id: ${{ steps.u.outputs.version_id }}
    steps:
      - id: u
        run: |
          pnpm wrangler versions upload --name my-worker
          echo "version_id=$(pnpm wrangler versions list --name my-worker \
            --json | jq -r '.[0].id')" >> "$GITHUB_OUTPUT"

  deploy-staging:
    needs: upload
    steps:
      - run: |
          pnpm wrangler versions deploy "${{ needs.upload.outputs.version_id }}" \
            --name my-worker \
            --env staging \
            --percentage 100

  deploy-production:
    needs: deploy-staging
    environment: production      # manual approval gate
    steps:
      - run: |
          pnpm wrangler versions deploy "${{ needs.upload.outputs.version_id }}" \
            --name my-worker \
            --env production \
            --percentage 100
```

## Anti-patterns

- Running `wrangler deploy` (legacy one-shot) in production pipelines—this uploads and
  promotes atomically, bypassing any approval gate or canary phase.
- Storing version IDs only in ephemeral CI logs. Always write them to job outputs or a
  dedicated KV/D1 release registry so the rollback runbook can retrieve them.
- Using `--percentage` splits without a monitoring soak window. A timed CI job or a
  Cloudflare Tail Worker alert should gate the ramp, not just a fixed sleep.
- Uploading from a non-reproducible build (e.g., `Date.now()` baked into the bundle).
  The artifact stored via `versions upload` must be identical to what you tested.

## Gotchas

- `wrangler versions list` returns versions newest-first; index `[0]` is always the
  latest upload, not the currently live version. Use `wrangler deployments list` to
  confirm what is actually serving traffic.
- Version IDs are UUIDs scoped to the worker name + account. They are not portable
  across accounts or renamed workers.
- The `--percentage` flag requires that all listed versions' percentages sum to exactly
  100. Omitting `--version OLD_ID:N` when sending partial traffic to a new version will
  cause the command to fail.
- `wrangler versions upload` does not run D1 migrations. Run migrations before the upload
  step so the stored artifact is never ahead of the database schema.

## Verification

```bash
# Confirm what version is currently live
wrangler deployments list --name my-worker --env production

# Confirm the stored version matches your commit SHA
wrangler versions view "$VERSION_ID" --name my-worker

# Tail live logs to validate canary traffic
wrangler tail my-worker --env production --format json
```

## Related

- `wrangler-environments-staging-production.md`
- `canary-deployment-strategy.md`
- `cloudflare-workers-observability-tail-workers.md`
- `rollback-strategy.md`
- `git-tag-semantic-versioning-workers-deploy-gates.md`

## Sources

- Cloudflare Wrangler v3 Versions docs: https://developers.cloudflare.com/workers/wrangler/commands/#versions
- Cloudflare gradual deployments guide: https://developers.cloudflare.com/workers/platform/gradual-rollouts/
