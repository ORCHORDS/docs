# github-actions-secrets-management

**Issue:** How to manage secrets in GitHub Actions across repos, environments, and orgs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Secrets scattered across repo settings, environment configs, and org level cause inconsistency. Teams struggle with secret rotation, scoping, and auditing which workflows can access what.

## Pattern / Solution
GitHub Actions secrets exist at three levels — org, repo, and environment — with increasing specificity overriding broader scope.

**Org-level secret (available to selected repos):**
```yaml
# In workflow — just reference it; no special config needed
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.ORG_DEPLOY_TOKEN }}" | somecommand
```

**Environment-scoped secret (requires environment match):**
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production          # gates access to production secrets
    steps:
      - run: ./deploy.sh
        env:
          API_KEY: ${{ secrets.PROD_API_KEY }}
```

**Secret rotation pattern — use `gh` CLI:**
```bash
gh secret set MY_SECRET --body "newvalue" --repo owner/repo
# Or for environment secrets:
gh secret set MY_SECRET --body "newvalue" --env production --repo owner/repo
```

**Masking custom values at runtime:**
```yaml
- name: Mask derived token
  run: |
    TOKEN=$(generate-token.sh)
    echo "::add-mask::$TOKEN"
    echo "RUNTIME_TOKEN=$TOKEN" >> $GITHUB_ENV
```

## Gotchas
- Secrets are never printed in logs but can be exfiltrated via malicious third-party actions — pin actions to full commit SHA, not a tag
- Environment secrets only flow to jobs that declare `environment:` — a missing environment key silently gets the non-environment value (or nothing)
- `GITHUB_TOKEN` cannot trigger other workflow runs by default; use a PAT or GitHub App token when cross-workflow triggers are needed
- Org secrets set to "selected repositories" don't automatically include new repos — you must add each one
- Secret names are case-insensitive in the UI but case-sensitive in `${{ secrets.NAME }}` expressions

## Related
- `github-actions-environment-protection.md`
- `github-actions-oidc-cloudflare.md`
- `github-fine-grained-personal-access-tokens.md`
