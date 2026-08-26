# definition-of-done-checklist

**Issue:** "Done" means different things to different engineers, causing rework after sprint review
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A story is marked done, then product finds missing edge cases. QA finds untested paths. Ops finds no runbook. The feature goes back to in-progress, inflating the next sprint's carry-over.

## Pattern / Solution
A Definition of Done (DoD) is a shared checklist that every story must pass before it's accepted. It is team-wide and non-negotiable.

**Standard DoD checklist:**
```
Code
- [ ] Code reviewed and approved by at least one peer
- [ ] No unresolved review comments
- [ ] No TODOs left without a linked ticket

Tests
- [ ] Unit tests cover the new behavior
- [ ] Integration/E2E tests added or updated
- [ ] Test coverage does not decrease from baseline

Quality
- [ ] Linter and formatter pass
- [ ] No new security warnings (SAST scan clean)
- [ ] Performance impact assessed (load test if applicable)

Documentation
- [ ] Public API changes reflected in API docs
- [ ] README or runbook updated if operational behavior changed
- [ ] CHANGELOG entry added for user-facing changes

Deployment
- [ ] Feature flag added if the change needs a dark launch
- [ ] Deployed to staging and smoke-tested
- [ ] Monitoring/alerting configured for new code paths

Product
- [ ] Acceptance criteria verified by product owner
- [ ] Accessibility requirements met
```

**Customization:**
Trim or extend this list per team. Keep it to what you actually check — a 30-item DoD that gets rubber-stamped is worse than a 10-item one that's taken seriously.

## Gotchas
- DoD applies to every story, not just "important" ones — consistency is the point
- Review the DoD quarterly and remove items nobody ever fails or enforces
- DoD is different from acceptance criteria — DoD is team-level, AC is story-level

## Related
- `definition-of-ready-checklist.md`
- `code-review-checklist.md`
- `pr-size-guidelines.md`
