# deploy-gate-antipatterns

**Issue:** Deploy gate checking single workflow allows deploys past failing checks
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 316f773e
**Author:** the platform team
**Status:** fixed (316f773e)

## Symptom
Production deploys proceeded while CodeQL, gitleaks, or other required checks were still failing. The deploy gate showed green because it only verified one workflow.

## Root cause
The `get-conclusion` job in deploy workflows queried a single CI workflow's conclusion. Other required workflows (gitleaks, CodeQL) weren't checked. A push that passed lint+build but failed security scanning would deploy.

## Fix
Deploy gate now verifies ALL required workflows passed on the same HEAD SHA:

```yaml
- name: Verify all required checks passed
  run: |
    SHA=${{ github.sha }}
    for check in ci gitleaks; do
      conclusion=$(gh api "repos/$REPO/commits/$SHA/check-runs" \
        --jq ".check_runs[] | select(.name==\"$check\") | .conclusion" | head -1)
      if [ "$conclusion" != "success" ]; then
        echo "::error::Required check '$check' is $conclusion"
        exit 1
      fi
    done
```

## Verification
- **Test:** Deploy fails when gitleaks is red
- **CI:** PR #<number> green

## Gotchas
- Always check the same SHA — a push between the CI run and deploy gate could pass stale results
- GitHub status checks and check runs are different APIs — use the one your CI produces
- Duplicate migration steps in separate deploy workflows can race against the same DB. One workflow owns migrations.
- `--no-frozen-lockfile` in CI silently allows lockfile drift — always use `--frozen-lockfile`

## Related
- `lessons/example project-audit-2026-08.md`
- `deploy/trunk-based-development.md`
- `github/github-branch-protection.md`
