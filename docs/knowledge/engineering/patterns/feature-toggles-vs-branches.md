# feature-toggles-vs-branches

**Issue:** Feature branches vs trunk-based development + feature flags
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a 6-month feature branch. Main has moved on. The
branch has 200 merge conflicts. You spend 2 weeks merging.
The merge breaks production. You roll back. You're back to
the start.

## Root cause
**Long-lived branches are merge hell.** The longer the
branch, the more drift, the more conflicts, the more risk.

**Source:** Trunk-based development:
https://trunkbaseddevelopment.com/

> "Developers commit directly to trunk (main). Short-lived
> branches (1-2 days) are the exception, not the rule."

## The 3 models

### Model 1: Long-lived feature branches
- **Duration:** weeks to months
- **Merge:** when the feature is "done"
- **Pros:** clear ownership, isolated work
- **Cons:** merge hell, hard to test, hard to review

### Model 2: Short-lived branches + PR
- **Duration:** 1-3 days
- **Merge:** once approved + CI green
- **Pros:** quick to merge, easy to review
- **Cons:** still has merge conflicts (just less)

### Model 3: Trunk-based development + feature flags
- **Duration:** 0 days (commit to main behind a flag)
- **Merge:** continuously
- **Pros:** no merge hell, continuous integration, easy to
  roll back
- **Cons:** flag management, requires discipline

## The "trunk-based" approach

```bash
# 1. Create a short-lived branch (1-2 days max)
git checkout -b fix/small-bug main
# 2. Make the change
# 3. Open a PR #<number>. After approval + CI green, merge
git checkout main
git merge --squash fix/small-bug
git push

# For a feature (longer than 2 days):
# 1. Create a feature flag
git checkout -b feat/new-dashboard main
# 2. Build the feature behind the flag
# 3. Open a PR (merge behind the flag)
# 4. After merge, the feature is in main but not visible
# 5. Turn on the flag for 1% → 10% → 50% → 100%
# 6. Remove the flag
```

The feature is in main from day 1. The flag controls visibility.
No merge hell at the end.

## The "branch by abstraction" pattern

For a large refactor, use branch by abstraction:
1. Create an abstraction layer
2. Implement the new behavior behind the abstraction
3. Switch callers to the new behavior (one at a time)
4. Remove the old behavior

```ts
// Step 1: abstraction
interface UserRepository {
  getById(id: string): Promise<User | null>;
  // ...
}

// Step 2: old + new implementations
class OldUserRepository implements UserRepository { ... }
class NewUserRepository implements UserRepository { ... }

// Step 3: feature flag
const useNew = await isFeatureEnabled('new-user-repo');
const repo = useNew ? new NewUserRepository() : new OldUserRepository();

// Step 4: gradually switch callers (1 route at a time)
// Step 5: remove OldUserRepository + flag
```

## The "strangler fig" pattern

For replacing a legacy system with a new one:
1. Build the new system alongside the old
2. Route a small subset of traffic to the new (via load
   balancer, gateway, or feature flag)
3. Gradually increase the subset
4. Decommission the old

```ts
// In the API gateway
if (request.url.pathname.startsWith('/api/v2/')) {
  return env.NEW_SERVICE.fetch(request);
} else {
  return env.OLD_SERVICE.fetch(request);
}
```

## The "git workflow" comparison

| Workflow | Branches | Merge | CI |
|---|---|---|---|
| Git Flow | main, develop, feature/* | When feature is done | On PR |
| GitHub Flow | main, feature/* | After PR review | On PR |
| Trunk-based | main only (or 1-2 day branches) | Continuous | On commit |

For most teams, **GitHub Flow + feature flags** is the right
balance. Short branches (1-3 days), PR review, merge to main,
feature flag for in-progress work.

## The "code review" tradeoff

| Workflow | Review depth | Time to merge |
|---|---|---|
| Long-lived branches | Deep (the whole feature) | Days to weeks |
| Short branches + PR | Medium (the change) | Hours to days |
| Trunk + flags | Light (the change) | Minutes to hours |

A "deep review" of a 6-month feature is impractical. A "light
review" of a 200-line change is fast. Pick the right depth
for the change size.

## When to use each model

✅ **Long-lived branches** when:
- The feature is huge (months of work)
- The team is small (1-2 people)
- The merge conflicts are minimal
- The feature is well-isolated

✅ **Short branches + PR** when:
- The team is medium (3-10 people)
- The features are small to medium
- The CI is fast (< 10 minutes)
- Code review is valued

✅ **Trunk + flags** when:
- The team is large (10+ people)
- The CI is fast + reliable
- The deploys are frequent (multiple per day)
- The features can be turned off

## The "merge conflict" cost

A merge conflict is:
- Time to resolve: 30-60 minutes per conflict
- Risk of bugs: each resolution is a chance for a mistake
- Demotivation: developers hate resolving conflicts

The "10x rule": a 10-day branch is 10x more likely to have
conflicts than a 1-day branch. A 100-day branch is 10x more
likely than a 10-day branch. The cost grows exponentially.

## Verification
- **Test:** Branch lifetime is tracked; alert if > 5 days
- **Live:** The number of merge conflicts per PR is monitored
- **Audit:** Quarterly review of branch workflow

## Gotchas
- **Trunk-based requires a good CI.** Without fast, reliable
  CI, you can't safely commit to main multiple times per day.
- **Trunk-based requires a good test suite.** Without tests,
  you can't know if your commit broke something.
- **Feature flags are not free.** They have a maintenance
  cost (cleanup, monitoring). See `feature-flags.md`.
- **The "merge conflict" mindset is broken.** Modern
  workflows minimize conflicts by integrating often. The
  conflict-free workflow is the goal, not the conflict-
  resolution workflow.
- **Code review is still important.** Trunk + flags doesn't
  mean "no review." It means "smaller reviews, more often."

## Related
- `worktree/rebase-vs-merge.md`
- `worktree/squash-merge-default.md`
- `feature-flags.md`
- `feature-flags-best-practices.md`
- Trunk-based: https://trunkbaseddevelopment.com/
- GitHub Flow: https://guides.github.com/introduction/flow/
