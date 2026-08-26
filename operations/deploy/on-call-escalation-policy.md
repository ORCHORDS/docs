# on-call-escalation-policy

**Issue:** Rules for when and how to escalate an incident beyond the first responder
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without a clear escalation policy, responders either escalate too early (waking everyone up for a non-issue) or too late (letting a P1 drag on because they did not want to disturb senior engineers). A written policy removes judgment calls at 3 AM.

## Pattern / Solution
**Severity definitions**
| Severity | Definition | Response time | Escalation if no progress |
|---|---|---|---|
| P0 | Full outage / data loss / security breach | Immediate | 10 minutes |
| P1 | Degraded service affecting > 10% of users | 5 minutes | 20 minutes |
| P2 | Partial degradation, workaround exists | 30 minutes | 2 hours |
| P3 | Minor bug, no user impact | Next business day | — |

**Escalation chain**
```
Alert fires
  └─▶ Primary on-call (auto-paged)
        └─▶ No ack in 5 min → Secondary on-call (auto-paged by PagerDuty)
              └─▶ No resolution in 20 min (P1) / 10 min (P0) → Engineering Manager
                    └─▶ Data loss / security / prolonged P0 → CTO / CISO
```

**Communication during an incident**
1. Open an incident Slack channel `#inc-YYYY-MM-DD-<short-description>` within 5 minutes
2. Post an initial status update within 10 minutes (even "investigating, no update yet")
3. Post a brief update every 30 minutes until resolved
4. Post resolution summary within 1 hour of resolution

**Declaring resolution**
- Metrics back to baseline for ≥ 10 continuous minutes
- Root cause identified (even if not fully fixed)
- Mitigation or fix deployed
- Post-mortem ticket opened

## Gotchas
- PagerDuty schedules must be kept up to date — an on-call rotation with a vacant slot is a hidden risk
- Escalation should never feel punitive; frame it as getting more eyes, not assigning blame
- Always loop in the service owner even if they are not on-call — they have context no one else does
- "No update" updates are required; silence during an incident is worse than bad news

## Related
- `incident-runbook-template.md`
- `slo-alerting-thresholds.md`
- `post-deploy-monitoring-checklist.md`
