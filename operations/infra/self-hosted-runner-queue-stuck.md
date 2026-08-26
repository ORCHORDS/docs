# self-hosted-runner-queue-stuck

**Issue:** GitHub Actions self-hosted runner shows 8+ jobs queued + 0 in_progress for hours
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (workaround: cancel queued + force-push to retrigger)

## Symptom
You open a PR. The Actions tab shows:
- ✅ Required: 4 expected
- ⏳ Queued: 8
- 🔄 In progress: 0
- ⏱️ Waiting: 0+ hours

No jobs run. No error. The runner is online (you can `ssh x-99.local`),
but it's not picking up jobs.

## Root cause
The self-hosted runner on X-99 is a **single-replica, single-job**
runner (not a runner group). When it's busy on a non-the platform job
(e.g. example.com's CI), all the platform jobs queue. The runner label
is `self-hosted, Linux, X64` — no `the platform-only` label to scope it.

**Source:** GitHub self-hosted runners docs:
https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners

> "By default, self-hosted runners do not have a label that scopes
> them to a single repository or organization."

## Fix
Three options:

### Option 1: Cancel + re-trigger (fast, dirty)
```bash
# Cancel all queued jobs
gh run list --repo <your-org>/<your-repo> --status queued --json databaseId -q '.[] | .databaseId' | \
  xargs -I {} gh run cancel {}

# Force-push the branch to re-trigger
git push --force-with-lease origin <branch>
```

This gets a fresh run with a new runner lease. ~3-5 min to first
green check. **Use this when CI is stuck and you need to merge now.**

### Option 2: Use the GH-hosted runner for the stuck job
Edit `.github/workflows/<workflow>.yml` to change `runs-on`:
```yaml
runs-on: ubuntu-latest  # was: [self-hosted, Linux, X64]
```

This re-routes the job to GH-hosted. Consumes Actions minutes
(budget concern #open-issue-actions-budget). **Use when X-99 is genuinely broken.**

### Option 3: Add a runner group (proper fix)
In GH org settings → Actions → Runner groups → create
`the platform-runners` group → assign only the platform repos → add the X-99
runner label `the platform-only`. Jobs in this group will only run on
`the platform-only`-labeled runners. This is the **right fix** but
requires org admin access.

## Verification
- **Test:** After applying Option 1, `gh run list --status in_progress`
  shows jobs within 5 min
- **Live:** Per-PR cycle is now ~12-25 min from force-push to all-green
- **4/4 green is the merge bar** for the platform PRs

## Gotchas
- **Don't disable the self-hosted runner** unless you're prepared
  for the GH-hosted budget hit. The self-hosted runner is what makes
  the 25-min cycle possible.
- **The X-99 runner has 32GB RAM, 8 cores, 500GB SSD.** It's beefy.
  Don't run unrelated heavy jobs on it; it's reserved for CI.
- **Force-push on PR-owned feature branches is safe.** The PR
  automatically tracks the new head. Force-push on `main` is
  NEVER safe — even with `--force-with-lease`.
- **If 4/4 green is hit, merge immediately.** Don't wait for the
  "extra" CodeQL job; it often runs after the merge.

## Related
- the platform issue #open-issue-actions-budget (Actions budget)
- a sibling repo `.github/workflows/ci.yml` uses GH-hosted (no runner group)
- Self-hosted runner setup: https://docs.github.com/en/actions/hosting-your-own-runners
