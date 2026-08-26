# postmortem-writing-guide

**Issue:** Incidents recur because learnings aren't captured or actioned
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The same type of outage happens every few months. Each time the team firefights, resolves it, then moves on. No systemic fix lands. Engineers burn out on the hamster wheel.

## Pattern / Solution
Write a postmortem within 48 hours of every P1/P2 incident. Postmortems are blameless documents — they analyze systems, not people.

**Template:**
```markdown
# Postmortem: [Service] — [Brief Description]

**Date of incident:** YYYY-MM-DD
**Duration:** Xh Ym
**Severity:** P1 / P2
**Author:** @name
**Reviewed by:** @name
**Status:** draft | reviewed | action items tracked

## Summary
2-3 sentence executive summary: what happened, impact, and root cause.

## Impact
- Users affected: X% of traffic / N users
- Revenue impact: $X (if known)
- SLA breach: yes / no

## Timeline
| Time (UTC) | Event |
|------------|-------|
| 14:00 | Alert fired |
| 14:08 | On-call acknowledged |
| 14:35 | Root cause identified |
| 15:12 | Fix deployed |
| 15:20 | Incident resolved |

## Root Cause Analysis
Use "5 Whys" or a causal chain. Be specific about the technical mechanism.

## Contributing Factors
What conditions made this worse or harder to detect?

## What Went Well

## What Could Be Improved

## Action Items
| Action | Owner | Due Date | Ticket |
|--------|-------|----------|--------|
| Add circuit breaker | @bob | +2 weeks | #1234 |
```

**Review process:**
1. Author shares draft within 24–48 hours
2. Team reviews async within 3 days
3. Action items are filed in the tracker before the postmortem is closed
4. Postmortems are stored in a shared index for trend analysis

## Gotchas
- Action items without owners and due dates will never get done
- "Human error" is never a root cause — ask why the system allowed the error to have impact
- Don't skip postmortems for near-misses; near-miss postmortems are the cheapest learning
- Length should be proportional to severity — a P2 doesn't need a 10-page novel

## Related
- `incident-commander-role.md`
- `blameless-culture-implementation.md`
- `on-call-playbook-template.md`
