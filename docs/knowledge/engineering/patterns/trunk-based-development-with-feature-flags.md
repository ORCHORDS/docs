# trunk-based-development-with-feature-flags

**Issue:** TBD + flags + merge queue
**Date:** 2026-08-09
**Status:** documented

## Symptom
3 PRs ready. All green. You merge in sequence.
PR #<number> breaks main. PRs 1 and 2 were "green" but
on top of broken PR #<number>. You need merge queue.

## Root cause
**Sequence ≠ race-free.** TBD + queue + flags.

**Source:** TBD + GitHub Docs 2026.

## The "TBD" concept

TBD (Trunk-Based Development):
- **Branch:** main only
- **Commit:** Daily
- **Duration:** < 1 day branches
- **Use:** Continuous integration
- **Why:** Always releasable

The TBD is the model.

## The "feature flag" concept

For incomplete:
- **Wrap:** In flag
- **Merge:** Disabled
- **Ship:** Dark
- **Activate:** Per flag
- **Why:** Merge ≠ release

The flag is the gate.

## The "merge queue" concept

For sequence:
- **Batch:** Combined diff
- **Test:** On combined
- **Order:** FIFO
- **Use:** Race-free
- **Why:** No breaks

The queue is the order.

## The "commit daily" pattern

For cadence:
- **Every:** 24 hours
- **Why:** Integration
- **Skip:** Reverts trunk
- **Fix:** Daily

The commit is daily.

## The "short-lived branch" pattern

For lifetime:
- **Hours:** < 1 day
- **Why:** Merge debt
- **Fix:** Push often
- **Long:** Anti-pattern

The branch is short.

## The "release flag" pattern

For type:
- **Lifespan:** Days to weeks
- **Remove:** At 100%
- **Use:** Incomplete
- **Type:** Release
- **Why:** Defined

The release is per type.

## The "flag types" pattern

For choice:
- **Release:** Days-weeks
- **Experiment:** A/B
- **Ops:** Kill switch
- **Permission:** Identity
- **Why:** Match lifespan

The type is per need.

## The "merge queue" pattern

For race:
- **CI:** On combined
- **Order:** FIFO
- **Group:** Batched
- **Use:** Many PRs
- **Why:** Race-free

The queue is FIFO.

## The "long-lived branches" anti-pattern

For long:
- **Issue:** Merge hell
- **40 branches:** 3-day conflict
- **Fix:** Hours
- **Why:** Debt

The branch is short.

## The "TBD without flags" anti-pattern

For no flags:
- **Issue:** Work not merged
- **Fix:** Flag incomplete
- **Why:** Lost benefit

The flag is used.

## The "stale flags" anti-pattern

For old:
- **Issue:** Debt compounds
- **Fix:** Remove at 100%
- **Why:** Combinatorial

The flag is cleaned.

## The "wrong type" anti-pattern

For conflate:
- **Issue:** Release used as permission
- **Fix:** Match type
- **Why:** Cleanup

The type matches.

## The "no merge queue" anti-pattern

For small team:
- **Issue:** Cross-PR breaks
- **Fix:** Queue
- **Why:** Cheap insurance

The queue is set.

## The "no CI gate" anti-pattern

For skip:
- **Issue:** Broken trunk
- **Fix:** Enforced CI
- **Why:** TBD requires

The CI is enforced.

## The "release branch" anti-pattern

For quarter:
- **Issue:** GitFlow
- **Fix:** TBD + flags
- **Why:** Lost CI

The branch is short.

## The "TBD checklist" pattern

For checklist:
- [ ] Commit daily
- [ ] Branches < 1 day
- [ ] Flags for incomplete
- [ ] Match flag type
- [ ] Merge queue enabled
- [ ] CI on queue
- [ ] Flags cleaned weekly
- [ ] No release branches
- [ ] Default flag = off
- [ ] DORA + SPACE tracked

The checklist is 10.

## The "merge = deploy, flag = release" pattern

For model:
- **Merge:** To trunk
- **Deploy:** Continuous
- **Release:** Per flag
- **Why:** Decoupled
- **Fix:** Both

The model is decoupled.

## The "AI agents TBD" pattern

For AI:
- **Many small PRs:** Agents
- **Need:** TBD
- **Merge queue:** Required
- **Why:** Volume
- **Fix:** Both

The agent is TBD.

## Verification
- **Test:** Daily commit
- **Test:** Flag cleaned
- **Test:** Queue FIFO
- **Audit:** Weekly

## Gotchas
- **The "long branches" anti-pattern.** Hours.
- **The "stale flags" anti-pattern.** Cleaned.
- **The "no queue" anti-pattern.** Set.

## Related
- `worktree/github-merge-queue.md`
- `worktree/conventional-commits.md`
- `patterns/feature-flags-best-practices.md`
- `deploy/trunk-based-development.md`
- `deploy/canary-deployments.md`
- TBD: https://trunkbaseddevelopment.com/
- Fowler: https://martinfowler.com/articles/feature-toggles.html
- GitHub queue: https://docs.github.com/en/repos/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-queues
