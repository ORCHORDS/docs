# change-failure-rate

**Issue:** Measuring and reducing the change failure rate (CFR) as a DORA metric
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Change failure rate (CFR) is the percentage of production deployments that cause an incident requiring immediate action (rollback, hotfix, or incident declaration). Elite teams achieve < 5%; poor performers exceed 30%.

## Pattern / Solution
CFR calculation:
```sql
-- CFR by service (last 30 days)
SELECT
  d.service,
  COUNT(d.id) AS total_deploys,
  COUNT(i.id) AS failing_deploys,
  ROUND(100.0 * COUNT(i.id) / COUNT(d.id), 1) AS cfr_pct
FROM deployments d
LEFT JOIN incidents i ON
  i.service = d.service
  AND i.detected_at BETWEEN d.deployed_at AND d.deployed_at + INTERVAL '2 hours'
  AND i.severity IN ('P1', 'P2')
WHERE d.environment = 'production'
  AND d.deployed_at > NOW() - INTERVAL '30 days'
GROUP BY d.service
ORDER BY cfr_pct DESC;
```

Linking deployments to incidents (automated):
```bash
# In incident webhook handler — correlate to recent deploy
INCIDENT_TIME=$1  # ISO8601
SERVICE=$2

LAST_DEPLOY=$(psql $DB -t -c "
  SELECT version, deployed_at
  FROM deployments
  WHERE service = '$SERVICE'
    AND environment = 'production'
    AND deployed_at < '$INCIDENT_TIME'
  ORDER BY deployed_at DESC
  LIMIT 1;
")

if [ -n "$LAST_DEPLOY" ]; then
  # Link in incident tracker
  curl -X POST "$INCIDENT_API/incidents/$INCIDENT_ID/links" \
    -d "{\"type\":\"deploy\",\"version\":\"$LAST_DEPLOY\"}"
fi
```

CFR reduction strategies:
```markdown
1. Automated testing — every PR must pass unit + integration tests
2. Canary deployments — 5% traffic for 15 min before full rollout
3. Feature flags — decouple deploy from release; toggle per user segment
4. Pre-production environment parity — staging mirrors production config
5. Load testing gate — performance regression blocks deploy
6. Automated rollback — trigger on error rate threshold breach
```

Alert on CFR trending up:
```yaml
# Prometheus alerting rule
- alert: HighChangeFailureRate
  expr: |
    (
      increase(incidents_total{severity=~"P1|P2",env="production"}[7d])
      /
      increase(deployments_total{env="production",status="success"}[7d])
    ) > 0.10
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "CFR > 10% — review deployment quality gates"
```

## Gotchas
- CFR requires a precise incident-to-deploy linkage window; 2-hour window is standard but varies by system
- A team with low deployment frequency can have 0% CFR with poor quality; always read CFR alongside frequency
- Hotfixes count as deployments AND as failures — they inflate both numerator and denominator
- Planned maintenance (database migrations with expected brief errors) should be excluded from CFR via incident tagging

## Related
- `deployment-metrics-tracking.md`
- `deployment-frequency-metrics.md`
- `mean-time-to-recovery.md`
- `canary-deployments.md`
