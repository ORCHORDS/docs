# Cloudflare Pages Preview Environments Per Pull Request

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want every pull request to get its own live preview URL on Cloudflare Pages automatically, with isolated D1/KV data, a GitHub comment posted to the PR with the preview link, and automatic cleanup of preview data when the PR is merged or closed.

## Context

Cloudflare Pages creates a `<branch-name>.<project>.pages.dev` deployment for every Git branch push. The branch name is available inside the Worker as `CF_PAGES_BRANCH`. You can bind environment-specific secrets per deployment context using `wrangler pages secret put --env preview`, and you can post the preview URL to the PR via a GitHub Actions workflow that runs on `pull_request` events. On PR close, a second workflow job deletes preview-only D1 rows and KV keys.

## GitHub Actions — post preview URL as PR comment

```yaml
# .github/workflows/pages-preview.yml
name: Pages Preview

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  comment-preview-url:
    if: github.event.action != 'closed'
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - name: Derive preview URL
        id: preview
        run: |
          BRANCH="${{ github.head_ref }}"
          # Cloudflare slugifies branch names: lowercase, replace non-alphanum with '-'
          SLUG=$(echo "$BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-\|-$//g')
          echo "url=https://${SLUG}.my-pages-project.pages.dev" >> "$GITHUB_OUTPUT"

      - name: Post preview URL comment
        uses: actions/github-script@v7
        with:
          script: |
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });
            const marker = '<!-- pages-preview-bot -->';
            const body = `${marker}\n### Cloudflare Pages Preview\n🔗 ${{ steps.preview.outputs.url }}\n\nDeployed from branch \`${{ github.head_ref }}\``;
            const existing = comments.find(c => c.body?.includes(marker));
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
                issue_number: context.issue.number,
                body,
              });
            }

  cleanup-preview-data:
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - run: npm ci

      - name: Delete preview D1 rows
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          BRANCH: ${{ github.head_ref }}
        run: |
          npx wrangler d1 execute my-db-preview \
            --command "DELETE FROM sessions WHERE branch = '${BRANCH}'" \
            --env preview

      - name: Delete preview KV keys
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          BRANCH: ${{ github.head_ref }}
        run: |
          # List and bulk-delete keys prefixed with the branch name
          npx tsx scripts/cleanup-kv.ts "$BRANCH"
```

## KV cleanup script

```typescript
// scripts/cleanup-kv.ts
import { execSync } from 'node:child_process';

const branch = process.argv[2];
if (!branch) { console.error('Usage: cleanup-kv.ts <branch>'); process.exit(1); }

const KV_NAMESPACE_ID = process.env.KV_NAMESPACE_ID!;
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

async function listKeys(cursor?: string): Promise<{ keys: { name: string }[]; cursor?: string; complete: boolean }> {
  const params = new URLSearchParams({ prefix: `preview:${branch}:`, limit: '1000' });
  if (cursor) params.set('cursor', cursor);
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/keys?${params}`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  const data = await res.json() as any;
  return { keys: data.result, cursor: data.result_info?.cursor, complete: data.result_info?.count < 1000 };
}

async function deleteKeys(keys: string[]): Promise<void> {
  if (keys.length === 0) return;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/bulk/delete`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(keys),
    }
  );
  if (!res.ok) throw new Error(`Delete failed: ${await res.text()}`);
}

(async () => {
  let cursor: string | undefined;
  let total = 0;
  do {
    const { keys, cursor: next, complete } = await listKeys(cursor);
    await deleteKeys(keys.map(k => k.name));
    total += keys.length;
    cursor = complete ? undefined : next;
  } while (cursor);
  console.log(`Deleted ${total} KV keys for branch ${branch}`);
})().catch(err => { console.error(err); process.exit(1); });
```

## Worker — reading CF_PAGES_BRANCH for per-preview config

```typescript
// functions/_middleware.ts  (Pages Functions middleware)
export async function onRequest({ request, env, next }: EventContext<Env, string, unknown>): Promise<Response> {
  const branch = env.CF_PAGES_BRANCH ?? 'unknown';
  const response = await next();
  const headers = new Headers(response.headers);
  headers.set('X-Preview-Branch', branch);
  return new Response(response.body, { status: response.status, headers });
}

export interface Env {
  CF_PAGES_BRANCH: string;
  DB: D1Database;
  CACHE: KVNamespace;
}
```

## Setting preview-specific secrets

```bash
# Set a secret scoped to the preview deployment context
wrangler pages secret put DATABASE_URL --project-name my-pages-project --env preview
# Prompts for value interactively

# Or non-interactively via stdin
echo "$PREVIEW_DB_URL" | wrangler pages secret put DATABASE_URL \
  --project-name my-pages-project --env preview
```

## Anti-patterns

- **Sharing the production D1 database with preview deployments** — a preview migration or test that truncates a table will corrupt production data.
- **Hardcoding the preview URL format** — Cloudflare slugifies branch names differently than a naive `toLowerCase()`; always replicate the slug algorithm.
- **Not cleaning up preview data** — over time preview KV keys and D1 rows accumulate and may exceed namespace limits.
- **Using `CF_PAGES_BRANCH` as an auth mechanism** — it is not secret; use a proper secret token for any privileged preview endpoint.

## Gotchas

- Branch names with `/` (e.g. `feature/new-ui`) are slugified to `feature-new-ui` by Pages. The slug algorithm: lowercase, replace all non-alphanumeric characters with `-`, collapse consecutive `-`, strip leading/trailing `-`.
- `wrangler pages secret put` scopes secrets to `production` or `preview` — not to individual branches. Per-branch secrets require the Pages API directly.
- The `closed` event fires for both merged and manually closed PRs; the cleanup job runs in both cases.
- Pages Functions `env.CF_PAGES_BRANCH` is always available in Functions, but not available in a standalone Worker that is bound as a service binding.

## Verification

```bash
# Check that the preview URL is live
curl -si https://my-feature-branch.my-pages-project.pages.dev/ | head -5

# Confirm branch header is set
curl -si https://my-feature-branch.my-pages-project.pages.dev/ | grep X-Preview-Branch

# List Pages deployments for the project
wrangler pages deployment list --project-name my-pages-project
```

## Related

- `wrangler-environments-staging-prod-promotion.md`
- `workers-blue-green-deploy-traffic-split-kv.md`
- `workers-deployment-annotations-version-tags.md`

## Sources

- Cloudflare Pages preview deployments: https://developers.cloudflare.com/pages/configuration/preview-deployments/
- Pages Functions: https://developers.cloudflare.com/pages/functions/
- Wrangler Pages secrets: https://developers.cloudflare.com/pages/functions/bindings/#secrets
