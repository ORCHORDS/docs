# github-actions-oidc-cloudflare-deploy

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) CI stores a `CLOUDFLARE_API_TOKEN` secret with `Zone:Edit` and `Workers Scripts:Edit` permissions. The token never rotates, every repository contributor can trigger a deploy that uses it, and a leaked token gives an attacker persistent write access to all Workers and DNS zones until manually revoked. The team wants zero-rotation credentials with a blast radius limited to the specific Worker and environment being deployed.

## Context

GitHub Actions OIDC (OpenID Connect) lets a workflow job request a short-lived signed JWT from GitHub's identity provider (`https://token.actions.githubusercontent.com`) and exchange it for a scoped, time-limited credential from a cloud provider. Cloudflare supports OIDC-based API token issuance via Workload Identity Federation. The resulting token is valid for minutes, scoped to specific resources, and never stored anywhere — no rotation, no secret sprawl. This replaces the `CLOUDFLARE_API_TOKEN` secret entirely for deploy workflows targeting the Cloudflare account.

## GitHub OIDC token mechanics

GitHub's OIDC provider issues a JWT per workflow job when the job has `id-token: write` permission. The JWT contains standard OIDC claims plus GitHub-specific claims:

| Claim | Example value | Purpose |
|---|---|---|
| `iss` | `https://token.actions.githubusercontent.com` | Issuer; Cloudflare validates this |
| `sub` | `repo:example project-app/example project:environment:production` | Subject; used for policy binding |
| `aud` | `cloudflare` (caller-set) | Audience; must match Cloudflare's expectation |
| `ref` | `refs/heads/main` | Git ref that triggered the job |
| `event_name` | `push` | Triggering event |
| `environment` | `production` | GitHub Actions environment name |
| `sha` | `abc123...` | Commit SHA |

The `sub` claim format is `repo:{owner}/{repo}:ref:refs/heads/{branch}` for branch triggers, or `repo:{owner}/{repo}:environment:{name}` when an environment is used. Cloudflare policy bindings filter on `sub` to restrict which repos/branches can exchange tokens.

## Cloudflare Workload Identity Federation setup

One-time Cloudflare configuration (dashboard or API):

1. Navigate to **My Profile → API Tokens → Create Token**.
2. Select "Custom token" — do NOT use API key.
3. Under **Permissions**, add: `Account:Cloudflare Workers Scripts:Edit`, `Zone:Workers Routes:Edit` (scope to specific zone/account).
4. Under **Client IP Address Filtering**, leave blank (OIDC exchange IPs vary).
5. Under **TTL**, set to match expected deploy window (e.g. 15 minutes).
6. Under **Identity Federation** (preview / Workload Identity) section: set Issuer to `https://token.actions.githubusercontent.com`, Subject pattern to `repo:example project-app/example project:environment:production`.

Cloudflare's API endpoint for OIDC token exchange (when federation is configured):

```
POST https://api.cloudflare.com/client/v4/accounts/{account_id}/tokens/exchange
Content-Type: application/json
{ "oidc_token": "<github-jwt>" }
```

## Workflow permissions block

The `permissions` block must appear at the **job level** or **workflow level** and must include `id-token: write`. Without it, the `ACTIONS_ID_TOKEN_REQUEST_TOKEN` environment variable is not set and the token request fails silently.

```yaml
name: Deploy example project Worker

on:
  push:
    branches: [main]

permissions:
  contents: read        # minimum for checkout
  id-token: write       # REQUIRED: request OIDC JWT from GitHub

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production   # sets sub claim to repo:...:environment:production
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Request GitHub OIDC token
        id: oidc
        run: |
          TOKEN=$(curl --silent --fail \
            -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=cloudflare" \
            | jq -r '.value')
          echo "::add-mask::$TOKEN"
          echo "token=$TOKEN" >> $GITHUB_OUTPUT

      - name: Exchange for Cloudflare API token
        id: cf-token
        env:
          CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          OIDC_JWT: ${{ steps.oidc.outputs.token }}
        run: |
          CF_API_TOKEN=$(curl --silent --fail \
            -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/tokens/exchange" \
            -H "Content-Type: application/json" \
            -d "{\"oidc_token\": \"${OIDC_JWT}\"}" \
            | jq -r '.result.token')
          echo "::add-mask::$CF_API_TOKEN"
          echo "cf_token=$CF_API_TOKEN" >> $GITHUB_OUTPUT

      - name: Deploy with Wrangler
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.cf-token.outputs.cf_token }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env production
```

## cloudflare/wrangler-action OIDC integration

As of wrangler-action v3.x, OIDC can be passed directly when Workload Identity Federation is configured on the Cloudflare side. If the action adds native OIDC support, the exchange step collapses:

```yaml
      - name: Deploy with Wrangler (native OIDC)
        uses: cloudflare/wrangler-action@v3
        with:
          # No apiToken needed when OIDC federation is configured
          accountId: ${{ vars.CF_ACCOUNT_ID }}
          command: deploy --env production
          # wrangler-action will request the OIDC token internally
          # if apiToken is absent and id-token: write is set
```

Check the wrangler-action release notes before relying on this — OIDC support availability varies by version. Pin to a specific tag (`@v3.14.0`) rather than the floating `@v3` to avoid surprise behaviour changes.

## Audience and subject claim scoping

Restricting `sub` to a specific GitHub environment is the most important security control:

```
repo:example project-app/example project:environment:production   ← only production environment jobs
repo:example project-app/example project:ref:refs/heads/main      ← only main branch (no env)
repo:example project-app/example project:*                        ← any job in this repo (too broad)
```

Use the narrowest `sub` pattern that satisfies the deploy scenario. Production deploys should always be bound to a named environment so the `environment:production` sub claim is used. Without an environment, the sub falls back to the ref, which can be triggered from any branch with write access.

## Anti-patterns

- Setting `id-token: write` at the workflow level when only one job needs it — other jobs in the workflow gain token request capability unnecessarily. Set it at the job level.
- Using `audience=https://token.actions.githubusercontent.com` (the issuer) as the audience — the audience should be `cloudflare` or the specific audience Cloudflare's federation endpoint expects.
- Logging the OIDC JWT or the Cloudflare API token to stdout without `::add-mask::` — they appear in plaintext in the Actions log and are readable by anyone with log access.
- Binding Cloudflare policy to `repo:example project-app/example project:*` — any branch or workflow in the repo can deploy to production.
- Omitting the `environment:` key on the deploy job — the `sub` claim falls back to the ref form, breaking policy bindings that expect `environment:production`.

## Gotchas

- `ACTIONS_ID_TOKEN_REQUEST_TOKEN` and `ACTIONS_ID_TOKEN_REQUEST_URL` are only set when `id-token: write` is in scope. A missing permission produces a blank env var, and the curl fails with a 401 — the error message does not mention permissions.
- Fork PRs cannot request OIDC tokens regardless of permissions — GitHub strips `id-token: write` for security. Deploy workflows triggered by `pull_request` from forks will silently lose OIDC capability.
- Cloudflare's Workload Identity Federation (OIDC token exchange endpoint) was in beta/preview as of mid-2026 — confirm GA status before treating it as production-stable.
- The exchanged Cloudflare token inherits the TTL set on the Cloudflare side, not GitHub's JWT TTL. If the Cloudflare token TTL is shorter than the deploy step duration, Wrangler will receive 401 mid-deploy.
- `::add-mask::` only masks the exact string passed to it. If the OIDC JWT is base64 with no padding, the masked value may differ from what appears in logs if jq normalizes it.

## Verification

```bash
# Verify the OIDC token contains expected claims
echo "$OIDC_JWT" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{sub, aud, iss, environment}'
```

Expected output for a production environment deploy:
```json
{
  "sub": "repo:example project-app/example project:environment:production",
  "aud": ["cloudflare"],
  "iss": "https://token.actions.githubusercontent.com",
  "environment": "production"
}
```

After the exchange step, verify the Cloudflare token is scoped correctly:
```bash
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  https://api.cloudflare.com/client/v4/user/tokens/verify | jq '.result'
```

The response should show `"status": "active"` and list only the permission groups configured in the Workload Identity policy.

## Related

- `github-actions-oidc-cloudflare.md`
- `github-actions-secrets-management.md`
- `github-actions-environment-protection.md`
- `github-actions-immutable-oidc-subject-claims.md`
- `github-actions-id-token-permission-job-scope.md`
- `github-actions-cloudflare-deploy-workflow.md`

## Sources

- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- https://github.com/cloudflare/wrangler-action
- https://token.actions.githubusercontent.com/.well-known/openid-configuration
