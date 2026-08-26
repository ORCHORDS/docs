# incident-commander-role

**Issue:** During incidents everyone talks at once, nobody owns the timeline, and critical steps get missed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A P1 fires. Five engineers jump into the war room. One is chasing logs, another is restarting pods, a third is pinging external vendors, and nobody is talking to stakeholders. An hour later, the incident is resolved but nobody documented what was tried, what worked, or when it happened.

## Pattern / Solution
Designate an Incident Commander (IC) at the start of every incident. The IC coordinates — they do not fix.

**IC responsibilities:**
1. **Declare** — state the incident severity and open the incident channel/bridge
2. **Assign roles** — nominate a lead investigator and a scribe
3. **Timebox investigations** — "You have 10 minutes on that hypothesis, then we re-assess"
4. **Communicate** — post updates to stakeholder channels every 15–30 min
5. **Resolve or escalate** — make the call to escalate if no progress in agreed window
6. **Close** — declare the incident resolved, set postmortem owner and deadline

**IC does NOT:**
- Dig into logs personally
- Write the fix
- Make unilateral architectural changes during the incident

**Rotation:**
- IC role rotates through senior engineers on a weekly or monthly basis
- IC training is a 2-hour session covering the incident process + tabletop exercise

**Communication template during incident:**
```
[UPDATE 14:32] Incident: Payment service high error rate
Status: INVESTIGATING
Impact: ~5% of checkout requests failing
Action: Team investigating DB query performance
Next update: 14:47
IC: @alice
```

## Gotchas
- A single engineer owning both IC and technical lead roles is a recipe for tunnel vision
- IC must actively cut off rabbit holes — "let's park that and focus on the highest-impact hypothesis"
- Declare severity early and err toward higher severity — it's easy to downgrade, hard to catch up on comms

## Related
- `postmortem-writing-guide.md`
- `on-call-playbook-template.md`
- `blameless-culture-implementation.md`
