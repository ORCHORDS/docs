# decision-records-lightweight

**Issue:** ADRs / RFCs — decision records discipline
**Date:** 2026-08-09
**Status:** documented

## Symptom
"Why did we use Postgres?" "Why is the API
versioned in URL?" Nobody remembers. The Confluence
page is gone. You realize decisions weren't recorded.
6 months of "why" lost.

## Root cause
**Decisions decay.** ADRs (immutable) + RFCs (mutable).

**Source:** MADR 4.0 + adr.github.io 2026.

## The "ADR" concept

ADR:
- **Format:** Short markdown
- **Storage:** `docs/decisions/`
- **State:** Immutable
- **Use:** Record decision
- **When:** Architecturally significant

The ADR is the record.

## The "RFC" concept

RFC:
- **Format:** Markdown + PR
- **Storage:** `.rfc/` dir
- **State:** Mutable
- **Use:** Discuss + converge
- **When:** Proposal phase

The RFC is the proposal.

## The "RFC → ADR" pattern

For flow:
- **RFC:** Open PR
- **Discuss:** Threads
- **Accept:** Merge
- **Snapshot:** To ADR
- **Why:** Proposal + record

The flow is RFC → ADR.

## The "MADR 4.0" pattern

For template:
- **Released:** 2024-09-17
- **Status:** Current 2026
- **Front matter:** YAML
- **Sections:** Context, Drivers, Options, Outcome, Consequences
- **Why:** Standard

The MADR is the template.

## The "YAML front matter" pattern

For meta:
```yaml
---
status: proposed | rejected | accepted | deprecated | superseded by ADR-0007
date: 2026-08-09
decision-makers: @alice, @bob
consulted: @security-team
informed: @all-hands
---
```

The meta is structured.

## The "status lifecycle" pattern

For status:
- **proposed:** In discussion
- **accepted:** Live
- **deprecated:** Replaced by feature
- **superseded by:** ADR-XXXX
- **rejected:** Not chosen

The status is explicit.

## The "one decision one file" pattern

For file:
- **Filename:** `NNNN-title-with-dashes.md`
- **Range:** 0001-9999
- **Never:** Edit after accept
- **Always:** New ADR to supersede
- **Why:** Audit trail

The file is immutable.

## The "numbered, dated" pattern

For naming:
- **Number:** 4 digits
- **Date:** ISO 8601
- **Title:** Kebab-case
- **Why:** Sortable + findable
- **Example:** the PostgreSQL decision record

The name is structured.

## The "PR review" pattern

For review:
- **PR:** Standard GitHub PR
- **Reviewers:** 1-2 typically
- **Discussion:** Threaded
- **Approval:** Required
- **Why:** Code review style

The PR is the review.

## The "lightweight" pattern

For weight:
- **Length:** 1-2 pages
- **Not:** 20-page spec
- **Detail:** Appendix
- **Why:** Many over system life
- **Fix:** Appendices

The weight is light.

## The "design doc vs ADR" pattern

For split:
- **Design doc:** Exploration
- **ADR:** Decision only
- **Link:** ADR to design
- **Why:** ADR captures why
- **Per:** Decision, not journey

The split is per use.

## The "default to lightweight" pattern

For default:
- **Heavy:** Architecturally significant
- **Light:** Most decisions
- **Why:** Adoption
- **Fix:** Lower the bar

The default is light.

## The "conflate ADR + RFC" anti-pattern

For conflate:
- **Issue:** Half-decided
- **Fix:** Split phases
- **Why:** Trust lost
- **Method:** RFC PR → ADR

The conflate is split.

## The "pros/cons dump" anti-pattern

For dump:
- **Issue:** Padding
- **Fix:** Decision outcome first
- **Why:** Dilutes record
- **Per:** Section, not body

The dump is structured.

## The "edit accepted" anti-pattern

For edit:
- **Issue:** Audit lost
- **Fix:** New ADR supersedes
- **Why:** History matters
- **Link:** Old to new

The edit is forbidden.

## The "heavyweight gating" anti-pattern

For heavy:
- **Issue:** Adoption killed
- **Fix:** Light default
- **Why:** Committee review
- **Per:** Significant only

The gate is light.

## The "design doc as ADR" anti-pattern

For disguise:
- **Issue:** 20 pages
- **Fix:** ADR + link
- **Why:** Scope creep
- **Per:** Decision only

The doc is separate.

## The "stale corpus" anti-pattern

For stale:
- **Issue:** Unmaintained
- **Fix:** Status lifecycle
- **Why:** Worse than none
- **Cadence:** Audit

The corpus is current.

## The "off-repo" anti-pattern

For off-repo:
- **Issue:** Wiki, Notion
- **Fix:** In repo
- **Why:** Code + reasons together
- **Per:** Decision

The repo is the source.

## The "YADR" pattern

For YAML:
- **Released:** March 2026
- **Format:** YAML syntax
- **Use:** Machine-parseable
- **Tooling:** Lint, index
- **Why:** Pipeline

The YADR is YAML.

## The "ADG CLI" pattern

For tooling:
- **Tool:** ADG (Go)
- **Generate:** ADR files
- **Validate:** Templates
- **2026:** Reference tool
- **Why:** Discipline

The ADG is the tool.

## The "ADR checklist" pattern

For checklist:
- [ ] One decision, one file
- [ ] Numbered, dated
- [ ] Immutable after accept
- [ ] Status explicit
- [ ] PR reviewed
- [ ] Lightweight
- [ ] MADR 4.0 template
- [ ] Front matter set
- [ ] Supersede link
- [ ] In repo (not wiki)
- [ ] No padding
- [ ] Audit cadence

The checklist is 12.

## The "MADR template" pattern

For template:
```markdown
# Use Postgres for OLTP

## Context and Problem Statement
[What's the issue?]

## Decision Drivers
* Performance
* Cost
* Team expertise

## Considered Options
* Postgres
* MySQL
* CockroachDB

## Decision Outcome
Chosen option: Postgres, because [why].

## Consequences
* Good: [benefits]
* Bad: [tradeoffs]

## Confirmation
[How to confirm this worked]
```

The template is MADR.

## The "RFC template" pattern

For RFC:
```markdown
# RFC: Use Postgres for OLTP

## Problem
[What's the issue?]

## Proposal
[Use Postgres]

## Alternatives
[Considered]

## Tradeoffs
[Pros/cons]

## Open Questions
[Discussion]

## Decision
[Snapshot to ADR when accepted]
```

The RFC is mutable.

## The "status audit" pattern

For audit:
- **Cadence:** Quarterly
- **Check:** Status current
- **Update:** Deprecated/superseded
- **Why:** Trust
- **Tool:** ADG

The audit is recurring.

## The "file structure" pattern

For repo:
```
docs/
  decisions/
    0001-use-typescript.md
    0002-monorepo-pnpm.md
    0003-cloudflare-pages.md
  rfc/
    0042-use-pgvector.md  # PR
```

The structure is in-repo.

## The "PR description" pattern

For PR:
- **Type:** RFC
- **Reviewers:** 1-2
- **Discussion:** Threaded
- **Approval:** Required
- **Merge:** → ADR

The PR is the gate.

## Verification
- **Test:** New devs find ADRs
- **Test:** Status current
- **Test:** Supersede links work
- **Audit:** Quarterly

## Gotchas
- **The "conflate" anti-pattern.** Split.
- **The "edit accepted" anti-pattern.** New ADR.
- **The "stale" anti-pattern.** Audit.

## Related
- `lessons/lazy-fail-evidence-discipline.md`
- `lessons/scope-discipline.md`
- `lessons/focus-time-over-velocity.md`
- `worktree/conventional-commits.md`
- `worktree/git-bisect-run-2026.md`
- MADR: https://adr.github.io/madr/
- ADR GitHub: https://adr.github.io/
- MADR repo: https://github.com/adr/madr
- ozimmer: https://ozimmer.ch
