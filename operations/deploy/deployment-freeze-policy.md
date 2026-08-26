# deployment-freeze-policy

**Issue:** When and how to enforce a deployment freeze to protect production stability during high-risk periods
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployments during holiday peaks, large marketing campaigns, or end-of-quarter processing windows carry disproportionate risk — fewer engineers are available to respond and the cost of an outage is highest. A formal freeze policy prevents ad-hoc deploys from slipping through.

## Pattern / Solution
**Standard freeze windows**
| Period | Duration | Scope |
|---|---|---|
| Major holiday (e.g. Black Friday) | 72 h before → 24 h after | All production services |
| Major product launch | Launch day ±12 h | All production services |
| End-of-quarter close | Last 3 business days | Finance-adjacent services |
| On-call staff reduction | Entire duration | All production services |

**What is blocked during a freeze**
- Any non-emergency application code deploy
- Database schema changes
- Infrastructure changes (Terraform applies, ECS task definition updates)
- Dependency upgrades

**What is allowed during a freeze**
- Hotfixes for active P0/P1 incidents (require two-engineer sign-off)
- Config changes via feature flags (not code deploy)
- Read-only infrastructure changes (dashboard updates, alert tuning)

**Enforcement mechanisms**
```yaml
# GitHub branch protection: require "freeze-exempt" label on PRs during freeze
# Use a GitHub Action that checks a repo variable

- name: Check deployment freeze
  run: |
    FREEZE=$(gh api /repos/$GITHUB_REPOSITORY/actions/variables/DEPLOY_FREEZE --jq '.value')
    if [ "$FREEZE" = "true" ]; then
      echo "::error::Deployment freeze is active. Label PR with freeze-exempt for emergencies."
      exit 1
    fi
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Gotchas
- Freeze must be declared with at least 5 business days notice to avoid blocking planned work
- "Hotfix exemption" must require explicit approval — not just the deployer's own judgment
- Infrastructure freezes are harder to enforce than code freezes; require Terraform plan review even during freeze
- Communicate freeze start/end to external vendors who may trigger deploys on your behalf

## Related
- `hotfix-process.md`
- `cab-change-management.md`
- `rollback-runbook.md`
