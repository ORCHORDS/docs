# deployment-metrics-tracking

**Issue:** Instrumenting and tracking deployment pipeline metrics for DORA and operational insight
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams cannot improve what they do not measure. DORA metrics (deployment frequency, lead time, MTTR, change failure rate) require consistent instrumentation across the delivery pipeline.

## Pattern / Solution
Emit deploy events to a metrics store:
```bash
# In CI deploy step
emit_deploy_event() {
  local service=$1 version=$2 environment=$3 status=$4 duration_s=$5

  # Datadog event
  curl -X POST "https://api.datadoghq.com/api/v1/events" \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"title\": \"Deploy: $service $version → $environment\",
      \"text\": \"Status: $status | Duration: ${duration_s}s\",
      \"tags\": [\"service:$service\",\"env:$environment\",\"status:$status\"],
      \"alert_type\": \"$([ $status = success ] && echo info || echo error)\"
    }"

  # Also write to internal DB
  psql $METRICS_DB -c "
    INSERT INTO deployments (service, version, environment, status, duration_s, deployed_at, actor)
    VALUES ('$service','$version','$environment','$status',$duration_s,NOW(),'$CI_ACTOR');
  "
}
```

SQL queries for DORA metrics:
```sql
-- Deployment frequency (deploys per day, production only)
SELECT DATE(deployed_at) AS day, COUNT(*) AS deploys
FROM deployments
WHERE environment = 'production' AND status = 'success'
GROUP BY day ORDER BY day DESC LIMIT 30;

-- Lead time (time from commit to production deploy)
SELECT AVG(EXTRACT(EPOCH FROM (d.deployed_at - c.committed_at))/3600) AS lead_time_hours
FROM deployments d
JOIN commits c ON d.version = c.sha
WHERE d.environment = 'production' AND d.status = 'success'
AND d.deployed_at > NOW() - INTERVAL '30 days';

-- Change failure rate
SELECT
  COUNT(*) FILTER (WHERE status = 'failed') * 100.0 / COUNT(*) AS failure_rate_pct
FROM deployments
WHERE environment = 'production'
AND deployed_at > NOW() - INTERVAL '30 days';
```

Grafana dashboard panel (PromQL for Prometheus-stored events):
```promql
# Deployment frequency
increase(deployment_total{env="production",status="success"}[24h])

# Deployment success rate
rate(deployment_total{env="production",status="success"}[7d]) /
rate(deployment_total{env="production"}[7d])
```

## Gotchas
- Track both pipeline-triggered and manual (hotfix) deployments; manual deployments skew DORA metrics
- Lead time starts from commit timestamp, not PR merge — align definition across the team
- Distinguish "deployment failed" (infra/pipeline issue) from "deployment caused incident" (change failure)
- Aggregate per service, not only globally — one slow service masks high-performing ones

## Related
- `deployment-frequency-metrics.md`
- `mean-time-to-recovery.md`
- `change-failure-rate.md`
- `performance-baseline-tracking.md`
