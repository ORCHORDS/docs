# long-lived-branches-cause-merge-hell

**Issue:** A feature branch lives for six weeks. The team keeps building on it because "the feature isn't done yet", rebasing becomes a weekly chore, and by merge time the diff is 9,000 lines, the reviewer gives up, the merge conflicts with three other features merged in the meantime, and the integration bugs discovered after merging take longer than the feature itself. This article captures why long-lived branches fail — the core finding of the trunk-based development literature (Atlassian, trunkbaseddevelopment.com, CircleCI, LaunchDarkly, Statsig) is that branch age is the single best predictor of merge pain — and how to keep integration cheap.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How merge hell unfolds

1. **"Done" is defined as feature-complete, not integrated.** The branch stays open until the whole feature works, which guarantees it diverges from trunk for the entire build. Every day of divergence adds conflict surface, and the cost is compounding, not linear: a 6-week branch is far worse than 6 times a 1-week branch.
2. **Weekly rebases substitute for integration.** Rebase keeps history pretty but doesn't validate anything — the code compiles against trunk but is never tested against the trunk the other three features also changed. The conflicts you can see (textual) get resolved while the conflicts you can't (semantic, behavioral) accumulate silently.
3. **The big merge lands unreviewed.** A 9,000-line diff exceeds any reviewer's capacity; approval becomes "I trust you" with a thumbs-up. The review gate exists precisely for the riskiest change of the quarter and is weakest exactly there.
4. **Post-merge bugs look nothing like the branch's tests.** The branch's test suite passed in isolation the whole time; the failures after merging come from interactions with features that landed mid-branch. Nobody can reproduce them locally without the exact trunk state, so debugging happens in staging, slowly.
5. **The fix — "merge more often" — arrives too late as policy.** After the painful merge, the team agrees to "keep branches shorter", but with no supporting practices (flags, slicing) the next big feature repeats the cycle, because the root constraint was never addressed: incomplete features must be able to land safely.

## Root causes

1. **Trunk is kept "always releasable", so unfinished work can't enter it.** The team correctly protects trunk's stability but incorrectly concludes that half-done features must live on branches. The resolution is to decouple deployment from release (flags, dark launches), not to lengthen branches.
2. **Features are sliced horizontally across the stack.** A "branch per feature" where the feature spans UI, API, schema, and infra guarantees a wide, long-lived diff. Vertical thin slices — one narrow path through the stack, end to end — are mergeable in days.
3. **Merge frequency is treated as a personal habit, not an architectural constraint.** Integration cost is designed by how the work is decomposed, and by contract points (API boundaries, schema changes) that force coordination. If two features must touch the same file for weeks, the decomposition is wrong.
4. **GitFlow-style process makes long branches the default.** Multi-level branching models (develop, release, feature, hotfix) institutionalize divergence: every layer is a long-lived branch that must eventually be reconciled. The trunk-based literature's counter-proposal is blunt — the only long-lived branch is trunk itself.
5. **Fear of trunk instability beats fear of integration delay.** Teams feel the pain of a broken trunk immediately and the pain of merge hell months later, so they over-insure against the visible risk. This is a temporal-discounting error, not an engineering judgment.

## What to do instead

1. **Cap branch age, then enforce it with automation.** Target merged within 1-2 days (the trunkbaseddevelopment.com guidance for short-lived branches); have CI or a bot flag branches older than 3 days and escalate at 5. The number matters less than the existence of a number everyone can see.
2. **Hide unfinished work with flags, not branches.** Merge behind a feature flag default-off so trunk carries the code without exposing the behavior. The flag, not the branch, becomes the unit of incompleteness — and flags are cheap to flip, while branches are expensive to merge.
3. **Slice features into mergeable increments.** Before starting, decompose the feature into increments that each leave trunk coherent: scaffolding first, then behavior behind a flag, then the flag on. Each increment is a small PR with a small diff and a real review.
4. **Integrate trunk into the branch continuously.** Merge trunk into the branch (or rebase) on every change to trunk, run the full suite each time, and treat a red post-merge-in as a stop-work event. Semantic integration must be exercised daily, not discovered at the end.
5. **Pair on the big merges that still happen.** When a large merge is unavoidable, author plus reviewer resolve conflicts together with the tests running, because semantic conflicts need two people's context. Never let a mega-merge be resolved alone at 6pm.

## Gotchas

1. **Short-lived branches still need review discipline.** Trunk-based development trades branch lifetime for review latency: if PRs sit unreviewed for days, you have silently recreated long-lived branches with extra steps. Review SLAs are part of the deal.
2. **Flags create their own debt.** Every flag must have an owner and a removal date, or you accumulate hundreds of stale code paths — a cleanup problem that compounds just like the merge problem it replaced. Track flags like tech debt.
3. **Trained-on-GitFlow tooling fights back.** Release trains, release branches, and version-branch tooling assume long-lived branches; adopting trunk-based without changing the release tooling produces a hybrid that has the costs of both models.
4. **A single trunk requires trunk to actually be healthy.** If trunk breaks regularly, people will hoard stable branches as insurance. Invest in trunk CI quality (fast, deterministic, rollback-friendly) before demanding everyone integrate into it.
5. **"We're special, our features are huge" is usually a slicing failure.** Exceptions exist (platform rewrites, hardware-coupled work), but in review, most "unavoidable" mega-branches turned out to be five mergeable increments stacked behind one psychological commitment to shipping it all at once.
