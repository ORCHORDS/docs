# github-marketplace-actions-vetting

**Issue:** Evaluating the safety and reliability of third-party GitHub Marketplace actions before using them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Marketplace actions run in your CI environment with access to secrets. A malicious or abandoned action can exfiltrate credentials or break workflows.

## Pattern / Solution
Checklist before adopting a Marketplace action:
1. Verified creator badge — GitHub verifies the publisher's identity.
2. Star count and weekly downloads — proxies for community adoption.
3. Recent commit activity — abandon risk indicator.
4. Pin to a commit SHA, not a mutable tag:
```yaml
# Instead of:
uses: some/action@v3
# Pin to SHA:
uses: some/action@a1b2c3d4e5f67890abcdef1234567890abcdef12  # v3.1.0
```
5. Review the `action.yml` — check `runs.using`, input handling, and whether it calls external services.
6. Add to Dependabot for automatic update PRs:
```yaml
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
```
7. Restrict allowed actions in Org Settings → Actions → Allow select actions.

## Gotchas
- Tags like `@v3` are mutable — a compromised maintainer can push malicious code under the same tag.
- `uses: actions/*` and `uses: github/*` are from GitHub itself and are generally safe.
- Actions with `runs.using: docker` pull external images — check the image source.
- Minimise `GITHUB_TOKEN` permissions; check if the action needs elevated permissions.

## Related
- `github-actions-secrets-management.md`
- `github-organization-settings.md`
- `github-advanced-security-setup.md`
