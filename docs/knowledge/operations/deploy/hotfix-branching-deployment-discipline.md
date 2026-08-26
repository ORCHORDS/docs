# hotfix-branching-deployment-discipline

**Issue:** During a production incident on example project, the on-call engineer pushed a one-line fix directly to `main`, deployed it from a laptop while the CI queue was backed up, and never cherry-picked the change back through the release branch. Three weeks later the same bug resurfaced in the next release, and the post-incident review could not reconstruct which gates the emergency deploy had skipped. The team has no written rules distinguishing a hotfix from a normal deploy, so every incident re-improvises the process under pressure.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Qualifies as a Hotfix

1. **User-facing severity is the trigger, not urgency of the requester.** A hotfix is for an active production incident: data loss, security hole, payment failure, or a broken critical path. A stakeholder wanting a feature early is a prioritization problem, not a hotfix.
2. **Small and reversible by definition.** If the fix is more than roughly 50 lines or touches more than one subsystem, it is a branch-and-deploy-fast, not a hotfix — large emergency changes have historically caused the follow-on incident more often than the original.
3. **Rollback is evaluated first.** Before writing a hotfix, ask whether reverting the offending deploy is faster and safer. Rollback needs no code review at all; see `rollback-runbook.md` in this directory.
4. **Time-boxed authority.** Hotfix authority belongs to the incident commander role, expires when the incident closes, and every use of it is logged to the incident timeline.

## Branching Rules

1. **Cut from the production tag, not from `main`.** The fix must apply to the exact commit running in production; `main` may have moved past it with unreleased work. Branch `hotfix/<issue>-<slug>` from the deployed Git tag.
2. **Land the fix on the hotfix branch and deploy that tag.** The pipeline builds and ships the hotfix branch commit — never an uncommitted local build.
3. **Merge back both places, always.** In a GitFlow-style layout the hotfix merges to `main` and to the release branch; under trunk-based development it merges to `main` immediately and there is no second place. The classic failure (documented in `worktree/branch-strategies-2026.md`) is merging only to `main` and letting the fix evaporate at the next release cut.
4. **One fix per branch.** Bundling "while I'm in here" changes onto a hotfix branch is how a 2-line emergency fix becomes an unreviewable 300-line diff.
5. **Cherry-pick, don't rebase the branch away.** Use `git cherry-pick -x` so the origin SHA is recorded in the commit message for traceability.

## Gate Triage: What May Be Skipped vs Never

1. **Never skip: unit tests, build, and artifact signing.** A hotfix that cannot pass a test suite in CI is not a hotfix, it is a gamble. Fast-track means expedited scheduling, not disabled verification.
2. **Never skip: at least one human review.** Even 10 minutes of a second pair of eyes during the incident. Solo-authored emergency changes are the top source of secondary incidents in post-incident reviews.
3. **Usually skippable: full E2E regression, load tests, and staging soak.** These are the hours-long gates; run them against the merge-back to `main` instead, while production is already on the hotfix.
4. **Compress, don't remove, approvals.** A single named approver (incident commander) replaces the normal two-reviewer rule; the change-management record still exists, created retroactively within 24 hours — this is the standard "emergency change" pattern in ITIL-style change control.
5. **Feature flags beat hotfixes where possible.** If the offending behavior is behind a flag, killing the flag is a config change with instant revert — see `feature-flag-deploy-coupling.md`.

## Pipeline Fast-Path Design

1. **A pre-declared lane, not ad-hoc button-mashing.** Define a `hotfix` deploy pipeline variant up front: same build/test steps, dedicated runner pool or priority queue, and pre-warmed environments, so the emergency path is exercised and known-good before it is needed.
2. **Test the fast-path in drills.** Rollback and hotfire drills (see `rollback-drills-restore-testing.md`) should include a timed hotfix lane exercise; if the expedited path has not run in 3 months, its first real use will fail on rot.
3. **Bypass nothing silently.** Every skipped gate in the hotfix lane emits an event to the incident channel: "e2e suite skipped by policy for hotfix #482". Skips must be visible in the moment, not discovered in review.
4. **Same observability as a normal deploy.** The hotfix deploy runs the same post-deploy smoke checks and monitoring annotations so dashboards can correlate the incident recovery with the deploy marker.

## Post-Hotfix Hygiene

1. **Merge back within 24 hours.** The longer the hotfix branch lives, the more it conflicts with `main`; past a few days the merge-back becomes its own mini-project.
2. **Retro-run the skipped gates.** Run the skipped E2E/load suites against the merged `main` commit and record results on the incident ticket — this closes the audit gap between what was verified before deploy and after.
3. **Count hotfixes as a quality signal.** Hotfix frequency next to change-failure-rate (see `change-failure-rate.md`) tells you whether your normal pipeline is too slow — teams that hotfix weekly usually have a gate problem, not a code problem.
4. **Post-incident review covers the process, not just the bug.** Every hotfix triggers at least a lightweight review question: could this have been a rollback, a flag kill, or a normal fast deploy instead?
