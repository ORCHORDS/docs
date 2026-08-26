# decision-log-template

**Issue:** Team decisions are made in meetings or Slack and are lost when context is needed later
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Six months after a major architectural decision, nobody can explain why a particular approach was chosen. The engineer who made the call has left. A new engineer wants to change it but doesn't know the constraints that made the original choice necessary.

## Pattern / Solution
A decision log captures choices at the point they're made, with context and rationale. It's lighter than an ADR — suited for operational, product, and process decisions that don't warrant a full ADR.

**When to log a decision:**
- The decision is hard to reverse
- Multiple people were involved in making it
- The reason for the choice will be non-obvious in 6 months
- It involves a trade-off that some stakeholders didn't like

**Decision log entry template:**
```markdown
## Decision: [Short title]

**Date:** YYYY-MM-DD
**Deciders:** @alice, @bob, @carol
**Status:** decided | superseded | deprecated

### Context
What situation forced this decision? What constraints applied?

### Options considered
1. **Option A:** [Description] — Pros: X. Cons: Y.
2. **Option B:** [Description] — Pros: X. Cons: Y.

### Decision
We chose **Option A** because [specific reason tied to the context].

### Consequences
- We accept: [trade-off]
- We will revisit this if: [trigger condition]

### Related
- Ticket: #1234
- ADR: 0012 (if applicable)
```

**Where to store it:**
- Operational decisions: team Notion/Confluence space, tagged "decision-log"
- Technical decisions: `docs/decisions/` in the repo (or use ADR format)
- Product decisions: product wiki, linked from the relevant epic

**Cadence:**
- Log decisions at the time they're made, not retroactively
- A monthly "decision review" in the team retro: what decisions were made this month? Are any worth logging?

## Gotchas
- Don't log every decision — meeting agenda items and minor choices don't qualify
- "We just went with the default" is a valid decision log entry — document it to prevent future questioning
- Link the decision log entry in the relevant PR or ticket description

## Related
- `adr-architecture-decision-records.md`
- `meeting-efficiency-patterns.md`
- `rfc-request-for-comments-process.md`
