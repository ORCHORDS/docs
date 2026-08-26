# post-mortem-blameless-template

**Issue:** Conducting blameless post-mortems that produce systemic improvements, not blame
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Post-mortems result in "human error" as root cause with no action items. Engineers avoid admitting mistakes. Same incidents recur.

## Pattern / Solution
Blameless post-mortem template:
```markdown
# Post-Mortem: [Title] — [Date]

**Severity:** P0 / P1 / P2
**Duration:** HH:MM (detection) to HH:MM (resolution)
**Impact:** [# users affected, error rate, revenue impact]
**Author(s):** [names]
**Status:** Draft / In Review / Complete

---

## Summary
One paragraph: what happened, how it was detected, how it was resolved.

## Timeline (UTC)
| Time  | Event |
|-------|-------|
| 14:32 | Deploy v1.4.2 shipped |
| 14:47 | Alert: p99 latency > 2s |
| 14:49 | IC declared, war room opened |
| 15:18 | Root cause identified |
| 15:23 | Rollback complete, error rate normal |
| 15:31 | Incident resolved |

## Root Cause
Describe the technical root cause. NOT "Bob made a mistake."
Use 5-whys to find the systemic cause:
- Why did latency spike? → N+1 query in /orders endpoint
- Why was it deployed? → Code review missed ORM query in loop
- Why did review miss it? → No automated query analysis in CI
- Why no CI check? → Tool exists but never configured for this repo
- ROOT CAUSE: Missing tooling and process, not individual error

## Contributing Factors
- No staging load test representative of production traffic
- Database slow query log not monitored in real time

## What Went Well
- Alert fired within 5 minutes (within SLO)
- Rollback procedure was documented and fast
- Good cross-team communication

## Action Items
| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add sqlfluff/django-zen-queries to CI | @alice | 2026-08-25 | Open |
| Create slow query dashboard + alert | @bob | 2026-08-18 | Open |
| Load test in staging before P0 deploys | @charlie | 2026-09-01 | Open |
```

## Gotchas
- "Human error" is never a root cause — it is a symptom of a system that allows human error
- Action items without owner and due date are never done — assign immediately in the meeting
- Publish post-mortems internally within 5 business days while details are fresh
- Track action item completion in the next sprint — incomplete items from post-mortems compound technical debt

## Related
- `incident-war-room-setup.md`
- `chaos-engineering-gameday.md`
- `toil-reduction-sre.md`
