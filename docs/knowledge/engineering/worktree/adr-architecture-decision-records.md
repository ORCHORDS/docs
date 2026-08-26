# adr-architecture-decision-records

**Issue:** Teams make big technical decisions verbally then forget the rationale six months later
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A new engineer asks "why are we using Kafka instead of SQS?" and nobody remembers. The person who made the call left. The decision gets relitigated every quarter.

## Pattern / Solution
Adopt Architecture Decision Records (ADRs) as lightweight, file-based decision logs stored in the repo.

**Directory layout:**
```
docs/decisions/
  0001-use-kafka-for-event-streaming.md
  0002-adopt-postgres-as-primary-db.md
```

**Minimal template:**
```markdown
# ADR-NNNN: Title

**Status:** proposed | accepted | deprecated | superseded by ADR-XXXX
**Date:** YYYY-MM-DD
**Deciders:** @alice, @bob

## Context
What situation forced a decision?

## Decision
What was chosen and why?

## Consequences
What trade-offs does this introduce?
```

**Workflow:**
1. Open a PR with the ADR file before or during implementation
2. Reviewers comment on the ADR, not just the code
3. Merge the ADR when the decision is accepted
4. Mark old ADRs "superseded" rather than deleting them

Tools: `adr-tools` CLI auto-numbers files and links supersession chains.

## Gotchas
- ADRs record decisions, not options — write them after you've decided, not as a brainstorm doc
- Superseded ADRs must stay in the repo; deleting breaks the audit trail
- Don't wait for "big" decisions — capture medium ones too (library choices, naming conventions)
- ADR numbering should be global across the repo, not per-team

## Related
- `rfc-request-for-comments-process.md`
- `design-doc-template.md`
- `decision-log-template.md`
