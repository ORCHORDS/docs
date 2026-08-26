# Automated Preview Deployments for Cloudflare Pages on Pull Requests

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want every pull request to automatically publish a shareable preview URL on Cloudflare Pages so reviewers can test changes in a production-like environment without merging first. Preview deployments should be created on PR open/sync, have their URL posted as a PR comment, and be cleaned up when the PR is closed or merged.

---

## Context

Cloudflare Pages supports named branch deployments: any `wrangler pages deploy` call with `--branch=<name>` publishes to a deterministic preview URL of the form `<branch>.<project>.pages.dev`. Naming the branch `pr-<number>` gives a stable URL per PR that does not change across pushes. GitHub Actions orchestrates the workflow: a `pull_request` trigger builds the project, deploys the preview, and upserts a PR comment containing the URL. A separate workflow on `pull_request` with `types: [closed]` deletes the preview deployment via the Cloudflare API to keep the account tidy. Per-branch environment variables are injected at deploy time using `--binding` flags so each preview can point to a staging API or test database.

---

## Section 1 — Config / wrangler.toml

```toml
# wrangler.toml (Pages project)
name = "my-pages-app"
pages_build_output_dir = "dist"
compatibility_date = "2026-08-01"

[env.preview]
vars = { ENVIRONMENT = "preview", API_BASE_URL = "https://api-staging.example.com" }

[env.production]
vars = { ENVIRONMENT = "production", API_BASE_URL = "https://api.example.com" }
```

---

## Section 2 — Implementation / Deploy Script

```bash
#!/usr/bin/env bash
# scripts/deploy-preview.sh
set -euo pipefail

PR_NUMBER="${PR_NUMBER:?}"
PROJECT_NAME="${CF_PAGES_PROJECT:?}"
ACCOUNT_ID="${CF_ACCOUNT_ID:?}"
BRANCH="pr-${PR_NUMBER}"

echo "Building project..."
npm run build

echo "Deploying to branch: $BRANCH"
DEPLOY_OUTPUT=$(wrangler pages deploy dist/ \
  --project-name="$PROJECT_NAME" \
  --branch="$BRANCH" \
  --commit-message="PR #${PR_NUMBER}" 2>&1)

echo "$DEPLOY_OUTPUT"

# Extract preview URL from wrangler output
PREVIEW_URL=$(echo "$DEPLOY_OUTPUT" | grep -Eo 'https://[a-zA-Z0-9._-]+\.pages\.dev' | tail -1)

if [[ -z "$PREVIEW_URL" ]]; then
  # Fallback: construct URL from branch name
  SAFE_BRANCH=$(echo "$BRANCH" | tr '/' '-' | tr '[:upper:]' '[:lower:]')
  PREVIEW_URL="https://${SAFE_BRANCH}.${PROJECT_NAME}.pages.dev"
fi

echo "preview_url=$PREVIEW_URL" >> "${GITHUB_OUTPUT:-/dev/stdout}"
echo "Preview URL: $PREVIEW_URL"
```

```javascript
// scripts/upsert-pr-comment.mjs  (Node 20+)
// Upserts a single "Pages Preview" comment per PR to avoid spam.
import { Octokit } from "@octokit/rest";

const [
  ,
  ,
  owner,
  repo,
  prNumber,
  previewUrl,
] = process.argv;

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
const MARKER = "<!-- cf-pages-preview -->";

const body = `${MARKER}
### Cloudflare Pages Preview

| | |
|---|---|
| **URL** | ${previewUrl} |
| **Branch** | \`pr-${prNumber}\` |
| **Updated** | ${new Date().toUTCString()} |

_Preview deploys automatically on every push to this PR._`;

const { data: comments } = await octokit.issues.listComments({
  owner,
  repo,
  issue_number: Number(prNumber),
});

const existing = comments.find((c) => c.body?.includes(MARKER));

if (existing) {
  await octokit.issues.updateComment({
    owner,
    repo,
    comment_id: existing.id,
    body,
  });
  console.log(`Updated comment ${existing.id}`);
} else {
  const { data } = await octokit.issues.createComment({
    owner,
    repo,
    issue_number: Number(prNumber),
    body,
  });
  console.log(`Created comment ${data.id}`);
}
```

---

## Section 3 — CI / Automation

```yaml
# .github/workflows/preview-deploy.yml
name: Preview Deploy

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write
  contents: read

jobs:
  preview:
    runs-on: ubuntu-latest
    environment: preview
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      CF_PAGES_PROJECT: my-pages-app
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Deploy preview
        id: deploy
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: bash scripts/deploy-preview.sh

      - name: Post / update PR comment
        run: |
          node scripts/upsert-pr-comment.mjs \
            ${{ github.repository_owner }} \
            ${{ github.event.repository.name }} \
            ${{ github.event.pull_request.number }} \
            "${{ steps.deploy.outputs.preview_url }}"

---
# .github/workflows/preview-cleanup.yml
name: Preview Cleanup

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      CF_PAGES_PROJECT: my-pages-app

    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Delete preview deployment
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          BRANCH="pr-${PR_NUMBER}"

          # List deployments for the branch and delete each one
          DEPLOYMENTS=$(curl -s \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${CF_PAGES_PROJECT}/deployments?env=preview" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            | jq -r --arg branch "$BRANCH" '.result[] | select(.deployment_trigger.metadata.branch==$branch) | .id')

          for DEP_ID in $DEPLOYMENTS; do
            echo "Deleting deployment: $DEP_ID"
            curl -s -X DELETE \
              "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${CF_PAGES_PROJECT}/deployments/${DEP_ID}?force=true" \
              -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
              | jq '.success'
          done
          echo "Cleanup complete for branch $BRANCH"
```

---

## Anti-patterns

- **Using `--branch=${{ github.head_ref }}`** — feature branch names may contain slashes or uppercase letters that produce invalid Pages URLs; always sanitise or use `pr-<number>` instead.
- **Creating a new comment on every push** — spams the PR thread; use the marker-based upsert approach to keep a single comment updated.
- **Granting `CF_API_TOKEN` write access to production** — preview workflows only need `Account:Cloudflare Pages:Edit`; scope the token narrowly.
- **Skipping cleanup on PR close** — stale preview deployments count toward account limits and expose old code publicly; always run the cleanup workflow.

---

## Gotchas

- Cloudflare Pages free plan limits preview deployments per project; check the account dashboard before relying on this pattern at scale.
- The `wrangler pages deploy` command exits 0 even when the upload succeeds but the build fails on the Pages side; always parse the output URL and HTTP-check it before posting the comment.
- `@octokit/rest` must be added to `package.json` devDependencies or installed ad-hoc in CI; pin the version to avoid breaking changes.
- Branch names in Pages are lowercased and have special characters replaced with hyphens; the fallback URL construction in `deploy-preview.sh` must match that normalisation.
- The cleanup API call requires `?force=true` to delete deployments that are the "active" deployment on the branch.

---

## Verification

```bash
# Manually trigger a preview deploy for PR #<number>
PR_NUMBER=42 CF_ACCOUNT_ID=<id> CF_PAGES_PROJECT=my-pages-app bash scripts/deploy-preview.sh

# List all preview deployments for the project
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/my-pages-app/deployments" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '[.result[] | {id, branch: .deployment_trigger.metadata.branch, url: .url}]'

# Check preview URL responds
curl -I https://pr-42.my-pages-app.pages.dev

# Delete a specific preview deployment
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/my-pages-app/deployments/<dep-id>?force=true" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq .success
```

---

## Related

- `workers-deployment-smoke-test-health-check.md`
- `workers-rollback-wrangler-versions.md`

---

## Sources

- Cloudflare Pages Wrangler deploy — https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- Cloudflare Pages REST API — https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/
- GitHub Actions pull_request event — https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request
