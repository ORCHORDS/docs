# GitHub Actions Environment Secrets vs Repo Secrets Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Workers project stores `CLOUDFLARE_API_TOKEN` as a repository secret. Every workflow job in every branch can read and use this token, including untrusted code in PR builds from forks and feature branches. When a single token covers all environments (staging, production, canary), a misconfigured or malicious workflow step can deploy directly to production using the same credential it uses for preview builds.

## Context

GitHub Actions has three secret scopes: **organization secrets** (available to some or all repos in an org), **repository secrets** (available to all workflow jobs in the repo), and **environment secrets** (available only to jobs that declare `environment:` with the matching environment name). Environment secrets support approval gates, deployment branch/tag policies, and wait timers. For Cloudflare Workers, the standard pattern is to use environment-scoped secrets for per-environment API tokens so that production credentials are physically unreachable unless the job is explicitly deploying to the production environment and a reviewer has approved.

## Secret scope hierarchy

| Secret type | Visibility | Supports approval gates | Best used for |
|---|---|---|---|
| Org secret | All or selected repos | No | Shared read-only tokens, npm registry auth |
| Repo secret | All jobs in the repo | No | Dev/test tokens, non-environment-specific tools |
| Environment secret | Jobs with matching `environment:` | Yes | Per-environment Cloudflare tokens, database URIs |

When the same secret name is defined at both repo and environment scopes, the **environment secret takes precedence** in jobs that declare that environment. Org-level secrets are overridden by repo-level, which are overridden by environment-level.

## Creating environment secrets via the API

```bash
# Create the 'production' environment and set its Cloudflare API token
gh api \
  --method PUT \
  "/repos/{owner}/{repo}/environments/production" \
  --field "reviewers[0][type]=Team" \
  --field "reviewers[0][id]=12345" \
  --field "deployment_branch_policy[protected_branches]=true"

# Set the environment-scoped secret (requires separate encryption with the env public key)
gh secret set CLOUDFLARE_API_TOKEN \
  --env production \
  --body "$CF_PROD_TOKEN"

gh secret set CLOUDFLARE_API_TOKEN \
  --env staging \
  --body "$CF_STAGING_TOKEN"
```

## Workflow: environment-scoped Cloudflare tokens

```yaml
name: Deploy Workers

on:
  push:
    branches: [main, staging]

permissions:
  contents: read

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    environment: staging           # unlocks staging env secrets only
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}   # staging token
          accountId: ${{ vars.CF_ACCOUNT_ID }}
          command: deploy --env staging

  deploy-production:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production        # requires reviewer approval + unlocks prod secrets
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}   # production token (different value)
          accountId: ${{ vars.CF_ACCOUNT_ID }}
          command: deploy --env production
```

Both jobs reference `secrets.CLOUDFLARE_API_TOKEN` by the same name but receive different values because the secret is defined separately at the `staging` and `production` environment scopes.

## Migrating from repo secrets to environment secrets

```bash
#!/usr/bin/env bash
# scripts/migrate-secrets-to-environments.sh
# One-time migration: read the existing repo secret values and re-set them per environment.
# GitHub does not expose secret values after creation — you must have the originals.

set -euo pipefail

REPO="your-org/your-repo"

# Set production environment secret
gh secret set CLOUDFLARE_API_TOKEN \
  --repo "$REPO" \
  --env production \
  --body "$CF_PROD_TOKEN"

gh secret set CLOUDFLARE_ACCOUNT_ID \
  --repo "$REPO" \
  --env production \
  --body "$CF_ACCOUNT_ID"

# Set staging environment secret
gh secret set CLOUDFLARE_API_TOKEN \
  --repo "$REPO" \
  --env staging \
  --body "$CF_STAGING_TOKEN"

gh secret set CLOUDFLARE_ACCOUNT_ID \
  --repo "$REPO" \
  --env staging \
  --body "$CF_ACCOUNT_ID"

# Delete the old repo-level secret after verifying deploys work
# gh secret delete CLOUDFLARE_API_TOKEN --repo "$REPO"
echo "Verify staging and production deploys succeed before deleting repo-level secrets."
```

## TypeScript: listing secrets by scope for an audit

```typescript
// scripts/audit-secret-scopes.ts
// Audits which environments define CLOUDFLARE_API_TOKEN vs repo-level.
// Requires a PAT with repo and environment read permissions.

const REPO = "your-org/your-repo";
const SECRET_NAME = "CLOUDFLARE_API_TOKEN";

interface SecretEntry {
  name: string;
  created_at: string;
  updated_at: string;
}

async function fetchJson<T>(url: string, token: string): Promise<T> {
  const res = await fetch(`https://api.github.com${url}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json() as Promise<T>;
}

async function auditSecrets(token: string): Promise<void> {
  const { secrets: repoSecrets } = await fetchJson<{ secrets: SecretEntry[] }>(
    `/repos/${REPO}/actions/secrets`,
    token
  );

  const isRepoLevel = repoSecrets.some((s) => s.name === SECRET_NAME);
  console.log(`Repo-level ${SECRET_NAME}: ${isRepoLevel ? "EXISTS (risk)" : "not present"}`);

  const { environments } = await fetchJson<{ environments: Array<{ name: string }> }>(
    `/repos/${REPO}/environments`,
    token
  );

  for (const env of environments) {
    const { secrets: envSecrets } = await fetchJson<{ secrets: SecretEntry[] }>(
      `/repos/${REPO}/environments/${encodeURIComponent(env.name)}/secrets`,
      token
    );
    const has = envSecrets.some((s) => s.name === SECRET_NAME);
    console.log(`  [${env.name}] ${SECRET_NAME}: ${has ? "scoped" : "MISSING"}`);
  }
}

auditSecrets(process.env.GH_TOKEN!);
```

## Environment protection rules for Workers deploys

Set deployment branch policies and required reviewers on the production environment:

```yaml
# .github/workflows/protect-production.yml
# This workflow itself cannot set protection rules — use the API or UI.
# Document the expected state for compliance purposes.
#
# production environment settings:
#   required_reviewers: [team/platform-lead]
#   deployment_branch_policy:
#     protected_branches: true          # only branches with branch protection rules
#     custom_branches: []
#   wait_timer: 5                       # minutes before auto-proceeding (0 = immediate)
```

## Anti-patterns

- Storing a single `CLOUDFLARE_API_TOKEN` at the repo level that grants `Account:Workers Scripts:Edit` across all zones — any branch build can trigger a production deploy.
- Using the same Cloudflare API token value for staging and production environments, even if stored separately — a staging token should have narrower zone/resource scope than a production token.
- Referencing `secrets.CLOUDFLARE_API_TOKEN` in a job that does not declare `environment:` — the job receives the repo-level secret, bypassing environment approval gates entirely.
- Setting the token as an org secret shared across all repos — a compromise in any one repo exposes the credential across the entire org.

## Gotchas

- A job that declares `environment: production` in its `environment:` field but does not actually deploy still triggers the approval gate and consumes a deployment slot. Reserve `environment:` for jobs that perform deployments.
- Fork PRs cannot access environment secrets — GitHub strips them for security. CI jobs that run tests on PRs from forks must avoid `environment:` declarations and use separate non-sensitive variables for those builds.
- Secret names are case-sensitive. `CLOUDFLARE_API_TOKEN` and `cloudflare_api_token` are different secrets. Define a naming convention and enforce it with a linter or policy check.
- GitHub does not surface which secret scope (org/repo/environment) was used at runtime. If a job reads a secret, it cannot tell whether it came from the environment or fell back to the repo level. Delete repo-level secrets explicitly after migration.
- Environment secrets cannot be referenced outside of `jobs.<job-id>.environment:` — they are not available in `on:` conditions or `defaults:` blocks.

## Verification

```bash
# Confirm no repo-level CLOUDFLARE_API_TOKEN remains after migration
gh secret list --repo your-org/your-repo | grep CLOUDFLARE_API_TOKEN
# Expected: no output (or output should show it's gone)

# Confirm environment secrets exist
gh secret list --env production --repo your-org/your-repo
gh secret list --env staging --repo your-org/your-repo

# Trigger a deploy to production and verify it pauses for reviewer approval
gh workflow run deploy.yml --ref main
gh run watch   # should show "Waiting for approval" before the deploy-production job
```

## Related

- `github-actions-secrets-management.md`
- `github-actions-environment-protection.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-environments-deployment-protection-rules.md`
- `github-actions-github-token-permission-minimization.md`
- `github-fine-grained-personal-access-tokens.md`

## Sources

- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- https://docs.github.com/en/rest/actions/secrets
- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/security-hardening-for-github-actions#hardening-for-github-hosted-runners
