# git-stash-2026

**Issue:** A developer is mid-feature when an urgent bug comes in. The developer needs to switch branches without losing work. The developer debates `git stash`, `git worktree`, commit-on-feature-branch. The developer needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 stash commands

1. `git stash` - save WIP, working tree clean.
2. `git stash push -m "msg"` - with a message.
3. `git stash list` - show all stashes.
4. `git stash pop` - apply and remove latest stash.
5. `git stash apply stash@{n}` - apply without removing.
6. `git stash drop stash@{n}` - remove without applying.
7. `git stash branch <name>` - create branch from stash.

## The 5 best practices

1. **Stash with a message** describing the WIP state.
2. **Use `git stash push -u`** to include untracked files.
3. **Use `git stash show -p`** to inspect before popping.
4. **Use `git worktree`** for longer parallel work (see dedicated entry).
5. **Don't stash secrets.** Stash history is per-clone and may be pushed to backup.

## The 5 anti-patterns

1. **Stashing in a panic** without a message. Mystery stash.
2. **Stashing in subdirectories** without `-u`. Untracked files lost.
3. **Long-term stash management.** Stashes are for short-term parking.
4. **Stashing build artifacts** that should be in `.gitignore`.
5. **Stash in shared branch** (impossible, but mixed with `git stash` of staged changes).

## Gotchas

- Stash creates a commit on a hidden ref (`refs/stash`); it's per-clone, not pushed.
- `git stash pop` after conflicts keeps the stash; resolve or `git stash drop`.
- `git stash --keep-index` stashes unstaged, keeps staged changes.
- `git stash push <pathspec>` stashes only specific files.
- Stash can include untracked with `-u`; ignored files with `-a` (careful).

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-stash
- https://www.atlassian.com/git/tutorials/saving-changes/git-stash
