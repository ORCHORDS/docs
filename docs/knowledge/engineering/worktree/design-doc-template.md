# design-doc-template

**Issue:** Engineers start coding without a shared understanding of what they're building
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Work begins, then mid-sprint someone asks "wait, how does auth work here?" Assumptions diverge. The feature ships but the implementation doesn't match what product or infrastructure expected.

## Pattern / Solution
A design doc is written before significant implementation begins. It's lighter than a formal spec but heavier than a ticket description.

**Template:**
```markdown
# Design: [Feature Name]

**Author(s):** @name
**Reviewers:** @name, @name
**Status:** draft | in-review | approved | implemented
**Last updated:** YYYY-MM-DD

## Problem Statement
What user or system problem does this solve? Why now?

## Goals
- Bullet list of what success looks like

## Non-Goals
- Explicitly list what this does NOT address

## Background / Context
Relevant prior work, existing systems, constraints.

## Proposed Design
Describe the solution. Include:
- Component diagram or data flow
- API contracts (request/response shapes)
- Data model changes
- Error handling approach

## Alternatives Considered
Why were other approaches rejected?

## Security & Privacy Considerations

## Observability Plan
Metrics, logs, and alerts that will be added.

## Rollout Plan
Phasing, feature flags, migration steps.

## Open Questions
- [ ] Item still unresolved
```

**Process:**
1. Author drafts doc and shares with tech lead before writing code
2. Async review period (2–5 days depending on scope)
3. Approval = written comment "LGTM" from designated reviewers
4. Doc lives in `docs/design/` in the repo or in the team wiki, linked from the epic

## Gotchas
- A design doc is not a substitute for an ADR — write both if the decision is cross-cutting
- Avoid over-engineering the doc for small features; use judgment on scope
- Update the doc as decisions change during implementation; don't let it go stale

## Related
- `adr-architecture-decision-records.md`
- `rfc-request-for-comments-process.md`
- `pr-size-guidelines.md`
