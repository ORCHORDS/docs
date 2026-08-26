# github-squash-vs-merge-vs-rebase

**Issue:** Choosing the right merge strategy for pull requests and understanding the trade-offs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams argue about merge strategies without understanding the history, bisect, and changelog implications of each choice.

## Pattern / Solution
| Strategy | History | Bisect | Use when |
|---|---|---|---|
| Merge commit | Preserves all commits + merge commit | Clean | Long-lived feature branches, audit trails |
| Squash merge | Single commit on base branch | Easy | PR is the unit of work, noisy branch history |
| Rebase merge | Linear, all branch commits replayed | Hardest to debug | Clean linear history with full granularity |

Enforce in Settings → General → Pull Requests — uncheck strategies you do not want.

For squash-based workflows, require PR titles to follow conventional commits format so the squash message is meaningful.

## Gotchas
- Squash loses individual commit authorship — all changes attribute to the PR author.
- Rebase rewrites SHAs, so force-push is required on the branch; this confuses open review threads.
- Merge commits make `git bisect` harder in noisy-history repos.
- Some tools (release-it, semantic-release) read PR titles on squash — keep them descriptive.
- Mixed strategies in the same repo make bisect and revert operations unpredictable.

## Related
- `github-commit-message-conventions.md`
- `github-merge-queue.md`
- `github-fork-and-pr-workflow.md`
