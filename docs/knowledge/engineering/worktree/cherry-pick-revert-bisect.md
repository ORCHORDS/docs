# cherry-pick-revert-bisect

**Issue:** cherry-pick, revert, bisect — production hotfix
**Date:** 2026-08-09
**Status:** documented

## Symptom
Production has a bug. A commit on main is the cause.
You need the fix on release/v1.2 without the other
unrelated changes. You don't know which tool. You
wish you had a guide.

## Root cause
**Use the right tool.** cherry-pick + revert + bisect.

**Source:** DevOpsBeast + Git-Automation 2026.

## The "3 tools" pattern

For each task:
- **cherry-pick:** Move commit to another branch
- **revert:** Undo on shared branch (safe)
- **bisect:** Find the bad commit

The 3 are the toolkit.

## The "cherry-pick" pattern

For cherry-pick:
- **Good for:** Backport hotfix to release
- **Good for:** Rescue one commit from bad branch
- **Good for:** Move without force-push
- **Bad for:** Move many commits (use rebase)
- **Bad for:** Primary integration (use merge)

The cherry-pick is targeted.

## The "cherry-pick -x" pattern

For audit:
```bash
git cherry-pick -x abc1234
# Adds "(cherry picked from commit <commit-sha>)"
```

The -x is mandatory for backports.

## The "cherry-pick -s" pattern

For DCO:
```bash
git cherry-pick -x -s abc1234
# Adds Signed-off-by
```

The -s is for DCO projects.

## The "cherry-pick range" pattern

For range:
```bash
# Picks abc123..def456 (exclusive of abc123)
git cherry-pick abc123..def456
```

The range is the batch.

## The "cherry-pick conflict" pattern

For conflict:
```bash
# After pause
# 1. Resolve files
git add path/to/file
# 2. Continue
git cherry-pick --continue
```

The conflict is per file.

## The "cherry-pick abort" pattern

For abort:
```bash
git cherry-pick --abort
# Restores to pre-pick state
```

The abort is clean.

## The "atomic commit" pattern

For cherry-pick:
- **Required:** Atomic (one fix, no refactor)
- **Why:** Non-atomic = untested changes leak
- **Fix:** Interactive rebase first

The commit is atomic.

## The "revert" pattern

For revert:
- **Safe for shared:** Yes
- **Adds:** New commit (inverse)
- **Use:** Undo on main, release branches
- **Bad for:** Local (use reset)

The revert is safe.

## The "revert vs reset" pattern

For choice:
| Situation | Use |
|---|---|
| Local, not pushed | reset --hard |
| Shared, pushed | revert |
| Need to remove from history | rebase -i (only unshared) |
| Want to roll back feature | revert |

The choice is per need.

## The "revert merge" pattern

For merge:
```bash
git revert -m 1 <merge-sha>
# -m 1: keep parent 1 (mainline)
```

The merge is reverted.

## The "revert range" pattern

For range:
```bash
# One commit per revert
git revert HEAD~5..HEAD

# One combined revert
git revert --no-commit HEAD~5..HEAD
git commit -m "revert: roll back buggy changes"
```

The range is batched.

## The "revert the revert" pattern

For forward fix:
```bash
# Bad commit → revert → fix forward
# Revert the revert after fix merges
git revert <revert-sha>
```

The revert-of-revert restores.

## The "bisect" pattern

For find regression:
```bash
# Start
git bisect start
git bisect bad              # current
git bisect good v1.0        # known good
# Test... if bug: git bisect bad, else: git bisect good
# Repeat until found
git bisect reset
```

The bisect is binary search.

## The "bisect run" pattern

For automation:
```bash
git bisect start
git bisect bad
git bisect good v1.0
git bisect run ./test.sh
# exit 0 = good, non-zero = bad, 125 = skip
```

The run is automated.

## The "bisect skip" pattern

For uncertain:
```bash
# Can't tell if bad/good at this commit
git bisect skip

# In script, exit 125 to skip
```

The skip is for unknowns.

## The "hotfix workflow" pattern

For prod hotfix:
1. **Bisect:** Find bad commit
2. **Revert:** On main
3. **Cherry-pick:** On release branches
4. **Fix forward:** On feature branch
5. **PR:** Corrected feature
6. **Supersedes:** Revert

The workflow is 6 steps.

## The "pre-flight" pattern

For cherry-pick:
```bash
# 1. Clean working tree
git status --porcelain

# 2. Fetch latest
git fetch origin

# 3. Switch to target
git switch release/vX.Y.Z
git reset --hard origin/release/vX.Y.Z
```

The preflight is verified.

## The "atomic check" pattern

For source:
```bash
# Inspect
git show abc1234 --stat
git show abc1234 -p
# Confirm: only the fix, no refactor
```

The source is verified.

## The "backport branch" pattern

For traceability:
```bash
COMMIT_SHA=abc1234
TARGET_VERSION=v1.2.x
git push origin "HEAD:backport/${COMMIT_SHA}-to-${TARGET_VERSION}"
# Open PR
# CI runs
# Merge
```

The branch is per backport.

## The "annotated tag" pattern

For release:
```bash
git tag -a vX.Y.Z+1 -m "Hotfix: <description>"
git push origin vX.Y.Z+1
# Annotate, sign
```

The tag is annotated.

## The "compatibility check" pattern

For versions:
- **Issue:** Cherry-pick across versions can break
- **Check:** API/ABI compatibility
- **Action:** Test thoroughly
- **Rule:** Never across major without verification

The compat is verified.

## The "no cherry-pick across majors" anti-pattern

For across majors:
- **Issue:** API changed, refactor missing
- **Fix:** Re-implement against old code

The major is re-implemented.

## The "force-push shared" anti-pattern

For force:
- **Issue:** Breaks others
- **Fix:** Use revert (not reset)

The force is forbidden on shared.

## The "no bisect script" anti-pattern

For no script:
- **Issue:** Manual = slow, error-prone
- **Fix:** Automate with `bisect run`

The script is automated.

## The "no -x" anti-pattern

For no -x:
- **Issue:** Lose link to original
- **Fix:** Always -x for backports

The -x is required.

## The "dirty tree cherry-pick" anti-pattern

For dirty:
- **Issue:** Untracked changes lost
- **Fix:** Stash / commit first

The tree is clean.

## The "non-atomic cherry-pick" anti-pattern

For non-atomic:
- **Issue:** Bundled refactor leaks
- **Fix:** Interactive rebase first

The atomic is enforced.

## The "PR for backport" pattern

For PR:
- **Always:** Push to backport/<sha>-to-<version>
- **Always:** Open PR to release branch
- **CI:** Must pass
- **Merge:** Squash or merge commit

The PR is required.

## The "verify script" pattern

For check:
```bash
#!/bin/bash
# Exit 0 = good, non-zero = bad
# Test the fix
if [some_condition]; then
  exit 0
fi
exit 1
```

The script is binary.

## The "production hotfix" pattern

For prod:
1. Page on-call
2. Identify bad commit (bisect if needed)
3. **Revert** on main
4. **Cherry-pick** to release branches
5. **Fix forward** on feature branch
6. Verify in prod
7. Postmortem
8. Action items

The hotfix is 8 steps.

## The "workflow checklist" pattern

For checklist:
- [ ] Pre-flight clean
- [ ] Fetch + reset
- [ ] Source commit atomic
- [ ] Cherry-pick with -x
- [ ] Conflict resolved
- [ ] PR opened (not direct push)
- [ ] CI passed
- [ ] Annotated tag
- [ ] Release notes

The checklist is 9.

## Verification
- **Test:** Cherry-pick applied
- **Test:** Revert works
- **Test:** Bisect finds
- **Audit:** Per release

## Gotchas
- **The "force-push shared" anti-pattern.** Revert.
- **The "no -x" anti-pattern.** Always -x.
- **The "non-atomic" anti-pattern.** Rebase first.

## Related
- `worktree/rebase-vs-merge-detail.md`
- `worktree/git-worktree-best-practices.md`
- `worktree/squash-merge-default.md`
- `worktree/gitlinks-trap.md`
- `deploy/cab-change-management.md`
- `deploy/gitops.md`
- DevOpsBeast: https://devopsbeast.com/courses/git-internals/advanced-workflows/cherry-pick-revert-bisect
- Git-Automation: https://www.git-automation.com/conflict-resolution-safe-merge-operations/cherry-pick-backporting/cherry-picking-hotfixes-across-release-branches/
