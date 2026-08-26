# rfc-request-for-comments-process

**Issue:** Large cross-team changes get designed in a vacuum and cause surprises at review time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team ships a new API contract that breaks three other teams. Or a platform change is implemented before impacted teams know it's coming. Downstream engineers find out in code review or at production deploy time.

## Pattern / Solution
An RFC (Request for Comments) is a structured proposal for significant changes that solicits feedback before work begins.

**When to write an RFC:**
- The change affects more than one team or service
- It introduces a new dependency, protocol, or data contract
- It deprecates an existing interface
- Implementation will take more than two weeks

**RFC lifecycle:**
```
Draft → Open for Comment (1-2 weeks) → Final Comment Period (3 days) → Accepted / Rejected → Implemented → Closed
```

**Lightweight template:**
```markdown
# RFC-NNNN: Title

**Author:** @name
**Status:** draft
**Created:** YYYY-MM-DD
**Review deadline:** YYYY-MM-DD

## Summary (2-3 sentences)

## Motivation

## Detailed Design

## Drawbacks

## Alternatives Considered

## Open Questions
```

**Process:**
1. Author posts RFC to a shared channel (e.g. `#rfcs`) and tags affected teams
2. Comment window is fixed (don't let it drift open indefinitely)
3. Author summarizes feedback and makes a call or escalates to a decision-maker
4. Accept/reject decision is recorded with reasoning

## Gotchas
- An RFC is not a committee vote — the author or a DRI makes the final call
- "No objections after deadline" counts as acceptance
- Don't use RFC for every ticket; reserve it for cross-cutting changes
- Keep the open period short — long review windows produce stale feedback

## Related
- `adr-architecture-decision-records.md`
- `design-doc-template.md`
- `cross-team-dependency-management.md`
