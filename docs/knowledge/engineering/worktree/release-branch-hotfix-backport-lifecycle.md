# Release Branch Hotfix Backport Lifecycle

When production breaks, the fix must ship from a release branch, not `main`. The release branch holds the code that is actually deployed; `main` has moved on with features that are not yet released and cannot ride along in an emergency patch. The hotfix lifecycle — branch, fix, test, ship, backport, verify, retire — has failure modes at every seam: fixes that never reach `main`, fixes that reach `main` as a rewritten (and subtly different) change, and release branches that live forever. This article covers the full lifecycle as an operational discipline with controls at each step.

## Scope

This article addresses the hotfix workflow for maintained release branches: branching strategy for the fix, cherry-picking mechanics, divergence management between the release branch and `main`, version numbering conventions, and branch retirement. It covers team process and Git mechanics. It does not cover trunk-based development without release branches, deployment automation tooling, or incident command structure.

## Workflow or implementation guidance

The lifecycle in canonical form:

1. **Declare the hotfix.** From the incident, identify the release branch for the affected production version (e.g., `release/2.7`). If the fix is non-trivial, first reproduce on that branch. Declare the hotfix in the incident channel with: affected version, target release branch, intended patch version (2.7.4), and owner.
2. **Branch from the release branch.** `git switch release/2.7 && git switch -c hotfix/2.7.4/fix-payment-retry`. Never branch from `main` for a production fix: `main` contains unreleased changes that would ride along and expand the blast radius of the patch.
3. **Fix minimally.** The change set should be the smallest correct fix, excluding refactors, drive-by cleanups, and dependency bumps unless strictly required. Every additional commit widens review and regression surface under time pressure. Smallness is a safety property, not a style preference.
4. **Test against the release branch context.** Run the release branch's CI suite, plus a regression test that fails before the fix and passes after, on the hotfix branch. If the test only exists on `main`, port it into the hotfix branch so it ships with the patch.
5. **Ship.** Merge the hotfix branch into the release branch (direct merge or via a fast tracked PR with reduced review requirements per the emergency policy), tag `v2.7.4`, and deploy per the release pipeline.
6. **Backport to `main` — this step is the one teams skip and regret.** Two mechanisms:
   - **Cherry-pick the hotfix commits onto `main`** (or open a PR to `main` containing them). Because `main` has diverged, the pick may conflict; resolve conflicts preserving the fix's semantics, not merely textual overlap.
   - **Merge the release branch back into `main`** — acceptable only if the release branch is short-lived and contains nothing else; for long-lived branches, merging drags every accumulated release-only change into `main` and inverts the intended flow. Prefer cherry-pick.
7. **Verify equivalence.** After the backport lands on `main`, confirm the fix exists there: by cherry-pick provenance (`git log --cherry-pick --right-only main...release/2.7` style symmetry checks that suppress equivalent patches), by the regression test running in `main` CI, or by a linked pair of PRs (hotfix PR ↔ backport PR) cross-referenced in descriptions.
8. **Retire the branch.** Hotfix branches are deleted after merge; release branches are deleted when the version falls out of support. A release branch nobody deploys is a liability: it receives security bumps nobody verifies and invites accidental branching.

Cherry-pick mechanics worth standardizing. Use `git cherry-pick -x` to record the source commit hash in the new commit message — provenance that later audits and `--cherry-pick` symmetry checks rely on. For multi-commit hotfixes, cherry-pick the full range or use `git cherry-pick -x <base>..<tip>`; if review policy wants a single reviewable change on `main`, keep the hotfix itself as one commit from the start rather than squashing during backport (squashing during backport destroys the 1:1 mapping that symmetry checks use).

Divergence management. Over a release's life, `main` and the release branch accumulate asymmetries: refactors on `main` renamed the function the hotfix touches; the hotfix lands on `main` differently by necessity. Accept this, but require the *behavioral* regression test to exist on both branches, since it is the equivalence proof that survives textual divergence. Track divergence size: if backport conflicts become routine (say, >30% of hotfits conflict), the release branch is too long-lived or `main` churns too hard in stable areas — both are process signals, not Git problems.

Version discipline. Patch version increments only on the release branch; `main` is unversioned (or continuously versioned per trunk practice). The tag lives on the release branch merge commit. Recording "hotfix v2.7.4 ↔ backport PR #1234 ↔ incident INC-555" in one place (the incident record) creates the audit spine regulators and postmortems walk.

A worked example: payment retries double-charge in 2.7.3. Hotfix branched from `release/2.7`, one commit fixing the retry loop plus one test; tagged v2.7.4, deployed. Backport cherry-pick hits a conflict because `main` extracted the loop into `RetryPolicy`. Resolution: apply the same guard inside `RetryPolicy.shouldRetry`, keep the same test (adjusted import), and link both PRs. Six weeks later a similar bug report arrives; the engineer greps the test file, finds the 2.7.4 regression test on `main`, and knows exactly what already exists — the payoff of the equivalence step.

## Controls

- Enforce hotfix branch naming (`hotfix/<version>/<slug>`) in automation that rejects pushes of other shapes to release branches outside the emergency path.
- Require `-x` on cherry-picks via commit-message lint (source hash line present on backport commits); block backport merges without it.
- Require a regression test in the hotfix PR that fails pre-fix, and require that test to run in both release-branch CI and `main` CI after backport.
- Maintain an explicit support policy table (which release branches are active, end-of-support dates); automation opens a deletion PR on the date.
- Quarterly audit: list commits on active release branches with no `main` counterpart (`git cherry-pick --right-only --cherry-pick ...` or equivalent), and burn down the list; every unmatched commit is latent divergence that will surprise the next release.
- Emergency review policy: hotfix PRs need one senior review plus post-incident full review within 48 hours; track that the follow-up review happens.

## Validation evidence

- Cherry-pick provenance recording (`-x`), patch-id symmetry detection (`git log --cherry-pick`, `--left-right` with `--cherry-pick`), and branch/tag mechanics are specified in the official Git documentation (git-cherry-pick and git-log manual pages, Git Book distributed workflows chapters).
- GitHub's branch protection and required-check configuration governs the PR-based enforcement layer and is documented in GitHub's repository administration guide.
- A reproducible audit: run `git log --left-right --cherry-pick main...release/2.7` after a completed cycle; output shows `>` commits only for release-specific changes (version bumps) and `=` for none when backports are complete — a mechanical completeness proof for step 7.

## Failure modes and correction

- **Fix ships but never lands on `main`.** Symptom: the bug reappears in the next release; customers lose trust. Correct by making backport PR creation part of the hotfix definition of done, tracked in the incident record.
- **Backport rewritten beyond recognition.** Symptom: `main` and release behavior drift; the same bug number has two different code realities. Correct by behavioral-test equivalence and minimizing squash-during-backport.
- **Hotfix branches from `main`.** Symptom: patch carries unreleased features; regression blast radius explodes. Correct by automation rejecting release-branch PRs from non-hotfix refs and by training.
- **Long-lived release branches.** Symptom: backport conflicts routine, security patches pile up unverified. Correct by shortening support windows or adopting a backport-bot discipline (auto-open backport PRs the moment a fix lands on `main`).
- **Zombie branches.** Symptom: engineers branch from `release/1.9` "because it worked". Correct by scheduled deletion with announcements and a support-policy table.

## Limitations

- The lifecycle assumes release branches are an explicit support commitment; trunk-based teams with deploy-from-main pipelines need a different (simpler) hotfix path.
- Patch-id symmetry checks fail on semantically identical but textually rebased commits; they are an audit aid, not proof of behavioral equivalence — the regression test carries that burden.
- Very large organizations with layered release trains (multi-repo, multi-month trains) add staging complexity beyond single-repo cherry-pick flow.
- Emergency policy relaxation (fewer reviewers) trades review rigor for speed; the 48-hour follow-up review exists to repay that debt and must be enforced culturally.

## Canonical sources

- Software Freedom Conservancy (Git project), git-cherry-pick(1) Manual Page (-x provenance, patch equivalence): https://git-scm.com/docs/git-cherry-pick
- Software Freedom Conservancy (Git project), Pro Git Book, distributed workflows and branch management chapters: https://git-scm.com/book/en/v2
