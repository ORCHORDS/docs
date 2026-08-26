# project-stage-issue-flow-md-sync

**Issue:** Work flows through a repo as issues and PRs, but the .md docs (README, CHANGELOG, CONTRIBUTING, plans) drift out of sync with reality because nobody knows WHICH doc to update at WHICH stage. The team needs a per-stage documentation contract.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 8-stage flow

1. **Discovery.** Read README/CONTRIBUTING/existing masters/recent PRs; log every gap as its own child issue. No fixes yet.
2. **Master.** Create/extend the master issue; attach children with `--add-sub-issue`; order execution top-to-bottom.
3. **Plan.** Per child: search official docs and current reputable sources FIRST; post findings as a comment on the child. Never implement from memory.
4. **Execute.** One branch (`fleet/issue-N`) + one PR per child; `Fixes #N` in the PR body auto-closes on merge.
5. **Review.** Every reviewer finding is addressed or explicitly rebutted with evidence — silence is not an answer.
6. **Merge+check.** Merge → child closes → checkbox ticks → Status line edit in the same session.
7. **Doc sync.** Update the docs the merged change affects (table below).
8. **Close.** All boxes ticked → summary comment → close master; new gaps become a NEW master.

## Per-stage doc contract

1. **Discovery:** read everything, write nothing.
2. **Master creation:** CONTRIBUTING.md gains one pointer line ("current campaign: see #N").
3. **Plan:** the child issue's research comment is the doc — findings live on the issue.
4. **Execute:** code + tests only; usage-doc changes ride the SAME PR as the feature.
5. **Merge:** CHANGELOG.md gets one entry per child (`- (#N) what — visible effect`); README gets new flags/commands/env vars.
6. **Merge:** repo plans (ENGINEERING-PLAN.md, ROADMAP.md) tick their phase item.
7. **Close:** AGENTS.md/CLAUDE.md gain only durable rules (not narrated history); CHANGELOG cuts the phase's release section.
8. **Always:** if a doc contradicts merged code after stage 5, that's a bug — file a child issue immediately.

## Rules that prevent doc rot

1. **Docs ride the same PR as the code** when usage changes (new command, env var, default). "Docs later" PRs never get written.
2. **CHANGELOG is additive per merge**, not batch-written at release — memory reconstructs badly.
3. **AGENTS.md holds session-independent rules only**; session history lives in issue comments.
4. **One pointer, not duplication** — CONTRIBUTING points at the master issue instead of copying its contents.
5. **Plans tick items** (strikethrough or checkbox) rather than being rewritten — the plan stays auditable.

## Failure modes

1. Docs updated after the campaign instead of per-merge — drift compounds invisibly.
2. README shipping a flag the code dropped in review — same-PR rule violated.
3. CONTRIBUTING duplicating master content — two copies diverge within weeks.
4. Narrated history in AGENTS.md — the file grows unbounded and stops being read.
5. Contradiction between doc and code treated as cosmetic — it misleads the next agent into "fixing" working code.

## Related

- `master-issue-pattern.md`
- `master-issue-checkoff-followup-protocol.md`
