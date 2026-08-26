# feature-architecture-decisions

**Issue:** Document architecture decisions with ADRs
**Date:** 2026-08-09
**Status:** documented

## Symptom
A new engineer asks "why do we use D1 over Postgres?"
Three engineers give three different answers. The new
engineer doesn't know who to believe. A year later, the
team discusses "should we move to Postgres?" and the
discussion goes in circles because the original context
is lost.

## Root cause
**Architecture decisions are made in meetings, not
written down.** Six months later, nobody remembers why.

**Source:** ADR template by Michael Nygard:
https://github.com/joelparkerhenderson/architecture-decision-record

## The "ADR" pattern

An ADR (Architecture Decision Record) is a short doc that
captures:
- The decision
- The context
- The consequences
- The alternatives

## The "ADR template"

```markdown
# ADR-001: Use D1 over Postgres for the user database

## Status
Accepted (2026-08-09)

## Context
We need a database for our app. We're deploying to
Cloudflare Pages + Workers. Options considered:
- D1 (Cloudflare SQLite)
- Postgres (self-hosted or Neon/Supabase)
- DynamoDB

We need:
- Low latency (edge replication)
- Low cost
- SQL compatibility (familiar to the team)
- Multi-region support

## Decision
We use D1.

## Consequences

### Positive
- Cheap ($5/month for our scale)
- Fast (edge replicated)
- SQL compatible (SQLite)
- Multi-region reads

### Negative
- 10GB per database (need to shard if we grow)
- Single-region writes (writes go to primary)
- Some Postgres features not available

## Alternatives considered

### Postgres
- More features (better SQL, JSON support, etc.)
- More expensive ($25+/month for managed)
- Higher latency from edge

### DynamoDB
- Better scaling
- More complex (NoSQL)
- Vendor lock-in

## Notes
- Migration plan: use a thin repository layer; if we
  outgrow D1, we can swap to Postgres
```

## The "ADR lifecycle"

### Status values
- **Proposed:** Under discussion
- **Accepted:** Decision made
- **Deprecated:** No longer relevant
- **Superseded by ADR-XXX:** A new ADR replaces this one

### The "lifecycle"
1. **Propose:** Open a PR with `Status: Proposed`
2. **Discuss:** Team comments; iterate
3. **Accept:** Merge with `Status: Accepted`
4. **Implement:** Build the thing
5. **Revisit:** When the context changes, write a new ADR

## The "ADRs in the repo" pattern

Store ADRs in the repo:
```
docs/
  adr/
    0001-use-d1-over-postgres.md
    0002-use-argon2-for-passwords.md
    0003-monorepo-with-pnpm.md
    0004-use-graphql.md
```

The ADRs are versioned with the code.

## The "lightweight ADR" pattern

For less critical decisions, a lighter format:
```markdown
## Decision: Use Vitest over Jest
- **Date:** 2026-08-09
- **Status:** Accepted
- **Context:** We need a test framework. Jest is the
  default; Vitest is newer and faster.
- **Decision:** Use Vitest.
- **Why:** Faster; ESM-native; better DX.
- **Trade-offs:** Smaller community; fewer plugins.
```

For critical decisions, the full ADR.

## The "decision matrix" pattern

For complex decisions, a matrix:
| Option | Cost | Performance | DX | Risk |
|---|---|---|---|---|
| D1 | $5/mo | Excellent | Familiar | Single-region |
| Postgres | $25+/mo | Good | Familiar | More setup |
| DynamoDB | Variable | Excellent | Unfamiliar | Vendor lock-in |

The matrix is the "options comparison"; the ADR is the
"decision + context."

## The "decision log" pattern

For the team, a "decision log" index:
```markdown
# Architecture Decision Log

| # | Title | Status | Date |
|---|---|---|---|
| 0001 | Use D1 over Postgres | Accepted | 2026-08-09 |
| 0002 | Use Argon2 for passwords | Accepted | 2026-08-09 |
| 0003 | Use Cloudflare Workers | Accepted | 2026-08-09 |
```

The index is a table; the ADRs are the details.

## The "RFC" alternative

For larger changes, use RFCs (Request for Comments):
```markdown
# RFC: Multi-region active-active

## Summary
We want to deploy our app in multiple regions with
active-active failover.

## Motivation
- Reduce latency for global users
- Survive regional outages

## Detailed design
- Multi-region D1 (primary + replicas)
- Geo-routing via CF
- Conflict resolution via timestamps

## Drawbacks
- More complex deploys
- Higher cost

## Alternatives
- Single region with CDN
- Active-passive failover
```

RFCs are longer; ADRs are shorter. Use RFCs for big
changes; ADRs for decisions.

## The "decision" anti-patterns

### 1. "Decisions in Slack"
A decision is made in Slack. Six months later, nobody
finds it. The decision is re-litigated.

**Fix:** Always write the decision down (ADR or doc).

### 2. "Decisions in code comments"
A code comment says "we use D1 because it's fast." The
context is gone.

**Fix:** ADRs explain the context; code comments explain
the code.

### 3. "Decisions in a wiki"
A wiki is editable by anyone. The "decision" gets edited
or deleted.

**Fix:** ADRs in the repo are versioned + code-reviewed.

### 4. "Decisions in meeting notes"
Meeting notes are lost; decisions are not tracked.

**Fix:** Decisions go in ADRs; meeting notes are reference.

## The "revisit the decision" pattern

Every quarter, review the ADRs:
- Is the decision still relevant?
- Has the context changed?
- Is there a new decision needed?

A "live" ADR is one that matches the current state. A
"dead" ADR is one that's been superseded.

## The "ADR review" pattern

For a major ADR, have a structured review:
1. **Author proposes** (PR with the ADR)
2. **Team comments** (1 week)
3. **Author revises** (addresses comments)
4. **Team approves** (PR merged)
5. **Status: Accepted**

This is the same as a code review, but for decisions.

## Verification
- **Process:** ADRs are in the repo
- **Live:** ADRs are referenced in PRs
- **Audit:** Quarterly review of ADR list

## Gotchas
- **The "ADR is a wall of text" anti-pattern.** An ADR
  should be short (1-2 pages). If it's longer, link to
  details.
- **The "ADR is not updated" anti-pattern.** The ADR's
  status should be current. If a decision is reversed,
  mark it "Superseded."
- **The "ADR for every decision" anti-pattern.** Not every
  decision needs an ADR. Use ADRs for non-obvious
  decisions.
- **The "ADR is hidden" anti-pattern.** ADRs in
  `docs/adr/` are discoverable. ADRs in a private wiki
  are not.

## Related
- `documentation-as-code.md`
- `pr-template-and-issue-templates.md`
- `safe-deploy-checklist.md`
- ADR template: https://github.com/joelparkerhenderson/architecture-decision-record
- AWS Prescriptive Guidance: https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html
