# Git range-diff review after rebasing a patch series

**Issue:** A rebase or revised patch series can accidentally alter, drop, split, or add changes beyond the intended conflict resolution.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use `git range-diff` to compare the old and new versions of a commit series after rebasing, conflict resolution, or review-driven rewriting. It matches commits by patch similarity and shows how each patch changed, which answers a different question from comparing only the final trees.

The output is human-oriented porcelain and is not stable machine-readable data. It supports review but does not replace compilation, tests, policy checks, or a final aggregate diff.

## Controls and verification

- Preserve an unambiguous reference to the pre-rewrite series, such as a branch or reflog position.
- Check for unmatched additions and deletions as well as modified matched commits.
- Review author and commit-message changes when provenance matters.
- Use path restriction only when the excluded paths are intentionally outside scope.
- Do not parse range-diff output as a stable automation protocol.
- Run the full required checks on the rewritten head.

## Example verification flow

1. Record the old tip before rebasing.
2. Rebase and resolve conflicts.
3. Compare the old and new series with a common base or the documented three-revision form.
4. Explain every added, removed, or materially changed patch.
5. Compare the final tree and run all required tests.

## Sources

- [Git: git-range-diff](https://git-scm.com/docs/git-range-diff)
- [Git: revisions](https://git-scm.com/docs/gitrevisions)
- [Git: rebase](https://git-scm.com/docs/git-rebase)
