# meeting-efficiency-patterns

**Issue:** Meetings are long, undirected, and produce no documented decisions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 60-minute architecture discussion ends with: "let's take this offline." No decision, no action items, no notes. Two weeks later, the same discussion restarts. Engineers dread meetings because they're associated with wasted time.

## Pattern / Solution
Run meetings with explicit type, agenda, DRI, and documented outcomes.

**Meeting types and their defaults:**
| Type | Format | Duration | Outcome |
|------|--------|----------|---------|
| Decision | Prepared options, vote | 30 min | Written decision + rationale |
| Brainstorm | Diverge then converge | 45 min | Filtered list of ideas |
| Status update | Replace with async | 0 min | Slack post |
| Retrospective | Structured formats | 60 min | Action items |
| 1-1 | Engineer-owned agenda | 30 min | Notes in shared doc |
| Kickoff | Alignment on goals, scope, roles | 60 min | Written brief |

**Meeting hygiene checklist:**
- [ ] Agenda posted 24h in advance (or meeting is declined)
- [ ] DRI (Directly Responsible Individual) named for the meeting
- [ ] Clear purpose stated: "We need to decide X" or "We need to brainstorm Y"
- [ ] Invite list scoped to people who are needed (not just informed)
- [ ] Notetaker assigned at the start
- [ ] Last 5 minutes reserved for: action items, owners, deadlines
- [ ] Notes shared in channel within 24h

**Techniques for better meetings:**
- **Silent start:** First 5 min, everyone reads the agenda/pre-read silently before discussion
- **Timeboxed rounds:** Each agenda item gets a fixed time (6-min rule: no item longer than 6 min without a break)
- **Parking lot:** Capture off-topic items in a list, address after the meeting or schedule separately
- **Decision template:** "We decided X because Y. We explicitly did not choose Z because W."

## Gotchas
- "Let's schedule a call" is often an avoidance of hard async writing — ask "could this be a doc?"
- Meetings without a DRI meander — designate a facilitator for every meeting
- Recording every meeting is not a substitute for notes; nobody watches 1h recordings

## Related
- `async-communication-guidelines.md`
- `decision-log-template.md`
- `working-agreement-template.md`
