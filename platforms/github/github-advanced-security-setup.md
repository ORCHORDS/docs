# github-advanced-security-setup

**Issue:** Enabling GitHub Advanced Security (GHAS) features on a repository or organisation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GHAS bundles code scanning, secret scanning, and dependency review. It requires enablement at the repo or org level before alerts appear.

## Pattern / Solution
Via org settings (bulk enable):
1. Org Settings → Security → Code security → GitHub Advanced Security → Enable for all repositories.
2. Enable secret scanning and push protection across the org.

Via repository API:
```bash
gh api -X PATCH repos/:owner/:repo \
  -f security_and_analysis[advanced_security][status]=enabled \
  -f security_and_analysis[secret_scanning][status]=enabled \
  -f security_and_analysis[secret_scanning_push_protection][status]=enabled
```
Bulk enable with `gh` scripting:
```bash
gh api --paginate /orgs/myorg/repos -q '.[].name' | \
  xargs -I{} gh api -X PATCH repos/myorg/{} \
    -f security_and_analysis[advanced_security][status]=enabled
```

## Gotchas
- GHAS is included for public repositories; private repos require GitHub Enterprise or Team + GHAS add-on.
- Enabling on many repos simultaneously can generate a large volume of initial alerts.
- Code scanning requires a separate workflow (CodeQL) to produce results.
- Secret scanning push protection blocks commits containing secrets before they reach the remote.

## Related
- `github-ghas-code-scanning.md`
- `github-secret-scanning-custom-patterns.md`
- `github-dependabot-security-updates.md`
