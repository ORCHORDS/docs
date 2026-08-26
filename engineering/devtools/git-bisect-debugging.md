# git-bisect-debugging

**Issue:** Regression introduced in unknown commit across hundreds of changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Bug exists in current HEAD but not in a release from 3 weeks ago.

## Pattern / Solution
git bisect start, git bisect bad (current), git bisect good v2.1.0 (last known good). Git checks out midpoint. Test then mark good or bad. Binary search finds commit in log2(n) steps. Automate: git bisect run npm test.

## Gotchas
- git bisect reset to return to original HEAD after finding culprit
- Script must exit 0 for good, 1-127 for bad (not 125, which means skip)

## Related
- git-reflog-recovery, git-interactive-rebase
