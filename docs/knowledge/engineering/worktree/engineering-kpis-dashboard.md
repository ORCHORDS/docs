# engineering-kpis-dashboard

**Issue:** Engineering metrics are scattered across five tools and nobody looks at them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
DORA metrics are in LinearB. Test coverage is in Codecov. Incidents are in PagerDuty. PR cycle time is calculated from GitHub manually once a quarter. Leadership asks for a health summary and the EM spends three hours stitching it together.

## Pattern / Solution
Build a single engineering KPI dashboard that aggregates the most important signals and makes them visible weekly.

**Dashboard sections:**

**1. Delivery health (DORA)**
- Deployment frequency (target: daily)
- Lead time for change (target: < 24h)
- Change failure rate (target: < 5%)
- MTTR (target: < 1h)

**2. Quality signals**
- Open P1/P2 bugs (target: 0 P1s; < 3 P2s)
- Test coverage trend (direction matters more than absolute number)
- Build success rate (target: > 95%)
- PR cycle time (target: < 24h from open to merge)

**3. Team health**
- On-call page volume (pages/engineer/week; target: < 2)
- Sprint carry-over rate (target: < 15%)
- Tech debt allocation (% of sprint; target: 15-20%)

**4. Developer experience (quarterly)**
- SPACE survey score
- Build time (target: < 10 min)
- Environment setup time for new hires (target: < 1 day)

**Tooling options:**
- Lightweight: Notion/Confluence table updated weekly by EM
- Medium: Datadog dashboard pulling from GitHub + PagerDuty APIs
- Full: LinearB or Faros for automated DORA + engineering analytics

**Alerting:**
Set threshold alerts for any metric that crosses from green to yellow. Don't wait for quarterly reviews to notice a trend.

## Gotchas
- Dashboards with > 15 metrics get ignored — keep it to 8-10 key signals
- Automate data collection; manual dashboards go stale within two weeks
- Never display individual-level metrics on a team dashboard

## Related
- `dora-metrics-implementation.md`
- `developer-productivity-metrics.md`
- `space-framework-developer-experience.md`
- `stakeholder-update-template.md`
