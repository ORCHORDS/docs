# github-merge-queue

**Issue:** GitHub merge queue — race-free merging
**Date:** 2026-08-09
**Status:** documented

## Symptom
PR #<number> and PR #<number> both merge in sequence. PR #<number>
breaks main. PR #<number> is "green" but on top of broken
PR #<number>. You realize the sequence wasn't tested.
You need merge queue.

## Root cause
**Sequential merges miss cross-PR breaks.** Batch.

**Source:** GitHub Docs 2026.

## The "merge queue" concept

Merge queue:
- **Mode:** `merge_group` event
- **CI:** On combined diff
- **Order:** FIFO
- **Base:** Latest
- **Use:** High-traffic

The queue is batched.

## The "merge_group event" pattern

For CI:
```yaml
on:
  pull_request:
  push:
  merge_group:
```

The event is merge_group.

## The "third-party CI" pattern

For external:
- **Listen on:** `gh-readonly-queue/{base}`
- **Trigger:** When branch prefixed
- **Why:** Custom CI
- **GitHub:** Just use event

The CI is per need.

## The "min_group_size" pattern

For size:
- **Small:** Fast PRs
- **Large:** Fewer cross breaks
- **Trade:** Time vs safety
- **Why:** Tunable
- **Default:** 1-5

The size is per traffic.

## The "max_group_size" pattern

For cap:
- **Why:** Avoid deploy chaos
- **Use:** When merge = deploy
- **When:** Auto-deploy
- **Fix:** Cap concurrency

The cap is per need.

## The "build_concurrency" pattern

For CI:
- **Range:** 1-100
- **Direct:** Parallel merge_group runs
- **Why:** Throttle CI
- **When:** Many PRs

The concurrency is throttled.

## The "jump to top" pattern

For emergency:
- **Effect:** Invalidate group
- **Use:** Hot-fix only
- **Why:** Disruptive
- **Fix:** After merge

The jump is rare.

## The "only non-failing" pattern

For strict:
- **On:** All pass
- **Off:** Trailing PR rescues
- **Use:** Strict teams
- **Default:** Off
- **Why:** Throughput

The toggle is per policy.

## The "wildcard unsupported" pattern

For branches:
- **Issue:** Wildcard rules
- **Fix:** Explicit branches
- **Why:** Conflict
- **Doc:** "Cannot be enabled"

The wildcard is avoided.

## The "vs auto-merge" pattern

For difference:
- **Auto-merge:** One PR, own checks
- **Merge queue:** Batch, combined
- **Why:** Race-safe
- **Pick:** Queue for many

The queue is race-safe.

## The "vs branch protection" pattern

For complement:
- **Queue:** Batches
- **Protection:** Defines rules
- **Together:** Best
- **Why:** Layered
- **Required:** Both

The pair is required.

## The "high-traffic" pattern

For use:
- **PRs/day:** Dozens to hundreds
- **Branches:** main, develop
- **Teams:** Multiple
- **Why:** Frequent breaks
- **Skip:** Low volume

The volume drives.

## The "low-volume" anti-pattern

For low:
- **Issue:** Latency, no benefit
- **Fix:** Don't enable
- **Why:** Queue waits
- **Rule:** >10 PRs/day

The low skips queue.

## The "no merge_group CI" anti-pattern

For no CI:
- **Issue:** Silently merges
- **Fix:** Configure CI
- **Why:** Validation needed

The CI is configured.

## The "wildcard" anti-pattern

For wildcard:
- **Issue:** Cannot enable
- **Fix:** Explicit
- **Why:** Doc says

The wildcard is replaced.

## The "replace tests" anti-pattern

For tests:
- **Issue:** Queue doesn't fix flaky
- **Fix:** Real tests
- **Why:** Queue batches, not heals

The tests are real.

## The "high min_group" anti-pattern

For high:
- **Issue:** PRs wait
- **Fix:** Lower min
- **Why:** Tradeoff

The min is per traffic.

## The "confuse auto-merge" anti-pattern

For conflate:
- **Issue:** Wrong expectation
- **Fix:** Document
- **Why:** Different

The doc is clear.

## The "skip protection" anti-pattern

For skip:
- **Issue:** Queue insufficient
- **Fix:** Add protection
- **Why:** Both needed

The protection is on.

## The "no timeout" anti-pattern

For no timeout:
- **Issue:** Hung CI blocks
- **Fix:** Set timeout
- **Why:** Default fail

The timeout is set.

## The "merge queue checklist" pattern

For checklist:
- [ ] On high-traffic branch
- [ ] CI on merge_group event
- [ ] min_group_size set
- [ ] max_group_size set
- [ ] build_concurrency set
- [ ] status_check_timeout
- [ ] only-non-failing decided
- [ ] No wildcard rules
- [ ] Protection + queue
- [ ] Documented for team

The checklist is 10.

## The "queue config" pattern

For config:
```yaml
# branch protection + queue
required_status_checks:
  strict: true  # for queue
merge_queue:
  min_group_size: 1
  max_group_size: 5
  wait_time: 5
  build_concurrency: 3
```

The config is per branch.

## The "CI on queue" pattern

For CI:
```yaml
# .github/workflows/ci.yml
on:
  merge_group:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm test
```

The CI is on event.

## The "queue visualizer" pattern

For observe:
- **GitHub UI:** Queue tab
- **Status:** Grouped
- **CI:** Per group
- **Why:** Transparency

The UI is per repo.

## The "scale notes" pattern

For scale:
- **Small repo:** Overhead
- **Medium:** Sweet spot
- **Large:** Required
- **Why:** Volume

The scale is per repo.

## The "GA timeline" pattern

For status:
- **GA:** July 2023
- **Public:** All org public repos
- **Private:** Enterprise Cloud
- **Free:** Not for private
- **2026:** Stable

The GA is mature.

## Verification
- **Test:** Queue forms
- **Test:** CI on combined
- **Test:** FIFO order
- **Test:** Failure stops group
- **Audit:** Per release

## Gotchas
- **The "no CI" anti-pattern.** Required.
- **The "wildcard" anti-pattern.** Explicit.
- **The "low volume" anti-pattern.** Skip.

## Related
- `worktree/git-submodules-vs-subtrees.md`
- `worktree/rebase-vs-merge-detail.md`
- `github/branch-protection-and-codeowners.md`
- `github/reusable-workflows-vs-composite.md`
- `patterns/safe-deploy-checklist.md`
- GitHub Docs: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- Merge methods: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github
- GA changelog: https://github.blog/changelog/2023-07-12-merge-queue-is-now-generally-available/
