# deploy-queue-merge-train

**Issue:** On an active team, several pull requests pass CI on Tuesday, then merge one after another — and main breaks. Each PR was green against an older base, and the combination was never tested together. Deploys from a broken main either halt everyone (rollback, revert, re-verify) or ship a bad bundle. A deploy queue, implemented as a merge queue or merge train, fixes the class of problem: candidate changes are serialized, combined into batch merge groups with the exact state that will land, validated together, and only then merged and deployed in order. GitHub uses exactly this mechanism to ship hundreds of changes a day to github.com. Where merge races and deploy collisions — not code review — are the throughput bottleneck, a queue converts main from "probably green" to "continuously verified."

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core mechanics

1. **merge_group as the trigger that matters.** A merge queue validates PRs after temporarily merging them into a group with the tip of main, and CI must run on that merge_group event, not just on the PR head. If your workflows only trigger on pull_request, the queue merges entirely untested combinations — the exact failure mode you installed the queue to prevent.

2. **Temporary merge refs.** The queue builds each batch on an ephemeral ref (the stacked combination of queued PRs plus main). Checks that hardcode branch names or inspect the PR base will silently test the wrong thing; ensure pipeline logic resolves the ref it was given rather than assuming.

3. **Dynamic batch formation.** Groups form from whatever is queued when a train slot frees up: two PRs land as one batch today, five tomorrow. Treat batch composition as incidental — every check must pass for the batch as a whole, because that combined state is what will be deployed.

4. **Fail and split.** When a batch fails, the queue identifies or bisects to the culprit PR, dequeues it, and re-queues the rest against a fresh base. The train keeps moving; only the offending change is thrown off. Confirm your failure-splitting behavior explicitly (native queues split the batch; some third-party queues add per-PR bisecting) so a single bad PR cannot stall the line.

## Queue configuration

1. **Batch size tuned to blast radius.** Bigger batches raise throughput (one CI run amortized over more PRs) but make failures more expensive to attribute and revert. Teams commonly settle in the 2-5 PR range and lower it when failure-splitting proves noisy.

2. **A hard CI speed budget.** Queues amplify slow pipelines, because every queued PR waits for full validation of its group. Hold validation under roughly 10-15 minutes or the queue backs up at peak hours; if you cannot, fix CI duration before adding a queue, not after.

3. **Check-in limits and priorities.** Cap simultaneous merge groups per repository, and decide ordering policy up front: FIFO by default, with priority lanes for hotfixes if your tooling supports it. Native GitHub queues are deliberately simple (no priorities, limited batching controls); teams with complex needs either layer tooling on top or accept the simplicity.

4. **Required checks aligned to the queue.** The set of checks that must pass on the merge group should equal the set that protects main — no more, no less. Extra required checks double the work; missing ones let unverified combinations through.

## From merge queue to deploy queue

1. **Merge as the deploy trigger.** With a queue, every merge to main is batch-verified and deployable, so "deploy on merge" becomes safe at high frequency. The queue has effectively become your deploy queue: deployments leave the station in the same order changes were validated.

2. **Serializing actual deploys.** Even with ordered merges, deployment execution may need a lock: one rollout in flight per environment, subsequent deploys queued behind it. Without a deploy lock, two validated batches can roll simultaneously and make canary signals unreadable.

3. **Rollback interacts with the train.** Define in advance what a production rollback means for the queue: typically the reverted change re-enters as a new PR at normal priority, while the train continues. Urgency flows through the revert PR and any priority lane, never through an out-of-band deploy that bypasses the queue's guarantees.

## Failure handling and operations

1. **Culprit identification.** When a batch fails, first suspect the newest PR, but verify by the queue's split-and-retry evidence rather than finger-pointing. Persist which PR failed in which batch — that history is how you find repeat offenders whose PRs only fail in combination.

2. **Dequeue versus retry.** A flaky test failure in a batch is not a code problem; decide policy explicitly (auto-retry once, then dequeue) so flakiness degrades throughput gracefully instead of wedging the train behind a rerun loop.

3. **Watch the queue as a system.** Alert on queue depth and time-to-merge trends. A queue that steadily grows means CI is too slow, batches too large, or too many failing PRs entering — all fixable, but only if someone is looking at the train's throughput the same way they look at production latency.
