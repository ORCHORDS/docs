# pre-production-checklist

**Issue:** Systematic checklist to verify a release is ready for production deployment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Release teams skip steps under pressure, causing avoidable incidents. A mandatory pre-production checklist provides a consistent gate regardless of who is deploying.

## Pattern / Solution
Pre-production checklist (copy to release tracking issue):

```markdown
## Pre-Production Checklist — [Service] [Version] [Date]

### Code & Tests
- [ ] All CI checks pass (unit, integration, e2e)
- [ ] No CRITICAL/HIGH CVEs in container scan
- [ ] Code review approved by ≥2 reviewers
- [ ] No TODO/FIXME comments in changed files (or tracked in issues)
- [ ] Database migrations reviewed and tested in staging

### Deployment
- [ ] Image tagged with Git SHA (not `latest`)
- [ ] Helm chart version bumped
- [ ] Deployment verified in staging with production-equivalent data
- [ ] Rollback procedure documented and tested (smoke test rollback in staging)
- [ ] Feature flags configured for staged rollout (if applicable)

### Configuration
- [ ] All required environment variables present in production
- [ ] Secrets rotated or confirmed current in secrets manager
- [ ] External service API keys valid and scoped correctly
- [ ] DNS changes (if any) propagated and verified

### Observability
- [ ] Health check endpoint responding in staging
- [ ] Metrics dashboards reviewed — no pre-existing anomalies
- [ ] Alerts configured for new features/endpoints
- [ ] Runbook updated for new failure modes

### Communication
- [ ] Stakeholders notified of deployment schedule
- [ ] On-call engineer aware and available
- [ ] Deployment freeze calendar checked
- [ ] Slack #deploys channel notification ready

### Sign-Off
- Deployer: ________________  Date: ________
- Reviewer: ________________  Date: ________
```

Automate checklist enforcement in CI:
```yaml
# .github/PULL_REQUEST_TEMPLATE/release.md
## Pre-Production Checklist
- [ ] CI passes
- [ ] Security scan clean
- [ ] Staging verified
- [ ] On-call notified
```

## Gotchas
- Checklists must be short enough to complete in under 5 minutes or they are skipped under pressure
- Digital checklists (GitHub PR template, Jira checklist) are auditable; paper/verbal checklists are not
- Review the checklist itself quarterly — stale items get rubber-stamped
- "Verified in staging" requires production-equivalent secrets and config, not toy values

## Related
- `deployment-approval-workflow.md`
- `deployment-verification-smoke-tests.md`
- `post-deploy-monitoring-checklist.md`
- `zero-downtime-deployment-checklist.md`
