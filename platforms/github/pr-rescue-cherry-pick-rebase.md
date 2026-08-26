# pr-rescue-cherry-pick-rebase

**Issue:** PR #<number> on example-org/example-repo sat open while main moved; a direct `git rebase main` produced intractable conflicts (the base files had been restructured underneath it). Force-pushing through the rebase risked mangling the change. The PR needed rescuing without losing its reviewed commits.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## The rescue pattern (what worked)

1. **Create a fresh branch off current main:** `git checkout main && git pull && git checkout -b fix/issue-305-v2`.
2. **Cherry-pick the PR's commits onto it:** `git cherry-pick <sha1> <sha2>` — conflicts now appear one commit at a time against the new structure.
3. **Resolve each conflict against the NEW file shapes** — not by replaying the old hunks; read the restructured code and re-apply intent.
4. **Open a NEW PR** referencing the old one ("supersedes #305") and close the original — cleaner than force-pushing a mangled history reviewers already commented on.
5. **Squash the pick-resolutions** if the intermediate conflict states would confuse review; keep the final diff minimal.

## When to use which

1. **Rebase:** branch is young, conflicts are textual, few reviewers invested — plain `git rebase main` is fine.
2. **Cherry-pick rescue:** conflicts are structural (files moved/split), or the branch has review history worth preserving as reference.
3. **New PR supersede:** the old PR's diff is so entangled with dead base code that even cherry-picked diffs mislead reviewers.
4. **Never:** force-push blind conflict resolutions (`theirs`/`ours` mass-take) into an reviewed PR — that's how silently wrong merges happen.
5. **In fleets:** automation should default to cherry-pick-rescue because agent branches age fast while humans review slowly.

## Prevention beats rescue

1. **Land agent PRs fast** — review latency is the aging agent; a 48h-old agent PR against a moving main is already at risk.
2. **Small diffs rebase cleanly** — the entangled PR was a multi-concern change; single-concern PRs almost never need rescue.
3. **Renovate the base first** — if the PR's target files were restructured, re-implement on top of the new structure instead of porting the old diff.
4. **Close superseded PRs with a pointer comment** — future readers (and agents) must find the successor.
5. **Note the rescue in the successor PR body** so reviewers know history was rebuilt and review the diff, not the commit count.

## Related

- `github-squash-vs-merge-vs-rebase.md`
- `codex-review-merge-gate.md`
