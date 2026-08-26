# rebase-vs-merge-detail

**Issue:** Rebase vs merge — when to use which
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a feature branch. You commit 5 times. You
rebase on main. The history is clean. You push. Your
teammate has pulled your old commits. They get
confused. You wish you had a rule.

## Root cause
**Rebase rewrites history.** Use it carefully.

**Source:** Atlassian git tutorial.

## The "merge vs rebase" pattern

For merge vs rebase:
- **Merge:** Preserves history, safe for shared
- **Rebase:** Linear history, safe for local only

| Aspect | Merge | Rebase |
|---|---|---|
| History | Non-linear | Linear |
| Commit hashes | Preserved | Changed |
| Merge commits | Created | None |
| Conflict resolution | Once | Per commit |
| Safe for shared | Yes | No |
| Shows when | Yes | No |

The trade-off is clear.

## The "golden rule" pattern

The golden rule: **Never rebase on public branches.**

If anyone else has the branch, rebasing breaks their
work.

## The "feature branch rebase" pattern

For a local feature branch:
```bash
# 1. Update feature branch with main
git checkout feature-branch
git fetch origin
git rebase origin/main

# 2. Resolve conflicts (if any)
git rebase --continue

# 3. Force push (your branch only)
git push --force-with-lease origin feature-branch
```

The feature branch is updated.

## The "interactive rebase" pattern

For cleaning up commits:
```bash
# Last 4 commits
git rebase -i HEAD~4
# In the editor:
pick a1b2c3d Add user authentication
squash e4f5g6h Fix typo
squash i7j8k9l WIP
pick m1n2o3p Add tests
# Result: clean history with meaningful commits
```

The history is cleaned.

## The "PR workflow" pattern

For a PR workflow:
1. **Before PR:** Rebase on main
2. **During PR:** Don't rebase (others are reviewing)
3. **After approval:** Squash merge

```bash
# 1. Before PR
git rebase origin/main

# 2. Push PR
git push origin feature-branch

# 3. After review, don't rebase

# 4. Squash merge in GitHub
```

The workflow is structured.

## The "git config" pattern

For team config:
```ini
# .gitconfig
[pull]
    rebase = true
[rebase]
    autoStash = true
[alias]
    pushf = push --force-with-lease
```

The config is consistent.

## The "force-with-lease" pattern

For safer force push:
```bash
# ❌ Bad: force overrides remote
git push --force

# ✅ Good: force-with-lease checks for changes
git push --force-with-lease
```

The force is safer.

## The "rebase vs merge choice" pattern

For choice:
| Situation | Use |
|---|---|
| Integrate shared branches | Merge |
| Update your feature branch | Rebase |
| Clean up before PR | Interactive rebase |
| Multiple devs on one branch | Merge |
| Linear history preferred | Rebase |
| Preserve feature story | Merge with --no-ff |
| Quick single-commit features | Squash merge |

The choice is per situation.

## The "git pull" pattern

For pull:
```bash
# Default: merge
git pull

# Force: rebase
git pull --rebase
```

The pull behavior is per team.

## The "merge --no-ff" pattern

For non-fast-forward merge:
```bash
# Forces a merge commit
git merge --no-ff feature-branch
```

The history shows the merge.

## The "squash merge" pattern

For squash:
```bash
# 5 commits become 1
git merge --squash feature-branch
git commit -m "Add feature X"
```

The history is one commit.

## The "rebase vs merge in PR" pattern

For a PR:
- **Personal branch:** Rebase freely
- **PR open:** Don't rebase
- **After approval:** Squash merge (GitHub setting)

The rule is per stage.

## The "force push" anti-pattern

For force push:
- **Issue:** Overwrites remote history
- **Use:** `git push --force-with-lease`
- **Never:** `git push --force` (unconditional)

The force is conditional.

## The "rebase on shared" anti-pattern

For rebase on shared:
- **Issue:** Breaks others' work
- **Use:** Never

The rebase is private.

## The "auto-merge" pattern

For auto-merge:
```bash
# GitHub CLI
gh pr merge --auto --squash feature-branch
```

The auto-merge is set.

## The "branch cleanup" pattern

For cleanup:
```bash
# Delete merged branch
git branch -d feature-branch

# Delete remote
git push origin --delete feature-branch
```

The branch is cleaned.

## The "rebase vs merge" verification

For verification:
- **Test:** Rebase keeps linear history
- **Test:** Merge preserves history
- **Test:** Force-with-lease is safe
- **Audit:** Quarterly review of process

The verification is per rule.

## Gotchas
- **The "rebase on shared" anti-pattern.** Never.
- **The "force push" anti-pattern.** Use --force-with-lease.

## Related
- `worktree/git-worktree-best-practices.md`
- `worktree/squash-merge-default.md`
- `worktree/gitlinks-trap.md`
- Atlassian: https://www.atlassian.com/git/tutorials/merging-vs-rebasing
- OneUptime: https://oneuptime.com/blog/post/2026-01-24-git-rebase-vs-merge-strategies/view
