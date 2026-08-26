# Git Worktree PR Preview Environment Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Reviewing a pull request for a Cloudflare Worker requires checking it out locally, running
`wrangler dev`, and verifying behavior manually — a multi-minute context switch. You want
each open PR to automatically get a named Cloudflare Workers preview that reviewers can
hit with `curl` or a browser, tied to the exact commit under review, without affecting
staging or production. When the PR closes the preview should be deleted.

## Context

Cloudflare Workers supports deploying a worker under any arbitrary name. You can deploy
`pr-412-payments-worker` alongside `payments-worker` in the same account without conflict.
By convention you scope preview worker names to the PR number and worker name so they are
discoverable and deletable by automation. Git worktrees allow local reproduction of a PR's
state without disturbing the main checkout, which is useful during reviewer investigation.
The canonical automation path uses GitHub Actions, not local worktrees, but a developer
worktree workflow is documented here for manual debugging of the preview.

## Creating a Preview on PR Open / Push

```yaml
# .github/workflows/pr-preview.yml
name: PR Preview

on:
  pull_request:
    types: [opened, synchronize, reopened]

concurrency:
  group: pr-preview-${{ github.event.pull_request.number }}
  cancel-in-progress: true

env:
  PREVIEW_WORKER: pr-${{ github.event.pull_request.number }}-payments-worker

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write   # to post the preview URL as a PR comment
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4

      - run: pnpm install --frozen-lockfile

      - name: Deploy preview worker
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm wrangler deploy \
            --name "$PREVIEW_WORKER" \
            --env preview \
            --var "PR_NUMBER:${{ github.event.pull_request.number }}" \
            apps/worker-payments/src/index.ts

          # Construct the preview URL (Workers subdomain pattern)
          ACCOUNT_SUBDOMAIN="${{ vars.CF_WORKERS_SUBDOMAIN }}"
          echo "url=https://${PREVIEW_WORKER}.${ACCOUNT_SUBDOMAIN}.workers.dev" \
            >> "$GITHUB_OUTPUT"

      - name: Comment preview URL on PR
        uses: actions/github-script@v7
        with:
          script: |
            const url = "${{ steps.deploy.outputs.url }}";
            const body = `### Preview deployed\n\n` +
              `Worker: \`${{ env.PREVIEW_WORKER }}\`\n` +
              `URL: ${url}\n\n` +
              `_Updates on every push. Deleted when this PR closes._`;
            // Find and update existing bot comment, or create new one
            const comments = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
            });
            const existing = comments.data.find(
              c => c.user.type === "Bot" && c.body.includes("Preview deployed")
            );
            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.payload.pull_request.number,
                body,
              });
            }
```

## Deleting the Preview on PR Close

```yaml
# .github/workflows/pr-preview-cleanup.yml
name: PR Preview Cleanup

on:
  pull_request:
    types: [closed]

jobs:
  delete-preview:
    runs-on: ubuntu-latest
    env:
      PREVIEW_WORKER: pr-${{ github.event.pull_request.number }}-payments-worker
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm wrangler delete \
            --name "$PREVIEW_WORKER" \
            --env preview \
            --force || echo "Preview worker not found — already deleted."
```

## Wrangler Config for Preview Environment

```toml
# apps/worker-payments/wrangler.toml
name = "payments-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[env.preview]
# name is overridden via --name CLI flag; this sets bindings for preview
vars = { ENVIRONMENT = "preview" }

[[env.preview.kv_namespaces]]
binding = "SESSIONS"
id = "PREVIEW_KV_NAMESPACE_ID"       # a dedicated preview KV namespace

[[env.preview.d1_databases]]
binding = "DB"
database_id = "PREVIEW_D1_DATABASE_ID"  # a seeded copy of the schema, not production
```

## Local Developer Workflow: Worktree + wrangler dev

```bash
# A reviewer wants to reproduce a bug in the preview environment locally
# without disturbing their main checkout

git worktree add ../pr-412 origin/pr/412

# Install isolated deps
cat > ../pr-412/.npmrc <<'EOF'
virtual-store-dir=.pnpm-store
EOF
(cd ../pr-412 && pnpm install --frozen-lockfile)

# Run wrangler dev pointed at the preview bindings
cd ../pr-412/apps/worker-payments
pnpm wrangler dev --env preview --local

# When done, clean up
cd -
rm -rf ../pr-412/node_modules ../pr-412/.pnpm-store
git worktree remove --force ../pr-412
```

## Auditing Active Preview Workers

```typescript
// scripts/list-preview-workers.ts
// Lists all deployed preview workers and which PRs they belong to
import { execSync } from "node:child_process";

interface WorkerEntry {
  id: string;
  created_on: string;
}

const raw = execSync("wrangler workers list --json", { encoding: "utf-8" });
const workers: WorkerEntry[] = JSON.parse(raw);

const previews = workers
  .filter((w) => /^pr-\d+-/.test(w.id))
  .map((w) => {
    const match = w.id.match(/^pr-(\d+)-(.+)$/);
    return {
      worker: w.id,
      pr: match ? Number(match[1]) : null,
      baseName: match ? match[2] : w.id,
      createdOn: w.created_on,
    };
  });

console.table(previews);
```

```bash
# Cron job to delete stale previews for closed PRs
# Add to a scheduled GitHub Actions workflow (e.g. nightly)
pnpm tsx scripts/list-preview-workers.ts | \
  awk 'NR>1 {print $2}' | \
  while read PR_NUM; do
    STATE=$(gh pr view "$PR_NUM" --json state -q .state 2>/dev/null || echo "MISSING")
    if [[ "$STATE" == "CLOSED" || "$STATE" == "MERGED" || "$STATE" == "MISSING" ]]; then
      echo "Deleting stale preview for PR #$PR_NUM"
      pnpm wrangler delete \
        --name "pr-${PR_NUM}-payments-worker" \
        --env preview \
        --force
    fi
  done
```

## Anti-patterns

- Deploying preview workers to the same environment config as staging. Preview workers
  should bind to isolated KV namespaces and D1 databases so a PR can't corrupt staging
  data.
- Using `--env production` or the production KV/D1 IDs in preview deployments. Always
  maintain a `preview` environment block in `wrangler.toml` with dedicated resource IDs.
- Forgetting to delete preview workers when PRs close. Cloudflare charges for stored
  Worker script versions. A nightly audit script (shown above) should catch any that the
  `pull_request:closed` trigger missed.
- Constructing the preview URL from account metadata fetched at runtime in the workflow.
  Store the Workers subdomain as a repository variable (`vars.CF_WORKERS_SUBDOMAIN`) so
  the URL is deterministic and can be posted as a PR comment without an extra API call.

## Gotchas

- Worker names are globally unique per account, not per project. If two workers in your
  monorepo share the same base name, use a project prefix: `pr-412-payments` and
  `pr-412-notifications`.
- `wrangler delete` exits non-zero if the worker doesn't exist. Add `|| true` or
  `--force` in cleanup jobs to avoid failing the workflow on a PR that never got a
  preview (e.g., it was closed before the deploy job ran).
- The `pull_request` event triggers on forks only if the fork owner has been granted
  repository write access or the workflow is allowed to run on forks. Prefer
  `pull_request_target` with explicit `ref` pinning for external contributor PRs, with
  a manual approval requirement to prevent secret exfiltration.

## Verification

```bash
# Confirm the preview worker is live
curl -sf "https://pr-412-payments-worker.myaccount.workers.dev/health"

# List all scripts in the account matching the PR preview pattern
wrangler workers list --json | jq -r '.[].id | select(startswith("pr-"))'

# Verify the preview worker is using the preview KV namespace, not production
wrangler workers list --json | jq '.[] | select(.id=="pr-412-payments-worker")'
```

## Related

- `github-actions-concurrency-cancel-workers-deploy.md`
- `wrangler-environments-staging-production.md`
- `pnpm-workspace-git-worktree-isolation.md`
- `git-worktree-parallel-wrangler-environments.md`
- `feature-flags-2026.md`

## Sources

- Cloudflare Workers environments: https://developers.cloudflare.com/workers/wrangler/environments/
- GitHub Actions pull_request event: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request
- Wrangler delete command: https://developers.cloudflare.com/workers/wrangler/commands/#delete
