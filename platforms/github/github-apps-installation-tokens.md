# github-apps-installation-tokens

**Issue:** Generating short-lived installation access tokens from a GitHub App for automation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Personal access tokens are tied to individuals. GitHub Apps produce short-lived tokens scoped to specific repos, making them safer for CI/CD pipelines.

## Pattern / Solution
```yaml
      - uses: actions/create-github-app-token@v1
        id: app-token
        with:
          app-id: ${{ vars.APP_ID }}
          private-key: ${{ secrets.APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}

      - uses: actions/checkout@v4
        with:
          token: ${{ steps.app-token.outputs.token }}
```
Generating manually via curl:
```bash
# 1. Create a JWT signed with the App private key (valid 10 min)
# 2. POST /app/installations/{id}/access_tokens
# Response: { "token": "ghs_...", "expires_at": "..." }
```

## Gotchas
- Installation tokens expire after 1 hour; re-request them if the workflow is long.
- The App must be installed on the target repository or org.
- Store the private key as a secret; it is a PEM file with newlines — use multi-line secret input.
- App tokens can be scoped to specific repositories within the installation.

## Related
- `github-fine-grained-personal-access-tokens.md`
- `github-actions-secrets-management.md`
