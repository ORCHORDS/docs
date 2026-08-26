# github-merge-queue-mechanics

**Issue:** A team enforces "branch up to date before merge" and requires green CI on `main`, yet `main` still breaks several times a week: two PRs each pass CI against yesterday's `main`, then merge minutes apart, and their combination (or the intermediate commits) was never tested. Authors also burn time manually rebasing every time the base moves. The fix is GitHub's merge queue, but enabling it without understanding merge groups, the `merge_group` event, and the queue settings causes a different failure mode: every queued PR is ejected from the queue because the required check never reports against the temporary validation branch.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the queue actually works

1. **FIFO batching into merge groups.** When an author clicks "Add to merge queue", the PR enters a first-in-first-out queue. GitHub packs queued PRs into batches called merge groups — each group is the current base branch plus the changes of one or more queued PRs — and validates the group, not each PR in isolation.
2. **Temporary read-only branches.** Validation runs on temporary branches under `gh-readonly-queue/{base_branch}/pr-N` (e.g. `gh-readonly-queue/main/pr-123`). These branches are internal: they appear in `git ls-remote` and webhook payloads but not in the branch picker. Each time a new PR enters the batch, GitHub recreates downstream temporary branches to include the earlier PRs' changes.
3. **The `merge_group` event is mandatory.** Workflows must trigger on `merge_group` (alone or alongside `pull_request`) or the merge will fail, because the required status check is never reported for the validation branch. `on: [pull_request]` does not fire for queued PRs — this is the single most common misconfiguration.
4. **Required checks must report against the merge group.** The same check contexts (job names, `workflow / job` pairs) enforced by the ruleset must run and succeed on the `merge_group` build. If a check only reports on `pull_request`, the queue treats it as missing and times the PR out.
5. **Third-party CI keys off the branch prefix.** External systems (Buildkite, Jenkins, CircleCI) that cannot handle `merge_group` should trigger on pushes matching `gh-readonly-queue/{base_branch}/**`. When a merge group is invalidated, GitHub emits a `merge_group` webhook so CI can cancel in-flight builds for the superseded group.

## Configuring the queue

1. **Enable via ruleset or branch protection.** Merge queue is toggled under "Require merge queue" in the base branch's protection rule or ruleset. It cannot be enabled on rulesets whose conditions use wildcard (`*`) branch patterns — target explicit branch names like `main`.
2. **Merge method.** Choose merge, rebase, or squash for how the queue lands the batch; this is independent of the repo's normal merge settings. Squash-only is the common choice so each queued PR lands as one commit on `main`.
3. **Build concurrency.** Caps the number of concurrent `merge_group` builds (1–100) to throttle CI spend on busy queues; higher values merge faster but run more validation builds.
4. **Merge limits and wait time.** Min/max PRs per batch (1–100) plus a wait time GitHub sits on a smaller-than-minimum batch before merging anyway. Limits affect how many PRs land per merge to `main`, not how many CI builds run.
5. **"Only merge non-failing PRs".** When off, a group can merge even if an earlier PR failed, as long as the final group state passes — useful for throughput, risky if failures indicate real conflicts.
6. **Check timeout.** The status check timeout bounds how long the queue waits for CI on a merge group before declaring failure and ejecting the PRs. Set it above your worst-case CI duration (including queued runner time) or flaky capacity problems will masquerade as merge failures.

## Failure and recovery behavior

1. **Ejection reasons.** A PR is removed from the queue when its checks fail, the check timeout expires, a user removes it, or branch protection has unresolvable failures (e.g. a required check that can never report). The PR timeline shows the removal reason — read it before retrying, because re-queuing a PR whose checks can't report just burns another timeout cycle.
2. **Group rebuild, not full queue drain.** On failure, GitHub rebuilds the remaining temporary branches without the failed PR; later PRs are revalidated against the new head. Nothing merges until a group fully passes.
3. **Queue-jumping is expensive.** Merging a PR out of order forces a full rebuild of all in-progress merge groups because the commit graph breaks. Occasional hotfix jumps are fine; routine jumping collapses merge velocity.
4. **Conflict handling.** PRs that conflict with the new batch head fail validation like any other failure — fix the conflict locally and re-add to the queue. The queue never auto-resolves conflicts.
5. **Interplay with auto-merge.** Auto-merge does not bypass the queue: when both are enabled, a PR satisfying all other requirements is added to the queue rather than merged immediately (see `github-auto-merge.md`).

## Workflow and verification checklist

1. **Trigger block.** Use `on: pull_request` plus `merge_group` (plus `push` to `main` for post-merge smoke): `on: { pull_request: {}, merge_group: {}, push: { branches: [main] } }`. Jobs that must not run pre-merge can gate on `github.event_name == 'merge_group'`.
2. **Concurrency that coexists with the queue.** Scope `concurrency` groups per-`merge_group` so queued validation builds cancel superseded groups but never cancel unrelated PR builds (see `github-actions-concurrency.md`).
3. **Sharded/conditional checks.** Path-filtered or matrix jobs that skip on the merge group will report as missing — provide an always-present anchor job or enable "skipped checks are passing" where acceptable, mirroring the advice in `github-required-status-checks.md`.
4. **Verify the lifecycle end to end.** A queued PR should show "Added to queue → checks running on temporary branch → merged" in the timeline. Then temporarily push a red check and confirm the PR is ejected with the failure reason rather than merging.
5. **Watch the queue depth.** Sustained queue depth means CI is the bottleneck, not merge policy: raise build concurrency, shorten CI, or batch looser — do not disable the queue to "unblock" merges.

## Related

1. **`github-required-status-checks.md`.** Required check contexts and the `merge_group` reporting trap.
2. **`github-auto-merge.md`.** Auto-merge hands off to the queue instead of direct merging.
3. **`github-actions-concurrency.md`.** Cancel-superseded patterns that stay queue-safe.
