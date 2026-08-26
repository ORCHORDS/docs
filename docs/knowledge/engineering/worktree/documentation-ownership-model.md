# documentation-ownership-model

**Issue:** Documentation exists but is outdated, owned by nobody, and engineers don't trust it
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
There are 400 Confluence pages. Nobody knows which ones are current. Engineers verify everything against the code rather than trusting the docs. The cost of maintaining the docs is perceived as higher than the value.

## Pattern / Solution
Documentation must have explicit owners, freshness signals, and a minimum-viable scope.

**Ownership model:**
- Every doc has one owner (a team, not a person — people leave)
- Owner is listed in the doc header: `**Owner:** @team-payments`
- Owner is responsible for keeping the doc accurate, not writing it alone

**Freshness signals:**
- Add a "Last verified" date to every critical doc
- Docs not verified in 6 months get auto-tagged `[stale?]`
- Quarterly doc audit: each team reviews their owned docs and updates or archives

**Tiered documentation approach:**
| Tier | Content | Owner | Review cadence |
|------|---------|-------|----------------|
| T1 — Critical | Runbooks, security policies, APIs, onboarding | Team | Monthly |
| T2 — Operational | Architecture overviews, design docs, ADRs | Team | Quarterly |
| T3 — Reference | How-to guides, tutorials, meeting notes | Author | Annually or archive |

**Doc-as-code principles:**
- Keep T1 and T2 docs in the repo (Markdown), not in a separate wiki
- Docs change in the same PR as the code they describe
- CODEOWNERS includes docs directories to enforce review

**When to write docs (not everything):**
- Write docs when: the information is asked more than twice, it's needed at 2am, or it's needed by someone new
- Don't write docs for: things that should be obvious from well-named code, one-off decisions

## Gotchas
- A doc nobody reads is worse than no doc — it creates false confidence
- Orphaned docs (owner team no longer exists) should be archived or deleted, not kept
- "Link to the code" is sometimes the best documentation for implementation details

## Related
- `inner-source-guidelines.md`
- `engineering-onboarding-template.md`
- `changelog-communication-process.md`
