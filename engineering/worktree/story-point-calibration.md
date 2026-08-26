# story-point-calibration

**Issue:** Story points mean different things to different team members, making velocity unreliable
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
One engineer's "5" is another's "2". Velocity jumps 40% between sprints with no change in output. New team members have no anchor. Cross-team comparisons become meaningless politics.

## Pattern / Solution
Calibrate story points against concrete reference stories kept in a shared "calibration deck."

**Building the calibration deck:**
1. Pick 5–7 completed stories that the whole team agrees represent different sizes
2. Label them with their accepted point values
3. Store them in the team wiki or Confluence space
4. Before planning poker, reference these stories: "A 3 is like when we added the password reset flow"

**Reference anchor examples:**
```
1 point  → Fix a config typo and deploy
3 points → Add a new API endpoint with tests (happy path only)
5 points → New feature with DB migration, API, and frontend changes
8 points → Integration with a third-party service we haven't used before
13 points → Feature requiring changes across 3 services with unknowns
```

**Re-calibration triggers:**
- New team members join (onboard them with the calibration deck in week 1)
- Velocity swings > 25% for two consecutive sprints
- Team structure changes (split or merge)
- After adopting a new tech stack that changes what "complexity" means

**Keep velocity honest:**
- Measure velocity in points completed (accepted by product), not started or in-review
- Calculate velocity as a rolling average of the last 3 sprints
- Don't adjust points retroactively after discovering a story was harder than expected

## Gotchas
- Points measure complexity + uncertainty, not time — resist mapping them to hours
- Teams that share reference anchors converge faster than teams given a definition alone
- Re-calibrate after a major refactor — the codebase health affects what's "a 5" now

## Related
- `estimation-techniques.md`
- `sprint-planning-engineering.md`
- `definition-of-ready-checklist.md`
