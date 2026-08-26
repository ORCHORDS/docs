# stakeholder-update-template

**Issue:** Engineering updates to leadership are either too technical, too infrequent, or buried in Jira
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A VP asks the EM "how's the migration going?" The EM gives a 10-minute technical explanation about database sharding. The VP wanted: "on track, ships in two weeks, risk is X." The disconnect repeats every quarter.

## Pattern / Solution
Write stakeholder updates in a consistent, skimmable format — outcomes first, details second.

**Weekly async update (Slack or email):**
```
## Engineering Update — [Team Name] — [Week of Date]

**Status:** 🟢 On track / 🟡 At risk / 🔴 Blocked

### This week shipped
- [Feature / fix]: [impact in user or business terms]

### Next week plan
- [Item]: [expected outcome]

### Risks / decisions needed
- [Risk description]: [what decision or help is needed from stakeholders]

### Metrics pulse
- Deployment frequency: X/week
- Incident count: N (P1: 0, P2: N)
- On-call health: 🟢 Normal
```

**Monthly stakeholder deck (for leadership reviews):**
```
Slide 1: Team health snapshot (DORA metrics, headcount, open roles)
Slide 2: Progress against quarterly goals (OKRs or milestones)
Slide 3: Key decisions made this month and their rationale
Slide 4: Risks and mitigations
Slide 5: What we need (decisions, resources, unblocking)
```

**Writing style rules:**
- Lead with outcomes, not activity ("We improved checkout reliability by 15%" not "We fixed bugs in the payment service")
- Use plain language for risk and status — no jargon
- If it requires background to understand, put it in an appendix or link
- Decisions needed must be specific: "We need a decision on X by [date] or Y will be delayed"

## Gotchas
- "Everything is fine" updates that omit real risks erode trust when the risk materializes
- Don't make stakeholders dig into Jira to verify claims — the update should stand alone
- Cadence consistency matters more than length; late updates are worse than short ones

## Related
- `changelog-communication-process.md`
- `cross-team-dependency-management.md`
- `engineering-kpis-dashboard.md`
