# post-deploy-monitoring-checklist

**Issue:** What to watch on dashboards for the first 30 minutes after every production deployment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Many regressions are invisible at deploy time and surface gradually as traffic hits new code paths. A structured 30-minute watch window catches regressions before they breach SLOs.

## Pattern / Solution
**T+0 to T+5 min — critical signals**
- [ ] HTTP 5xx error rate < baseline (last 7-day p95)
- [ ] HTTP 4xx rate unchanged (a spike means a route broke or auth changed)
- [ ] P99 latency ≤ 1.5× pre-deploy baseline
- [ ] Pods/tasks all in Running/ACTIVE state
- [ ] No OOMKilled events (`kubectl get events --field-selector reason=OOMKilling`)

**T+5 to T+15 min — business metrics**
- [ ] Conversion funnel completion rate unchanged
- [ ] Payment / checkout success rate unchanged
- [ ] Queue depth stable (SQS / Kafka consumer lag not growing)
- [ ] Database connection pool utilization < 80%
- [ ] Cache hit rate not dropped (a cache key change can tank hit rate)

**T+15 to T+30 min — secondary signals**
- [ ] Background job throughput unchanged
- [ ] Third-party webhook delivery success rate normal
- [ ] CDN cache-hit ratio stable (a cache-control header change can shift this)
- [ ] Log volume not spiking (a noisy log = runaway error loop)

**Escalation trigger**
If any critical signal is red for > 2 minutes after deploy, initiate rollback without waiting for root cause.

```
Deploy ──5 min──▶ Check critical ──10 min──▶ Check business ──15 min──▶ Check secondary
                       │                           │
                  ALERT → rollback            ALERT → rollback
```

## Gotchas
- Compare against the same hour last week, not just the last 5 minutes (traffic is time-of-day dependent)
- Autoscaling can mask a latency spike — check per-instance metrics, not aggregate
- A deploy that adds a new metric will show a "spike from zero" — exclude new metrics from baselines
- On-call engineer must stay available for the full 30-minute window, not hand off immediately after pod readiness

## Related
- `deployment-verification-smoke-tests.md`
- `slo-alerting-thresholds.md`
- `synthetic-monitoring-deploy.md`
- `incident-runbook-template.md`
