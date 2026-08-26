# rfc-process-design

**Issue:** Big decisions — changing the public API, adopting a new datastore, restructuring the deployment — get made in a hallway chat or a long Slack thread, then implemented. Six months later nobody can reconstruct why the decision was made, what alternatives were rejected, or who agreed to what, and the same debate reopens with each new team member. Meanwhile, when someone does write a design document, it balloons into a 40-page specification that reviews die in, because there was no shared template, no clear review window, and no definition of "decided". The team needs a lightweight RFC (request for comments) process: written proposals with a fixed structure, an explicit decision gate, and an archive that future readers can mine for rationale.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When an RFC is required

1. **Write a threshold rule, not a feeling.** RFC when the change is hard to reverse, crosses module or team boundaries, alters public contracts, or adds/removes a dependency; typo fixes and internal refactors never need one.
2. **Time it between shape and lock-in.** Guidance from teams running mature processes (Attentive, Pragmatic Engineer): start the RFC once a concrete design direction exists but before implementation details are settled — earlier produces vapor, later produces rubber-stamping.
3. **Small can still be written down.** For decisions below the RFC threshold, a one-paragraph decision-record comment on the tracking issue captures rationale without the ceremony.
4. **Never use RFCs as after-the-fact documentation.** A doc written to justify code already merged is a postmortem in costume; Fuchsia's explicit rule — RFCs are for buy-in before building, not archival description — prevents this decay.

## Document structure

1. **Summary (5 lines).** What is proposed and what changes if accepted; a reader who stops here should still vote intelligently.
2. **Motivation and problem statement.** The concrete pain, with evidence (issues, metrics, support load) — most rejected RFCs fail here, not in the solution, because the problem was fuzzy.
3. **Proposed change.** The design at the level of interfaces and moving parts, with diagrams where structure matters; implementation minutiae stays out.
4. **Alternatives considered.** Each real alternative with why it was not chosen, including "do nothing" — this section is the archive's highest-value content and the first thing future re-openers must engage with.
5. **Tradeoffs and risks.** What gets worse, what breaks, what migration costs; an RFC with no listed downside has not been thought through.
6. **Rollout and migration.** How the change lands incrementally, including the escape hatch if it needs reverting.

## Lifecycle states

1. **`draft` → `review` → `decided` (or `rejected`) → `implemented`.** Each transition is marked in the RFC's front matter and its tracking issue, so status is never inferred from vibe.
2. **Review has a clock.** A stated window (e.g. 7-10 calendar days) with a named owner who calls the result; open-ended review is where RFCs go to die silently.
3. **A small, named reviewer set.** The Pragmatic Engineer's rule: a few select reviewers beats an all-hands invite — two or three domain stakeholders plus one skeptical generalist produces better feedback than twenty thumbs.
4. **Feedback is resolved, not just received.** Every substantive comment gets addressed or explicitly rebutted in the thread before the decision call, mirroring code-review discipline; silence is not consensus.
5. **Decision rights are written down.** State up front who decides (author + tech lead, or a maintainers vote) so the end of review produces a verdict instead of a fade-out.
6. **Rejection is a first-class outcome.** A rejected RFC is kept and indexed — a documented "no, because" prevents relitigating the same idea annually.

## Process mechanics

1. **One numbered RFC per decision.** Sequential IDs with files in `docs/rfcs/` (or issues tagged `rfc`) give stable references like "see RFC-14" for code comments and future issues.
2. **The RFC links to a tracking issue.** When accepted, spawn or link an implementation issue; the RFC records the what-and-why, the issue tracks the doing, and neither duplicates the other.
3. **Asynchronous-first discussion.** Written comments on the doc itself, with at most one sync meeting for genuinely contested points — transparency patterns (InnerSource) show async written debate scales across teams where meetings do not.
4. **Set a size ceiling.** If an RFC exceeds roughly 5-8 pages, split it: one umbrella decision plus scoped children; bloat is the top killer of review quality.
5. **Template lives in-repo.** A copy-paste `docs/rfcs/0000-template.md` with the section skeleton and the state machine at the top removes the blank-page excuse.

## After the decision

1. **Stamp the outcome in the doc.** Accepted/rejected, date, deciders, and a one-line summary of the deciding argument become part of the permanent record.
2. **Link decisions from code.** PRs and comments reference the RFC number, so archaeology from a suspicious codebase spot leads straight to rationale.
3. **Revisit on triggers, not nostalgia.** An RFC is reopened when its stated assumptions break (new evidence, new constraints), and the reopening must engage the alternatives section — "I would decide differently" without new information is not a trigger.
4. **Audit the pipeline quarterly.** Count RFCs stuck in `review` past their window and decisions never linked to implementation issues; both are process leaks that compound.
5. **Mine the archive for patterns.** Repeated rejected-proposal themes are product signal, and recurring tradeoff sections flag structural debt the roadmap should address.
