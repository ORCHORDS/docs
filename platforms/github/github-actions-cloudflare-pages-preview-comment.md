# GitHub Actions: Post Cloudflare Pages Preview URL as PR Comment

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
After a Cloudflare Pages preview deployment succeeds, reviewers must manually hunt for the preview URL in the Actions log.
This article shows how to capture the deployment URL and post it as a sticky PR comment automatically.

## Context
Cloudflare Pages assigns a unique subdomain for every branch/PR deployment (e.g. `pr-42.<project>.pages.dev`).
Wrangler's `pages deploy` command emits the URL to stdout, which can be captured in GitHub Actions via an output variable.
The `gh` CLI or the `octokit` REST API can then upsert a "bot comment" so the link stays at the top of the PR without duplicating on every push.

---

## Capture the Deployment URL from Wrangler

```yaml
# .github/workflows/pages-preview.yml
name: Pages Preview

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write   # required to post comments

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    outputs:
      preview_url: ${{ steps.deploy.outputs.preview_url }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Build
        run: npm run build

      - name: Deploy to Cloudflare Pages (preview)
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler pages deploy ./dist \
            --project-name my-pages-project \
            --branch "${{ github.head_ref }}" \
            2>&1)
          echo "$OUTPUT"
          # Wrangler prints: "Deployment complete! Take a peek over at <URL>"
          URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.pages\.dev[^\s]*' | tail -1)
          echo "preview_url=$URL" >> "$GITHUB_OUTPUT"
```

---

## Upsert the Preview Comment

Upserting (find-and-replace) avoids a flood of comments on repeated pushes:

```yaml
  comment-preview-url:
    runs-on: ubuntu-latest
    needs: deploy-preview
    if: needs.deploy-preview.outputs.preview_url != ''

    steps:
      - name: Find existing bot comment
        id: find_comment
        uses: peter-evans/find-comment@v3
        with:
          issue-number: ${{ github.event.pull_request.number }}
          comment-author: 'github-actions[bot]'
          body-includes: '<!-- pages-preview-comment -->'

      - name: Create or update comment
        uses: peter-evans/create-or-update-comment@v4
        with:
          comment-id: ${{ steps.find_comment.outputs.comment-id }}
          issue-number: ${{ github.event.pull_request.number }}
          edit-mode: replace
          body: |
            <!-- pages-preview-comment -->
            ### Cloudflare Pages Preview

            | Field | Value |
            |-------|-------|
            | Branch | `${{ github.head_ref }}` |
            | Commit | `${{ github.sha }}` |
            | Preview URL | ${{ needs.deploy-preview.outputs.preview_url }} |

            _Updated: ${{ github.event.pull_request.updated_at }}_
```

---

## Pure octokit Alternative (no third-party action)

Use `actions/github-script` to avoid third-party action dependencies:

```yaml
      - name: Upsert preview comment (octokit)
        uses: actions/github-script@v7
        env:
          PREVIEW_URL: ${{ needs.deploy-preview.outputs.preview_url }}
        with:
          script: |
            const MARKER = '<!-- pages-preview-comment -->';
            const body = `${MARKER}\n### CF Pages Preview\n🔗 ${process.env.PREVIEW_URL}\nCommit: \`${context.sha.slice(0,7)}\``;

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });

            const existing = comments.find(c => c.body?.includes(MARKER));

            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
              core.info(`Updated comment ${existing.id}`);
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body,
              });
              core.info('Created new preview comment');
            }
```

---

## Anti-patterns
- Posting a new comment on every push — creates noise and buries the URL in the PR timeline.
- Parsing the URL with a fragile regex that breaks when Wrangler changes its output format — pin `wrangler` in `package.json` or use `>=3.x` range with snapshot tests of the output.
- Using `GITHUB_TOKEN` with only `contents: read` — comment creation requires `pull-requests: write`.
- Storing the CF API token as a plain env var in the workflow file rather than a repository secret.

## Gotchas
- `--branch` must be URL-safe; replace `/` with `-` for branch names like `feature/foo`.
- Wrangler may emit the URL on stderr; redirect and capture both streams (`2>&1`).
- `peter-evans/find-comment` matches by comment author `github-actions[bot]` only when the workflow uses `GITHUB_TOKEN`; custom apps have a different author slug.
- The `pull-requests: write` permission is at job level and does NOT inherit from the `workflow_dispatch` event — add it explicitly.
- Pages deployments triggered from forks use a read-only `GITHUB_TOKEN` that cannot post comments; gate the comment job with `if: github.event.pull_request.head.repo.full_name == github.repository`.

## Verification
```bash
# Confirm the deployment exists via Cloudflare API
curl -s -H "Authorization: Bearer $CF_PAGES_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/my-pages-project/deployments" \
  | jq '.result[0] | {id, url, latest_stage}'

# List PR comments via gh CLI
gh pr view 42 --comments --json comments \
  | jq '.comments[] | select(.body | contains("pages-preview-comment")) | .body'
```

## Related
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-workers-preview-environments.md`
- `github-actions-pr-comment-bot.md`
- `github-actions-environment-protection.md`

## Sources
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- https://github.com/peter-evans/create-or-update-comment
- https://docs.github.com/en/rest/issues/comments
- https://developers.cloudflare.com/workers/wrangler/commands/#pages
