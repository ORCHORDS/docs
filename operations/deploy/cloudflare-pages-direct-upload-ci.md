# Uploading Pages Assets Directly via the Cloudflare API (No Git Integration)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your build system produces a compiled asset directory that must be uploaded to Cloudflare Pages without relying on Git integration — for example when the build runs on ephemeral agents, when the source repository is private with no Cloudflare access, or when you need deterministic deployment aliases for preview environments. Direct upload via `wrangler pages deploy` gives full CI control over what is pushed and when.

---

## Context

Cloudflare Pages Direct Upload decouples the deploy trigger from Git events. Instead of connecting a repository in the Pages dashboard, you run `wrangler pages deploy <dir>` from any environment that holds a valid `CLOUDFLARE_API_TOKEN`. Each invocation creates a new deployment with a unique preview URL; you can pin a custom alias to a deployment and roll back to any previous one with a single CLI command. The underlying mechanism uses the Pages Upload API, which accepts multipart asset bundles chunked by the `@cloudflare/pages-shared` library — useful if you need programmatic control over which files are included. Aliases (branch preview URLs, custom preview domains) are managed via `wrangler pages deployment alias` commands and are distinct from the production URL assigned to the project.

---

## Section 1 — GitHub Actions Workflow for Direct Upload

```yaml
# .github/workflows/pages-direct-upload.yml
name: Pages Direct Upload

on:
  push:
    branches: [main, 'preview/**']
  pull_request:
    types: [opened, synchronize]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  PAGES_PROJECT: my-pages-app

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - run: npm ci
      - run: npm run build   # produces ./dist

      - name: Determine branch name
        id: branch
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            BRANCH="pr-${{ github.event.pull_request.number }}"
          else
            BRANCH="${GITHUB_REF_NAME//\//-}"
          fi
          echo "name=$BRANCH" >> $GITHUB_OUTPUT

      - name: Deploy to Pages
        id: deploy
        run: |
          OUTPUT=$(npx wrangler pages deploy ./dist \
            --project-name "$PAGES_PROJECT" \
            --branch "${{ steps.branch.outputs.name }}" \
            --commit-hash "${{ github.sha }}" \
            --commit-message "${{ github.event.head_commit.message || 'PR deploy' }}" \
            2>&1)
          echo "$OUTPUT"
          DEPLOY_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+'| tail -1)
          echo "url=$DEPLOY_URL" >> $GITHUB_OUTPUT

      - name: Comment preview URL on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `Preview deployed: ${{ steps.deploy.outputs.url }}`
            });
```

---

## Section 2 — Programmatic Upload with @cloudflare/pages-shared

```typescript
// scripts/upload-pages.ts
import { createPagesDeployment } from '@cloudflare/pages-shared/dist/metadata-generator';
import { readdir, readFile, stat } from 'fs/promises';
import { join, relative } from 'path';
import { createHash } from 'crypto';

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;
const PROJECT = process.env.PAGES_PROJECT!;
const DIST_DIR = process.argv[2] ?? './dist';

interface AssetFile {
  path: string;
  hash: string;
  size: number;
  content: Buffer;
}

async function collectAssets(dir: string): Promise<AssetFile[]> {
  const results: AssetFile[] = [];
  const entries = await readdir(dir, { withFileTypes: true, recursive: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const abs = join(entry.path ?? dir, entry.name);
    const content = await readFile(abs);
    const hash = createHash('sha256').update(content).digest('hex');
    const stats = await stat(abs);
    results.push({ path: '/' + relative(dir, abs), hash, size: stats.size, content });
  }
  return results;
}

async function uploadDirect(assets: AssetFile[]) {
  const manifest = Object.fromEntries(assets.map((a) => [a.path, a.hash]));

  // Step 1: create deployment and get upload targets
  const initRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}/deployments`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifest }),
    }
  );
  const init = (await initRes.json()) as { result: { id: string; file_upload_urls: Record<string, string> } };
  const { id: deployId, file_upload_urls: uploadUrls } = init.result;
  console.log(`Deployment ${deployId} created, uploading ${Object.keys(uploadUrls).length} files`);

  // Step 2: upload required files
  await Promise.all(
    Object.entries(uploadUrls).map(async ([hash, url]) => {
      const asset = assets.find((a) => a.hash === hash);
      if (!asset) return;
      await fetch(url, { method: 'PUT', body: asset.content });
    })
  );

  // Step 3: finalise
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}/deployments/${deployId}/finalize`,
    { method: 'POST', headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );

  console.log(`Deployment complete: https://${deployId}.${PROJECT}.pages.dev`);
}

collectAssets(DIST_DIR).then(uploadDirect).catch((err) => { console.error(err); process.exit(1); });
```

---

## Section 3 — Alias Management and Rollback

```bash
#!/usr/bin/env bash
# scripts/manage-pages-alias.sh
set -euo pipefail

PROJECT="${PAGES_PROJECT:-my-pages-app}"

# List recent deployments
echo "==> Recent deployments"
npx wrangler pages deployment list --project-name "$PROJECT" | head -20

# Rollback to a specific deployment
rollback() {
  local DEPLOY_ID="$1"
  echo "==> Rolling back to $DEPLOY_ID"
  npx wrangler pages deployment rollback "$DEPLOY_ID" \
    --project-name "$PROJECT"
  echo "Rollback complete. Production now serves $DEPLOY_ID"
}

# Set a branch alias to a specific deployment
set_alias() {
  local DEPLOY_ID="$1"
  local ALIAS="$2"
  echo "==> Setting alias '$ALIAS' -> $DEPLOY_ID"
  curl -s -X PATCH \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"aliases\": [\"$ALIAS\"]}" \
    "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT/deployments/$DEPLOY_ID" \
    | jq '.result.aliases'
}

case "${1:-list}" in
  list)    ;;
  rollback) rollback "$2" ;;
  alias)   set_alias "$2" "$3" ;;
  *) echo "Usage: $0 [list|rollback <id>|alias <id> <alias>]"; exit 1 ;;
esac
```

---

## Anti-patterns
- **Uploading with a global API key instead of a scoped token** — use a token with only `Account:Cloudflare Pages:Edit` permission.
- **Skipping `--branch` on preview deploys** — without a branch name, all deployments land on the production alias and override it.
- **Parallelising too many file uploads** — the API enforces per-account concurrency limits; batch uploads in groups of 50 or use the SDK's built-in chunking.
- **Not finalising the deployment** — the deployment stays in `uploading` state indefinitely if you forget the finalize call.

---

## Gotchas
- `wrangler pages deploy` requires Wrangler ≥ 3.x; earlier versions do not support the `--branch` flag.
- The Pages API deduplicates assets by SHA-256 hash; only new or changed files consume upload quota in each deployment.
- `wrangler pages deployment rollback` changes the production alias but does not delete the newer deployments — they remain accessible at their preview URLs.
- Preview deployment URLs follow the pattern `<hash>.<project>.pages.dev`, not `<branch>.<project>.pages.dev`; the branch alias is a separate CNAME.

---

## Verification

```bash
# Deploy and print the URL
npx wrangler pages deploy ./dist \
  --project-name my-pages-app \
  --branch main

# List deployments
npx wrangler pages deployment list --project-name my-pages-app

# Rollback to previous
npx wrangler pages deployment rollback <previous-deploy-id> \
  --project-name my-pages-app

# Verify production URL responds
curl -s -o /dev/null -w "%{http_code}" https://my-pages-app.pages.dev
```

---

## Related
- `cloudflare-pages-deploy-hooks-external-ci.md`
- `workers-assets-static-site-deploy.md`

---

## Sources
- Wrangler Pages deploy command — https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- Cloudflare Pages Direct Upload API — https://developers.cloudflare.com/api/resources/pages/subresources/deployments/
- Pages deployment rollback — https://developers.cloudflare.com/pages/configuration/rollbacks/
