# incident-war-room-setup

**Issue:** Structuring an incident war room for effective coordination and fast resolution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
During incidents, multiple people debug the same thing, no one tracks what's been tried, communication is chaotic, and customers wait for updates that never come.

## Pattern / Solution
Role assignments (assign immediately, not during chaos):
```
Incident Commander (IC):    coordinates, owns timeline, calls all-clear
Technical Lead:             drives diagnosis and fix — one voice for decisions
Comms Lead:                 external/internal status updates
Scribe:                     real-time log of what happened and when
Subject Matter Experts:     called in as needed, IC-controlled
```

War room Slack channel structure:
```
#incident-YYYY-MM-DD-N    (main coordination)
#incident-N-comms         (customer-facing updates only)
```

Incident timeline template (Scribe uses this):
```
[HH:MM UTC] INCIDENT OPENED - IC: @alice, Tech Lead: @bob
[HH:MM UTC] Symptom: API error rate 15%, latency p99 8s (normal: 200ms)
[HH:MM UTC] Hypothesis 1: DB connection pool exhausted — checking...
[HH:MM UTC] RULED OUT: pool at 50% capacity
[HH:MM UTC] Hypothesis 2: bad deploy at 14:32 — checking diff...
[HH:MM UTC] CONFIRMED: deploy v1.4.2 introduced N+1 query in /orders
[HH:MM UTC] ACTION: @charlie rolling back to v1.4.1
[HH:MM UTC] Rollback complete. Error rate dropping: 15% → 2% → 0.1%
[HH:MM UTC] INCIDENT RESOLVED - Duration: 47 min, Impact: ~8K users
```

Customer status page update cadence:
```
< 5 min after detection: "We are investigating reports of X"
Every 15 min: "Update: [what we know, what we're doing]"
On resolution: "Resolved: [brief cause], post-mortem to follow"
```

## Gotchas
- IC must prevent "too many cooks" — only Tech Lead acts on the system during incident
- Avoid scope creep — fix only what is causing the incident; unrelated improvements wait
- Keep war room focused: move speculation to a thread, not the main channel
- Declare incident early, close it late — better to over-declare than miss user impact

## Related
- `post-mortem-blameless-template.md`
- `runbook-automation.md`
- `alerting-fatigue-reduction.md`
