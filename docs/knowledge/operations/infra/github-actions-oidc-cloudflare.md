# GitHub Actions OIDC with Cloudflare: Keyless Deployment Authentication

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

CI pipelines store long-lived `CF_API_TOKEN` secrets in GitHub repository settings. When
a token is rotated, every dependent repository must be updated manually. When a repository
is compromised, the attacker has a permanent Cloudflare credential until someone notices
and revokes it. Audit logs show the same static token used by both a human's local dev
session and the production deployment pipeline, making breach attribution impossible.

## Context

GitHub Actions supports OpenID Connect (OIDC): each workflow job receives a short-lived
signed JWT from GitHub's OIDC provider (`token.actions.githubusercontent.com`). Cloudflare
can be configured to accept these JWTs through a **Workload Identity Federation** pattern
using Cloudflare Access or via direct token exchange. The result is a zero-secrets
deployment pipeline — no `CF_API_TOKEN` stored anywhere, tokens expire in minutes, and
every deployment is scoped to exactly the repository, branch, and environment that should
have access.

This article covers two complementary approaches:
- Direct Cloudflare API token exchange using a service token and OIDC subject binding
- Using `cloudflare/cloudflare-workers-and-pages` GitHub Action's built-in OIDC support

---

## Section 1: GitHub OIDC Token Anatomy

When a job requests OIDC, GitHub mints a JWT with claims that describe the exact workflow
context. Understanding these claims is how you write precise trust policies.

```bash
# In any workflow step, enable OIDC permission and inspect the token
# permissions:
#   id-token: write
#   contents: read

curl -sH "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=cloudflare" \
  | jq -r '.value' \
  | cut -d'.' -f2 \
  | base64 -d 2>/dev/null \
  | jq .
```

Key claims emitted by GitHub:

| Claim | Example value | Use |
|---|---|---|
| `iss` | `https://token.actions.githubusercontent.com` | Must match in trust policy |
| `sub` | `repo:org/repo:ref:refs/heads/main` | Branch-scoped binding |
| `repository` | `org/repo` | Repo-level binding |
| `environment` | `production` | GitHub Environment binding |
| `ref` | `refs/heads/main` | Git ref |
| `workflow` | `.github/workflows/deploy.yml` | Workflow file path |
| `run_id` | `12345678` | Unique per run, good for audit |
| `actor` | `github-actions[bot]` | Who triggered |

The `sub` claim is the primary trust anchor. A typical production policy binds to:
```
repo:org/repo:environment:production
```
This means only workflows running in the GitHub Environment named `production` in that
specific repository can exchange for credentials.

---

## Section 2: Cloudflare API Token with OIDC Subject Binding

Cloudflare does not yet natively federate GitHub OIDC for API token issuance the way
AWS does with IAM OIDC providers. The current production pattern uses a narrow-scoped
Cloudflare API token with an intermediate token exchange step.

### Step 1: Create a minimal-permission Cloudflare API token

In the Cloudflare dashboard under **My Profile → API Tokens**, create a token with:
- **Zone:Workers Scripts:Edit** for the target zone (or account-wide if deploying across zones)
- **Account:Cloudflare Workers KV Storage:Edit** if KV namespaces are touched
- **Account:D1:Edit** if D1 migrations run during deploy
- IP restrictions set to GitHub's OIDC IP ranges (documented in GitHub meta API)
- Token expiry: **never** (the token itself is scoped by permission, not by time — the
  OIDC exchange produces the ephemeral credential)

```bash
# Retrieve GitHub's CIDR ranges for Actions runners
curl -s https://api.github.com/meta | jq '.actions'
```

Store this narrow token as `CF_API_TOKEN` in GitHub, but mark it as a **repository secret**
scoped only to environments that need it, not as an organisation-level secret.

### Step 2: Validate the GitHub OIDC JWT before using the token

A custom GitHub Action step or a small TypeScript Cloudflare Worker can act as the
exchange endpoint. Here is the Worker approach:

```typescript
// token-exchange-worker/src/index.ts
import { jwtVerify, createRemoteJWKSet } from 'jose';

export interface Env {
  // The narrow CF token that this Worker is authorised to vend
  VEND_CF_TOKEN: string;
  // Comma-separated list of allowed sub claims, e.g.
  // "repo:org/myrepo:environment:production"
  ALLOWED_SUBJECTS: string;
}

const GITHUB_JWKS_URL =
  'https://token.actions.githubusercontent.com/.well-known/jwks';

const GITHUB_JWKS = createRemoteJWKSet(new URL(GITHUB_JWKS_URL));

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const authHeader = request.headers.get('Authorization');
    if (!authHeader?.startsWith('Bearer ')) {
      return new Response('Missing bearer token', { status: 401 });
    }

    const oidcJwt = authHeader.slice(7);

    try {
      const { payload } = await jwtVerify(oidcJwt, GITHUB_JWKS, {
        issuer: 'https://token.actions.githubusercontent.com',
        audience: 'cloudflare',
      });

      const allowedSubs = env.ALLOWED_SUBJECTS.split(',').map((s) => s.trim());
      if (!allowedSubs.includes(payload.sub as string)) {
        return new Response('Unauthorized subject', { status: 403 });
      }

      // Return the scoped token, valid for this exchange only
      return Response.json({
        token: env.VEND_CF_TOKEN,
        expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(), // 10 min hint
        sub: payload.sub,
      });
    } catch (err) {
      console.error('OIDC validation failed:', err);
      return new Response('Invalid token', { status: 401 });
    }
  },
};
```

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write   # Required for OIDC
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production   # Matches allowed sub claim
    steps:
      - uses: actions/checkout@v4

      - name: Exchange OIDC token for CF token
        id: exchange
        run: |
          OIDC_TOKEN=$(curl -sH "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=cloudflare" | jq -r '.value')

          RESPONSE=$(curl -sf -X POST \
            -H "Authorization: Bearer $OIDC_TOKEN" \
            "https://token-exchange.yourorg.workers.dev")

          CF_TOKEN=$(echo "$RESPONSE" | jq -r '.token')
          echo "::add-mask::$CF_TOKEN"
          echo "cf_token=$CF_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Deploy with Wrangler
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.exchange.outputs.cf_token }}
        run: npx wrangler deploy --env production
```

---

## Section 3: Native OIDC via Cloudflare Workers and Pages Action

The official `cloudflare/wrangler-action` (v3.x) and `cloudflare/cloudflare-workers-and-pages`
action support OIDC natively when you set `apiToken: ''` and configure a Cloudflare Access
service token with the OIDC audience.

```yaml
# .github/workflows/deploy-native.yml
name: Deploy (native OIDC)

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Deploy Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          command: deploy --env production
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
```

When Cloudflare adds native OIDC federation (expected mid-2026 GA), the `apiToken` field
will accept an OIDC audience value and no secret will need to exist at all. Track
`developers.cloudflare.com/changelog` for the feature flag.

---

## Section 4: Branch and Environment Scoping Strategy

The power of OIDC is fine-grained trust. Map your deployment tiers to GitHub Environments
and encode them into allowed subjects:

```
# Staging: any branch in the repository
repo:org/myapp:ref:refs/heads/*

# Production: only the main branch, only in the production environment
repo:org/myapp:environment:production

# Release tag deploys only
repo:org/myapp:ref:refs/tags/v*
```

Implement required reviewers in GitHub Environments for production. This means even if
the OIDC exchange succeeds, a human must approve the workflow run before any deploy step
executes. OIDC + Environment protection rules = two independent controls.

```yaml
# GitHub Environment settings (configured in repo Settings → Environments)
# protection_rules:
#   - type: required_reviewers
#     reviewers:
#       - teams/platform-eng
#   - type: branch_policy
#     allowed_branches:
#       - main
```

---

## Section 5: Cloudflare Audit Log Correlation

Every Wrangler API call emits a Cloudflare audit log event. With OIDC-bound tokens, you
can correlate each deploy event back to a specific GitHub run.

Pass the GitHub run ID as a custom header or tag during deployment:

```typescript
// Custom deploy script that stamps metadata on the Worker
const deployMetadata = {
  github_run_id: process.env.GITHUB_RUN_ID,
  github_sha: process.env.GITHUB_SHA,
  github_actor: process.env.GITHUB_ACTOR,
  deployed_at: new Date().toISOString(),
};

// Write to a KV namespace as a deploy manifest
await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_ID}/values/last_deploy`,
  {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(deployMetadata),
  }
);
```

Then query Cloudflare audit logs filtered by the API token used:

```bash
curl -sH "Authorization: Bearer $CF_AUDIT_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/audit_logs?action.type=worker.script.update&since=$(date -d '24 hours ago' -u +%Y-%m-%dT%H:%M:%SZ)" \
  | jq '.result[] | {time: .when, actor: .actor.email, resource: .resource.name}'
```

---

## Section 6: Secret Hygiene Audit

Even after migrating to OIDC, verify no static tokens remain:

```bash
# Scan repository secrets for CF_ prefixed values (GitHub CLI)
gh secret list --repo org/myapp

# Check all environments
for env in staging production; do
  echo "=== $env ==="
  gh secret list --repo org/myapp --env "$env"
done

# Scan workflow files for hardcoded token patterns
grep -rE 'CF_API_TOKEN|cfApiToken|cloudflare_api_token' .github/workflows/
```

Also audit Cloudflare tokens for unused ones:
```bash
curl -sH "Authorization: Bearer $CF_AUDIT_TOKEN" \
  "https://api.cloudflare.com/client/v4/user/tokens" \
  | jq '.result[] | {id: .id, name: .name, status: .status, last_used: .last_used_on}'
```

---

## Anti-Patterns

- **Using `id-token: write` at the workflow level** instead of the job level. This grants
  OIDC to every job including third-party actions that should not have it. Always set
  `permissions` at the job level.
- **Trusting only the `repository` claim** without the `environment` claim. This allows
  any branch in the repo to deploy to production. Always require the `environment` claim
  for production targets.
- **Storing the exchanged token in `$GITHUB_ENV`** — it persists across steps and may be
  logged. Use `::add-mask::` and output via `$GITHUB_OUTPUT` with masking.
- **Wide-permission Cloudflare tokens** in the exchange worker. If the worker is compromised,
  the blast radius equals the token permissions. Scope tokens to the minimum: the target
  account, the target service, the target zone.
- **Not rotating the intermediate token** used by the exchange worker itself. That token is
  the only long-lived secret in the system and must be rotated quarterly.

---

## Gotchas

- GitHub OIDC tokens have a 5-minute validity window. The exchange must happen close to
  the deploy step in the same job.
- `ACTIONS_ID_TOKEN_REQUEST_URL` is only set when `id-token: write` is in scope. Workflows
  calling reusable workflows must explicitly pass the permission through.
- Cloudflare's Wrangler action re-fetches metadata on every run. If the token exchange
  happens in an earlier job, pass the token via a job output, not an artifact, to avoid
  filesystem exposure.
- When a GitHub Environment has a deployment wait timer, the OIDC token may expire before
  the workflow resumes. Re-request the token in the deploy step, not a preceding one.
- The `sub` claim format changed between GitHub Enterprise Server versions. Self-hosted
  runners on GHES may emit `enterprise:` prefixed subs.

---

## Verification Checklist

```bash
# 1. Confirm no CF_API_TOKEN secrets exist at org level
gh secret list --org yourorg | grep -i cloudflare

# 2. Confirm environment protection rules are enabled
gh api /repos/org/myapp/environments/production \
  | jq '.protection_rules'

# 3. Run a deploy dry-run and check Cloudflare audit logs for the run_id
GITHUB_RUN_ID=12345678
curl -sH "Authorization: Bearer $CF_AUDIT_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/audit_logs?since=2026-08-21T00:00:00Z" \
  | jq --arg rid "$GITHUB_RUN_ID" '.result[] | select(.metadata.github_run_id == $rid)'

# 4. Attempt to trigger a deploy from a non-production branch and verify it fails
git checkout -b test-oidc
git commit --allow-empty -m "OIDC test"
git push origin test-oidc
# Should get 403 from token exchange worker
```

---

## Related Articles

- `wrangler-toml-multi-environment-config.md` — environment-specific wrangler config
- `cloudflare-account-organization-team-access.md` — account-level permission boundaries
- `terraform-cloudflare-provider-workers-d1.md` — IaC deployments that also need tokens
- `secrets-rotation-runbook.md` — rotating the intermediate exchange token
- `workers-secrets-rotation-automation.md` — rotating Worker-bound secrets

---

## Sources

- GitHub OIDC documentation: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- Cloudflare API token scopes: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- `jose` library for JWT validation in Workers: https://github.com/panva/jose
- Wrangler Action GitHub OIDC support: https://github.com/cloudflare/wrangler-action
- GitHub Actions IP ranges meta API: https://api.github.com/meta
