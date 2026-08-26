# GitHub Actions GITHUB_TOKEN permission minimization

**Issue:** A workflow grants its built-in GitHub token broad default permissions, so a compromised action or unsafe trigger can modify repository data beyond the job’s real purpose.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Decision

Set an explicit `permissions:` block for every workflow; grant only each job’s minimum access. Prefer the short-lived built-in `GITHUB_TOKEN` for same-repository operations. For cross-repository or broader automation, use a narrowly installed GitHub App with short-lived installation tokens rather than a personal token.

**Sources:**

- [Use GITHUB_TOKEN for authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [GitHub Actions workflow syntax: permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Apps and enterprise automation](https://docs.github.com/en/enterprise-cloud@latest/admin/concepts/enterprise-fundamentals/automations-in-your-enterprise)

## Pattern

```yaml
permissions: {}

jobs:
  test:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

  publish-attestation:
    permissions:
      contents: read
      attestations: write
      id-token: write
    runs-on: ubuntu-latest
```

Specifying a permission scope sets unspecified scopes to `none`. Put write access on the smallest job that needs it, not at workflow scope.

## Trigger boundary

Treat `pull_request_target` as privileged: it can receive a read/write `GITHUB_TOKEN` even for a public-fork trigger. Never check out, build, or execute untrusted pull-request code under that event with a writable token or deployment secret.

## Verification

- Workflow inventory records each job’s required token scopes and why.
- A test-only job has no write scope.
- A deliberate attempt to perform an unrelated GitHub API mutation fails.
- Fork-origin pull requests cannot reach deployment secrets or writable repository operations.
- Workflows needing wider access use a separately owned GitHub App installation, with its repository scope reviewed.

## Gotchas

- An action can access `github.token` even if it was not passed as an input; permissions—not omission from YAML—are the security boundary.
- `write-all` and inherited permissive defaults obscure capability review.
- `id-token: write` permits OIDC token minting, not repository write access, but must still be limited to jobs that exchange it.

## Related

- `github/github-actions-secrets-management.md`
- `github/github-actions-oidc-cloudflare.md`
- `github/actions-policy-sha-pinning-and-blocklists-2026.md`
- `cloudflare/api-token-least-privilege-and-rotation-governance.md`
