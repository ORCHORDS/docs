# GitHub Merge Queue Batching Strategy

A merge queue serializes the last step of integration: instead of many pull requests merging concurrently onto `main` and each hoping CI still passes afterward, the queue tests each PR stacked on the exact commit that will precede it, in order, and only then merges. This converts "CI passed on a stale base" failures into pre-merge detection, at the cost of throughput. Batching — grouping multiple PRs into one temporary merge and one CI run — is the main lever for throughput, and it changes the failure semantics in ways that must be understood before enabling it. This article covers how merge queues and batching work, configuration strategy, and operational practice.

## Scope

This article addresses GitHub merge queues as configured in branch protection (`merge queue` under "Require merge queue"), including batching settings (batch size, wait time to fill a batch), check-selection behavior, dequeue-on-failure semantics, and interaction with required checks and required workflows. It covers strategy and operations for engineering teams. It does not cover merge methods generally (squash versus merge commits), CODEOWNERS, or general branch protection setup.

## Workflow or implementation guidance

A merge queue entry is a PR marked "ready to merge" into a protected branch. GitHub creates a temporary branch per entry containing the PR's changes applied on top of the current queue head; required checks run on that temporary ref; on success the PR merges to the base branch and the queue advances, with subsequent entries rebased onto the new head. Without batching, each entry waits for the previous entry's full CI run.

Batching changes the shape: with a batch size of N and a wait time of T seconds, the queue groups up to N ready entries, merges them into one temporary ref, runs required checks once, and on success merges all N in queue order (each entry's merge is still individually recorded). The tradeoffs:

1. **Latency versus cost.** Batch of 1: maximum serialization, slowest average merge under load, highest confidence per PR. Larger batches amortize CI across PRs — throughput scales — but every PR in a failed batch may be implicated in the failure.
2. **Failure semantics under batching.** If a batch's checks fail, GitHub dequeues entries per the configured failure strategy: the queue bisects or falls back to smaller batches (GitHub's documented behavior is to retry the failed batch's entries in smaller groups/serially to isolate the offender). Entries that were merely "in the wrong batch" get re-queued, not rejected — but PR authors see red checks on temporary refs and sometimes misread this as their PR failing. Communication matters: label queue-run checks clearly in required-check naming (`merge-queue / integration`) so authors distinguish queue isolation runs from their own CI.
3. **Required checks must be reported for the temporary ref.** Checks required on the base branch must also run on queue temp branches; workflows keyed to `pull_request` alone will not satisfy queue evaluation. Configure required checks to trigger on `merge_group` events (GitHub's event for queue runs) and register the same check name in branch protection; a mismatch produces an eternal queue ("waiting for status") — the single most common misconfiguration.
4. **Flaky tests amplify under batching.** A 1% flake rate per entry is a 10% batch-failure rate at batch size 10; the queue will isolate and retry, but wall-clock throughput collapses. Stabilize or quarantine flaky suites before raising batch sizes.
5. **Choosing batch size and wait time.** Start conservative: batch 3–5, wait 60–120 seconds on busy hours; monitor (a) median PR-ready-to-merged time, (b) batch failure rate, (c) isolation-retry counts. Raise batch size while batch-failure rate stays below roughly the rate that serial retries cost more than they save. Very high batch sizes (15+) only pay off with fast, reliable CI.
6. **Check selection.** Use the check-selection filters to run in queue exactly the checks that must gate integration (full e2e, cross-repo impact), not every advisory job; the queue multiplies whatever CI you point at it.
7. **Merge method inside the queue follows the branch's merge settings** (squash, merge commit, rebase). For a batch that merges N entries, each entry still lands per the configured method in queue order.

Operational workflow:

- Announce the queue with clear docs: what authors see (temporary branch runs), what "dequeued" means (failure or expired, re-queue allowed), and hotfix bypass policy (admins can merge urgently outside the queue — rare, logged).
- Monitor queue depth and dwell time as first-class service metrics; alert when depth trends upward for multiple days (the queue becomes the bottleneck, usually due to CI duration, not queue config).
- Treat "entry stuck pending required check" as a config bug on the `merge_group` event wiring, not a GitHub outage, until proven otherwise.

A worked example: a platform team with a 25-minute full CI enables the queue with batch 5 / wait 90s and requires `ci / full-matrix` on both `pull_request` and `merge_group`. Before: 3% of merges broke `main` after green PR CI (base staleness). After: `main` breakage drops to near zero (every change tested on its true predecessor), while p50 merge latency rises 20 minutes; batching at 5 cuts added latency versus serial by running the full matrix once per group. The team then trims the queue check set to tests that genuinely need serialization (integration, performance baselines) and leaves unit tests to PR CI.

## Controls

- Enforce the queue on protected base branches with required checks configured to fire on `merge_group`; a CI contract test should assert that every check name listed in branch protection has a workflow reporting it for `merge_group` events.
- Set batch size and wait time from measured CI duration and flake rate; revisit monthly with queue metrics in hand rather than leaving initial values forever.
- Keep an audited admin bypass procedure for hotfixes; every bypass creates a merge to the base that skipped queue verification and should trigger a post-hoc queue-equivalent run.
- Alert on queue dwell time percentiles and depth; page on "no progress" states (entries pending > 2× median full-CI duration) to catch the waiting-for-check misconfiguration early.
- Track per-batch isolation retries; a rising trend localizes to specific PRs or test flakiness and feeds the flake quarantine process.

## Validation evidence

- Merge queue behavior — temporary branches, `merge_group` event, batch size and wait-time configuration, dequeue-on-failure, and check requirements — is documented in GitHub's official repository and pull-request administration documentation for managing a merge queue.
- GitHub's API and webhook surface (branch protection rules requiring merge queue; `merge_group` event payloads) is specified in the GitHub REST/webhooks documentation, providing the contract CI systems integrate against.
- A reproducible validation: open two ready PRs with a batch of 2 and a short wait; observe one `merge_group` run covering both, then merge one PR with a deliberately failing required check and observe the batch fail, the offender isolated in a subsequent smaller batch/serial run, and the healthy entry merged — demonstrating the documented isolation semantics in your repo's actual configuration.

## Failure modes and correction

- **Eternal "waiting for status".** Cause: required check not reported on `merge_group`. Correct by wiring the workflow to the event and matching the check name exactly.
- **Queue throughput collapse.** Cause: flaky suites inside the queue check set at large batch size. Correct by stabilizing/quarantining flaky tests and re-tuning batch size.
- **Authors confused by red temp-ref checks.** Cause: naming and docs. Correct by distinct check names (`merge-queue / …`) and a runbook explaining isolation.
- **Stale PRs entering the queue.** PRs older than their base benefit from auto-update before enqueueing; if the queue rebases entries, conflicts surface at enqueue — treat conflict-at-enqueue as actionable author feedback, not a queue bug.
- **Bypass drift.** Frequent admin merges outside the queue erode the guarantee. Correct by auditing bypass frequency and fixing the underlying latency drivers.

## Limitations

- Merge queues serialize by design; they cannot make a slow CI suite fast, only make its verdict trustworthy and amortize cost via batching.
- Batching couples unrelated PRs' outcomes in failure analysis; isolation retries recover correctness but cost time.
- Queue behavior details (batch fallback strategy) are service-side and can change with platform updates; re-validate after GitHub changelog entries touching merge queues.
- Cross-repository queues (monorepo-style multi-repo coordination) are not covered by GitHub's native queue; those need orchestration outside this article's scope.

## Canonical sources

- GitHub, Managing a merge queue (GitHub Docs, Repositories → Configuring branches and merges): https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- GitHub, Git worktree documentation reference for the underlying multi-checkout pattern used in queue isolation tooling: https://git-scm.com/docs/git-worktree
