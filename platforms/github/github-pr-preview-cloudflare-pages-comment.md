# Posting Cloudflare Pages Preview URLs as GitHub PR Comments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your CI deploys a preview to Cloudflare Pages for every pull request, but the deployment URL is buried in job logs. Reviewers must open the Actions UI, scan through output, and manually copy a URL before they can test the preview. You want the preview URL posted directly as a PR comment with a visual badge, updated automatically on re-deploy, and cleaned up when the PR closes.

---

## Context

Cloudflare Pages deployments produce a unique preview URL of the form `https://<hash>.my-project.pages.dev` on every push. The `wrangler pages deploy` command prints this URL to stdout in its final lines. A GitHub Actions workflow can capture that output, parse the URL with `grep` or `jq`, then use the `gh` CLI to post or update a PR comment. The `gh pr comment --edit-last` flag updates the existing comment in place on re-deploy, so reviewers always see the latest URL without a growing thread of stale links. On PR close a separate cleanup job calls `wrangler pages deployment delete` to remove the preview and reclaim the slot.

---

## Section 1 — GitHub Actions workflow

```yaml
# .github/workflows/pages-preview.yml
name: Pages Preview

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

permissions:
  contents: read
  pull-requests: write   # needed to post / edit PR comments

jobs:
  deploy-preview:
    if: github.event.action != 'closed'
    runs-on: ubuntu-latest
    outputs:
      preview_url: ${{ steps.deploy.outputs.preview_url }}
      deployment_id: ${{ steps.deploy.outputs.deployment_id }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Build
        run: npm run build

      - name: Deploy to Cloudflare Pages
        id: deploy
        run: |
          # Capture the full wrangler output
          DEPLOY_OUTPUT=$(npx wrangler pages deploy ./dist \
            --project-name my-pages-project \
            --branch "pr-${{ github.event.pull_request.number }}" \
            2>&1)

          echo "$DEPLOY_OUTPUT"

          # Extract preview URL — wrangler prints it as the last URL on stdout
          PREVIEW_URL=$(echo "$DEPLOY_OUTPUT" | grep -oP 'https://[a-z0-9-]+\.my-pages-project\.pages\.dev' | tail -1)

          # Extract the deployment ID for cleanup later
          DEPLOYMENT_ID=$(echo "$DEPLOY_OUTPUT" | grep -oP '(?<=deployment id: )[a-f0-9-]+'  | head -1)

          if [ -z "$PREVIEW_URL" ]; then
            echo "ERROR: Could not extract preview URL from wrangler output"
            exit 1
          fi

          echo "preview_url=$PREVIEW_URL" >> "$GITHUB_OUTPUT"
          echo "deployment_id=$DEPLOYMENT_ID" >> "$GITHUB_OUTPUT"
          echo "Preview URL: $PREVIEW_URL"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Post or update PR comment
        run: |
          PREVIEW_URL="${{ steps.deploy.outputs.preview_url }}"
          PR_NUMBER="${{ github.event.pull_request.number }}"
          SHORT_SHA="$(echo ${{ github.sha }} | cut -c1-7)"

          BODY=$(cat <<EOF
          ## 🚀 Preview Deployment

          | | |
          |---|---|
          | **Preview URL** | $PREVIEW_URL |
          | **Commit** | \`$SHORT_SHA\` |
          | **Branch** | \`${{ github.head_ref }}\` |
          | **Status** | ✅ Ready |

          > Updated at $(date -u '+%Y-%m-%d %H:%M UTC')
          EOF
          )

          # --edit-last updates the most recent comment from this workflow;
          # if no prior comment exists, it creates a new one.
          gh pr comment "$PR_NUMBER" \
            --body "$BODY" \
            --edit-last \
            || gh pr comment "$PR_NUMBER" --body "$BODY"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  cleanup-preview:
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Find and delete preview deployments for this PR branch
        run: |
          BRANCH="pr-${{ github.event.pull_request.number }}"

          # List all deployments for this branch
          DEPLOYMENT_IDS=$(npx wrangler pages deployment list \
            --project-name my-pages-project \
            --branch "$BRANCH" \
            --json 2>/dev/null | jq -r '.[].id' || echo "")

          if [ -z "$DEPLOYMENT_IDS" ]; then
            echo "No deployments found for branch $BRANCH"
            exit 0
          fi

          for ID in $DEPLOYMENT_IDS; do
            echo "Deleting deployment $ID"
            npx wrangler pages deployment delete \
              --project-name my-pages-project \
              "$ID" --yes || echo "Skipped $ID"
          done
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Post cleanup comment
        run: |
          gh pr comment "${{ github.event.pull_request.number }}" \
            --body "Preview deployment cleaned up after PR close. 🧹" \
            --edit-last \
            || true
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Section 2 — Parsing the wrangler output reliably (bash helper)

```bash
#!/usr/bin/env bash
# scripts/extract-pages-url.sh
# Usage: wrangler pages deploy ./dist ... 2>&1 | bash scripts/extract-pages-url.sh
#
# Wrangler prints lines like:
#   ✨ Deployment complete! Take a peek over at https://abc123.my-project.pages.dev
# or:
#   Success! Your site is now live at https://abc123.my-project.pages.dev

set -euo pipefail

PROJECT_NAME="${PAGES_PROJECT_NAME:-my-pages-project}"

PREVIEW_URL=""

while IFS= read -r line; do
  echo "$line"  # pass through to stdout so logs are still visible

  # Try the canonical wrangler success line first
  if url=$(echo "$line" | grep -oP "https://[a-z0-9-]+\.${PROJECT_NAME}\.pages\.dev"); then
    PREVIEW_URL="$url"
  fi
done

if [ -z "$PREVIEW_URL" ]; then
  echo "extract-pages-url.sh: ERROR — no preview URL found in wrangler output" >&2
  exit 1
fi

echo "PREVIEW_URL=$PREVIEW_URL" >> "${GITHUB_OUTPUT:-/dev/null}"
echo "Extracted preview URL: $PREVIEW_URL" >&2
```

Call it from the workflow:

```yaml
- name: Deploy and extract URL
  run: |
    PAGES_PROJECT_NAME=my-pages-project \
    npx wrangler pages deploy ./dist \
      --project-name my-pages-project \
      --branch "pr-${{ github.event.pull_request.number }}" \
      2>&1 | bash scripts/extract-pages-url.sh
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Section 3 — Verification / Testing

```bash
# Open a test PR and confirm the comment appears
gh pr create --title "test: preview comment" --body "testing preview URL comment" --draft

# Watch the workflow run
gh run watch $(gh run list --workflow pages-preview.yml --limit 1 --json databaseId -q '.[0].databaseId')

# List comments on the PR to confirm the preview URL is there
PR_NUM=$(gh pr list --head $(git branch --show-current) --json number -q '.[0].number')
gh pr view $PR_NUM --json comments | jq '.comments[-1].body'

# Simulate a re-deploy by pushing another commit and confirm --edit-last works
git commit --allow-empty -m "trigger re-deploy" && git push
gh run watch $(gh run list --workflow pages-preview.yml --limit 1 --json databaseId -q '.[0].databaseId')

# Verify only one comment exists (not two)
gh pr view $PR_NUM --json comments | jq '.comments | length'

# Close the PR and confirm cleanup
gh pr close $PR_NUM
gh run watch $(gh run list --workflow pages-preview.yml --limit 1 --json databaseId -q '.[0].databaseId')
npx wrangler pages deployment list \
  --project-name my-pages-project \
  --branch "pr-$PR_NUM" \
  --json | jq 'length'
# Expected: 0
```

---

## Anti-patterns

- **Hardcoding the preview URL pattern** — `grep -oP 'https://[a-z0-9-]+\.my-pages-project\.pages\.dev'` breaks if Cloudflare changes the subdomain format. Prefer parsing the `--json` flag on `wrangler pages deployment list` after deploy.
- **Always creating a new comment** — Using `gh pr comment` without `--edit-last` adds a new comment on every push, flooding the PR thread. Always attempt `--edit-last` first.
- **Skipping cleanup on PR close** — Stale preview deployments consume your Cloudflare Pages deployment quota (500 per project on the free plan). Always delete previews when the PR closes.
- **`pull_request` event with `secrets.GITHUB_TOKEN` lacking write** — The default token for PRs from forks has read-only pull-requests permission. The `permissions: pull-requests: write` block at the job or workflow level is required for comment operations.

---

## Gotchas

- `gh pr comment --edit-last` edits the most recent comment made by the authenticated actor (the `GITHUB_TOKEN` bot), not the most recent comment in the thread. If another step posts a comment between deploys, `--edit-last` may edit the wrong comment — add a sentinel string like `<!-- pages-preview -->` to the comment body and use the GitHub API search instead.
- Wrangler's stdout and stderr are mixed; always redirect both streams (`2>&1`) when capturing deploy output, or the URL printed to stderr will be lost.
- `wrangler pages deployment delete` requires the deployment ID, not the URL. Capture and store the ID in `$GITHUB_OUTPUT` during the deploy step for reliable cleanup.
- Preview deployments on `main` branch in Cloudflare Pages are treated as production deployments and cannot be deleted via the API; only branch-named previews (e.g. `pr-42`) are eligible for programmatic deletion.

---

## Verification

```bash
# Confirm the Pages project exists and has the correct branch set up
npx wrangler pages project list

# Check current deployment count against the quota
npx wrangler pages deployment list \
  --project-name my-pages-project \
  --json | jq 'length'

# Manually verify a preview URL is reachable
PREVIEW=$(npx wrangler pages deployment list \
  --project-name my-pages-project --json | jq -r '.[0].url')
curl --fail --silent "$PREVIEW" | head -c 200
```

---

## Related

- `github-environments-cloudflare-workers-secrets.md`
- `github-dependabot-workers-package-updates.md`

---

## Sources

- Cloudflare Pages Wrangler deploy — https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- GitHub CLI pr comment — https://cli.github.com/manual/gh_pr_comment
- Cloudflare Pages deployment limits — https://developers.cloudflare.com/pages/platform/limits/
- wrangler pages deployment delete — https://developers.cloudflare.com/workers/wrangler/commands/#deployment-delete
