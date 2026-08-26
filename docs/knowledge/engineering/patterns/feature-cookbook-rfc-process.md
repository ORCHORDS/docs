# feature-cookbook-rfc-process

**Issue:** RFC process — propose, discuss, decide
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have an idea. You code it. You ship it. The team
didn't know about it. Someone else was working on the
same thing. The team is fragmented.

## Root cause
**Without an RFC process, work is uncoordinated.** Use
an RFC.

**Source:** Various product guides.

## The "RFC" concept

An RFC (Request for Comments) is a document that
proposes a change and asks for feedback.

**Source:** IETF RFC process:
https://www.rfc-editor.org/

## When to write an RFC

Write an RFC for:
- **Big change:** A new feature, a refactor, an
  architectural change
- **Cross-team:** Affects multiple teams
- **Risky:** Could break things
- **Reversible:** Probably not (avoid premature RFCs)

For small changes (a bug fix, a small refactor), no
RFC is needed.

## The "RFC template"

```markdown
# RFC: <Title>

**Author:** @alice
**Date:** 2026-08-09
**Status:** Draft / Accepted / Rejected / Superseded
**Reviewers:** @bob, @charlie

## Summary
One paragraph: what is the proposal?

## Motivation
Why are we doing this? What problem does it solve?

## Detailed design
How does it work? Code, schema, API, etc.

## Drawbacks
What are the downsides? Why might this be a bad idea?

## Alternatives
What other approaches were considered?

## Open questions
What is still unclear?

## Adoption plan
How will this be rolled out? Migration? Compatibility?

## Timeline
When will this be implemented?

## References
Links to related work, prior art, etc.
```

The template is consistent.

## The "RFC process" steps

1. **Draft:** The author writes the RFC
2. **Share:** Post to the team / repo
3. **Review:** Reviewers + team provide feedback
4. **Iterate:** The author updates the RFC
5. **Decision:** The team accepts or rejects
6. **Implement:** The accepted RFC is implemented
7. **Archive:** The RFC is archived in the repo

The process is structured.

## The "RFC repository" pattern

For an RFC repo:
```
/rfcs
  /001-database-choice.md
  /002-monorepo-tooling.md
  /003-auth-redesign.md
  /004-rate-limiting.md
  /README.md
```

The RFCs are versioned + searchable.

## The "RFC status" pattern

For RFC status:
- **Draft:** In progress
- **Review:** Open for comments
- **Accepted:** Approved, will implement
- **Rejected:** Not approved
- **Superseded:** Replaced by a newer RFC
- **Implemented:** Done

The status is clear.

## The "RFC review" pattern

For review:
- **Async:** Reviewers read and comment
- **Sync:** A meeting to discuss
- **Decision period:** 1-2 weeks

The review is structured.

## The "RFC comments" pattern

For comments, the reviewer says:
- **Blocking:** Must be addressed
- **Non-blocking:** Nice to address
- **Question:** Needs clarification
- **Praise:** Looks good

The comment type is clear.

## The "RFC acceptance" pattern

For acceptance:
- **Consensus:** All reviewers agree
- **Lazy consensus:** No objections in 1-2 weeks
- **Author's call:** The author decides
- **Team vote:** Majority wins

The acceptance is documented.

## The "RFC anti-pattern" anti-patterns

### 1. No RFC for big changes
- **Issue:** Surprise changes, fragmented work
- **Fix:** RFC for big changes

### 2. RFC is too long
- **Issue:** Reviewers don't read
- **Fix:** Keep it short (1-2 pages)

### 3. RFC is too short
- **Issue:** Missing details, misunderstood
- **Fix:** Cover motivation, design, drawbacks

### 4. No decision date
- **Issue:** RFC sits in limbo
- **Fix:** Set a decision date

### 5. RFC is theater
- **Issue:** Decision already made; RFC is for show
- **Fix:** Genuinely open to feedback

### 6. No implementation plan
- **Issue:** RFC is accepted but never implemented
- **Fix:** Include an adoption plan + timeline

## The "RFC vs ADR" distinction

| Use case | Use |
|---|---|
| **Propose a new feature** | RFC |
| **Document a decision after the fact** | ADR |
| **Cross-team impact** | RFC |
| **Internal decision** | ADR |

For most decisions, ADR is enough. For big changes,
RFC.

## The "ADR" pattern

For ADRs (Architecture Decision Records):
```markdown
# ADR 0001: Use Cloudflare Workers

## Status
Accepted (2026-08-09)

## Context
We need a runtime. Options: Workers, AWS Lambda, Vercel.

## Decision
We chose Cloudflare Workers.

## Consequences
- Global edge, low latency
- Tight integration with D1, R2
- 30s CPU limit

## Alternatives considered
- AWS Lambda: cold starts, region-specific
- Vercel: limited to Next.js, expensive
```

The ADR is short + archival.

## Verification
- **Test:** RFCs are written for big changes
- **Test:** ADRs are written for decisions
- **Live:** Reviewers provide feedback
- **Audit:** Quarterly review of pending RFCs

## Gotchas
- **The "no RFC" anti-pattern.** Big changes are
  surprising.
- **The "RFC is theater" anti-pattern.** Genuinely
  engage.
- **The "RFC is too long" anti-pattern.** Keep it short.

## Related
- `feature-cookbook-feature-lifecycle.md`
- `feature-launch-checklist.md`
- `dependency-injection.md`
- `dependency-injection.md`
- IETF: https://www.rfc-editor.org/
- ADR: https://github.com/joelparkerhenderson/architecture_decision_records
