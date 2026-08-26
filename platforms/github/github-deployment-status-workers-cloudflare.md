# Syncing Cloudflare Workers Deployment Status Back to GitHub Deployments API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
When deploying Cloudflare Workers from GitHub Actions, the PR timeline shows no deployment status unless you explicitly call the GitHub Deployments API. Without this integration, reviewers cannot see whether the preview environment is live, in progress, or failed directly from the pull request UI. Syncing deployment status creates a rich feedback loop: a GitHub Deployment is created when a PR opens, transitions to `in_progress` when wrangler starts, and resolves to `success` or `failure` with a link to the Cloudflare preview URL.

---

## Context
The GitHub Deployments API is a two-step system: first create a `Deployment` resource tied to a ref (commit SHA or branch), then post `DeploymentStatus` updates as the deployment progresses. Each status can carry an `environment_url` that GitHub renders as a clickable link in the PR UI. For Workers, the environment URL is the preview URL emitted by `wrangler deploy`. GitHub Actions runs the workflow sequentially, allowing the deployment ID to be passed between steps using `$GITHUB_OUTPUT`. The workflow requires `deployments: write` permission on the GitHub token.

---

## Section 1 — GitHub Actions Workflow
```yaml
name: Deploy Workers with GitHub Deployment Status

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  deployments: write
  pull-requests: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: preview
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Create GitHub Deployment
        id: create-deployment
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          DEPLOYMENT_ID=$(gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            /repos/${{ github.repository }}/deployments \
            -f ref="${{ github.head_ref }}" \
            -f environment="preview" \
            -f description="Cloudflare Workers preview" \
            -F auto_merge=false \
            -F required_contexts[] \
            --jq '.id')
          echo "deployment_id=$DEPLOYMENT_ID" >> $GITHUB_OUTPUT

      - name: Set deployment status — in_progress
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            /repos/${{ github.repository }}/deployments/${{ steps.create-deployment.outputs.deployment_id }}/statuses \
            -f state="in_progress" \
            -f description="Deploying to Cloudflare Workers..."

      - name: Deploy to Cloudflare Workers
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler deploy --env preview 2>&1)
          echo "$OUTPUT"
          PREVIEW_URL=$(echo "$OUTPUT" | grep -oP 'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev' | head -1 || true)
          echo "preview_url=$PREVIEW_URL" >> $GITHUB_OUTPUT

      - name: Set deployment status — success
        if: success()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            /repos/${{ github.repository }}/deployments/${{ steps.create-deployment.outputs.deployment_id }}/statuses \
            -f state="success" \
            -f environment_url="${{ steps.deploy.outputs.preview_url }}" \
            -f description="Deployed to Cloudflare Workers"

      - name: Set deployment status — failure
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            /repos/${{ github.repository }}/deployments/${{ steps.create-deployment.outputs.deployment_id }}/statuses \
            -f state="failure" \
            -f description="Cloudflare Workers deployment failed"
```

## Section 2 — TypeScript Helper for GitHub Deployments API Calls
```typescript
// scripts/github-deployment.ts
// Used for programmatic control outside of gh CLI

const BASE = 'https://api.github.com';
const HEADERS = {
  Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  'Content-Type': 'application/json',
};

export type DeploymentState =
  | 'error'
  | 'failure'
  | 'inactive'
  | 'in_progress'
  | 'queued'
  | 'pending'
  | 'success';

export async function createDeployment(
  owner: string,
  repo: string,
  ref: string,
  environment = 'preview'
): Promise<number> {
  const res = await fetch(`${BASE}/repos/${owner}/${repo}/deployments`, {
    method: 'POST',
    headers: HEADERS,
    body: JSON.stringify({
      ref,
      environment,
      description: 'Cloudflare Workers preview deployment',
      auto_merge: false,
      required_contexts: [],
    }),
  });
  if (!res.ok) throw new Error(`Create deployment failed: ${res.status} ${await res.text()}`);
  const data = await res.json<{ id: number }>();
  return data.id;
}

export async function updateDeploymentStatus(
  owner: string,
  repo: string,
  deploymentId: number,
  state: DeploymentState,
  options: { environmentUrl?: string; description?: string } = {}
): Promise<void> {
  const res = await fetch(
    `${BASE}/repos/${owner}/${repo}/deployments/${deploymentId}/statuses`,
    {
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({
        state,
        environment_url: options.environmentUrl ?? '',
        description: options.description ?? '',
        auto_inactive: true,
      }),
    }
  );
  if (!res.ok) throw new Error(`Update deployment status failed: ${res.status} ${await res.text()}`);
}

// Usage example
async function main() {
  const [owner, repo] = (process.env.GITHUB_REPOSITORY ?? '').split('/');
  const ref = process.env.GITHUB_HEAD_REF ?? 'main';

  const deploymentId = await createDeployment(owner, repo, ref);
  console.log(`deployment_id=${deploymentId}`);

  await updateDeploymentStatus(owner, repo, deploymentId, 'in_progress', {
    description: 'Deploying...',
  });

  // ... run wrangler deploy ...
  const previewUrl = process.env.PREVIEW_URL ?? '';

  await updateDeploymentStatus(owner, repo, deploymentId, 'success', {
    environmentUrl: previewUrl,
    description: 'Deployed successfully',
  });
}

main().catch(console.error);
```

## Section 3 — Cleanup: Deactivating Old Preview Deployments
```typescript
// scripts/deactivate-deployments.ts
// Run on PR close to mark preview deployments as inactive

async function listDeployments(
  owner: string,
  repo: string,
  environment: string
): Promise<{ id: number }[]> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/deployments?environment=${environment}&per_page=100`,
    {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    }
  );
  return res.json();
}

async function deactivateDeployment(owner: string, repo: string, id: number): Promise<void> {
  await fetch(`https://api.github.com/repos/${owner}/${repo}/deployments/${id}/statuses`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ state: 'inactive' }),
  });
}

async function run() {
  const [owner, repo] = (process.env.GITHUB_REPOSITORY ?? '').split('/');
  const deployments = await listDeployments(owner, repo, 'preview');
  for (const d of deployments) {
    await deactivateDeployment(owner, repo, d.id);
    console.log(`Deactivated deployment ${d.id}`);
  }
}

run().catch(console.error);
```

---

## Anti-patterns
- **Skipping `required_contexts: []`** — Without explicitly clearing required contexts, GitHub may block the deployment creation if branch protection checks haven't run yet.
- **Not handling the `failure()` conditional step** — If the deploy step fails and no failure status is posted, the GitHub Deployment stays in `in_progress` indefinitely.
- **Using the same deployment for every push on a branch** — Create a new deployment per push so that deployment history is accurate and rollbacks are traceable.
- **Not setting `auto_inactive: true`** — Without it, previous `success` deployments for the same environment remain active in the GitHub UI, creating confusion about which is current.

---

## Gotchas
- The `deployments: write` permission must be set at the job level, not just the workflow level, when using `environment:` in the job definition.
- GitHub enforces unique deployments per ref + environment combination; creating two deployments for the same commit on the same environment returns the existing one (or 409).
- The `environment_url` is only rendered in the GitHub PR UI when `state` is `success` — setting it on `in_progress` statuses is silently ignored.
- Wrangler may not emit a `*.workers.dev` URL if the Worker is deployed with a custom domain only — verify the grep pattern matches your setup.
- GitHub Deployment API calls count against the REST API rate limit (5,000 requests/hour for authenticated apps); for high-frequency deploys, cache deployment IDs.

---

## Verification
```bash
# List recent deployments for the repo
gh api /repos/OWNER/REPO/deployments | jq '[.[] | {id, environment, sha: .sha[0:7], created_at}]'

# List statuses for a specific deployment
gh api /repos/OWNER/REPO/deployments/DEPLOYMENT_ID/statuses | jq '[.[] | {state, environment_url, created_at}]'

# Trigger the full workflow on a test PR
gh pr create --title "Test deployment status" --body "Testing Workers deployment sync"

# Verify the deployment environment link appears in the PR
gh pr view PR_NUMBER --json deployments
```

---

## Related
- `github-actions-workers-preview-url-pr-comment.md`
- `github-dependabot-auto-merge-workers.md`

---

## Sources
- GitHub Deployments REST API — https://docs.github.com/en/rest/deployments/deployments
- GitHub Deployment Statuses API — https://docs.github.com/en/rest/deployments/statuses
- Cloudflare Workers wrangler deploy — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- GitHub Actions deployments: write permission — https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
