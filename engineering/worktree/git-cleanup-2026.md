# git-cleanup-2026

**Issue:** A repo has 200 stale branches from feature work over 3 years. The team debates manual cleanup, `git branch --merged`, scheduled scripts. The team needs the 2026 reference for git branch hygiene.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 cleanup strategies

1. **Local merged branch cleanup.** `git branch --merged main | xargs git branch -d`.
2. **Remote stale branch cleanup.** `git fetch --prune` removes deleted-upstream tracking branches.
3. **Auto-delete on merge.** GitHub/GitLab setting to delete head branch on PR merge.
4. **Stale bot.** Periodic run of `stale` GitHub Action or custom script.
5. **Squash-only merge policy.** All PRs squash-merged, no merge commits, branches are atomic.

## The 5 best practices

1. **Enable auto-delete on merge** in repo settings.
2. **Run `git fetch --prune`** weekly to drop deleted-upstream tracking branches.
3. **Local cleanup monthly** with `git branch --merged`.
4. **Stale bot** with 30-day inactivity close.
5. **Document branch naming** so future-you can find the right branch.

## The 5 anti-patterns

1. **Keeping merged branches forever** - clutter.
2. **Force-pushing to cleaned-up branches** resurrects them.
3. **No branch naming convention** - "fix", "test", "wip" are useless.
4. **Stale branches with diverged history** - rebase pain when someone picks it up.
5. **Manual cleanup with no schedule** - never happens.

## Gotchas

- `git branch -d` won't delete unmerged branches; use `-D` (force) carefully.
- `--merged` only checks the current branch; specify it: `git branch --merged main`.
- `git remote prune origin` removes tracking refs to deleted remote branches.
- Some tools (Sourcetree, GitKraken) have built-in cleanup.
- Squash-merge on GitHub doesn't show in the contributor's commit count.

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-branch
- https://git-scm.com/docs/git-fetch
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github
- https://github.com/actions/stale
