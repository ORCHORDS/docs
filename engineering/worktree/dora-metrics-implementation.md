# dora-metrics-implementation

**Issue:** Teams don't know which DORA metrics to instrument or how to collect them accurately
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Leadership wants DORA metrics. Engineering doesn't know what counts as a "deployment" or "incident." Different teams measure differently. The resulting numbers aren't comparable and don't drive decisions.

## Pattern / Solution
DORA (DevOps Research and Assessment) defines four metrics that predict software delivery performance. Here's how to instrument them precisely.

**The four metrics + collection approach:**

**1. Deployment Frequency**
- Definition: How often code is deployed to production per day/week/month
- Source: CI/CD pipeline events (GitHub Actions, CircleCI deployment job completions)
- Count: Production deployments only; staging/preview don't count
- Tool: Query your deployment pipeline API or use LinearB / Faros / DORA Metrics Accelerator

**2. Lead Time for Change**
- Definition: Median time from first commit in a PR to production deployment
- Source: Git commit timestamp + deployment timestamp from CI
- Formula: `deploy_time - first_commit_time` (per PR/change set)
- Exclude: Hotfix lead time tracked separately

**3. Change Failure Rate**
- Definition: % of deployments that cause a production incident
- Source: Cross-reference deployment log with incident log
- Formula: `incidents_caused_by_deployment / total_deployments`
- Requires: Consistent incident tracking with "caused by deployment" flag

**4. Mean Time to Restore (MTTR)**
- Definition: Median time from incident start to service restoration
- Source: Incident management tool (PagerDuty, Opsgenie) timestamps
- Measure: `incident_resolved_at - incident_created_at`

**Performance benchmarks (2023 State of DevOps):**
| Metric | Elite | High | Medium | Low |
|--------|-------|------|--------|-----|
| Deploy frequency | On-demand (multiple/day) | 1/day–1/week | 1/week–1/month | < monthly |
| Lead time | < 1 hour | 1 day–1 week | 1 week–1 month | > 6 months |
| CFR | 0–5% | 5–10% | 10–15% | 15–45% |
| MTTR | < 1 hour | < 1 day | < 1 day | > 1 day |

## Gotchas
- Hotfixes skew MTTR and CFR — track them as a separate category for cleaner analysis
- Definition of "production" must be standardized (some teams have multiple prod envs)
- DORA metrics improve together — improving deployment frequency without reducing CFR is a red flag

## Related
- `developer-productivity-metrics.md`
- `space-framework-developer-experience.md`
- `ci-cd-pipeline-2026.md`
