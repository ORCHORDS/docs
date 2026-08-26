# Extracting Preview URL from wrangler pages deploy in CI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You run `wrangler pages deploy` in GitHub Actions and want the preview URL posted as a
GitHub commit status (or PR comment) so reviewers can click directly to the deployed
branch preview without digging through CI logs.

## Context

- Cloudflare Pages project deployed via Wrangler CLI in GitHub Actions.
- `wrangler pages deploy` prints a preview URL to stdout on success.
- The `CLOUDFLARE_PAGES_BRANCH` environment variable controls which branch alias is
  attached to the deployment.
- The GitHub Statuses API (`repos/{owner}/{repo}/statuses/{sha}`) is used to post the URL.

---

## Section 1 — Capturing the preview URL

`wrangler pages deploy` outputs a line like:

```
Deployment complete! Take a peek over at https://abc123.my-project.pages.dev
```

or, for a branch preview:

```
https://feature-my-feature.my-project.pages.dev
```

Capture it with a targeted regex:

```bash
# Run deploy and capture output
OUTPUT=$(npx wrangler pages deploy ./dist \
  --project-name "my-project" \
  --branch "$CLOUDFLARE_PAGES_BRANCH" \
  2>&1)

echo "$OUTPUT"

# Extract the first HTTPS URL that contains .pages.dev
PREVIEW_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.pages\.dev[^\s]*' | head -1)

echo "Preview URL: $PREVIEW_URL"
```

---

## Section 2 — Full workflow with commit status posting

```yaml
# .github/workflows/pages-deploy.yml
name: Deploy to Cloudflare Pages

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read
  statuses: write   # required to post commit status

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      # Use the PR branch name for previews, 'main' for production
      CLOUDFLARE_PAGES_BRANCH: ${{ github.head_ref || github.ref_name }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Post "pending" commit status
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          curl -fsSL -X POST \
            "https://api.github.com/repos/${{ github.repository }}/statuses/${{ github.sha }}" \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H 'Content-Type: application/json' \
            -d '{"state":"pending","context":"cloudflare-pages/preview","description":"Deploying to Cloudflare Pages…"}'

      - name: Deploy to Pages
        id: deploy
        run: |
          set +e
          OUTPUT=$(npx wrangler pages deploy ./dist \
            --project-name "my-project" \
            --branch "$CLOUDFLARE_PAGES_BRANCH" 2>&1)
          EXIT_CODE=$?
          set -e

          echo "$OUTPUT"

          PREVIEW_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.pages\.dev[^\s]*' | head -1)
          echo "preview_url=${PREVIEW_URL}" >> "$GITHUB_OUTPUT"
          echo "exit_code=${EXIT_CODE}" >> "$GITHUB_OUTPUT"

      - name: Post "success" commit status
        if: steps.deploy.outputs.exit_code == '0'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          curl -fsSL -X POST \
            "https://api.github.com/repos/${{ github.repository }}/statuses/${{ github.sha }}" \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg url "${{ steps.deploy.outputs.preview_url }}" \
              '{state:"success",context:"cloudflare-pages/preview",description:"Preview ready",target_url:$url}')"

      - name: Post "failure" commit status
        if: steps.deploy.outputs.exit_code != '0'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          curl -fsSL -X POST \
            "https://api.github.com/repos/${{ github.repository }}/statuses/${{ github.sha }}" \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg run_url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
              '{state:"failure",context:"cloudflare-pages/preview",description:"Pages deploy failed",target_url:$run_url}')"
          exit 1
```

---

## Section 3 — TypeScript URL extractor (reusable utility)

```typescript
// scripts/extract-pages-url.ts
import { execSync } from 'node:child_process';

export interface PagesDeployResult {
  previewUrl: string | null;
  productionUrl: string | null;
  deploymentId: string | null;
  exitCode: number;
  rawOutput: string;
}

export function deployPages(options: {
  dir: string;
  projectName: string;
  branch: string;
}): PagesDeployResult {
  let rawOutput = '';
  let exitCode = 0;

  try {
    rawOutput = execSync(
      `npx wrangler pages deploy ${options.dir} --project-name "${options.projectName}" --branch "${options.branch}"`,
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
    );
  } catch (err: unknown) {
    const e = err as { stdout?: string; stderr?: string; status?: number };
    rawOutput = (e.stdout ?? '') + (e.stderr ?? '');
    exitCode = e.status ?? 1;
  }

  // Branch preview URL: <random-hash>.<project>.pages.dev
  const previewMatch = rawOutput.match(
    /https:\/\/[a-z0-9-]+\.([a-z0-9-]+)\.pages\.dev/,
  );

  // Production alias: <project>.pages.dev (no hash prefix)
  const productionMatch = rawOutput.match(
    /https:\/\/([a-z0-9-]+)\.pages\.dev(?!\.)/,
  );

  const deploymentIdMatch = rawOutput.match(/Deployment ID:\s*([\w-]+)/);

  return {
    previewUrl: previewMatch?.[0] ?? null,
    productionUrl: productionMatch?.[0] ?? null,
    deploymentId: deploymentIdMatch?.[1] ?? null,
    exitCode,
    rawOutput,
  };
}

// CLI usage
const result = deployPages({
  dir: process.argv[2] ?? './dist',
  projectName: process.env.CF_PAGES_PROJECT ?? 'my-project',
  branch: process.env.CLOUDFLARE_PAGES_BRANCH ?? 'main',
});

console.log('Preview URL:', result.previewUrl);
console.log('Deployment ID:', result.deploymentId);

if (result.exitCode !== 0) {
  console.error('Deploy failed.\n', result.rawOutput);
  process.exit(result.exitCode);
}
```

---

## Anti-patterns

- **Parsing the URL from stderr** — `wrangler pages deploy` writes the URL to stdout;
  mixing stderr redirection (`2>&1`) can make the order non-deterministic on some
  Node.js versions. Separate stdout and stderr where possible.
- **Using `cut`/`awk` on a fixed column** — wrangler output format changes between
  minor versions; a regex targeting the `pages.dev` domain suffix is more stable.
- **Posting the status before knowing the URL** — a "success" status with a blank
  `target_url` is misleading; always set the URL in the same step.

## Gotchas

- `CLOUDFLARE_PAGES_BRANCH` is a Wrangler env var that sets the **branch alias**, not
  the git branch being deployed. Setting it to the PR branch name produces
  `<branch-slug>.<project>.pages.dev` preview URLs.
- The `--commit-dirty` flag suppresses the "working directory is dirty" error in CI
  environments where git status is modified by the build step.
- GitHub statuses are tied to a commit SHA, not a PR. If you squash-merge, the SHA
  changes and the status appears on the old commit — use PR comments as a fallback for
  important URLs.
- `statuses: write` permission is separate from `pull-requests: write`; both may be
  needed depending on your notification strategy.

## Related

- `workers-deployment-slack-webhook-notification.md`
- `workers-deployment-gates-manual-approval.md`
- Cloudflare Pages docs: https://developers.cloudflare.com/pages/

## Sources

- `wrangler pages deploy` reference: https://developers.cloudflare.com/workers/wrangler/commands/#pages-deploy
- GitHub Statuses API: https://docs.github.com/en/rest/commits/statuses
- `CLOUDFLARE_PAGES_BRANCH` env: https://developers.cloudflare.com/pages/configuration/build-configuration/
