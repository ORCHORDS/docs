# Posting Workers Preview URLs as PR Comments from GitHub Actions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
When a pull request triggers a Cloudflare Workers deployment, developers need immediate visibility into the preview URL without navigating to the Cloudflare dashboard. Manually tracking these URLs wastes time and breaks the review flow. Automating PR comments that post — and update — the Workers preview URL on each push keeps every reviewer in sync.

---

## Context
Cloudflare Workers deployments via `wrangler deploy` emit a preview URL to stdout when the `--dry-run` flag is omitted and environments are configured with custom domains or workers.dev routes. GitHub Actions can capture that output, extract the URL with a shell regex, and call the GitHub REST API to upsert a PR comment using a stored comment ID. Updating an existing comment (rather than creating a new one) keeps the PR timeline clean across multiple pushes. The comment ID is preserved between steps using `$GITHUB_OUTPUT` and can survive re-runs by caching it in a repository variable or a dedicated label.

---

## Section 1 — GitHub Actions Workflow
```yaml
name: Deploy Workers Preview

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Deploy to Workers (preview)
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler deploy --env preview 2>&1)
          echo "$OUTPUT"
          PREVIEW_URL=$(echo "$OUTPUT" | grep -oP 'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev' | head -1)
          echo "preview_url=$PREVIEW_URL" >> $GITHUB_OUTPUT

      - name: Find existing PR comment
        id: find-comment
        uses: peter-evans/find-comment@v3
        with:
          issue-number: ${{ github.event.pull_request.number }}
          comment-author: 'github-actions[bot]'
          body-includes: '<!-- workers-preview-url -->'

      - name: Create or update PR comment
        uses: peter-evans/create-or-update-comment@v4
        with:
          comment-id: ${{ steps.find-comment.outputs.comment-id }}
          issue-number: ${{ github.event.pull_request.number }}
          body: |
            <!-- workers-preview-url -->
            ## Cloudflare Workers Preview

            | Status | URL |
            |--------|-----|
            | Deployed | ${{ steps.deploy.outputs.preview_url }} |

            _Last updated: ${{ github.sha }}_
          edit-mode: replace
```

## Section 2 — Custom Comment Upsert Script (no third-party actions)
```typescript
// scripts/upsert-pr-comment.ts
// Run via: npx tsx scripts/upsert-pr-comment.ts

const GITHUB_TOKEN = process.env.GITHUB_TOKEN!;
const REPO = process.env.GITHUB_REPOSITORY!; // owner/repo
const PR_NUMBER = process.env.PR_NUMBER!;
const PREVIEW_URL = process.env.PREVIEW_URL!;
const MARKER = '<!-- workers-preview-url -->';

const [owner, repo] = REPO.split('/');
const headers = {
  Authorization: `Bearer ${GITHUB_TOKEN}`,
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  'Content-Type': 'application/json',
};

async function listComments(): Promise<{ id: number; body: string }[]> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${PR_NUMBER}/comments?per_page=100`,
    { headers }
  );
  if (!res.ok) throw new Error(`List comments failed: ${res.status}`);
  return res.json();
}

async function createComment(body: string): Promise<number> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${PR_NUMBER}/comments`,
    { method: 'POST', headers, body: JSON.stringify({ body }) }
  );
  if (!res.ok) throw new Error(`Create comment failed: ${res.status}`);
  const data = await res.json();
  return data.id;
}

async function updateComment(id: number, body: string): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/comments/${id}`,
    { method: 'PATCH', headers, body: JSON.stringify({ body }) }
  );
  if (!res.ok) throw new Error(`Update comment failed: ${res.status}`);
}

async function run() {
  const commentBody = [
    MARKER,
    '## Cloudflare Workers Preview',
    '',
    `**Preview URL:** ${PREVIEW_URL}`,
    '',
    `_Commit: ${process.env.GITHUB_SHA}_`,
  ].join('\n');

  const comments = await listComments();
  const existing = comments.find((c) => c.body.includes(MARKER));

  if (existing) {
    await updateComment(existing.id, commentBody);
    console.log(`Updated comment ${existing.id}`);
  } else {
    const id = await createComment(commentBody);
    console.log(`Created comment ${id}`);
  }
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

## Section 3 — Extracting the Preview URL from Wrangler Output
```bash
#!/usr/bin/env bash
# extract-preview-url.sh
# Captures wrangler deploy stdout and extracts the preview URL.
set -euo pipefail

DEPLOY_LOG=$(mktemp)
npx wrangler deploy --env preview 2>&1 | tee "$DEPLOY_LOG"

# workers.dev pattern
PREVIEW_URL=$(grep -oP 'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev' "$DEPLOY_LOG" | head -1 || true)

# Custom domain fallback
if [[ -z "$PREVIEW_URL" ]]; then
  PREVIEW_URL=$(grep -oP 'https://[^\s]+' "$DEPLOY_LOG" | grep 'Deployed' | head -1 || true)
fi

if [[ -z "$PREVIEW_URL" ]]; then
  echo "ERROR: Could not extract preview URL from wrangler output" >&2
  exit 1
fi

echo "preview_url=$PREVIEW_URL" >> "${GITHUB_OUTPUT:-/dev/null}"
echo "Extracted: $PREVIEW_URL"
```

---

## Anti-patterns
- **Creating a new comment on every push** — Without the find-comment + update pattern, each push appends a new comment, polluting the PR timeline with stale URLs.
- **Hardcoding the comment ID in workflow** — Comment IDs must be discovered dynamically; hardcoded IDs break across PRs and repositories.
- **Using `--dry-run` with wrangler** — `--dry-run` skips the actual deployment and never emits a real preview URL, making the output useless for this workflow.
- **Storing secrets in `$GITHUB_OUTPUT`** — Only store the preview URL in output, never the API token or account ID.

---

## Gotchas
- The `pull-requests: write` permission is required at the job level for the GitHub token to post comments.
- `wrangler deploy` output format can differ between wrangler v2 and v3; test the regex against your wrangler version.
- The `peter-evans/find-comment` action searches only the first 100 comments by default; add pagination for very active PRs.
- If the preview environment has a custom domain, the URL pattern may not match `*.workers.dev`; extend the grep pattern accordingly.
- GitHub Actions does not persist `$GITHUB_OUTPUT` between workflow runs; for multi-run caching, store the comment ID as a repository variable using the GitHub API.

---

## Verification
```bash
# Test URL extraction locally against a captured wrangler log
echo 'Deployed https://my-worker.my-account.workers.dev' | \
  grep -oP 'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev'

# Verify the PR comment was created/updated
curl -s \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OWNER/REPO/issues/PR_NUMBER/comments" | \
  jq '[.[] | select(.body | contains("workers-preview-url"))] | length'

# Check wrangler deploy output for URL patterns (v3)
npx wrangler deploy --env preview --dry-run 2>&1 | grep -i 'deploy'
```

---

## Related
- `github-deployment-status-workers-cloudflare.md`
- `github-app-webhook-workers-installation.md`

---

## Sources
- GitHub REST API — Issues Comments — https://docs.github.com/en/rest/issues/comments
- Wrangler CLI deploy — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- peter-evans/create-or-update-comment — https://github.com/peter-evans/create-or-update-comment
- GitHub Actions permissions — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token
