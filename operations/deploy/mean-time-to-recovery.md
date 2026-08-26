# mean-time-to-recovery

**Issue:** Measuring and reducing MTTR as a DORA metric for production incidents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
MTTR (mean time to recovery) measures how quickly a team restores service after an incident. Elite teams achieve under 1 hour; improvement requires both tooling and process changes.

## Pattern / Solution
MTTR calculation from incident records:
```sql
-- MTTR per service (last 90 days)
SELECT
  service,
  COUNT(*) AS incidents,
  AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))/60) AS avg_mttr_minutes,
  PERCENTILE_CONT(0.5) WITHIN GROUP (
    ORDER BY EXTRACT(EPOCH FROM (resolved_at - detected_at))/60
  ) AS median_mttr_minutes,
  MAX(EXTRACT(EPOCH FROM (resolved_at - detected_at))/60) AS max_mttr_minutes
FROM incidents
WHERE detected_at > NOW() - INTERVAL '90 days'
  AND severity IN ('P1', 'P2')
GROUP BY service
ORDER BY avg_mttr_minutes DESC;
```

Detection time reduction:
```yaml
# Datadog monitor — alert within 2 minutes of error rate spike
monitors:
  - name: "myapp error rate"
    type: metric alert
    query: "avg(last_2m):sum:myapp.http.errors{env:production}.as_rate() > 0.05"
    thresholds:
      critical: 0.05
    notify_no_data: false
    evaluation_delay: 60
```

Rollback automation to cut recovery time:
```bash
#!/bin/bash
# auto-rollback.sh — triggered by alert webhook
SERVICE=$1
PREVIOUS_TAG=$(git -C /repos/$SERVICE describe --tags --abbrev=0 HEAD~1)

echo "Rolling back $SERVICE to $PREVIOUS_TAG"
helm upgrade $SERVICE ./chart \
  --set image.tag=$PREVIOUS_TAG \
  --namespace production \
  --atomic \
  --timeout 5m

slack_notify "warning" "🔄 Auto-rollback: $SERVICE → $PREVIOUS_TAG"
```

MTTR improvement levers:
| Lever | Expected Impact |
|-------|----------------|
| Automated alerting (< 2 min detection) | -30-50% detection time |
| One-command rollback | -20-40% recovery time |
| Runbooks for top 10 incidents | -30% diagnosis time |
| On-call rotation < 5 people | -20% escalation time |
| Chaos engineering drills | -15% response confidence |

## Gotchas
- Measure time-to-detect separately from time-to-recover — they have different root causes
- MTTR averaged across P1 and P4 incidents is meaningless; segment by severity
- "Resolved" must be defined consistently (monitors green? users confirming? manual close?) — automate the definition
- Incidents that recur within 24h should be counted as one incident, not two

## Related
- `deployment-metrics-tracking.md`
- `change-failure-rate.md`
- `incident-runbook-template.md`
- `rollback-runbook.md`
- `post-incident-review-template.md`
