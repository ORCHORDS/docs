# Release Branch Strategies: Gitflow vs Trunk-based vs GitHub Flow

Date: 2026-08-17
Author: the platform team
Status: published

## Symptom

Long-lived feature branches cause painful merge conflicts before
every release, or the team ships bugs to production because
release branches accumulate unreviewed commits during a code
freeze period.

## Context

Three dominant strategies exist for managing how code moves from
developer to production: Gitflow (structured, multi-branch),
GitHub Flow (lightweight, short branches off `main`), and
trunk-based development (everyone commits to `main` within hours,
feature flags hide unfinished work). Cloudflare Pages
zero-downtime atomic deploys and instant rollback remove the two
main blockers to trunk-based development: a downtime window to
schedule around and inability to roll back quickly.

## Gitflow

Gitflow defines five branch types — two permanent, three
transient:

```
main          ←── production-tagged commits only
develop       ←── integration branch
feature/*     ←── from develop, PR back to develop
release/x.y   ←── from develop, merged to main + develop
hotfix/*      ←── from main, merged to main + develop
```

```bash
# Cut a release branch
git checkout -b release/2.3 develop
# Bump version, fix release bugs only
git checkout main
git merge --no-ff release/2.3
git tag -a v2.3.0 -m "Release 2.3.0"
git checkout develop
git merge --no-ff release/2.3
git branch -d release/2.3
```

Best for: quarterly release cadences, regulated environments
requiring a code freeze, or products with multiple supported
major versions in production simultaneously.

## GitHub Flow

`main` is always deployable; all work happens in short-lived
feature branches:

```
main   ←── always deployable
feat/* ←── short-lived, PR → main → auto-deploy
```

Rules that make it work:
1. Branches deleted immediately after merge.
2. `main` has branch protection + required status checks.
3. Deploy to a preview environment from the PR branch.
4. `main` deploys automatically on merge (CD pipeline).

Best for: SaaS products shipping continuously, small-to-medium
teams, services where every commit to `main` can go live.

## Trunk-Based Development

All developers push to `main` (or branches lasting ≤ 1 day)
multiple times per day. Feature flags control what users see:

```bash
# Short-lived branch — merged same day
git checkout -b feat/checkout-v2
# small, reviewable commit
git push origin feat/checkout-v2
# Auto-PR → fast review → merge → delete
```

Prerequisites at scale (10+ developers):
- Feature flags to hide in-progress features.
- Automated tests running in < 5 minutes.
- CODEOWNERS for sections needing human sign-off.

## Release Branch Lifecycle (When You Need One)

```
main ──●──────────────────────────────●──
        \                            /
         release/3.1 ──●──●──●──●──●
```

```bash
# Create from main at release commit
git checkout -b release/3.1 abc1234
git cherry-pick <fix-sha>        # verified fixes only
git tag -a v3.1.0 -m "Release 3.1.0"

# Back-merge to main so fixes are not lost
git checkout main
git merge --no-ff release/3.1
```

## Hotfix Workflow

```bash
git checkout -b hotfix/3.1.1 v3.1.0
git commit -m "fix: null pointer in payment processor"
git tag -a v3.1.1 -m "Hotfix 3.1.1"

git checkout main
git merge --no-ff hotfix/3.1.1
git branch -d hotfix/3.1.1
```

Open a PR targeting `main` even under time pressure — the fix
still needs CI and code review.

## Feature Flags as Alternative to Long-Lived Branches

| Flag type   | Scope           | Example use             |
|-------------|-----------------|-------------------------|
| Release     | per-environment | hide new checkout flow  |
| Experiment  | % of users      | A/B test pricing page   |
| Ops         | ops team only   | circuit breaker for API |
| Permission  | role-based      | admin-only beta feature |

Example using Cloudflare Workers KV as a flag store:

```ts
// workers/src/flags.ts
export async function isEnabled(
  flag: string,
  env: Env,
): Promise<boolean> {
  return (await env.FLAGS.get(flag)) === "true";
}

// In handler
if (await isEnabled("checkout-v2", env)) {
  return handleCheckoutV2(request, env);
}
return handleCheckoutV1(request, env);
```

Workers KV toggles flags without a redeploy, making trunk-based
development safe even for large in-flight changes.

## Anti-patterns

- Keeping feature branches open for more than one sprint —
  signals a design or scope problem, not just a git problem.
- Merging directly to `main` without a PR — skips review and
  breaks shared CI history.
- Using Gitflow on a team that ships daily — the overhead of
  `develop` and `release/*` exceeds the benefit.
- Deleting a release branch before back-merging to `main` —
  hotfixes on that branch are permanently lost.

## Gotchas

- Gitflow's `develop` branch becomes a bottleneck on large
  teams; every feature competes for the same integration point.
- "Squash and merge" in GitHub Flow loses individual commit
  history; ensure PR descriptions capture the intent fully.
- Trunk-based development requires a fast test suite; if tests
  take 30+ minutes, branches will live too long.
- Cloudflare Pages preview deployments are per-branch and auto-
  deleted when the branch is deleted.

## Verification

```bash
# Visualize branch topology
git log --oneline --graph --decorate --all | head -40

# Find stale branches (older than 7 days)
git for-each-ref --sort=committerdate refs/remotes \
  --format='%(committerdate:relative) %(refname:short)' | \
  grep -v "main\|HEAD"

# Confirm main branch protection is active
gh api repos/:owner/:repo/branches/main/protection \
  --jq '.required_status_checks.contexts'
```

## Related

- /documentation/docs/policies/worktree/trunk-based-development-2026.md
- /documentation/docs/policies/worktree/branch-strategies-2026.md
- /documentation/docs/policies/worktree/hotfix-process.md
- /documentation/docs/policies/worktree/feature-flags-2026.md
- /documentation/docs/policies/worktree/semantic-release-automation.md

## Source URLs (verified 2026-08-17)

- https://trunkbaseddevelopment.com/
- https://nvie.com/posts/a-successful-git-branching-model/
- https://docs.github.com/en/get-started/using-github/github-flow
- https://developers.cloudflare.com/pages/configuration/git-integration/
- https://martinfowler.com/articles/feature-toggles.html
