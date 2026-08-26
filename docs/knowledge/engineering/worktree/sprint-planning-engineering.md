# sprint-planning-engineering

**Issue:** Sprint planning meetings are long, contentious, and produce commitments the team can't keep
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Planning takes 3+ hours. Stories are pulled in that aren't refined. Engineers commit to more than their capacity. Mid-sprint work is added without removing anything. The sprint ends with 30% carry-over.

## Pattern / Solution
Run sprint planning as two phases: capacity check then story selection.

**Phase 1: Capacity (15 min before the meeting)**
- Count available engineer-days (exclude PTO, holidays, on-call tax)
- Apply a focus factor (typically 0.7 for sprint teams — 70% of hours are "real" work)
- Convert to story points using the team's historical velocity

**Phase 2: Story selection (in meeting)**
1. Product owner presents the ordered backlog (already refined — no unrefined stories in sprint)
2. Team pulls from the top until capacity is met
3. Each story must meet the Definition of Ready before it can be pulled
4. Reserve 15–20% capacity for unplanned work and tech debt

**Checklist for each story pulled:**
- [ ] Acceptance criteria written
- [ ] Dependencies identified and unblocked
- [ ] Estimated (or estimated now in < 5 min)
- [ ] Fits in one sprint

**Anti-pattern: the "stretch goal" trap**
Adding stretch goals implies the real commitment is soft. Don't. Commit to what you'll finish.

## Gotchas
- Planning velocity using the last 3 sprints is more accurate than team intuition
- If estimation takes > 5 min per story, the story needs more refinement — defer it
- Unrefined stories in a sprint are the #1 cause of mid-sprint scope creep
- PM attendance is required; it's a negotiation, not a team-internal meeting

## Related
- `estimation-techniques.md`
- `story-point-calibration.md`
- `definition-of-ready-checklist.md`
- `tech-debt-tracking-process.md`
