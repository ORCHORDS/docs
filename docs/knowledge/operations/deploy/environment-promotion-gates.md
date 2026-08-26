# environment-promotion-gates

**Issue:** Automated quality gates that must pass before code promotes from dev → staging → production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without explicit promotion gates, broken code slides all the way to production unchecked. Promotion gates encode the team's quality bar into the pipeline and make it impossible to accidentally skip testing.

## Pattern / Solution
**Promotion pipeline**
```
PR merge → dev deploy → [gate] → staging deploy → [gate] → prod deploy
```

**Gate definitions by environment**

| Gate | Dev | Staging | Prod |
|---|---|---|---|
| Unit tests pass | Required | Required | Required |
| Integration tests pass | Optional | Required | Required |
| E2E smoke tests pass | — | Required | Required |
| Security scan (SAST) | Required | Required | Required |
| Dependency audit | — | Required | Required |
| Manual QA sign-off | — | Optional | Required for new features |
| Load test baseline | — | — | Required for infra changes |

**GitHub Actions promotion gate**
```yaml
promote-to-staging:
  needs: [test, security-scan]
  if: github.ref == 'refs/heads/main' && needs.test.result == 'success'
  environment:
    name: staging
    url: https://staging.example.com
  steps:
    - name: Deploy to staging
      run: ./scripts/deploy.sh staging

promote-to-prod:
  needs: [promote-to-staging, e2e-tests]
  if: needs.e2e-tests.result == 'success'
  environment:
    name: production
    url: https://example.com
  # GitHub will pause here for manual approval if configured
  steps:
    - name: Deploy to production
      run: ./scripts/deploy.sh production
```

**Manual approval gate (GitHub environments)**
```yaml
# In GitHub repo settings: Environments → production → Required reviewers
# The workflow pauses until a reviewer approves
```

## Gotchas
- `if:` conditions on jobs do not replace environment protection rules — both are needed
- Flaky tests undermine gate confidence; fix flaky tests before adding them to required gates
- A gate that takes > 20 minutes will be bypassed under pressure — optimize CI first
- Track gate failure rates; a gate that never fails provides no signal

## Related
- `feature-flag-deploy-coupling.md`
- `deployment-verification-smoke-tests.md`
- `zero-downtime-deployment-checklist.md`
- `ephemeral-preview-environments.md`
