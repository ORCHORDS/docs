# Architecture Decision Records (ADR) Workflow

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Six months after a major infrastructure choice, no one
remembers why PostgreSQL was chosen over MongoDB.
A new engineer proposes switching, and the debate
restarts from zero. Alternatively, a decision was made
in a Slack thread that has since been deleted, and
the system now has an unexplained constraint baked in
at a layer nobody wants to touch.

## Context

Architecture Decision Records are short, focused
documents that capture the reasoning behind irreversible
or hard-to-reverse technical decisions. They are not
design documents, RFCs, or meeting notes. An ADR
records one decision at a time, the context that made
it necessary, and the consequences the team accepted
by choosing it. Once accepted, an ADR is immutable
(except to be superseded). This permanence is the
point: you can always read why a choice was made, even
if the person who made it has left the company.

## 1. ADR Format

Use the Nygard template. Keep each ADR under two pages.

```markdown
# ADR-NNNN: [Short noun-phrase title]

**Date:** YYYY-MM-DD
**Status:** [Proposed | Accepted | Rejected | Superseded by ADR-NNNN]
**Deciders:** [names or roles]

## Context

[1-3 paragraphs: what problem forced this decision,
what constraints applied, what options were evaluated.]

## Decision

[One paragraph: what was decided, stated as an active
affirmation. "We will use X." Not "X was decided."]

## Consequences

### Positive
- [benefit 1]
- [benefit 2]

### Negative
- [trade-off 1]
- [trade-off 2]

### Neutral
- [downstream change that is neither good nor bad]
```

The Consequences section is the most important and most
often skipped. Do not skip it. If you cannot state a
negative consequence, you have not thought hard enough.

## 2. ADR Lifecycle

```
Proposed
    |
    |-- review (team discussion, async or sync)
    |
    +----> Accepted     (decision stands)
    |
    +----> Rejected     (option not taken; record why)
    |
    +----> Superseded   (new ADR replaces this one)
              |
              +--> add "Superseded by ADR-NNNN" to status
                   leave original text intact
```

An ADR moves from Proposed to Accepted when the
decision owner and at least one other senior engineer
have reviewed and approved it (via PR review or a
documented comment). Rejected ADRs stay in the
repository; they are evidence that the option was
considered, which is valuable when someone proposes
the same thing later.

Never edit an Accepted ADR's Decision or Context.
If circumstances change, write a new ADR that supersedes
the old one and update the status field of the original.

## 3. Storing ADRs and the adr-tools CLI

Store ADRs in `docs/decisions/` at the repository root.

```
repo-root/
  docs/
    decisions/
      0001-use-postgresql-for-primary-storage.md
      0002-adopt-kubernetes-for-container-orchestration.md
      0003-supersede-0001-migrate-to-cockroachdb.md
  README.md
```

Use `adr-tools` to create sequentially numbered files:

```bash
# Install
brew install adr-tools       # macOS
pip install adr-tools        # Python wrapper

# Initialise in a new repo
adr init docs/decisions

# Create a new ADR (opens $EDITOR with template)
adr new "Use PostgreSQL for primary storage"
# Creates: docs/decisions/0001-use-postgresql-for-primary-storage.md

# Supersede an existing ADR
adr new -s 1 "Migrate primary storage to CockroachDB"
# Creates 0003-... and sets ADR-0001 status to Superseded
```

If `adr-tools` is unavailable, number manually: pad to
four digits, use hyphens, keep titles lowercase with
words separated by hyphens.

## 4. When to Write an ADR

Not every PR needs an ADR. Write one when the decision
meets at least one of these criteria:

```
+-------------------------------------------+---------+
| Criterion                                 | ADR?    |
+-------------------------------------------+---------+
| Hard to reverse without significant cost  | yes     |
| Affects more than one team or service     | yes     |
| Changes a cross-cutting concern           | yes     |
| Establishes a pattern others will follow  | yes     |
| Selects an external dependency / vendor   | yes     |
| Routine implementation choice within      |         |
|   a single service                        | no      |
| Refactor with no behaviour change         | no      |
| Tooling choice within one engineer's      |         |
|   local workflow                          | no      |
+-------------------------------------------+---------+
```

A good rule of thumb: if the decision would cause a
significant debate in code review or if reversing it
would require more than a day of work, write the ADR.

## 5. Linking ADRs from Code

When code exists because of an ADR, say so in a
comment. This creates a trail from the artifact back
to the reasoning.

```python
# Payment service — database connection pool
# ADR-0004: Connection pool sizing for payment-api
# docs/decisions/0004-payment-api-connection-pool.md
MAX_POOL_SIZE = 20
MIN_POOL_SIZE = 5
```

```go
// HealthCheck uses /healthz (not /health) per
// ADR-0011: Kubernetes health check endpoint naming
// See docs/decisions/0011-...
func HealthCheck(w http.ResponseWriter, r *http.Request) {
```

Do not paste the full ADR into source files. One line
with the ADR number and the file path is enough.

## Anti-patterns

- Writing ADRs for already-implemented decisions after
  the fact and backdating them — this is fiction, not
  documentation; note the date honestly.
- Treating the ADR as a substitute for technical
  discussion; the discussion happens first and the ADR
  captures its outcome.
- Storing ADRs in Confluence or Notion where they
  drift out of sync with the codebase; keep them in
  the repository they describe.
- Letting ADRs sit in Proposed state for weeks; a
  decision not made is still a decision.
- Writing an ADR for every config change or library
  version bump — this cheapens the signal.

## Gotchas

- Superseding is not the same as amending. If you edit
  the body of an Accepted ADR and call it "updated,"
  you have destroyed the immutable record.
- ADR numbering must be global within a repository;
  if two people create ADR-0015 on branches that merge,
  you have a conflict. Use a short-lived branch per ADR.
- Rejected ADRs have value; do not delete them when
  a proposal is turned down.
- In a monorepo with many services, consider a top-level
  `docs/decisions/` for cross-cutting ADRs and service-
  level `<service>/docs/decisions/` for local ones.

## Verification

1. Run `ls docs/decisions/ | grep -c ".md"` and confirm
   the count matches what the team expects.
2. Pick three recent significant PRs and verify each
   has a corresponding ADR or a link to an existing one
   in the PR description.
3. Check that no Accepted ADR has been edited after its
   initial merge by inspecting `git log --follow`.
4. Confirm `adr-tools` is listed in the repository's
   CONTRIBUTING guide or Makefile.

## Related

- `documentation/docs/policies/lessons/decision-records-lightweight.md`
- `documentation/docs/policies/lessons/technical-writing-engineers-rfcs-adrs.md`
- `documentation/docs/policies/lessons/documentation-decays-without-ownership.md`

## Source URLs (verified 2026-08-17)

- https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- https://adr.github.io/
- https://github.com/npryce/adr-tools
- https://engineering.atspotify.com/2020/04/when-should-i-write-an-architecture-decision-record/
- https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html
