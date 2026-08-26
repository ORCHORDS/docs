# github-actions-oidc-cloudflare

**Issue:** Using GitHub Actions OIDC to authenticate to Cloudflare without storing long-lived tokens
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Storing `CLOUDFLARE_API_TOKEN` as a long-lived secret is a rotation burden and a blast-radius risk. GitHub Actions supports OIDC — the runner obtains a short-lived JWT that can be exchanged for a scoped token, with no static secret stored in the repo.

## Pattern / Solution
Cloudflare supports OIDC via Workload Identity Federation. The workflow requests an OIDC token; Cloudflare validates it and issues a scoped API token.

**Cloudflare side (one-time setup via API or dashboard):**
Configure an API token using the OIDC identity provider at `https://token.actions.githubusercontent.com` with the sub claim restricted to your repo and branch.

**Workflow:**
```yaml
name: Deploy to Cloudflare

on:
  push:
    branches: [main]

permissions:
  id-token: write      # required to request the OIDC JWT
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Obtain Cloudflare OIDC token
        uses: cloudflare/cloudflare-workers-action@v1   # or manual exchange below
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}          # until full OIDC support

      # Manual OIDC exchange pattern (when using Cloudflare Wrangler directly):
      - name: Deploy with Wrangler
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: deploy
```

**Manual OIDC JWT fetch and exchange:**
```yaml
      - name: Get OIDC token
        id: oidc
        run: |
          TOKEN=$(curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=cloudflare" | jq -r '.value')
          echo "::add-mask::$TOKEN"
          echo "token=$TOKEN" >> $GITHUB_OUTPUT

      - name: Exchange for CF token
        run: |
          CF_TOKEN=$(curl -X POST https://api.cloudflare.com/client/v4/iam/tokens/oidc \
            -H "Content-Type: application/json" \
            -d "{\"jwt\": \"${{ steps.oidc.outputs.token }}\"}" | jq -r '.result.token')
          echo "::add-mask::$CF_TOKEN"
          echo "CLOUDFLARE_API_TOKEN=$CF_TOKEN" >> $GITHUB_ENV
```

## Gotchas
- `permissions: id-token: write` must appear at workflow or job level — without it the `ACTIONS_ID_TOKEN_REQUEST_TOKEN` env var is absent
- The OIDC token is audience-scoped; requesting the wrong audience produces a token Cloudflare rejects
- Cloudflare's full OIDC federation support rollout is ongoing — check docs for current status before relying on the manual exchange in production
- OIDC tokens expire quickly (minutes) — never cache them across steps
- Fork PRs cannot request OIDC tokens for security reasons

## Related
- `github-actions-secrets-management.md`
- `github-actions-environment-protection.md`
- `github-fine-grained-personal-access-tokens.md`
