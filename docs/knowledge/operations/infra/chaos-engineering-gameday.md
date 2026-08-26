# chaos-engineering-gameday

**Issue:** Running chaos experiments and game days to validate system resilience assumptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Disaster recovery procedures documented but never tested. Failover assumed to work but untested since initial setup. Team confidence in resilience based on design, not evidence.

## Pattern / Solution
Chaos experiment structure (Chaos Engineering principles):
```
1. Define steady state: what does normal look like?
   e.g. p99 latency < 200ms, error rate < 0.1%

2. Hypothesize: what do we expect to happen during the experiment?
   e.g. "RDS failover will complete in 60s with < 5% error spike"

3. Inject failure: as close to production as safely possible

4. Observe: did steady state hold? Where did it break?

5. Fix or accept: remediate weaknesses found, or consciously accept the risk
```

AWS Fault Injection Simulator:
```hcl
resource "aws_fis_experiment_template" "rds_failover" {
  description = "Force RDS Multi-AZ failover"
  role_arn    = aws_iam_role.fis.arn

  stop_condition {
    source = "aws:cloudwatch:alarm"
    value  = aws_cloudwatch_alarm.error_rate_high.arn
  }

  action {
    name        = "failover-rds"
    action_id   = "aws:rds:failover-db-cluster"
    resource {
      type        = "aws:rds:cluster"
      arns        = [aws_rds_cluster.main.arn]
    }
  }
}
```

Game day runbook template:
```markdown
## Game Day: [Scenario Name] — [Date]

**Hypothesis:** [What we expect to happen]
**Steady State:** [Metrics that define normal — attach dashboard]
**Blast Radius:** [What could break, who is affected]
**Rollback Plan:** [How to stop experiment and restore immediately]
**Observers:** [Who watches each system]

### Timeline
HH:MM — Baseline metrics captured
HH:MM — Experiment begins
HH:MM — [Observation notes]
HH:MM — Experiment ended / rolled back

### Findings
- Expected: ...
- Actual: ...
- Gaps discovered: ...

### Action Items
- [ ] Fix: ... (owner, due date)
```

Common experiments:
- Kill random pods (`kubectl delete pod -l app=api --field-selector=status.phase=Running`)
- Inject latency (`tc qdisc add dev eth0 root netem delay 100ms`)
- Fill disk (`fallocate -l 10G /tmp/filler`)
- Terminate primary DB instance

## Gotchas
- Never run chaos in production without blast radius analysis and rollback plan
- Start small — kill one instance, not all. Graduate to region-level failures
- Inform on-call team before experiments — don't create false incident pages
- Automated experiments (GameDays scheduled weekly) are more valuable than one-time events

## Related
- `incident-war-room-setup.md`
- `post-mortem-blameless-template.md`
- `sre-error-budget-policy.md`
