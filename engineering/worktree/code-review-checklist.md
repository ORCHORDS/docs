# code-review-checklist

**Issue:** Code reviews are inconsistent — some are rubber stamps, others are exhausting nitpicks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reviewers spend 45 minutes on formatting while missing a race condition. Or every PR triggers a style debate. New engineers don't know what "a good review" looks like. Senior engineers are the bottleneck because juniors defer everything to them.

## Pattern / Solution
Use a structured checklist with explicit priority tiers. Reviewers address tier 1 issues first; tier 3 is optional.

**Tier 1 — Must fix (blocking):**
- [ ] Correctness: Does the code do what the PR description says?
- [ ] Security: Are inputs validated? Is auth checked? No secrets in code?
- [ ] Data integrity: Are DB transactions used appropriately? No lost updates?
- [ ] Error handling: Are errors caught and handled or propagated intentionally?
- [ ] Breaking changes: Are API or schema changes backward compatible?

**Tier 2 — Should fix (non-blocking but expected):**
- [ ] Tests: Do tests cover the new behavior and edge cases?
- [ ] Readability: Would a new team member understand this in 6 months?
- [ ] Performance: Any obvious N+1 queries, missing indexes, or hot-path regressions?
- [ ] Documentation: Are public APIs and non-obvious logic commented?
- [ ] DoD: Does the PR satisfy the team's Definition of Done?

**Tier 3 — Nit (prefix with `nit:`, author's discretion):**
- Variable naming preferences
- Minor formatting differences not caught by the linter
- Style alternatives with no meaningful impact

**Reviewer etiquette:**
- Respond within one business day
- If you can't review fully, say so and hand off to another reviewer
- Use `nit:` prefix so authors know what's optional
- "Ask, don't tell" for design alternatives: "Have you considered X?" not "Do X instead"

## Gotchas
- Automate tier 3 with linters and formatters — reviewers should not spend time on it
- A PR with > 500 lines of diff should be split before review (see `pr-size-guidelines.md`)
- Authors should self-review using this checklist before requesting review

## Related
- `pr-size-guidelines.md`
- `definition-of-done-checklist.md`
- `pr-review-process-2026.md`
