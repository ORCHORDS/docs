# Technical Writing for Engineers — RFCs, ADRs, Postmortems, and Runbooks

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team makes the same architectural decisions repeatedly because
nobody remembers why the previous decision was made. A critical
incident happens at 3 AM and the on-call engineer spends 40 minutes
finding the right runbook, only to discover the commands are outdated.
Your RFC process is a formality — documents are written after the
implementation is complete, never before. Design discussions happen in
Slack threads that disappear after 90 days, leaving no searchable
record for new team members.

## Context

Technical writing for engineers encompasses RFCs (Request for
Comments), ADRs (Architecture Decision Records), design documents,
incident postmortems, and runbooks. These are not bureaucratic
overhead — they are decision-alignment tools that distribute knowledge
asynchronously, create searchable records, and reduce repeated
discussions. In 2026, with distributed and AI-augmented teams, written
communication is the primary medium for technical alignment. The key
principle is to match document weight to decision weight — a 2-day
task does not need a 20-page design doc, but a database migration
affecting 500M rows does.

## RFC template

```markdown
# RFC: [Title]
- **Author(s):** [Names]
- **Status:** Draft | In Review | Accepted | Rejected | Superseded
- **Created:** YYYY-MM-DD
- **Reviewers:** [Names/Teams]
- **Review deadline:** YYYY-MM-DD

## Problem Statement
What problem are we solving and why now?
[1-2 paragraphs, no solution discussion]

## Proposed Solution
Detailed technical approach.
[Include diagrams, API shapes, data models as needed]

## Alternatives Considered
| Option | Pros | Cons |
|--------|------|------|
| A      | ...  | ...  |
| B      | ...  | ...  |

## Risks and Mitigations
What could go wrong and how do we handle it?

## Open Questions
- [ ] Question needing team input

## Decision
[Filled after review period]
```

## ADR template (Nygard format)

```markdown
# ADR-NNN: [Short Title]
**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXX
**Date:** YYYY-MM-DD
**Deciders:** [Names]

## Context
What forces are at play? What is the technical and business context?
[Describe the situation that led to this decision]

## Decision
We will [decision]. Because [rationale].

## Consequences
- Positive: ...
- Negative: ...
- Risks: ...
```

## Postmortem sections

```
Required sections:
  1. Title and date
  2. Severity level (SEV1-4)
  3. Impact summary (duration, affected users/systems)
  4. Timeline (detection → response → mitigation → resolution)
  5. Root cause analysis (5 Whys or fault tree)
  6. Contributing factors (what made it worse)
  7. What went well (what prevented worse outcomes)
  8. Action items with owners and deadlines

Blameless language:
  BAD:  "John deployed broken code to production"
  GOOD: "The deployment pipeline lacked a canary stage,
         allowing the regression to reach 100% of traffic"
```

## Runbook principles

```
The 5 A's of runbooks:
  Actionable:    Commands and steps, not explanations
  Accessible:    Findable in under 60 seconds during an incident
  Accurate:      Reviewed monthly — stale runbooks are dangerous
  Authoritative: One canonical source, not scattered wiki pages
  Adaptable:     Parameterized for different environments

Runbook structure:
  1. Title and purpose (one sentence)
  2. Prerequisites (access, tools, permissions)
  3. Steps (numbered, copy-pasteable commands)
  4. Verification (how to confirm each step worked)
  5. Rollback (how to undo if something goes wrong)
  6. Escalation (who to contact if steps fail)
```

## Writing principles

```
For all technical documents:
  → Lead with the problem, not the solution
  → Define acronyms on first use
  → Use consistent terminology (one term per concept)
  → Include diagrams for system interactions
  → Write for the reader who joins 6 months from now
  → Keep paragraphs to 3-4 sentences maximum
  → Use active voice ("we chose X" not "X was chosen")
  → Date everything — context without a date is ambiguous
```

## Anti-patterns

- **Writing for yourself** — unexplained jargon, undefined acronyms,
  and assumed context exclude readers who are not already experts.
  Write for the reader who joins next quarter.
- **Skipping Alternatives Considered** — an RFC or ADR without
  alternatives looks like a rubber stamp, not a considered decision.
  Reviewers cannot evaluate a proposal without seeing what was
  rejected and why.
- **Blame language in postmortems** — "John caused the outage" shuts
  down learning and discourages honest reporting. Use system-focused
  language that identifies process gaps, not individuals.
- **Stale runbooks** — outdated commands and endpoints in runbooks
  are worse than no runbook because they create false confidence
  during incidents. Review all runbooks monthly.

## Gotchas

- **Gold-plating documentation** — a 20-page design doc for a 2-day
  task wastes everyone's time. Match document weight to decision
  weight. An ADR might be 10 lines; an RFC for a platform migration
  might be 10 pages.
- **No clear ownership** — documents without authors or reviewers
  rot. Every document needs an owner responsible for its accuracy
  and a review schedule.
- **RFC timing** — writing the RFC after implementation defeats its
  purpose. The RFC should drive discussion before code is written.
  If the implementation changes the design, update the RFC.
- **Inconsistent terminology** — using different terms for the same
  concept throughout a document (e.g., "service" vs "microservice"
  vs "module" for the same thing) erodes trust and causes confusion.

## Verification

- RFCs are written and reviewed before implementation begins.
- ADRs are recorded for all significant architectural decisions.
- Postmortems are completed within 5 business days of incidents.
- Runbooks are reviewed monthly and tested quarterly.
- All documents have clear ownership and review dates.
- New team members can find relevant docs within 60 seconds.

## Related

- `documentation/docs/policies/lessons/blameless-postmortem-learning-culture.md`
- `documentation/docs/policies/lessons/on-call-handoff-rotation-best-practices.md`
- `documentation/docs/policies/lessons/incident-communication-status-page-practices.md`

## Source URLs (verified 2026-08-16)

- Technical Writing in English: RFC, ADR, Design Doc Templates — https://www.youngju.dev/blog/english/2026-03-12-english-technical-writing-rfc-adr-design-doc-guide.en
- PRD vs ADR vs RFC: The Documents Every Engineer Should Know — https://aridanemartin.dev/blog/prd-adr-rfc-decision-documents/
- ADR GitHub — Architecture Decision Record Templates — https://adr.github.io/
- Blameless Incident Postmortems: Templates, RCA & Action Items — https://medium.com/@gkunzile/blameless-incident-postmortems-templates-rca-action-items-6905c0f8ca67
