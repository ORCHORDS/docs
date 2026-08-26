# GitHub Environments for Workers Staging/Production Secrets

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to deploy a Cloudflare Worker to a `staging` environment on every PR merge and to `production` only after a human approval. Storing a single `CLOUDFLARE_API_TOKEN` secret at the repository level means both environments share the same token, making it impossible to scope permissions or enforce a review gate before production traffic is affected.

---

## Context

GitHub Environments are named deployment targets you attach to individual workflow jobs. Each environment can hold its own secrets, variables, required reviewers, and wait timers independent of repository-level settings. When a job references `environment: production`, GitHub pauses the run and sends a review request to the configured approvers before any steps execute. Cloudflare recommends using separate API tokens scoped to each environment to limit blast radius if a token leaks. A staging token might have `Workers Scripts:Edit` on a staging account, while the production token is further locked to a specific zone or Worker name.

---

## Section 1 — GitHub Actions workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  deployments: write  # required to create GitHub deployment objects

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test

  deploy-staging:
    needs: test
    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: https://my-worker-staging.example.workers.dev
    concurrency:
      group: deploy-staging
      cancel-in-progress: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  deploy-production:
    needs: deploy-staging
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://my-worker.example.com
    concurrency:
      group: deploy-production
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Deploy to production
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

> `secrets.CLOUDFLARE_API_TOKEN` resolves to the environment-scoped value when the job specifies `environment:`, so the same key name returns different tokens for staging and production.

---

## Section 2 — wrangler.toml with multiple environments

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
ENV = "development"

[env.staging]
name = "my-worker-staging"
route = { pattern = "staging.example.com/*", zone_name = "example.com" }

[env.staging.vars]
ENV = "staging"
API_BASE = "https://staging-api.example.com"

[env.production]
name = "my-worker"
route = { pattern = "example.com/*", zone_name = "example.com" }

[env.production.vars]
ENV = "production"
API_BASE = "https://api.example.com"
```

---

## Section 3 — Configuring GitHub Environments via GitHub CLI

```bash
# Create the staging environment (no reviewers, no wait timer)
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/{owner}/{repo}/environments/staging \
  -f deployment_branch_policy=null

# Create the production environment with:
#   - required reviewer (user ID)
#   - 5-minute wait timer before deployment proceeds
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/{owner}/{repo}/environments/production \
  --field reviewers='[{"type":"User","id":12345678}]' \
  --field wait_timer=5 \
  --field prevent_self_review=true

# Add the staging token
gh secret set CLOUDFLARE_API_TOKEN \
  --env staging \
  --body "$STAGING_CF_TOKEN"

gh secret set CLOUDFLARE_ACCOUNT_ID \
  --env staging \
  --body "$CF_ACCOUNT_ID"

# Add the production token (different, more restricted token)
gh secret set CLOUDFLARE_API_TOKEN \
  --env production \
  --body "$PRODUCTION_CF_TOKEN"

gh secret set CLOUDFLARE_ACCOUNT_ID \
  --env production \
  --body "$CF_ACCOUNT_ID"

# Verify
gh api /repos/{owner}/{repo}/environments | jq '.environments[].name'
gh secret list --env staging
gh secret list --env production
```

---

## Anti-patterns

- **Single repository-level token** — A repository secret is visible to every job regardless of environment. A leaked staging token can then be used against production if both share the same credential.
- **Skipping `needs: deploy-staging`** — Without a staging gate, production deploys can proceed before staging smoke tests complete, defeating the purpose of the two-stage pipeline.
- **`cancel-in-progress: true` on production** — Cancelling a running production deploy can leave it in a partial rollout state; always queue production deploys.
- **Granting reviewers the `bypass` permission** — Self-review bypass lets a developer approve their own production deploy, removing the human control point.

---

## Gotchas

- GitHub Environment secrets take precedence over repository secrets of the same name, but only when the job declares the `environment:` key. A job without that key falls back to the repository-level secret.
- The wait timer counts from when the deployment review is approved, not from when the workflow starts.
- `prevent_self_review: true` requires the reviewer and the commit author to be different users; set it for production environments to enforce four-eyes principle.
- Deployment protection rules (branch policy) can further restrict which branches are allowed to deploy to production — combine them with required reviewers for defence in depth.

---

## Verification

```bash
# List environments and their protection rules
gh api /repos/{owner}/{repo}/environments | \
  jq '.environments[] | {name, protection_rules: [.protection_rules[].type]}'

# Watch a workflow run and see the pending approval step
gh run watch $(gh run list --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')

# Confirm which token was used (Cloudflare audit log)
curl -s https://api.cloudflare.com/client/v4/user/audit_logs \
  -H "Authorization: Bearer $PRODUCTION_CF_TOKEN" | \
  jq '.result[:3] | .[] | {action, when: .when, actor_email: .actor.email}'
```

---

## Related

- `github-oidc-cloudflare-api-token-keyless.md`
- `github-actions-wrangler-matrix-deploy.md`

---

## Sources

- GitHub Environments documentation — https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- Cloudflare API token permissions — https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- GitHub deployment protection rules — https://docs.github.com/en/actions/deployment/protecting-deployments/about-deployment-protection-rules
