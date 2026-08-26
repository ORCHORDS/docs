# git-reflog-2026

**Issue:** A developer runs `git reset --hard HEAD~3` to undo 3 commits. They realize they needed the work. The commits are gone. The developer thinks they're lost forever.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Git's reflog is the safety net for "I did something destructive and need it back." The 2026 default is knowing how to use reflog to recover from any local mistake.

## Root cause

Git tracks every movement of HEAD and every branch tip update in the reflog. `git reset --hard`, `git commit --amend`, branch deletion — all are recorded. The reflog is local; it persists for 90 days by default.

## The 5 reflog operations

| Operation | Command | Use |
|---|---|---|
| View reflog | `git reflog` | see all HEAD movements |
| View per-ref | `git reflog show <ref>` | see one branch's movements |
| Recover from reset | `git reset --hard <reflog-sha>` | restore from a reflog entry |
| Recover from rebase | `git reset --hard <reflog-sha>` | restore pre-rebase state |
| Recover deleted branch | `git checkout <reflog-sha>` then `git branch <name>` | restore the branch |

The 5 operations cover 90%+ of reflog use cases.

## The 5-step recovery pattern

For "I did something destructive and need it back":

1. **Run `git reflog`** to see all HEAD movements with timestamps
2. **Find the entry** before the destructive operation
3. **Note the SHA** of that entry
4. **Run `git reset --hard <sha>`** to restore
5. **Verify** the working tree and recent commits

The 5 steps are the standard recovery pattern.

## The reflog format

```
$ git reflog
a1b2c3d (HEAD -> main) HEAD@{0}: reset: moving to HEAD~3
e4f5g6h HEAD@{1}: commit: add new feature
i7j8k9l HEAD@{2}: commit: refactor auth
m0n1o2p HEAD@{3}: commit: initial implementation
q3r4s5t HEAD@{4}: clone: from github.com/myorg/myrepo
```

Each line: SHA, ref name, action description, relative timestamp. The SHA you want is the one BEFORE the destructive action.

## The 5 common reflog scenarios

| Scenario | What reflog shows | Recovery |
|---|---|---|
| `git reset --hard HEAD~N` | reset entry | `git reset --hard <sha-before-reset>` |
| `git commit --amend` | amend entry | `git reset --hard <sha-before-amend>` |
| `git rebase` (mid-rebase) | rebase entries | `git rebase --abort` (or reflog) |
| `git branch -D <name>` | branch delete entry | `git checkout <sha>` + `git branch <name>` |
| `git push --force` (replaced remote) | only local, push doesn't reflog | pull from reflog before push |

The 5 scenarios cover most destructive operations.

## The 3 reflog retention rules

1. **Default retention is 90 days** for reachable commits; 30 days for unreachable. Configurable via `gc.reflogExpireUnreachable` and `gc.reflogExpire`.
2. **`git gc` prunes the reflog** — runs automatically; reflog is not infinite.
3. **Pushed commits are not "lost"** — they're on the remote. Reflog is for local-only commits.

The 3 rules explain when reflog works and when it doesn't.

## The 5 anti-patterns

1. **Trusting `git reset --hard` is safe because of reflog.** It's a safety net, not a feature. Be intentional.
2. **Running `git reflog expire --expire=now --all` then `git gc --prune=now`.** This destroys the safety net. Don't.
3. **Confusing reflog with log.** `git log` shows reachable commits; `git reflog` shows all HEAD movements, including unreachable.
4. **Assuming reflog is on the remote.** It's local. A force-pushed commit on a collaborator's clone may not be recoverable via reflog.
5. **Not knowing `git fsck --lost-found`.** This finds dangling commits not in reflog; the 2026 last-resort tool.

## The fsck pattern (last resort)

If reflog doesn't have it (e.g., expired or pruned), try `git fsck`.

```bash
# Find dangling commits
git fsck --lost-found

# Dangling commits are listed; check each
git show <dangling-sha>
# If it's what you want:
git branch recover-<sha> <dangling-sha>
```

`git fsck` finds unreachable objects in the object database. Most "lost" commits are still there; they're just not reachable from any ref.

## The 5-step post-recovery verification

After a reflog-based recovery, verify 5 things.

1. **Working tree matches expectation** — `git status` shows what you expect
2. **HEAD is at the right commit** — `git log --oneline -5`
3. **Branch is correctly set** — `git branch -v` shows current branch
4. **No accidental commits lost** — `git fsck` is clean (no dangling)
5. **Remote is not affected** — if you didn't push, the remote is unchanged

The 5 verifications catch the common follow-on issues.

## The 4 reflog tips

1. **Add `git reflog` to your daily commands.** It's free; you only check it when needed.
2. **Use `git reflog show <branch>`** to see one branch's history.
3. **Use `git reflog --date=iso`** for absolute timestamps (useful for collaboration).
4. **The reflog is your local diary.** Treat it as a recovery tool, not a permanent log.

## The 3 reflog-related edge cases

1. **Multiple resets in a row.** Each is logged; the reflog shows the chain. Pick the right entry.
2. **`git stash drop` does not always reflog.** Stashed changes are commits; if they're reachable via stash reflog, recoverable.
3. **Squash-merge reflogs the squashed-out commits.** The original commits may be reachable.

The 3 edge cases are where reflog becomes a forensic tool.

## The 5 best practices

1. **Before any destructive operation, run `git reflog`.** Note the current SHA; you can return.
2. **Use `git stash` instead of `git reset` for "save my work" operations.** Stash is reflog-tracked; reset is destructive.
3. **Document your recovery pattern.** `git reflog + git reset --hard <sha>` is the answer; teach it.
4. **Set `gc.reflogExpireUnreachable=180 days`** for longer retention of unreachable commits.
5. **For `git push --force`, consider `--force-with-lease`** to avoid clobbering others' work.

## The 2026 workflow

A 2026 dev workflow that uses reflog effectively.

```bash
# Before destructive operations
git reflog  # note current state
# ... do work ...

# If something goes wrong
git reflog  # find the entry before the mistake
git reset --hard <sha>  # recover

# For experimental work
git checkout -b experiment
# ... try things ...
git checkout main  # discard experiment (commit it if you want to keep)

# For "save my work, try something else"
git stash
# ... try other work ...
git stash pop  # restore
```

The 3 patterns (reset recovery, branch discard, stash) cover 95% of dev workflow.

## Verification

The tell that reflog is well-understood:

- `git reflog` is part of the team's mental toolkit
- New devs are taught the 5-step recovery pattern
- `git reset --hard` is used intentionally, not casually
- `git fsck --lost-found` is in the team's debugging playbook
- Reflog retention is configured for the team's recovery needs

The tell it isn't:

- "I lost my work; I have to redo it"
- "Reset is fine, reflog has my back"
- No one knows what reflog is
- `git fsck` is the last-resort unknown

## Gotchas

- **Reflog is local.** A collaborator's destructive `git push --force` is not in your reflog.
- **90 days is the default.** Beyond that, unreachable commits may be garbage-collected.
- **`git reflog expire` is destructive.** Don't run it without thinking.
- **`git stash` is its own reflog.** `git stash list` shows saved stashes; `git stash show <n>` shows content.
- **Branches that are never created don't have reflogs.** A `git checkout <sha>` (detached HEAD) does; a branch is just a ref.

## Related

- `worktree/branch-strategies-2026.md` — branch patterns
- `worktree/git-rerere.md` — reuse recorded resolutions
- `worktree/git-bisect-automation.md` — bisect for bug finding
- `worktree/conventional-commits-2026.md` — commit message format

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-reflog — git-reflog docs
- https://git-scm.com/docs/git-fsck — git-fsck docs
- https://git-scm.com/docs/git-stash — git-stash docs
- https://git-scm.com/docs/git-reset — git-reset docs
- https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery — Git Internals data recovery
- https://stackoverflow.com/questions/5473/how-can-i-undo-git-reset — recover from reset
- https://ohshitgit.com/ — oh shit, git! (the popular recovery guide)
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository — removing sensitive data
