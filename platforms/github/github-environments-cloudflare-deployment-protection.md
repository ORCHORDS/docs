# GitHub Environments with Deployment Protection Rules for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker deploy to production triggered automatically on every merge to `main` — with no human gate — caused a breaking change to reach users. You need manual approval for production deployments, environment-scoped secrets, and a post-deploy health check that confirms the Worker is healthy before GitHub marks the deployment successful.

## Context

GitHub Environments are first-class deployment targets. Each environment can carry its own secrets, variables, and protection rules (required reviewers, wait timers, custom deployment protection rule webhooks). When a workflow job targets an `environment:`, GitHub enforces all configured protection rules before the job can run and reports deployment status back to the PR and commit.

Cloudflare Workers fit naturally into this model: staging auto-deploys, production requires approval, and a custom protection rule calls a Workers health endpoint to confirm a preview is healthy before the deployment is marked successful.

## Creating Environments and Protection Rules

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]

jobs:
  # -------------------------------------------------------
  # STAGING — deploys automatically, no approval required
  # -------------------------------------------------------
  deploy-staging:
    name: Deploy → staging
    runs-on: ubuntu-24.04
    environment:
      name: staging
      url: https://my-worker.staging.orchords.workers.dev

    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler@3.57.0

      - name: Deploy to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: wrangler deploy --env staging

      - name: Health check — staging
        run: |
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            https://my-worker.staging.orchords.workers.dev/health)
          if [ "$STATUS" != "200" ]; then
            echo "Health check failed: HTTP $STATUS"
            exit 1
          fi
          echo "Staging healthy: HTTP $STATUS"

  # -------------------------------------------------------
  # PRODUCTION — requires manual approval from a reviewer
  # -------------------------------------------------------
  deploy-production:
    name: Deploy → production
    runs-on: ubuntu-24.04
    needs: deploy-staging
    environment:
      name: production
      url: https://my-worker.orchords.workers.dev

    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler@3.57.0

      - name: Deploy to production
        env:
          # CF_API_TOKEN_PROD is scoped ONLY to the production environment
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: wrangler deploy --env production

      - name: Health check — production
        run: |
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            https://my-worker.orchords.workers.dev/health)
          if [ "$STATUS" != "200" ]; then
            echo "Health check failed: HTTP $STATUS"
            exit 1
          fi
          echo "Production healthy: HTTP $STATUS"
```

## Configuring the Production Environment via GitHub UI / API

In the GitHub repository settings under **Environments → production**:

1. **Required reviewers** — add one or more GitHub users or teams. The deployment job pauses until an approver clicks "Approve and deploy" in the GitHub UI.
2. **Wait timer** — optionally add a delay (e.g., 5 minutes) after approval before the job actually starts, giving time to abort.
3. **Deployment branches** — restrict to `main` only so feature branches can never target production directly.
4. **Environment secrets** — add `CF_API_TOKEN_PROD` here. It is available **only** to jobs that specify `environment: production`; no other job can access it.

Via the GitHub CLI:

```bash
# Set a secret scoped to the production environment
gh secret set CF_API_TOKEN_PROD \
  --env production \
  --repo example-org/example-repo \
  --body "$(cat ~/.cloudflare/prod-token)"

# Set a secret available to all environments (e.g., account ID)
gh secret set CF_ACCOUNT_ID \
  --repo example-org/example-repo \
  --body "abc123"
```

## Custom Deployment Protection Rule (Health Webhook)

GitHub supports custom deployment protection rules via GitHub Apps. A lightweight Workers-based webhook can act as this gate:

```typescript
// workers/deploy-gate/src/index.ts
import { Octokit } from "@octokit/rest";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const payload = await request.json<GitHubDeploymentProtectionPayload>();
    const { deployment, environment, installation } = payload;

    // Ping the preview URL derived from the deployment
    const previewUrl = deployment.payload?.preview_url ?? env.HEALTH_ENDPOINT;
    const healthResp = await fetch(`${previewUrl}/health`, { cf: { cacheTtl: 0 } });

    const octokit = new Octokit({ auth: env.GITHUB_APP_TOKEN });

    if (healthResp.ok) {
      await octokit.rest.repos.createDeploymentProtectionRuleStatus({
        deployment_protection_rule_callback_url: payload.callback_url,
        environment_name: environment,
        state: "approved",
        comment: `Health check passed: HTTP ${healthResp.status}`,
      } as any);
      return new Response("Approved", { status: 200 });
    }

    await octokit.rest.repos.createDeploymentProtectionRuleStatus({
      deployment_protection_rule_callback_url: payload.callback_url,
      environment_name: environment,
      state: "rejected",
      comment: `Health check failed: HTTP ${healthResp.status}`,
    } as any);
    return new Response("Rejected", { status: 200 });
  },
};

interface Env {
  GITHUB_APP_TOKEN: string;
  HEALTH_ENDPOINT: string;
}

interface GitHubDeploymentProtectionPayload {
  callback_url: string;
  environment: string;
  deployment: { payload?: { preview_url?: string } };
  installation: { id: number };
}
```

## Anti-patterns

- Storing `CF_API_TOKEN_PROD` as a repository-level secret — any job in any workflow can access it, removing the production gate.
- Skipping the staging health check and relying solely on the production gate — errors should be caught before the approval prompt.
- Using a single CF API token for all environments — a compromised staging token should not be able to deploy to production.
- Setting `required_reviewers: 0` on the production environment to speed up CI — this completely bypasses the protection rule.

## Gotchas

- Deployment protection rules (custom webhook gate) require a **GitHub App** installed on the repository — a personal access token is insufficient.
- The `environment: { url: ... }` field in the job sets the URL shown in the GitHub Deployments panel and in PR status checks; it does not affect routing.
- If the required reviewer is the same person who triggered the push, GitHub will not allow self-approval unless the organisation allows it in settings.
- Re-running a failed production job re-triggers the approval gate; approving the previous run does not carry over.

## Verification

```bash
# List deployments for the repository
gh api repos/example-org/example-repo/deployments \
  --jq '.[] | {id, environment, state, created_at}' | head -20

# Check the latest deployment status for production
gh api repos/example-org/example-repo/deployments \
  --jq '[.[] | select(.environment=="production")] | first | {id,state}'
```

## Related

- `github-actions-reusable-workflows-workers-deploy.md`
- `github-actions-composite-action-wrangler.md`
- `github-merge-queue-workers-ci-validation.md`

## Sources

- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://docs.github.com/en/actions/deployment/protecting-deployments/creating-custom-deployment-protection-rules
- https://developers.cloudflare.com/workers/wrangler/environments/
