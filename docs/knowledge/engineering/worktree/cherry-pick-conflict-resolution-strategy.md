# Cherry-Pick Conflict Resolution Strategy

## Scope

This article covers a disciplined strategy for resolving conflicts that arise during cherry-picks: when a conflict means the pick is still worth doing, when it means the target branch has already diverged past the point of picking, how to resolve mechanically without inventing new semantics, how to record provenance, and how to verify the result. It applies to backports to release branches, hotfix propagation, and picking individual commits off abandoned branches. It does not cover general merge-conflict tooling, rebase conflict handling, or the decision of revert versus cherry-pick during an incident.

## Workflow or implementation guidance

The central principle: during a cherry-pick conflict, you are applying someone else's decision to a context you did not write, so your job is to reconstruct their intent, not to improve it. Every deviation from that rule converts a mechanical backport into an unreviewed redesign smuggled into a release branch.

Run every pick through five phases.

**Phase 1 — Preflight.** The working tree must be clean and the target branch must be exactly at its remote state. Verify with `git status --porcelain` returning nothing, then `git fetch origin`, then `git switch release/v3.2` and `git reset --hard origin/release/v3.2`. A dirty tree during a pick is how half-applied work leaks into a release. If you cannot hard-reset because of local changes, stop — you are on the wrong branch or the wrong machine, and the pick needs a dedicated worktree instead.

**Phase 2 — Source audit.** Before picking, read the whole source commit, not just the diff hunks: `git show <sha>` including the message, and check it is atomic — one logical change. If the commit bundles a fix with a refactor, split it first with an interactive rebase on a scratch branch, and pick only the fix. Picking a bundle means resolving conflicts in code you never intended to ship.

**Phase 3 — Pick with provenance.** Use `-x` unconditionally for anything landing on a shared branch: `git cherry-pick -x <sha>`. The appended "(cherry picked from commit ...)" line is what lets a future auditor connect the release branch to the original change without guessing. Add `-s` where the project requires a sign-off. Never edit away the provenance line while resolving conflicts.

**Phase 4 — Conflict resolution with rules.** When the pick stops on conflicts, classify each conflict before touching it, because the classes have different correct responses.

- *Context drift*: both sides agree on the change, but surrounding lines moved. Resolve by repositioning the source hunk. Low risk.
- *Semantic overlap*: the target branch contains a different implementation of the same behavior. This is a stop signal. Do not merge the two implementations by hand; instead determine which one is canonical now. If the target already has the fix, abort the pick and close the backport as unnecessary, recording that decision on the ticket. If the source fix is the newer truth, the pick becomes a small ported patch that needs its own review, not a mechanical application.
- *Missing prerequisite*: the source commit depends on an earlier commit that was never backported. Resolve by picking the prerequisite first — check with `git log --oneline <target>..<source-branch>` or by reading the source PR's linked commits. Picking a dependent fix without its base produces code that compiles and behaves subtly wrong.
- *Generated-file conflict*: lockfiles, compiled schemas, or bundled output conflict. Never hand-merge these. Resolve by regenerating on the target branch with the source's inputs.

While resolving, keep three rules. First, resolve hunk by hunk and stage deliberately with `git add <path>`; never `git add -A` during a pick, because it stages unrelated drift. Second, the resolution must preserve the source change's observable behavior; if you find yourself choosing between the two sides' logic, you are in semantic overlap and should stop. Third, run the tests from the source PR against your resolution before continuing — `git cherry-pick --continue` only checks that conflicts are gone, not that the fix still works.

**Phase 5 — Escalation and abort.** If a pick stops more than twice, or a single conflict spans more than a screen of either side, the branches have diverged too far for mechanical picking. Abort with `git cherry-pick --abort`, which restores the pre-pick state cleanly, and port the change as a fresh commit on the target branch that references the original PR in its message. A hand-port with full review is slower than a clean pick but far cheaper than a botched one.

Every completed backport goes through a pull request to the release branch — never a direct push — so CI and a reviewer see the resolution. The reviewer's specific job is to diff the resolution against the source commit and confirm the deltas are contextual only.

## Controls

- Clean-tree and remote-sync preflight is mandatory; picks in a dirty tree are stopped.
- `-x` provenance on every pick to a shared branch; the provenance line is never removed.
- Source commits must be atomic; bundles are split on a scratch branch before picking.
- Conflict classification is explicit: context drift, semantic overlap, missing prerequisite, generated file.
- Generated files are regenerated, never hand-merged.
- `git add` is per-path; bulk staging during a pick is prohibited.
- Backports merge only through a PR with CI green and a reviewer who diffs resolution against source.
- Two-conflict or large-hunk threshold triggers abort and hand-port with review.

## Validation evidence

Every backport is verifiable after the fact, and the checks are cheap enough to run on each one:

- Confirm provenance: the merged commit on the release branch contains the "(cherry picked from commit <sha>)" trailer, and that sha exists on the source branch.
- Diff the pick against its source with `git range-diff` or a direct patch comparison; the expected deltas are limited to context and import paths. Deltas touching decision logic indicate a semantic resolution that needed review.
- Run the release branch's test suite, and specifically the tests covering the picked fix, on the target branch after the pick. Tests passing on the source branch prove nothing about the target.
- For generated files, verify the committed artifact matches a fresh regeneration on the release branch.
- Quarterly, list release-branch commits lacking provenance trailers; each is either a legitimate hand-port with a referenced PR or a process gap to close.

## Failure modes and correction

- **Improvising semantics.** The resolver fuses two implementations into a third that neither side tested. Correction: treat any choice between the sides' logic as semantic overlap — stop, abort, and hand-port with review.
- **Picking bundles.** A fix arrives glued to a refactor and both get backported. Correction: split on a scratch branch first; the release branch receives only the fix.
- **Missing prerequisites.** The fix lands but calls a function that does not exist on the target, or worse, exists with different behavior. Correction: check the source PR's dependency chain and pick prerequisites in order.
- **Hand-merged lockfiles.** Resolution edits a lockfile by hand and the build breaks in staging. Correction: regenerate on the target and commit only the regenerated output.
- **Lost provenance.** Resolutions get squashed into a commit with no source reference. Correction: enforcement of the `-x` trailer in the release-branch PR check; hand-ports must reference the original PR in the body.
- **Pushing through exhaustion.** The fifth conflict of the evening gets resolved carelessly. Correction: the abort threshold exists precisely for this; use it and port fresh the next morning.

## Limitations

Cherry-pick conflict resolution is inherently local reasoning about someone else's change; the strategy reduces but cannot eliminate misapplied fixes, which is why the PR review step is load-bearing and not ceremony. The classification scheme assumes the source change is small and atomic; large multi-commit features backported across majors are out of scope and should be re-implemented against the target. Provenance trailers help only if the source repository remains readable — picks across forks or deleted branches lose the audit trail. The abort thresholds are calibrated judgment, not measurements, and teams with heavily diverged release branches will hit them constantly, which is a signal to shorten branch lifetimes rather than to push through more conflicts.

## Canonical sources

- Git documentation — git-cherry-pick (including -x and conflict handling): https://git-scm.com/docs/git-cherry-pick
- Git documentation — git-range-diff for comparing resolutions against source: https://git-scm.com/docs/git-range-diff
- Atlassian Git tutorial — Cherry pick: https://www.atlassian.com/git/tutorials/cherry-pick
