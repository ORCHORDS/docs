# alerting-fatigue-reduction

**Issue:** Reducing noisy, non-actionable alerts that cause on-call burnout
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
On-call engineers acknowledge and silence alerts without investigating. Alert volume makes it impossible to distinguish signal from noise. Critical pages ignored because "it always fires".

## Pattern / Solution
Alert quality criteria (every alert must pass all):
```
1. Actionable: engineer knows what to do when it fires
2. Urgent: requires human attention within the response time
3. Novel: not already covered by a higher-level alert
4. Correct: fires when there is a real problem, rarely when there isn't
```

Alert audit — quantify noise:
```bash
# Prometheus: find alerts firing most frequently
curl -s 'http://alertmanager:9093/api/v1/alerts' | \
  jq '[.data[] | {alertname: .labels.alertname}] | group_by(.alertname) | map({name: .[0].alertname, count: length}) | sort_by(-.count)[:20]'
```

Reduce alert volume tactics:
```yaml
# 1. Use symptom-based alerts (user impact) not cause-based
# BAD: high CPU
- alert: HighCPU
  expr: cpu_usage > 80

# GOOD: latency affecting users
- alert: HighLatency
  expr: http_request_duration_p99 > 0.5

# 2. Require sustained condition (for)
- alert: DatabaseConnectionPoolExhausted
  expr: db_pool_available_connections < 5
  for: 5m   # not a transient spike

# 3. Group related alerts in Alertmanager
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s       # wait before first notification (more may join)
  group_interval: 5m    # interval between grouped notifications
  repeat_interval: 4h   # re-notify if still firing

# 4. Inhibit low-level alerts when high-level fires
inhibit_rules:
- source_match:
    alertname: ClusterDown
  target_match_re:
    alertname: .*
  equal: [cluster]
```

## Gotchas
- Never page for anything that auto-recovers in < 5 minutes without human action
- `for: 0m` triggers immediately on any single sample — almost always too aggressive
- Silencing is a symptom; fixing the alert or root cause is the cure
- Track mean time to acknowledge (MTTA) and time to resolve (MTTR) by alert to prioritize improvements

## Related
- `monitoring-sla-slo-sli.md`
- `prometheus-alertmanager-config.md`
- `incident-war-room-setup.md`
