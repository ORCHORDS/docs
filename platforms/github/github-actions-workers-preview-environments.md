# GitHub Actions Automated PR Preview Environments with Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A team reviewing a PR for a Cloudflare Worker has no live environment to test against. They
merge changes, wait for the staging deploy, find a bug, and open another PR. The feedback loop
is hours long. The team wants every open PR to automatically deploy to a unique, isolated
Workers URL so reviewers can interact with a live Worker that reflects exactly what is in the
PR branch, with the URL posted as a PR comment.

## Context

Cloudflare Workers preview URLs work by deploying a Worker to a unique subdomain of the
account's `workers.dev` domain (e.g., `pr-42-myworker.myteam.workers.dev`). Wrangler supports
this natively through named environments in `wrangler.toml` and the `--name` flag, which
overrides the Worker name at deploy time.

Preview environments for Workers differ from typical web-app previews (Vercel, Netlify) in
key ways:
- Each preview is a real deployed Worker, not a static hosting preview — it runs real edge code
- KV/D1/R2 bindings must either point at shared preview databases or be stubbed
- Preview Workers accumulate and must be deleted when the PR is closed
- `workers.dev` routes must be enabled (`workers_dev = true`) for the preview URL to work

The strategy uses:
1. A Wrangler `preview` environment in `wrangler.toml` inheriting production bindings but
   with overridable KV/D1 IDs
2. A `pull_request` workflow that deploys on open/sync and posts the URL as a comment
3. A `pull_request` closed workflow that deletes the preview Worker to avoid stale deployments

## Section 1: wrangler.toml Preview Environment Configuration

```toml
# wrangler.toml

name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# Production bindings
[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

[[kv_namespaces]]
binding = "CACHE"
id = "11111111222222223333333344444444"

# Preview environment — overrides name and bindings
[env.preview]
workers_dev = true

[[env.preview.d1_databases]]
binding = "DB"
database_name = "preview-db"       # Shared preview database (all PRs share one D1)
database_id = "ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb"

[[env.preview.kv_namespaces]]
binding = "CACHE"
id = "aaaabbbbccccddddeeeeffffaaaabbbb"   # Shared preview KV namespace

# Staging environment
[env.staging]
workers_dev = true
name = "my-worker-staging"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "staging-db"
database_id = "12345678-1234-1234-1234-123456789012"

[[env.staging.kv_namespaces]]
binding = "CACHE"
id = "12345678123456781234567812345678"
```

The `workers_dev = true` in the preview environment enables the `workers.dev` subdomain, which
Wrangler returns as the deployment URL after a successful deploy.

## Section 2: PR Deploy Workflow with Comment and Environment Tracking

```yaml
# .github/workflows/preview-deploy.yml
name: PR Preview Deploy

on:
  pull_request:
    types: [opened, synchronize, reopened]

# One preview deploy at a time per PR, never cancel a running deploy
concurrency:
  group: preview-${{ github.event.pull_request.number }}
  cancel-in-progress: false

permissions:
  contents: read
  pull-requests: write
  deployments: write

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    environment:
      name: preview-pr-${{ github.event.pull_request.number }}
      url: ${{ steps.deploy.outputs.preview_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Build
        run: pnpm build

      - name: Deploy preview Worker
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          # Deploy with a unique Worker name per PR to avoid collisions
          WORKER_NAME="my-worker-pr-${PR_NUMBER}"

          OUTPUT=$(pnpm wrangler deploy \
            --env preview \
            --name "${WORKER_NAME}" \
            --dispatch-namespace "" \
            2>&1)

          echo "$OUTPUT"

          # Extract the deployed URL from Wrangler output
          PREVIEW_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev' | head -1)

          if [[ -z "$PREVIEW_URL" ]]; then
            echo "::error::Could not extract preview URL from Wrangler output"
            exit 1
          fi

          echo "preview_url=${PREVIEW_URL}" >> "$GITHUB_OUTPUT"
          echo "worker_name=${WORKER_NAME}" >> "$GITHUB_OUTPUT"

          echo "## Preview Deployment" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "Worker: \`${WORKER_NAME}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "URL: ${PREVIEW_URL}" >> "$GITHUB_STEP_SUMMARY"

      - name: Find existing PR comment
        uses: peter-evans/find-comment@v3
        id: find-comment
        with:
          issue-number: ${{ github.event.pull_request.number }}
          comment-author: 'github-actions[bot]'
          body-includes: '<!-- workers-preview-comment -->'

      - name: Create or update PR comment
        uses: peter-evans/create-or-update-comment@v4
        with:
          comment-id: ${{ steps.find-comment.outputs.comment-id }}
          issue-number: ${{ github.event.pull_request.number }}
          edit-mode: replace
          body: |
            <!-- workers-preview-comment -->
            ## Cloudflare Workers Preview

            | | |
            |---|---|
            | **URL** | ${{ steps.deploy.outputs.preview_url }} |
            | **Worker** | `${{ steps.deploy.outputs.worker_name }}` |
            | **Commit** | `${{ github.sha }}` |
            | **Updated** | ${{ github.event.pull_request.updated_at }} |

            > Preview Workers share the `preview` D1 database and KV namespace.
            > Data written to this preview may be visible to other open PRs.

      # Run a smoke test against the preview URL
      - name: Smoke test preview Worker
        env:
          PREVIEW_URL: ${{ steps.deploy.outputs.preview_url }}
        run: |
          # Wait up to 30s for the Worker to be globally available
          MAX=6
          for i in $(seq 1 $MAX); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${PREVIEW_URL}/health")
            if [[ "$STATUS" == "200" ]]; then
              echo "Preview Worker is healthy (HTTP 200)"
              exit 0
            fi
            echo "Attempt ${i}/${MAX}: HTTP ${STATUS} — retrying in 5s..."
            sleep 5
          done
          echo "::warning::Preview Worker did not return 200 within 30s. It may still be propagating."
```

## Section 3: PR Close Workflow — Cleanup Preview Worker

Without cleanup, merged or closed PRs leave Workers deployed forever, consuming the account's
Worker slot limit and potentially serving stale code to anyone who still has the old URL.

```yaml
# .github/workflows/preview-cleanup.yml
name: PR Preview Cleanup

on:
  pull_request:
    types: [closed]

permissions:
  contents: read
  pull-requests: write
  deployments: write

jobs:
  cleanup-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Delete preview Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          WORKER_NAME="my-worker-pr-${PR_NUMBER}"
          echo "Deleting preview Worker: ${WORKER_NAME}"

          # Use the Cloudflare API directly — Wrangler delete is not idempotent
          HTTP_STATUS=$(curl -s -o /tmp/cf_delete_response.json -w "%{http_code}" \
            -X DELETE \
            "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

          cat /tmp/cf_delete_response.json

          if [[ "$HTTP_STATUS" == "200" ]]; then
            echo "Preview Worker deleted successfully."
          elif [[ "$HTTP_STATUS" == "404" ]]; then
            echo "Preview Worker not found — already deleted or was never deployed."
          else
            echo "::error::Failed to delete preview Worker. HTTP status: ${HTTP_STATUS}"
            exit 1
          fi

      # Mark the GitHub Environment as inactive / deleted
      - name: Deactivate GitHub deployment
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          ENV_NAME="preview-pr-${PR_NUMBER}"
          # Get all deployments for this environment
          DEPLOYMENTS=$(gh api \
            "repos/${{ github.repository }}/deployments?environment=${ENV_NAME}" \
            --jq '.[].id')
          for DEPLOY_ID in $DEPLOYMENTS; do
            # Set deployment status to inactive
            gh api -X POST \
              "repos/${{ github.repository }}/deployments/${DEPLOY_ID}/statuses" \
              -f state=inactive \
              -f description="Preview closed"
          done

      - name: Update PR comment on cleanup
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Find the preview comment and mark it as cleaned up
          COMMENT_ID=$(gh api \
            "repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments" \
            --jq '[.[] | select(.body | contains("workers-preview-comment"))] | .[0].id')

          if [[ -n "$COMMENT_ID" && "$COMMENT_ID" != "null" ]]; then
            gh api -X PATCH \
              "repos/${{ github.repository }}/issues/comments/${COMMENT_ID}" \
              -f body="<!-- workers-preview-comment -->
          ## Cloudflare Workers Preview

          ~~This preview has been deleted as the PR was closed.~~

          Worker \`my-worker-pr-${{ github.event.pull_request.number }}\` deleted."
          fi
```

## Anti-patterns

- **Using the same Worker name for all previews** — if two PRs deploy simultaneously with
  `--name my-worker-preview`, the second deploy overwrites the first and both PR authors test
  the same Worker. Always include the PR number in the name.
- **Pointing preview Workers at the production D1 database** — a preview PR that runs a
  migration or writes test data against production is catastrophic. Always use a dedicated
  `preview` D1 database ID in `wrangler.toml`'s `[env.preview]` section.
- **Not cleaning up on PR close** — Cloudflare accounts have a limit on the number of deployed
  Workers (500 on the paid plan). A busy repo with dozens of open PRs exhausts this limit within
  weeks. The cleanup workflow is not optional.
- **Hard-coding the preview URL in tests** — the preview URL changes on every deploy because the
  Worker name includes the PR number. Extract it from Wrangler output as shown, never hard-code.
- **`cancel-in-progress: true` on the concurrency group** — cancelling a running Wrangler
  deploy mid-flight can leave a partial Worker deployed. Set `cancel-in-progress: false` and
  let the current deploy finish; the next push will trigger a new deploy.

## Gotchas

- **Wrangler output format changes between versions** — the regex that extracts the URL from
  Wrangler output (`grep -oP 'https://[^\s]+\.workers\.dev'`) is fragile. Pin Wrangler to a
  specific version in `package.json` and test output parsing when upgrading Wrangler.
- **Preview Workers count against your account's deployed-Worker limit** — 500 Workers on the
  paid plan sounds like a lot until you have a busy monorepo. Enforce cleanup via branch
  protection: require the `preview-cleanup` job to complete before a PR can be re-opened.
- **`workers_dev = false` in the root config disables the preview URL** — if your production
  Worker disables `workers.dev` routing (using only custom domains), you must explicitly set
  `workers_dev = true` in `[env.preview]`.
- **Cold start after deploy** — the Cloudflare edge takes 10–30 seconds to propagate a new
  Worker globally. The smoke test uses a retry loop with 5-second sleeps. Without this, the
  smoke test always fails on the first request to a freshly deployed preview Worker.
- **Secrets are not automatically propagated to preview Workers** — `wrangler secret put` must
  be called separately for each unique preview Worker name. For preview environments, prefer
  environment variables via `[env.preview.vars]` in `wrangler.toml` over Wrangler secrets,
  since secrets require a separate API call per Worker name.

## Verification

```bash
# List all active preview Workers
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  jq '.result[] | select(.id | startswith("my-worker-pr-")) | {id, modified_on}'

# Test a specific preview URL
curl -v "https://my-worker-pr-42.myteam.workers.dev/health"

# Count active preview Workers (should stay below 50 for a healthy cleanup cadence)
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  jq '[.result[] | select(.id | startswith("my-worker-pr-"))] | length'

# Manually delete a specific preview Worker
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-worker-pr-42" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

## Related

- `github-actions-cloudflare-deploy-workflow.md` — base deploy workflow the preview workflow extends
- `github-actions-environments.md` — GitHub Environments used to track preview deployments
- `github-actions-pr-slash-command-dispatch-deploy-preview.md` — slash-command triggered previews
- `github-actions-cloudflare-d1-migration-pipeline.md` — handling D1 migrations for preview DBs
- `github-actions-concurrency.md` — concurrency group patterns that prevent parallel preview deploys
- `github-actions-oidc-cloudflare-deploy.md` — replacing CF_API_TOKEN with OIDC for preview deploys

## Sources

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-environments-for-deployment
- https://github.com/peter-evans/create-or-update-comment
