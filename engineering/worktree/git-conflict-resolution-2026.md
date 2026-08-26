# git-conflict-resolution-2026

**Issue:** A team merges a feature branch. Git says "CONFLICT". The team panics. They `git merge --abort`. The team loses 2 days of work. The team doesn't know how to resolve conflicts.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Git conflicts are normal. The 2026 production pattern is to understand the 3 conflict types, use the right tool, and resolve in minutes — not hours.

## Root cause

A conflict happens when Git can't auto-merge two changes. The 3 common types are: line conflicts (same line changed), file conflicts (file deleted vs modified), and rename conflicts (file renamed in both branches).

## The 4 conflict types

| Type | What | Example |
|---|---|---|
| Line conflict | same line changed in both branches | two commits edited `config.py` line 10 |
| File conflict | file deleted in one branch, modified in another | A deleted; B modified |
| Rename conflict | file renamed in both branches | A→B and A→C |
| Binary conflict | binary file changed in both branches | image, model weights, PDF |

The 4 types cover the 2026 production conflict space.

## The 5-step conflict resolution pattern

1. **Don't panic. Run `git status`.** Git tells you what's unmerged.
2. **Read the conflict markers.** `<<<<<<<`, `=======`, `>>>>>>>` delimit the 3 versions.
3. **Choose the resolution.** Keep yours, keep theirs, merge both, or rewrite.
4. **`git add` the resolved file.** Tells Git you've resolved it.
5. **`git commit` to complete the merge.** The merge commit is created.

The 5 steps are the 2026 production pattern.

## The conflict markers explained

```python
<<<<<<< HEAD
# Your branch's version
config_value = 10
=======
# Their branch's version
config_value = 20
>>>>>>> feature/new-config
```

- `<<<<<<< HEAD` — start of your version
- `=======` — divider
- `>>>>>>> feature/new-config` — end of their version

Remove the markers; keep the code you want.

## The 4 resolution strategies

| Strategy | When | Example |
|---|---|---|
| Keep mine | your change is correct | take the new value |
| Keep theirs | their change is correct | take the old value |
| Merge both | both are needed | combine features |
| Rewrite | the result is different | write a new version |

The 4 strategies cover the 2026 use cases. Most conflicts need "merge both" or "rewrite."

## The 5 best practices

1. **Pull and rebase frequently.** Reduce the window of conflict.
2. **Communicate with your team.** "I'm editing config.py; let me know if you're touching it."
3. **Use a visual merge tool.** VSCode, Meld, Beyond Compare, KDiff3.
4. **Test after resolving.** The resolved file should work; CI catches broken merges.
5. **Don't `git merge --abort` to escape.** Resolve the conflict; aborting loses work.

## The 5 anti-patterns

1. **Random `<<<<<<<` resolution.** Picking a side without understanding is broken.
2. **`git add .` to dismiss conflicts.** Doesn't resolve; just hides the markers.
3. **Rebasing shared branches.** Rewrites history; collab breaks.
4. **Force-push after rebase.** `git push --force-with-lease` is safer.
5. **Big merges with many conflicts.** Indicates the branch was too long-lived.

## The 5 conflict resolution tools

| Tool | Strength | When |
|---|---|---|
| VSCode merge editor | integrated, visual | dev |
| Meld | visual diff, 3-way | Linux |
| Beyond Compare | commercial, powerful | enterprise |
| KDiff3 | open source, 3-way | Linux |
| IntelliJ IDEA / WebStorm | integrated, smart | Java/Kotlin |

The 5 tools cover the 2026 use cases. VSCode is the most common; the others are for specific needs.

## The 3-way merge explained

Git's 3-way merge combines 3 versions: the common ancestor, your version, their version.

```
common ancestor:  config_value = 5
your version:     config_value = 10
their version:    config_value = 20
```

Git auto-merges when both changes are in different lines. When the same line is changed in both versions, Git can't decide; it produces a conflict.

## The 5 step workflow: `git pull --rebase`

For short-lived branches, `git pull --rebase` reduces conflicts.

```bash
# On feature branch
git fetch origin
git rebase origin/main  # or: git pull --rebase origin main
# Resolve any conflicts during the rebase
# ...
git push origin feature/my-feature
```

The 5 step workflow applies your commits on top of latest main, instead of creating a merge commit. Conflicts are per-commit, easier to resolve.

## The 5 step workflow: merge commit

For long-lived branches, merge commit is the default.

```bash
# On main branch
git fetch origin
git merge origin/feature/my-feature
# Resolve conflicts
# ...
git commit  # the merge commit
git push origin main
```

The 5 step workflow creates a merge commit; the branch's history is preserved.

## The 5 step workflow: cherry-pick

For picking a single commit from another branch.

```bash
# On target branch
git cherry-pick <commit-sha>
# Resolve conflicts if any
# ...
git push
```

The 5 step workflow is for hotfixes or backports. Use sparingly; creates "unrelated" commits in the target branch.

## The 4 merge strategies

| Strategy | Use | Trade-off |
|---|---|---|
| `recursive` (default) | most merges | standard 3-way |
| `octopus` | merging 3+ branches at once | no conflict resolution allowed |
| `ours` / `theirs` | prefer one side always | loses changes from the other |
| `subtree` | merge subproject into subtree | complex |

The 4 strategies are 2026 production choices; `recursive` is the default.

## The 5 best practices for team conflict avoidance

1. **Keep branches short.** Hours to a day for trunk-based; a week for GitHub Flow.
2. **Communicate.** "I'm in this file" in Slack.
3. **Pull frequently.** Reduces divergence.
4. **Use file ownership.** CODEOWNERS for the team responsible for a file.
5. **Squash before merge.** Reduces the number of commits to merge.

The 5 practices reduce conflicts at the source.

## The 5 step conflict resolution with VSCode

1. **Open the conflicted file in VSCode**
2. **VSCode shows `<<<<<<<`, `=======`, `>>>>>>>` with inline buttons**
3. **Click "Accept Current Change", "Accept Incoming Change", "Accept Both Changes", or "Compare"**
4. **Edit the merged result if needed**
5. **Save the file; VSCode stages it; commit the merge**

The 5 step VSCode workflow is the most common 2026 pattern.

## The 5 step conflict resolution with command line

```bash
# 1. See the conflict
git status
# Unmerged paths: both modified: config.py

# 2. Open the file; edit manually
vim config.py
# Remove conflict markers; keep the right code

# 3. Mark as resolved
git add config.py

# 4. Continue the merge
git commit  # or: git rebase --continue

# 5. Push
git push
```

The 5 step command-line workflow is the fallback when no IDE is available.

## The 4 step reresolve pattern

If the resolved merge doesn't work, the reresolve pattern.

1. **`git reset --hard HEAD`** to undo the merge
2. **Re-resolve** with a clearer head
3. **Test the resolved code** before committing
4. **`git commit` only when correct**

The 4 step pattern prevents committing broken merges.

## Verification

The tell that conflict resolution is real:

- Team knows the 5-step resolution pattern
- `git status` is the first action on a conflict
- Visual merge tools are configured
- Conflicts are resolved in minutes, not days
- Code is tested after resolution

The tell it isn't:

- `git merge --abort` is the response to any conflict
- Conflicts are resolved by random selection
- Resolved code is not tested
- Force-push overwrites collaborators' work
- "We never have conflicts" (because they merge long-lived branches)

## Gotchas

- **Conflict markers are in the file.** Removing them is part of the resolution.
- **Whitespace-only conflicts** can be ignored with `-Xignore-all-space`.
- **`git rerere` records resolutions.** Replay the same conflict resolution; see `worktree/git-rerere.md`.
- **Pull --rebase rewrites local history.** If you haven't pushed, it's safe; if you have, use `--force-with-lease`.
- **Octopus merge fails on conflict.** Use `recursive` (default) for conflict-able merges.

## Related

- `worktree/git-rerere.md` — reuse recorded resolutions
- `worktree/branch-strategies-2026.md` — branch patterns
- `worktree/git-reflog-2026.md` — recovery from mistakes
- `worktree/codeowners-advanced-2026.md` — file ownership

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-merge — git-merge docs
- https://git-scm.com/docs/git-merge-strategies — merge strategies
- https://git-scm.com/docs/git-rebase — git-rebase docs
- https://git-scm.com/docs/git-cherry-pick — git-cherry-pick docs
- https://git-scm.com/docs/gitattributes#_merge_driver — merge drivers
- https://code.visualstudio.com/docs/sourcecontrol/overview#_merge-conflicts — VSCode merge
- https://meldmerge.org/ — Meld
- https://www.gitkraken.com/ — GitKraken
- https://www.perforce.com/products/helix-merge-and-diff-tools — Beyond Compare
- https://www.atlassian.com/git/tutorials/using-branches/merge-conflicts — Atlassian merge conflicts
