# Squash Merge Versus Merge Commit Policy

How a pull request lands on the mainline is a policy decision with lasting consequences. Squash merging compresses the PR into a single commit; a merge commit preserves every branch commit plus a merge node; rebase merging replays commits without a merge node. The choice shapes history readability, `git bisect` granularity, commit attribution, revert semantics, and changelog tooling. Teams that drift between methods get the worst of each: noisy mainlines, un-revertable squashes, and attribution fights in CODEOWNERS-era tooling. This article covers the mechanics, the tradeoffs, and how to set and enforce a deliberate policy.

## Scope

This article addresses merge-method selection for pull requests on GitHub-style platforms: squash merge (single compressed commit), merge commit (preserve branch history with a merge node), and rebase merge (linear replay), including commit-message construction for squashes, attribution, revert behavior, and enforcement via repository settings. It covers policy design for team scale. It does not cover merge queues, hotfix backport mechanics, or monorepo build tooling.

## Workflow or implementation guidance

The three methods produce three different histories for the same work:

- **Merge commit:** `main` gains a merge commit with two parents. All intermediate branch commits (the WIPs, the "fix typo", the review-driven rewrites) enter the mainline. History is faithful to how work happened; the mainline is noisy; `git log` interleaves fragmentary commits; each intermediate commit may not build or pass tests in isolation.
- **Squash merge:** `main` gains exactly one commit whose diff equals the net PR diff. The mainline reads as a curated sequence of reviewable units. Intermediate history survives only on the (usually deleted) PR branch and in the PR page. The squash commit message defaults to the PR title plus commit list; policy should define its construction.
- **Rebase merge:** every branch commit replays onto `main`, rewritten with new hashes, no merge node. Linear like squash but multi-commit; each replayed commit keeps its original (possibly WIP-grade) message.

Decision framework:

1. **Default to squash for feature work.** The PR is the unit of review, so make it the unit of history. A squash commit corresponds one-to-one with a reviewed, CI-verified change set. `git bisect` lands on whole PRs — the granularity at which "does this commit build" is actually guaranteed, since intermediate branch commits are rarely individually green.
2. **Preserve merge commits where history itself is the artifact.** Release integration (merging `release/2.7` back or forward), long-lived vendor/topic branches whose commit lineage auditors must trace, and any workflow where per-commit provenance is contractual (some regulated or upstream-mirror contexts). Merge commits also make `git log --first-parent` a clean changelog of integrated units.
3. **Rebase merge for stacked small commits by disciplined authors** — few teams sustain the discipline (each replayed commit green and well-messaged). If you cannot enforce per-commit hygiene in CI, squash.
4. **One method per branch, enforced.** GitHub lets you enable all three; enabling all three invites per-author roulette. Enable exactly one on protected mainlines; exceptions (release merges) can be performed by automation or admins outside the PR button, deliberately.

Squash-specific policy details that make or break it:

- **Commit message construction.** The squash message should be: PR title as the subject (imperative, scoped, ≤72 chars), PR body or a curated summary as the body, plus a trailer pointing to the PR (`(#1234)` suffix or `Pull-Request: #1234`). Never let the default "(#1234)" commit-list blob ship as the subject.
- **Attribution.** Squash credits the PR author as committer; co-authors get lost unless trailers are added (`Co-authored-by:` lines for meaningful contributors). Policy: CI or a bot appends co-author trailers from PR metadata; release notes tooling reads trailers, so losing them erases contributors from the record.
- **Revert semantics.** A squash reverts as one commit — clean. But a squash that mixed two logical changes reverts both; keep PRs single-purpose so the revert unit matches the review unit. Merge commits revert with `git revert -m 1`, which is fine once but famously conflicts when the same region later changes — squash's one-commit model avoids the `-m` bookkeeping.
- **Cherry-pick/backport.** Squashed commits are stable, single units — ideal for cherry-picking to release branches. Un-squashed merge-commit histories make backports a range-picking exercise.
- **Commit signing.** Squash commits are created by the platform and, on GitHub, are signed by GitHub's web-flow key; GPG-signed author commits are preserved under merge/rebase methods. If your policy requires author signatures on mainline commits (supply-chain provenance programs), squash's platform signature is a different (weaker for author identity) claim — decide which claim you need.

Anti-patterns to outlaw: mixed squash-then-merge on the same mainline; "update branch" merges polluting PR history before squash (GitHub's "Update branch" button adds a merge node into the PR branch; the squash still nets out, but PR diff views get noisy — prefer rebase-update where offered); squashing PRs larger than ~1,500 changed lines (review already failed at that size; splitting beats squashing).

A worked example: a 40-commit PR lands. Squashed, `main` shows `Add retry budget to payment client (#1234)` — one bisect point, one revert unit, changelog entry automatic from the PR title. Merge-committed, `main` shows 40 interleaved fragments; bisect may pin "fix typo" as the culprit commit that doesn't even build standalone. The team's bisect time and revert friction, not aesthetics, are the measurable difference.

## Controls

- Configure exactly one merge method on each protected mainline; disable the others in repository settings; exceptions flow through automation with review.
- Enforce squash-message policy with a commit-message lint on mainline (subject ≤72 chars, imperative mood, PR reference present, trailers preserved) — check the resulting mainline commits in CI or via a bot on the merge event.
- Automate `Co-authored-by` trailer injection from PR contributors before squash; audit release notes tooling reads them.
- Keep PRs single-purpose: size limits in CI (soft warning at ~800 lines diff, hard review discussion at ~1,500) so squash units stay revertable.
- For repos needing author-signature provenance, document that squash replaces author signatures with platform signatures, and pair with branch protection requiring signed commits only if the platform signature satisfies the threat model.
- Quarterly spot-audit `git log --first-parent main`: it should read as a clean, ordered narrative of integrated PRs; interleaved noise indicates policy drift or method exceptions being abused.

## Validation evidence

- Squash, merge-commit, and rebase merge mechanics, their repository settings, commit-message construction (including PR-number suffix defaults and co-author trailer behavior), and platform commit signing are documented in GitHub's official documentation on configuring pull request merges.
- Git-side semantics — merge commits' two parents, `git revert -m`, bisect granularity, `--first-parent` traversal — are specified in the Git manual pages and Pro Git book.
- A reproducible comparison: land an identical two-commit PR twice in scratch branches, once squashed and once merge-committed; run `git log --oneline --first-parent`, `git bisect` over an injected breakage, and `git revert` of the change — the three commands demonstrate the operational differences concretely.

## Failure modes and correction

- **All methods enabled.** Symptom: unpredictable history shape; tooling (changelog, backport bots) breaks per PR. Correct by settings lockdown.
- **Default squash subjects shipping.** Symptom: mainline subjects like `fix (#1234)`; changelogs unusable. Correct by message lint plus PR title standards.
- **Lost co-authors.** Symptom: contributor recognition disputes; release notes missing people. Correct by automated trailers.
- **Squash mixing logical changes.** Symptom: reverting a bugfix reverts a feature. Correct by PR size/purpose limits.
- **Merge-commit hotspots reverting badly.** Symptom: `revert -m` conflicts recur in stable files. Correct by reserving merge commits for release integration, not feature flow.

## Limitations

- Merge-method policy is platform-shaped; GitLab and Gerrit have analogous but differently named controls and default behaviors.
- Squash erases fine-grained history; teams that legitimately need it (research provenance, some compliance regimes) must archive PR branches or export refs before deletion.
- Platform signing of squash commits satisfies authenticity-of-merge, not author-key provenance; strong supply-chain programs may require policy adjustments.
- History policy interacts with monorepo tooling (per-directory changelogs, split repos) in ways that need repo-specific design beyond a single-team default.

## Canonical sources

- GitHub, Configuring pull request merges (squash, merge commit, rebase settings and behavior): https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github
- Software Freedom Conservancy (Git project), Pro Git Book — branches, rebasing, and distributed workflows: https://git-scm.com/book/en/v2
