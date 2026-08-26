# verify-live-file-before-work

**Issue:** An autonomous agent picked up issue #<number> on example-org/example-repo, located a file matching the issue's description (pages/LiveStudio.tsx), and implemented a complete fix in it — but that file had been DELETED in PR #<number> a week earlier. The real live code path was `useStudioEngine.ts`. The PR was worthless and the issue had to be re-filed as #323 against the correct file.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Why agents pick dead files

1. **Issue text ages.** Issues describing file paths are written against the tree at filing time; refactors and deletions happen between filing and pickup.
2. **Name matching feels like verification.** An agent greps for a plausible filename, finds it in history or in a stale checkout, and treats the hit as proof.
3. **Stale checkouts.** A worktree cloned days ago doesn't have yesterday's deletion; the file genuinely exists on disk for that agent.
4. **Deleted-but-present artifacts.** Build output, dist folders, and editor caches can retain files the source tree no longer has.
5. **Nobody checks the import graph.** The dead file wasn't imported anywhere — a 10-second grep for importers would have caught it.

## The pre-work verification gate

1. **`git fetch && git log --oneline -5 -- <file>`** — confirm the file exists on the CURRENT default branch tip, not just locally.
2. **Grep for importers** — if nothing imports the file, it's dead code regardless of what the issue says.
3. **Trace from the entry point** — for "feature X is broken" issues, find the live module by following imports from the app entry, not by filename search.
4. **Check the issue date against recent merges** — if refactors landed after filing, re-map the issue's references before implementing.
5. **If the target is dead, say so** — close/comment the issue with the evidence and re-file against the live path instead of force-fitting the fix.

## Making it systematic for fleets

1. **Pre-flight step in the solver loop:** file-exists-on-main + has-importers checks BEFORE any edit — both are cheap git/grep calls.
2. **Block edits to files with zero importers** unless the issue explicitly says "new file".
3. **Record the live-path mapping in the PR body** ("issue said X, live path is Y because #318 deleted X") so reviewers see the reasoning.
4. **Auto-link the deleting PR** in a comment when re-filing — the paper trail prevents the next agent from making the same trip.
5. **Treat filename-from-issue as a hint, never an address.**

## Related

- `master-issue-pattern.md`
- `../lessons/` post-mortems
