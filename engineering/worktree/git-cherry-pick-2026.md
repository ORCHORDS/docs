# git-cherry-pick-2026

**Issue:** A team has a critical bug fix on `develop`. Production runs on `main`. The team needs to backport the fix. The team debates cherry-pick vs backport branch vs merge. The team needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 use cases for cherry-pick

1. **Hotfix backport.** Apply a commit from `main` to a release branch.
2. **Cross-feature borrowing.** Take one commit from feature-A into feature-B.
3. **Restore lost work.** Apply a commit that was lost in a force-push.
4. **Selective release.** Take only some commits from a feature branch into release.

## The 4 mechanics

1. **`git cherry-pick <sha>`** - apply the commit's diff to the current branch.
2. **`git cherry-pick <sha1>..<sha2>`** - apply a range.
3. **`git cherry-pick -n <sha>`** - apply but don't commit (for batching).
4. **`git cherry-pick -x <sha>`** - append `(cherry picked from commit ...)` to the message for traceability.

## The 4 anti-patterns

1. **Cherry-pick as a substitute for merging.** Diverges history; sync gets hard.
2. **Cherry-pick conflicts dismissed without review.** Conflicts are real semantic mismatches.
3. **No record** of what was cherry-picked. Audit trail lost.
4. **Cherry-pick of merge commits** (without `-m`) produces empty commits.

## The 4 best practices

1. **Use `-x`** to record the original commit SHA in the cherry-picked commit.
2. **Backport via dedicated branch** (`backport/1.x/fix-1234`), not directly to release.
3. **Test the cherry-picked commit** as if it were new code.
4. **Document** in the changelog which commits were cherry-picked.

## Gotchas

- Cherry-picking a merge commit requires `-m 1` (or `-m 2`) to pick which parent.
- Cherry-pick conflicts need manual resolution, same as merge.
- The original commit remains in the source branch; cherry-pick creates a new commit elsewhere.
- Git's `cherry` command (without -pick) detects which commits are missing between branches, useful for backport planning.

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-cherry-pick
- https://git-scm.com/docs/git-cherry
- https://www.atlassian.com/git/tutorials/cherry-pick
