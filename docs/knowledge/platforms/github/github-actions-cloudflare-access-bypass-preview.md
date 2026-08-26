# GitHub Actions: Bypass Cloudflare Access for CI Preview Deployments

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Preview deployments protected by Cloudflare Access return HTTP 302 → login redirects when hit by automated smoke tests, blocking CI pipelines.
This article shows how to create a Cloudflare Access Service Token and use it from GitHub Actions to authenticate non-interactive CI requests.

## Context
Cloudflare Access enforces identity checks in front of Workers, Pages, and tunneled origins.
Service Tokens are machine credentials (Client ID + Client Secret) that bypass Access policies — scoped to specific applications and revocable at any time.
In GitHub Actions, the secrets are injected as environment variables and passed via `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers on every request to the protected endpoint.

---

## Create the Service Token (Terraform / manual)

Provision via the Cloudflare API or Terraform to keep it in source control:

```hcl
# infra/cloudflare-access.tf
resource "cloudflare_access_service_token" "ci_preview" {
  account_id = var.cloudflare_account_id
  name       = "github-actions-ci-preview"
  # Token duration; max 365 days; rotate before expiry
  min_days_for_renewal = 30
}

resource "cloudflare_access_policy" "allow_ci" {
  application_id = cloudflare_access_application.preview.id
  zone_id        = var.zone_id
  name           = "Allow CI Service Token"
  precedence     = 1
  decision       = "non_identity"

  include {
    service_token = [cloudflare_access_service_token.ci_preview.id]
  }
}

output "ci_client_id" {
  value     = cloudflare_access_service_token.ci_preview.client_id
  sensitive = false
}
output "ci_client_secret" {
  value     = cloudflare_access_service_token.ci_preview.client_secret
  sensitive = true
}
```

Store the outputs as `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` in GitHub repository or environment secrets.

---

## Use the Service Token in GitHub Actions

```yaml
# .github/workflows/preview-smoke-test.yml
name: Preview Smoke Test

on:
  deployment_status:

jobs:
  smoke-test:
    if: github.event.deployment_status.state == 'success'
    runs-on: ubuntu-latest

    env:
      PREVIEW_URL: ${{ github.event.deployment_status.target_url }}
      CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
      CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}

    steps:
      - uses: actions/checkout@v4

      - name: Wait for DNS propagation
        run: sleep 10

      - name: Smoke test — health endpoint
        run: |
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
            -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
            "$PREVIEW_URL/api/health")
          echo "HTTP status: $STATUS"
          [ "$STATUS" -eq 200 ] || (echo "Health check failed" && exit 1)

      - name: Smoke test — authenticated JSON endpoint
        run: |
          BODY=$(curl -sf \
            -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
            -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
            "$PREVIEW_URL/api/version")
          echo "$BODY" | jq -e '.version' || (echo "Version endpoint malformed" && exit 1)
```

---

## Playwright E2E with Access Headers

Inject headers globally so every Playwright request is authenticated:

```typescript
// playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: {
    baseURL: process.env.PREVIEW_URL,
    extraHTTPHeaders: {
      'CF-Access-Client-Id': process.env.CF_ACCESS_CLIENT_ID ?? '',
      'CF-Access-Client-Secret': process.env.CF_ACCESS_CLIENT_SECRET ?? '',
    },
  },
});
```

```yaml
      - name: E2E tests against preview
        env:
          PREVIEW_URL: ${{ github.event.deployment_status.target_url }}
          CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
          CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}
        run: npx playwright test --project=chromium
```

---

## Rotating the Service Token Before Expiry

```yaml
# .github/workflows/rotate-cf-access-token.yml
name: Rotate CF Access Service Token

on:
  schedule:
    - cron: '0 9 1 * *'   # monthly, check for tokens expiring within 30 days

jobs:
  rotate:
    runs-on: ubuntu-latest
    steps:
      - name: Refresh token via Cloudflare API
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          SERVICE_TOKEN_ID: ${{ secrets.CF_ACCESS_SERVICE_TOKEN_ID }}
        run: |
          curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/service_tokens/$SERVICE_TOKEN_ID/refresh" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json" \
            | jq '.success'
```

---

## Anti-patterns
- Committing `client_id` / `client_secret` in workflow YAML or `.env` files — rotate immediately if leaked.
- Reusing one service token across all environments (staging, preview, production) — create per-environment tokens with least-privilege Access policies.
- Skipping the `non_identity` decision type in the Access policy — `bypass` disables Access entirely for the matched source, which is broader than intended.
- Not setting an expiry on the service token — tokens without rotation are a long-lived credential risk.
- Using the service token secret in `run:` steps where it may appear in logs — always pass via `-H` flags or as env vars masked by GitHub secrets.

## Gotchas
- The `CF-Access-Client-Id` header key is exact; case matters in some proxies but Cloudflare's edge is case-insensitive.
- `deployment_status` events fire for every deployment tool (Vercel, Netlify, Wrangler); filter by `github.event.deployment_status.environment` if the workflow should only run for Cloudflare Pages deployments.
- Playwright's `extraHTTPHeaders` applies to `page.goto()` navigations AND API calls from `request` fixtures, but NOT to service workers or `fetch()` calls made inside the browser context.
- Service token refresh extends the expiry but does NOT rotate the `client_secret`; a full regeneration (delete + recreate) is needed to cycle the secret.
- In GitHub Actions, the GITHUB_TOKEN cannot write secrets back to the repo; use a PAT or GitHub App token to update secrets after rotation.

## Verification
```bash
# Test locally that the service token bypasses Access
curl -I \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  "https://preview.example.com/api/health"
# Expected: HTTP 200 (not 302 or 403)

# Confirm token validity and expiry via API
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/service_tokens" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | select(.name=="github-actions-ci-preview") | {expires_at, client_id}'
```

## Related
- `github-actions-cloudflare-pages-preview-comment.md`
- `github-actions-workers-preview-environments.md`
- `github-actions-oidc-cloudflare.md`
- `github-actions-e2e-playwright.md`

## Sources
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- https://developers.cloudflare.com/cloudflare-one/policies/access/non-identity/
- https://developers.cloudflare.com/api/operations/access-service-tokens-create-a-service-token
- https://playwright.dev/docs/api/class-apirequestcontext#api-request-context-fetch
