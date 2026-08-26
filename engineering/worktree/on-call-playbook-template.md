# on-call-playbook-template

**Issue:** On-call engineers spend the first 20 minutes of an incident figuring out where to look
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An alert fires at 2am. The on-call engineer doesn't own this service. They dig through Slack history, ping sleeping teammates, and eventually find the runbook buried in a Confluence page last edited two years ago. MTTR explodes.

## Pattern / Solution
Every service must have a playbook living alongside the code in `docs/oncall/SERVICE.md`.

**Playbook template:**
```markdown
# On-Call Playbook: [Service Name]

**Owner team:** @team-name
**Escalation path:** @oncall → @team-lead → @director
**Slack channel:** #service-alerts
**Dashboards:** [Grafana link] | [DataDog link]
**Runbooks index:** [link]

## Service Overview
One paragraph: what does this service do and who depends on it?

## Alert Inventory
| Alert Name | Severity | First Action | Runbook Link |
|------------|----------|--------------|--------------|
| HighErrorRate | P1 | Check logs, then runbook | [link] |

## Common Failure Modes
### Symptom: DB connection pool exhausted
- Check: `SELECT count(*) FROM pg_stat_activity`
- Fix: Restart service pod; file ticket for pool sizing

### Symptom: Memory OOM
- Check: k8s events `kubectl describe pod`
- Fix: Rolling restart, then investigate heap dump

## Escalation Decision Tree
- Alert firing > 5 min AND users impacted → declare incident
- Not sure if users are impacted → check [synthetic monitor link]

## Recovery Verification
List of checks that confirm the service is healthy post-fix.

## Post-Incident
Link to postmortem template.
```

**Maintenance:**
- Playbook must be updated as part of any on-call ticket that reveals a gap
- Quarterly review: verify all dashboard and runbook links still work

## Gotchas
- Playbooks rot fast — link to live dashboards, never screenshot them
- "Escalate to X" must name a real person or rotation, not a team alias that nobody checks
- Keep the "first action" column to one sentence — on-call brains are not at full capacity

## Related
- `incident-commander-role.md`
- `postmortem-writing-guide.md`
- `engineering-kpis-dashboard.md`
