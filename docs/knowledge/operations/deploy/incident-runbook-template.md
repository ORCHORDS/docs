# incident-runbook-template

**Issue:** Standard template for writing service-specific incident runbooks that on-call engineers can execute under pressure
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
On-call engineers encountering an unfamiliar service incident waste time re-discovering diagnostic steps. A runbook pre-computes those steps so the responder can act within seconds of being paged.

## Pattern / Solution
Copy this template into `runbooks/<service-name>.md` and fill in each section.

```markdown
# Runbook: <Service Name>

## Service owner
Team: @team-name | On-call rotation: PagerDuty schedule link

## Quick links
- Dashboard: <Grafana/Datadog URL>
- Logs: <CloudWatch/Loki URL>
- Repo: <GitHub URL>
- Deployment: <Argo CD / ECS console URL>

## Alert inventory
| Alert name | Severity | Meaning | First action |
|---|---|---|---|
| HighErrorRate | P1 | 5xx > 1% for 5 min | Check logs for exception class |
| HighLatency | P2 | p99 > 2 s for 10 min | Check DB query plan |
| PodCrashLoop | P1 | Container restarting | `kubectl describe pod` |

## Diagnostic commands
```bash
# Tail live error logs
kubectl logs -l app=<service> -n prod --tail=100 -f | grep ERROR

# Check recent events
kubectl get events -n prod --sort-by='.lastTimestamp' | tail -20

# DB connection count
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"
```

## Known failure modes
### OOM killed
Symptom: `kubectl get events` shows OOMKilled
Fix: Scale HPA min replicas or increase memory limit in `k8s/deployment.yaml`

### DB connection pool exhaustion
Symptom: `FATAL: remaining connection slots are reserved`
Fix: Restart app pods to drain stale connections; check for connection leak in recent deploy

### Stuck migration job
Symptom: Deployment stuck at 0/1 ready
Fix: `kubectl describe job <migration-job>` → check logs → run migration manually if safe

## Escalation path
1. Page service owner (auto via PD)
2. If no ack in 5 min → page engineering manager
3. If data-loss risk → page CTO immediately
```

## Gotchas
- Runbooks go stale; review and update every quarter or after every P1 incident
- Commands must be copy-pasteable with no substitution required under pressure
- Include rollback link prominently — responders forget it exists when stressed
- Test the runbook in staging before the first real incident

## Related
- `on-call-escalation-policy.md`
- `rollback-runbook.md`
- `post-deploy-monitoring-checklist.md`
