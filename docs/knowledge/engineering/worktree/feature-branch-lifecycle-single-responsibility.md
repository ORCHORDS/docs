# Feature Branch Lifecycle Single Responsibility

## Scope

This article covers the lifecycle of a feature branch under a single-responsibility rule: one branch carries one coherent change, from creation through merge and deletion, with defined states, aging limits, and split procedures for branches that grow a second responsibility. It applies to trunk-based and short-lived-branch workflows. It does not cover branch strategy selection, merge method policy, or release branch management.

## Workflow or implementation guidance

A feature branch has one job. When it acquires a second job, every downstream activity degrades: review gets slower because the reviewer must hold two designs in mind, CI gets slower because it tests both, rollback gets riskier because reverting one change reverts the other, and the eventual squash commit tells two stories under one message. Single responsibility is not an aesthetic preference; it is what makes review, revert, and changelog generation tractable.

The lifecycle has five states, each with an exit condition.

**State 1 — Spawned.** Created from the default branch's current tip, named for exactly one responsibility. Exit: first commit pushed. A branch sitting spawned-but-empty for more than a day is usually someone parking a name; delete it or fill it.

**State 2 — In progress.** The developer is committing toward the single responsibility. Exit: opened as a draft pull request. Two aging rules apply here. First, branch age from default-branch divergence should stay under roughly three days before the first integration — either merge or rebase — because older divergence means the conflict bill compounds. Second, the in-progress state should end within a week. A branch that lives longer is either too large (split it) or blocked (make the blocker visible and stop committing on top of it).

**State 3 — Open for review.** Draft opened, then marked ready, with CI green. The branch is now shared property: no force-push without notice, no surprise scope additions. Exit: approved and merged, or rejected and deleted. This state has the hardest limit: if a PR sits in review beyond five business days, something is wrong — the change is too big, the reviewers are overloaded, or the design dispute is being litigated in line comments. All three have better venues: split, load-balance, or write a short design note.

**State 4 — Integrated.** Merged to the default branch. The merge is where responsibility is recorded: one branch, one merge or one squash, one changelog entry. Exit: branch deleted. Delete the branch at merge time, immediately and automatically. Deleted branches are recoverable from the merge commit, and a remote full of live merged branches is a navigation tax everyone pays forever.

**State 5 — Merged and deleted.** The terminal state. The branch's responsibility now lives in the default branch's history, ideally findable as one commit or one merge.

**The split procedure.** The rule earns its keep when a branch grows a second responsibility — you fix the feature, and along the way you repair an unrelated bug you tripped over. The procedure: commit the unrelated fix on the feature branch if you must, but do not merge it as part of the feature. Before opening review, split it out with an interactive rebase on a scratch branch — move the unrelated commits to a new branch off the default branch, open it as its own small PR, and let the feature branch drop back to its single responsibility. The cost of the split is ten minutes of rebase; the cost of not splitting is a reviewer disentangling two changes, a changelog entry that lies, and a revert that takes down a feature to remove a bug fix.

**Stacking, when work genuinely depends on work.** Sometimes responsibility two cannot exist without responsibility one. Stack it: a second branch based on the first, two PRs, the second marked as depending on the first and targeting the first branch until it merges. Stacking preserves single responsibility per branch; it trades merge-order coordination. Keep stacks two deep at most — deeper stacks serialize too many reviewers and rot quickly.

**Draft PRs as the aging control.** Opening a draft early makes branch age visible to the team without requesting review, which converts "quietly diverging branch" into "visible work in progress." It also gives CI a chance to run continuously rather than once at the end, so the integration exit is boring.

**The integration cadence rule.** However the team integrates — rebase onto the latest default branch or merge the default branch in — do it at least every two to three days on any open branch. The rule is about conflict interest: conflicts resolved in small batches while context is fresh are cheap; conflicts resolved after two weeks of parallel development are reimplementation.

## Controls

- One branch, one responsibility, enforced socially at PR open: the PR description states the single responsibility in one sentence.
- Aging limits by state: divergence-to-first-integration under three days, in-progress under one week, review under five business days.
- Integration cadence of every two to three days for any open branch.
- A defined split procedure using interactive rebase before review when a second responsibility appears.
- Stacking limited to two levels, with dependency marked on the upper PR.
- Automatic branch deletion on merge; merged-but-alive branches are audited and removed.

## Validation evidence

Branch lifecycle discipline is fully measurable from version-control history:

- Compute branch age at merge for the last quarter; the distribution's median and 90th percentile should sit inside the aging limits, and the tail should be explainable branch by branch.
- Measure divergence: for each merged PR, the number of commits that landed on the default branch while the feature branch was open. Rising divergence with flat PR size means integration cadence has slipped.
- Audit merged PRs for single responsibility: sample ten per month and check whether the diff and description tell one story. PRs whose review threads contain two unrelated topics are split failures.
- Count live branches older than two weeks; each one gets an owner conversation — merge it, split it, or delete it.
- Verify branch deletion on merge: the count of merged-but-live remote branches should be near zero at all times.
- Correlate PR review turnaround with PR size; when the two rise together, the split procedure is not being applied.

## Failure modes and correction

- **The accumulator.** A branch collects a feature, a bug fix, a dependency bump, and a refactor over three weeks. Correction: run the split procedure before review; if review has started, split into stacked PRs rather than expanding scope.
- **Zombie branches.** Half-finished branches live on the remote for months, blocking names and confusing navigation. Correction: two-week age audit with explicit merge/split/delete decisions.
- **Silent divergence.** The branch looks fine but is 200 commits behind the default branch. Correction: the integration cadence rule, made visible by divergence reporting per open PR.
- **Blocked-but-growing.** The PR waits on a decision while the developer keeps committing to it. Correction: freeze the branch when blocked; park new work on a fresh branch.
- **Deep stacks.** Five stacked PRs each waiting on the one below. Correction: two-level stack limit; deeper dependencies mean the bottom change is too large and should be merged behind a flag.
- **Merge-time deletion skipped.** Hundreds of live merged branches accumulate. Correction: automatic deletion on merge, plus a cleanup sweep.

## Limitations

Single responsibility per branch is a discipline for feature work; exploratory spikes, long-running refactors, and migration branches legitimately violate short-branch aging rules and need their own explicit lifecycles rather than being squeezed into these limits. The aging numbers are calibrated defaults that assume CI runs in minutes and reviews happen in business hours — a team with hour-long CI or distributed reviewers will need different numbers, and that is fine as long as they are chosen, not discovered. The split procedure depends on contributors being comfortable with interactive rebase; without that skill, splits happen rarely regardless of policy. Stacking support varies by platform and works best when the upper PR's base can be retargeted cleanly. Nothing here addresses whether the one responsibility itself is well designed — a perfectly disciplined branch can still carry a bad idea.

## Canonical sources

- Git documentation — git-branch (branch creation and lifecycle): https://git-scm.com/docs/git-branch
- Git documentation — git-rebase (interactive rebase for the split procedure): https://git-scm.com/docs/git-rebase
- GitHub Docs — Creating and deleting branches within your repository: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-and-deleting-branches-within-your-repository
- Atlassian Git tutorials — Comparing workflows (short-lived branch patterns): https://www.atlassian.com/git/tutorials/comparing-workflows
