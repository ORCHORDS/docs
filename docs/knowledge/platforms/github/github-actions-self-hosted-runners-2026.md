# Self-hosted runner speedups without weakening required checks

**Issue:** CI queues or runs slowly on self-hosted runners, and teams attempt to “speed it up” by skipping required checks, sharing mutable runner state, or disabling protection.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Goal

Reduce queue time and execution time while retaining the same required check contract: build, tests, security scans, provenance, and protected deployment gates must still run and report an unambiguous result.

**Sources:**

- [GitHub self-hosted runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [Deploy ARC runner scale sets](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/deploy-runner-scale-sets)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [Troubleshoot required status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)

## Safe speedups

### 1. Attack queue time first

Use ARC runner scale sets with explicit `minRunners` warm capacity and `maxRunners` budget. Tune the minimum from observed peak queue demand; do not set it from guesswork. ARC exposes Prometheus metrics for runner/job congestion.

Use ephemeral runners for autoscaling. GitHub recommends them because a runner receives one job, giving a clean environment and preventing a drained persistent runner from receiving new work.

### 2. Make startup cheap and reproducible

Publish a versioned, tested runner image with required toolchains, CA roots, and non-secret build dependencies already present. Update it through normal CI; pin the runner and action versions. Do not bake credentials, repository workspaces, or unreviewed mutable caches into the image.

Keep the runner image small, place it near the cluster, and pre-pull it on runner nodes where image-pull latency dominates.

### 3. Cache only immutable inputs

Cache package-manager downloads, compiler/tool caches, and container layers using keys that include the lockfile, platform, architecture, and relevant toolchain version. Record cache-hit rate and restore time.

Do not share writable workspaces, credentials, or untrusted build outputs across repositories or trust boundaries. A cache miss must execute the full verified install/build path successfully.

### 4. Parallelize independent checks

Split truly independent test shards and merge their reports. Preserve a single required “check complete” gate that evaluates every shard and fails when any shard is failed, cancelled, missing, or unexpectedly skipped.

Measure the slowest shard, not only aggregate CPU use. Raise runner concurrency only after load tests demonstrate that database, registry, and test fixtures remain reliable.

### 5. Cancel only obsolete work

Use workflow concurrency to cancel superseded branch/PR validation runs, but never cancel production deployment, migration, release, or rollback workflows that may have irreversible side effects. Give those workflows a separate concurrency group and explicit serialization.

### 6. Use selective execution safely

Path-aware selection may avoid irrelevant expensive jobs, but do not path-filter a workflow that is itself a required check: GitHub leaves skipped required workflows pending. Instead, keep the required workflow running and use a deterministic internal change-detection job; its final required gate must report success only after required applicable checks pass.

Treat GitHub’s changed-file/diff limits as a fail-safe condition: if selection cannot be determined confidently, run the broader check set.

## Required measurements

Track p50/p95 queue time, image pull/startup time, execution time by required check, cache hit rate, shard imbalance, runner saturation, failed/cancelled/missing check count, and time-to-green. Set SLOs and alert on regression before changing concurrency or capacity.

## Verification

- A load test at expected peak retains all required status checks and meets queue-time SLO.
- A cache miss, cold runner, and depleted warm pool still complete the full check set correctly.
- Cancelling an old PR run cannot cancel a protected deploy or release.
- A failed, missing, or skipped shard makes the aggregate required gate fail.
- An untrusted fork cannot access persistent runner state, secrets, or privileged runner groups.

## Related

- `infra/github-self-hosted-runners.md`
- `infra/arc-github-runners-k8s.md`
- `github/github-actions-github-token-permission-minimization.md`
- `github/the sharded matrix testing section in this file`
