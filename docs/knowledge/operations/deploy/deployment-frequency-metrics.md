# deployment-frequency-metrics

**Issue:** Measuring deployment frequency as a DORA metric and improving it systematically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployment frequency is a leading indicator of team health. Elite teams deploy multiple times per day; low performers deploy monthly. Measuring frequency identifies bottlenecks in the delivery pipeline.

## Pattern / Solution
DORA benchmark tiers (2023):
| Tier | Frequency |
|------|-----------|
| Elite | Multiple times per day |
| High | Once per day to once per week |
| Medium | Once per week to once per month |
| Low | Less than once per month |

Query from deployment events table:
```sql
-- Daily frequency trend (last 90 days)
SELECT
  DATE_TRUNC('week', deployed_at) AS week,
  service,
  COUNT(*) AS deploys,
  COUNT(*) / 7.0 AS deploys_per_day
FROM deployments
WHERE environment = 'production'
  AND status = 'success'
  AND deployed_at > NOW() - INTERVAL '90 days'
GROUP BY week, service
ORDER BY week DESC;

-- Rolling 30-day frequency per service
SELECT
  service,
  COUNT(*) AS total_deploys,
  ROUND(COUNT(*) / 30.0, 2) AS per_day
FROM deployments
WHERE environment = 'production'
  AND status = 'success'
  AND deployed_at > NOW() - INTERVAL '30 days'
GROUP BY service
ORDER BY per_day DESC;
```

Grafana panel JSON (for Prometheus counter):
```json
{
  "expr": "increase(deployments_total{env='production',status='success'}[7d]) / 7",
  "legendFormat": "{{service}} deploys/day"
}
```

Common blockers and solutions:
| Blocker | Solution |
|---------|----------|
| Manual QA gate | Automate regression suite |
| Long build times | Parallelism, caching, split test suites |
| Feature branches living > 1 day | Trunk-based development, feature flags |
| Manual approval for every deploy | Approval only for high-risk changes |
| Fear of breaking production | Improve canary + rollback capability |

## Gotchas
- Counting deployments per calendar week flattens spikes; use rolling windows for accuracy
- Distinguish service deployments from infrastructure changes — both matter but are different signal
- High frequency without quality metrics is meaningless — track alongside change failure rate
- A team deploying 20x/day all to one microservice may have a monolith decomposition problem, not a deployment win

## Related
- `deployment-metrics-tracking.md`
- `change-failure-rate.md`
- `mean-time-to-recovery.md`
- `trunk-based-development.md`
