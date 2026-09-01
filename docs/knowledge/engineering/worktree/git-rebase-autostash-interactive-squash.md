# Rebase Autostash Discipline With Interactive Squash Cleanup

## Scope

This article covers combining `--autostash` with interactive rebase for commit cleanup: when autostash is a safe accelerator and when it hides damage, how `fixup!`/`squash!` commits created with `commit --fixup` fold into their targets, how `--autosquash` ordering interacts with an unstashed working tree, and how to recover when an autostash application collides with rebased content. It applies to developers tidying a branch before opening or updating a pull request. It does not cover rebase-versus-merge policy, rebasing published shared branches, or range-diff review after rebase.

## Workflow or implementation guidance

The workflow being automated is mundane: you have work-in-progress in the working tree, upstream pushed a change you need, and you want to rebase without first committing a junk `wip` commit. `git rebase --autostash` stashes your dirty state, runs the rebase (interactive or not), then pops the stash afterward. It removes a real chore and, used with eyes open, is safe. The discipline is in knowing what autostash does not protect.

**What autostash actually does.** It is a plain `stash push --include-untracked`-style snapshot followed by an automatic `stash pop` after the rebase finishes or aborts. Two consequences follow. First, if the rebase changes lines your stashed edits touch, the pop conflicts — and because it is a pop, the conflicting stash entry is preserved while the working tree fills with conflict markers, leaving you mid-rebase *and* mid-stash-conflict simultaneously. Second, autostash entries are recoverable (`git stash list` still shows them), so an interrupted session is not data loss, but neither is it auto-resolved.

**The standard cleanup loop.** Before requesting review, fold review-fixup commits into the changes they amend:

```bash
git add -p                              # stage only the fix
git commit --fixup <target-sha>         # creates "fixup! <subject>" commit
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash --autostash ^<target-sha>~1
```

`--autosquash` rewrites the todo list so each `fixup!` commit is placed directly after its target and its action changed from `pick` to `fixup` (message discarded) — use `squash` instead when the messages must be combined and you need to edit the result. `commit --fixup` guarantees the linkage by subject prefix, which is why you should avoid duplicate commit subjects on one branch: `--autosquash` matches the first `fixup!` to a target with that subject, and duplicates make the pairing ambiguous. The `GIT_SEQUENCE_EDITOR=:` trick accepts the rewritten todo non-interactively, turning the whole loop into a single command; drop it when you want to inspect the reordered plan.

Note the rebase range in that loop: rebasing from the target's parent rather than from the branch point keeps history rewriting local to the commits being folded. Rebasing `--root` or from far back multiplies the surface for conflicts and for triggering the very pop-collision autostash cannot handle.

**Autostash safety rules.**

- Autostash with *fast-forward-only* content changes upstream (docs, untouched modules) is low risk; the pop applies cleanly.
- Autostash is dangerous when the rebase rewrites the same files your dirty state edits — typical when you are folding fixups into a commit whose file you still have unsaved edits in. The reliable sequence there: finish or shelve the dirty work first (`git stash push -m "wip before fold"`), run the interactive rebase without autostash, then pop manually. You get the same conflict, but at a moment you chose, with the rebase already complete.
- Never combine `--autostash` with `--exec` steps that mutate tracked files (generators, formatters): the exec runs mid-rebase while the stash is still aside, and its output files collide with the stash on pop.

**Verifying the fold.** An autosquash rewrite silently discards fixup messages — that is its job — so verification must confirm nothing else was discarded. `git range-diff <before>...<after>` (or compare against the pre-rebase tip you recorded, for example via a branch bookmark like `git branch backup/pre-fold`) shows per-commit what changed. The expected shape: the target commit grew, the fixup commits vanished, untouched commits show as unchanged. A fixup that vanished *without* its target growing means the pairing misfired — the classic duplicate-subject failure.

## Controls

- Fixups are created with `git commit --fixup <sha>`, never by hand-typing `fixup!` subjects.
- The fold command always includes `--autosquash` and an explicit rebase base at the target's parent; `--root` rewrites are forbidden on branches with collaborators.
- When dirty state overlaps files touched by the rebase, the stash is manual and explicit; autostash is reserved for non-overlapping dirty state.
- A `backup/pre-fold` branch (or reflog reference) is created before every interactive fold and retained until the PR merges.
- `git range-diff` against the backup runs after every fold; a fixup disappearing without its target growing is a blocking anomaly.
- Duplicate commit subjects on one branch are treated as a defect — squash them or retitle before accumulating fixups.

## Validation evidence

- After the fold, `git log --oneline` contains no `fixup!`/`squash!` subjects, and the target commit's diff (`git show <new-target-sha>`) includes the staged fix content — the two halves of "folded correctly."
- `git range-diff backup/pre-fold...HEAD` shows only the intended pairs changed; commit count decreases by exactly the number of fixup commits folded.
- A deliberate rehearsal on a scratch branch: dirty a file unrelated to the rebase, run with `--autostash`, confirm the dirty state returns afterward via `git status` and content comparison.
- The collision rehearsal: dirty a file the rebase rewrites, run with `--autostash`, observe the pop conflict, confirm `git stash list` still holds the entry — proving recovery exists before anyone relies on the shortcut in production work.
- `git fsck --lost-found` after an aborted session finds no orphaned blobs beyond expectation, and reflog (`git reflog`) still shows the pre-rebase ORIG_HEAD pointer.

## Failure modes and correction

- **Pop collision mid-rebase.** The autostash application conflicts while the rebase is still resolving, stacking two problems. Correction: resolve the stash conflict in the working tree, `git checkout --theirs`/manual edit as appropriate, then `git stash drop` only after confirming content; if the rebase itself is also stuck, `git rebase --abort` first — abort restores the branch while preserving the stash entry for a clean retry.
- **Mispaired fixup.** Two commits share a subject; the fixup folds into the wrong one and a review comment's change silently lands elsewhere. Correction: restore from `backup/pre-fold`, retitle the duplicate, re-fold; long-term rule against duplicate subjects.
- **Fixup vanished into nothing.** Range-diff shows the fixup commit gone but the target unchanged — usually a base selection error (`--autosquash` matched across a rewritten boundary). Correction: reset to backup, narrow the rebase range, redo.
- **Autostash as a habit-blanket.** A developer defaults to `rebase.autostash=true` globally and one day loses twenty minutes to a gnarly stacked conflict they never chose. Correction: keep the global setting off; opt in per-command where the overlap analysis was actually done.
- **Interactive editor never opens.** `GIT_SEQUENCE_EDITOR=:` left in an alias makes every rebase non-interactive, and a needed todo edit gets skipped. Correction: the no-op editor is used only in the one-line fold alias, not in general rebase aliases.

## Limitations

Autostash snapshots are not snapshots of the index and working tree in all states: partially staged interplay between index and worktree can flatten during the stash-pop round trip, so exotic staged-versus-unstaged splits should be committed or stashed deliberately rather than autostashed. `--autosquash` matches by subject line, which is fragile against amend-retitled commits and reworded targets; pairing by `--fixup` shorthand mitigates but does not eliminate it. Interactive rebase remains a history rewrite: the moment any of the branch's commits exist on a shared remote, folding requires a force-push and coordination, and none of the autostash machinery addresses that social problem. Recoverability leans on the reflog, which expires (default 90 days for reachable, 30 for unreachable entries), so "backup branches beat reflog" is the durable rule. Finally, none of this validates semantic equivalence — a fold that compiles and passes range-diff can still order changes differently than originally tested, so CI on the folded result is the actual safety net.

## Canonical sources

- Git documentation — git-rebase (including --autostash, --autosquash, --fixup interaction): https://git-scm.com/docs/git-rebase
- Pro Git, 2nd edition — Git Branching: Rebasing: https://git-scm.com/book/en/v2/Git-Branching-Rebasing
- Pro Git, 2nd edition — Git Tools: Rewriting History (interactive rebase, squashing ordered commits): https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History
- Git documentation — git-range-diff for post-fold verification: https://git-scm.com/docs/git-range-diff
