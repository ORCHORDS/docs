# ci-budget-exhaustion-migration

**Issue:** GitHub Actions included minutes run out mid-month and every workflow on private repos starts failing — the default spending limit on Free/Team plans is $0, so exhaustion is a hard stop, not a soft bill. The bill turns out to be driven less by job count than by *runner multipliers*: a macOS job consumes included minutes at 10x wall-clock and Windows at 2x, so one careless matrix cell on `macos-*` can eat hundreds of quota minutes in a single run. This article is the decision path we use when the budget runs dry: measure per-workflow burn first, then cut consumption in place (caching, matrix pruning, concurrency), and only then migrate to self-hosted runners — verified against 2025-2026 billing mechanics.

**Date:** 2026-08-15
**Repo:** ORCHORDS (workflow, multi-repo)
**Author:** ORCHORDS
**Status:** published

## The exhaustion event and the billing mechanics behind it

1. **Included minutes are per-plan, per-month, private repos only.** Public repository usage is always free. Included amounts (GitHub Free ~2,000 min/month; Pro/Team ~3,000; Enterprise 50,000) apply to GitHub-hosted runners on private repos — consistent with the plan ladder in `plan-selection-free-team-enterprise.md`. Check the Actions billing page for current numbers before modeling.
2. **Quota is consumed with an OS multiplier, not wall-clock.** Linux jobs count 1x, Windows 2x, macOS 10x (larger macOS runners more). A 12-minute `macos-14` job burns ~120 included minutes — the "billing surprise" that turns a modest iOS workflow into the single largest line of the bill. Per-minute overflow rates follow the same ratio (current published rates are on the order of cents per minute: Linux 2-core x64 well under $0.01, Windows 2x that, macOS roughly an order of magnitude above Linux).
3. **Exhaustion is a hard failure by default.** With a $0 spending limit, once minutes (or Packages/storage allowance) are gone, workflows on private repos fail immediately with a billing error until the month rolls over or an owner raises the spending limit/pays. Mid-month, with releases blocked, this is when the decision path below gets executed in a hurry.
4. **Self-hosted runner usage is free.** GitHub's billing docs state Actions usage is free for self-hosted runners and for public repositories — self-hosted jobs consume no included minutes on any plan. That fact anchors the endgame of this article; the dual-instance setup for multi-org consolidation is documented in `self-hosted-runners-dual-instance.md`.

## Step 1: measure per-workflow burn before touching anything

1. **Read the org's Actions usage report first.** Billing & Licensing > Usage gives per-repo totals; the Actions usage page under Settings shows which workflows consumed the minutes. This ranks offenders by *billable* (multiplied) minutes, not by runtime — the macOS job you assumed was minor is usually #1.
2. **Use the workflow timing API for precision.** `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/timing` returns billable time (in ms) per workflow across recent runs — scriptable into a per-workflow burn table so optimization effort lands where the multiplier pain actually is.
3. **Attribute one-off spikes separately.** Retried flaky jobs, unbounded `workflow_dispatch` experimentation, and debug-mode reruns (`github-actions-debug-mode.md` warns about this) produce usage that no structural fix will address; fix the flakiness, don't refactor the pipeline.
4. **Decide the target arithmetic explicitly.** The math that matters: monthly billable minutes = sum over jobs of (runtime × OS multiplier × run count). Every lever below attacks exactly one of those three factors.

## Step 2: cut consumption in place (before any migration)

1. **Cache aggressively, keyed by lockfile.** `actions/setup-node` with `cache: npm` (or pnpm/yarn), `setup-java` with `cache: gradle`, `setup-python` with `cache: pip` — keyed on the lockfile hash as documented in `github-actions-cache-dependencies.md`. Cold-install elimination routinely halves job runtime; on a 10x macOS job each saved minute is ten saved quota minutes.
2. **Cache Docker layers via the GitHub Actions cache backend.** `docker/build-push-action` with `cache-from: type=gha, cache-to: type=gha,mode=max` persists layer state between builds; large multi-stage builds drop from minutes to seconds on warm cache. Full pattern in `github-actions-docker-build-push.md`.
3. **Prune the matrix — the multiplier makes every cell expensive.** Cut to the versions you actually support, generate the matrix dynamically from what changed (`github-actions-dynamic-matrix-and-fail-fast.md`), use path filters so docs-only pushes skip CI entirely (`github-actions-path-filters.md`), and test bleeding-edge runtime versions on Linux rather than macOS wherever the framework allows.
4. **Keep only what needs macOS on macOS.** Build/sign the IPA on `macos-*`; run lint, unit tests, and JS bundling on `ubuntu-*` jobs. Same for Windows: cross-compile or test the Windows artifact from Linux jobs where the toolchain permits. This is the single biggest multiplier win and the core advice of `mobile-ci-cd-github-actions.md`.
5. **Cancel superseded runs and cap runtime.** Concurrency groups with `cancel-in-progress: true` for PR validation (`github-actions-concurrency.md`) plus per-job `timeout-minutes` (`github-actions-timeout-jobs.md`) stop the silent budget killers: queued duplicate runs and hung jobs that bill until the 6-hour limit.

## Step 3: the self-hosted migration

1. **Migrate in order of burn, not of convenience.** Move the heaviest Linux jobs first — they are free-tier-friendly to host (any box runs them), the runner install is a systemd unit, and they typically cover most of the billable volume. Leave macOS jobs on hosted runners or a cloud Mac service; a Linux box cannot execute them (see `mobile/ios-development-from-windows-fallbacks.md` for the cloud-Mac options).
2. **One registration per org; consolidate multiple orgs as dual instances.** A runner binds to one org only, so one Linux machine serving two orgs runs two runner directories as separate systemd services with distinct names/labels/users — the full recipe is `self-hosted-runners-dual-instance.md`.
3. **Route with labels and runner groups.** Label runners by capability (`self-hosted, linux, docker`), scope org-level runner groups to the repos that need them, and switch workflows one at a time by editing `runs-on` — this keeps a rollback path (flip the label back) during the transition.
4. **Accept the security trade-off knowingly.** Self-hosted on public repos exposes the machine to fork-PR code execution; keep self-hosted capacity on private repos or gate external contributors with required approval (details in `self-hosted-runners-dual-instance.md`). Also budget the real costs the free metering hides: the hardware, its electricity, and your time patching runners.
5. **When one box saturates, graduate to ARC instead of more boxes.** Actions Runner Controller with ephemeral scale sets is the autoscaling endpoint of this path (`infra/arc-github-runners-k8s.md`, `github-actions-self-hosted-runners-2026.md`).

## Decision summary and tripwires

1. **The ladder, in order:** measure burn → cache (setup-node/GHA cache/Docker layers) → prune matrices and path-filter → demote jobs off Windows/macOS onto Linux → concurrency+timeouts → self-hosted the Linux remainder → ARC at scale. Each rung is cheaper to implement than the next; stop as soon as the month fits the budget.
2. **Set a spending limit you can live with either way.** $0 gives predictable hard failure; a small nonzero cap gives a bill instead of an outage — choose deliberately per org, and make sure whoever owns the pager knows which policy is in effect.
3. **Monitor billable minutes like production.** Alert at 60/80/100% of included minutes (usage API or the billing page) so the next exhaustion event is a planned migration, not a mid-release surprise.
4. **Re-verify pricing each quarter.** Runner rates, included-minute amounts, and arm64 runner pricing have all moved during 2025-2026; the multipliers (2x Windows / 10x macOS) and free self-hosted usage were still the operative model as of this writing, but the bill is exactly the place where stale assumptions cost money.

## Related

1. **`self-hosted-runners-dual-instance.md`.** The endgame: two orgs, one Linux box, zero Actions bill.
2. **`plan-selection-free-team-enterprise.md`.** Where included minutes sit in the broader plan/licensing decision.
3. **`github-actions-cache-dependencies.md`** and **`github-actions-docker-build-push.md`.** The caching patterns referenced in Step 2.
4. **`github-actions-dynamic-matrix-and-fail-fast.md`** and **`github-actions-path-filters.md`.** Matrix pruning and selective execution.
5. **`github-actions-large-runners.md`.** The opposite lever — spending more per minute on purpose for speed — and its cost warnings.
