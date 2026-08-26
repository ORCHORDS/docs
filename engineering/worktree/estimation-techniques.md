# estimation-techniques

**Issue:** Software estimates are chronically wrong, causing missed deadlines and broken trust
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A feature is estimated at 3 days and takes 3 weeks. The team blames underestimation, but the real problem is a lack of structured technique and no accounting for unknown unknowns.

## Pattern / Solution
Use multiple techniques depending on context. No single method works for all situations.

**Planning Poker (relative sizing, team-based):**
- Each engineer privately picks a card (Fibonacci: 1, 2, 3, 5, 8, 13)
- Cards revealed simultaneously
- Outliers explain their reasoning; re-vote once
- Best for: sprint planning of pre-refined stories

**T-shirt sizing (rough backlog ordering):**
- S = < 1 day, M = 2–3 days, L = 1 week, XL = > 1 week
- No false precision; used during roadmap planning
- Best for: quarterly planning or early product conversations

**Three-point estimation (schedule commitments):**
- O = Optimistic (everything goes right)
- M = Most likely
- P = Pessimistic (everything goes wrong)
- Expected = (O + 4M + P) / 6
- Best for: external commitments or risk analysis

**Slice and count:**
- Decompose the feature into tasks, estimate each task at 0.5–2 days max
- Sum the tasks
- Best for: complex features with many unknowns

**Rules of thumb:**
- Add 30% for integration and review overhead
- Double any estimate involving a new external dependency
- Stories that need more than 5 min to estimate need more refinement first

## Gotchas
- Estimates are not commitments — communicate the difference explicitly to stakeholders
- Velocity-based planning (use past actuals) beats point estimation alone
- Never estimate alone for work that requires cross-team coordination
- Pressure to estimate lower is a team health signal worth raising

## Related
- `story-point-calibration.md`
- `sprint-planning-engineering.md`
- `definition-of-ready-checklist.md`
