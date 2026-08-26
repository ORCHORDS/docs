# definition-of-ready-checklist

**Issue:** Stories enter sprints half-baked, causing mid-sprint discovery work and missed commitments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Planning poker reveals nobody understands the story well enough to estimate it. Or an engineer picks up a ticket and spends a day figuring out what "done" even means. Blocked stories pile up waiting for clarification.

## Pattern / Solution
A Definition of Ready (DoR) is a checklist a story must pass before it can be pulled into a sprint. It's the product owner's responsibility to ensure readiness before planning.

**Standard DoR checklist:**
```
Problem definition
- [ ] User story follows "As a [user], I want [action], so that [value]" format
- [ ] Business value is stated

Scope
- [ ] Acceptance criteria are written and unambiguous
- [ ] Edge cases and error states are addressed in the AC
- [ ] Non-goals are stated (what this story does NOT do)

Dependencies
- [ ] External dependencies are identified
- [ ] Blocking dependencies are resolved or have a clear ETA
- [ ] Design assets attached (if UI work)

Feasibility
- [ ] Technical approach discussed with at least one engineer
- [ ] Story is small enough to complete in one sprint
- [ ] If large, it has been broken into sub-stories

Data & compliance
- [ ] PII or compliance implications flagged
- [ ] Analytics/tracking requirements specified
```

**Enforcement:**
- Stories failing DoR during planning are deferred to the backlog — no exceptions
- Refinement sessions (mid-sprint) exist to get stories to ready state for the next sprint

## Gotchas
- DoR is a shared contract — engineers can reject unready stories without it being confrontational
- Over-specifying AC removes necessary engineering judgment; aim for "just enough"
- Design dependencies are the most common blocker — check design readiness first

## Related
- `definition-of-done-checklist.md`
- `sprint-planning-engineering.md`
- `estimation-techniques.md`
