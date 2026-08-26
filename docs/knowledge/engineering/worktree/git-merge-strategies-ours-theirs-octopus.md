# Git Merge Strategies: ours, theirs, resolve, and octopus

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A PR merge is failing with unexpected conflicts, or you need deterministic automated merges (e.g., syncing a generated lockfile branch) where the default recursive strategy picks the wrong side without human review.

## Context
Cloudflare Workers monorepos with multiple environments (staging, canary, production) regularly need scripted merges: promoting a staging branch to production, auto-merging dependency-update PRs, or keeping a generated `wrangler.lock` branch in sync. Git exposes merge strategy selection via `-s <strategy>` (which algorithm to use) and strategy options via `-X <option>` (how that algorithm resolves ambiguity). Understanding the distinction prevents silent data loss.

## Strategy vs. strategy option
`-s` selects the *algorithm*; `-X` passes hints to that algorithm. They are not interchangeable.

| Flag | What it is | Example |
|---|---|---|
| `-s ort` | Strategy (algorithm) — default since Git 2.34 | `git merge -s ort feature` |
| `-s recursive` | Older default strategy | `git merge -s recursive feature` |
| `-s resolve` | Two-head only, no criss-cross rename tracking | `git merge -s resolve feature` |
| `-s ours` | Discard all changes from the other side entirely | `git merge -s ours stale-branch` |
| `-s octopus` | Merge >2 branches simultaneously | `git merge -s octopus feat-a feat-b feat-c` |
| `-X ours` | Within ort/recursive: auto-resolve conflicts favouring HEAD | `git merge -X ours dependency-bot/lockfile` |
| `-X theirs` | Within ort/recursive: auto-resolve conflicts favouring theirs | `git merge -X theirs env/staging` |

The critical trap: `-s ours` silently drops the entire incoming diff. `-X ours` resolves only *conflicted hunks* in favour of HEAD, leaving non-conflicting changes intact.

## -s ours: closing abandoned branches cleanly
Use `-s ours` to record that a branch was "merged" without bringing in any of its changes — necessary when you've already cherry-picked its commits elsewhere and want GitHub to close the PR without re-applying the diff.

```bash
# Cherry-picks already applied to main; now close the branch record
git checkout main
git merge -s ours origin/feat/legacy-auth \
  -m "chore: record merge of legacy-auth (cherry-picked in #441)"

# The tree is identical to HEAD before the merge — verify
git diff HEAD~ HEAD --stat
# (no files changed)
```

## -X theirs: automated dependency update merges
When Renovate or Dependabot opens a lockfile-only PR, conflicting line numbers in `pnpm-lock.yaml` are almost always safe to resolve by taking the incoming side.

```bash
# GitHub Actions step: auto-merge lockfile-only dependency PRs
git merge -X theirs origin/renovate/pnpm-lockfile-update \
  -m "chore(deps): auto-merge lockfile update"
```

```yaml
# .github/workflows/auto-merge-lockfile.yml
name: Auto-merge lockfile PRs

on:
  pull_request:
    paths:
      - 'pnpm-lock.yaml'
    types: [opened, synchronize]

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: startsWith(github.head_ref, 'renovate/')
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.base_ref }}
          fetch-depth: 0

      - name: Merge with -X theirs
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI Bot"
          git fetch origin "${{ github.head_ref }}"
          git merge -X theirs "origin/${{ github.head_ref }}" \
            -m "chore(deps): auto-resolve lockfile conflicts [skip ci]"
          git push origin HEAD:"${{ github.base_ref }}"
```

## -s octopus: parallel feature integration
`-s octopus` merges more than two branches in a single commit. Git aborts if any file is modified by more than one incoming branch — it only works when branches touch disjoint sets of files. Useful for assembling a release branch from multiple independently-developed features.

```bash
# Three features each touching separate Worker subdirectories
git checkout main
git merge -s octopus \
  origin/feat/kv-cache \
  origin/feat/d1-query-builder \
  origin/feat/r2-upload-handler \
  -m "feat: assemble v2.4.0 release from parallel features"

# If octopus aborts (overlapping changes), fall back to sequential merges
```

```typescript
// scripts/octopus-check.ts — pre-flight: confirm branches are disjoint
import { execSync } from "node:child_process";

function changedFiles(branch: string): Set<string> {
  const out = execSync(`git diff --name-only main...origin/${branch}`).toString();
  return new Set(out.trim().split("\n").filter(Boolean));
}

const branches = ["feat/kv-cache", "feat/d1-query-builder", "feat/r2-upload-handler"];
const seen = new Set<string>();
for (const branch of branches) {
  const files = changedFiles(branch);
  for (const f of files) {
    if (seen.has(f)) {
      console.error(`Overlap on ${f} — octopus will fail`);
      process.exit(1);
    }
    seen.add(f);
  }
}
console.log("Branches are disjoint — safe to octopus merge");
```

## -s resolve: lightweight two-branch merges
`-s resolve` is the pre-recursive algorithm. It does not handle criss-cross merge bases or rename detection, but it is faster and sufficient for merging two branches that diverged cleanly from a single base.

```bash
# Promoting staging → production when you know there's no rename churn
git checkout production
git merge -s resolve origin/staging \
  -m "chore: promote staging to production [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
```

## Wrangler environment promotion script
```bash
#!/usr/bin/env bash
# scripts/promote.sh — promote staging to production with explicit strategy
set -euo pipefail

STRATEGY=${STRATEGY:-ort}
STRATEGY_OPTS=${STRATEGY_OPTS:-""}
SOURCE=${SOURCE:-staging}
TARGET=${TARGET:-production}

git fetch origin "$SOURCE" "$TARGET"
git checkout "$TARGET"

MERGE_FLAGS="-s $STRATEGY"
[[ -n "$STRATEGY_OPTS" ]] && MERGE_FLAGS="$MERGE_FLAGS -X $STRATEGY_OPTS"

# shellcheck disable=SC2086
git merge $MERGE_FLAGS "origin/$SOURCE" \
  -m "chore: promote $SOURCE → $TARGET [$(git rev-parse --short origin/$SOURCE)]"

wrangler deploy --env production
```

## Anti-patterns
- Using `-s ours` when you meant `-X ours` — the former silently discards the entire incoming branch; the latter only resolves conflicted hunks.
- Running `-s octopus` without a disjoint-file pre-check; the merge aborts mid-way through, leaving the index in a partially-merged state that requires `git merge --abort`.
- Passing `-X theirs` on merges that touch application logic rather than generated files — it masks real conflicts that should be reviewed.
- Forgetting that `-s resolve` has no rename detection; a file moved in one branch and edited in another will not be tracked and the edit will be silently lost.
- Mixing `-s` and `-X` flags for different algorithms (e.g., `-s octopus -X theirs`) — octopus ignores `-X` options; the combination silently uses strategy defaults.

## Gotchas
- `-s ours` records the merge in `git log` but the working tree is byte-for-byte identical to HEAD before the merge; `git diff HEAD~` will show nothing.
- `git merge -s octopus` refuses to proceed if any of the named branches has diverged beyond what a three-way merge can handle cleanly; the error message says "Merge requires file-level merging" — fall back to sequential.
- GitHub's merge button always uses the default recursive/ort strategy with no `-X` option; scripted merges via the API or CLI are the only way to control strategy.
- The `ort` strategy (default post-2.34) handles criss-cross merges differently from `recursive`; results can differ on old repos with complex merge bases — test before changing CI defaults.
- `-X patience` (a diff algorithm hint) can be combined with `-X ours`/`-X theirs` but must be passed as separate `-X` flags: `git merge -X ours -X patience`.

## Verification
```bash
# Confirm strategy used in a past merge
git show --format="%H %s" <merge-sha>
git cat-file -p <merge-sha> | grep ^parent   # two parents = normal merge
# octopus merge has 3+ parent lines

# Verify -s ours produced no tree change
git diff <merge-sha>~1 <merge-sha> --stat
# Expected: (empty — no file changes)

# Verify -X theirs resolved correctly
git diff MERGE_HEAD..HEAD -- pnpm-lock.yaml | head -20
```

## Related
- [git-rebase-vs-merge-2026.md](git-rebase-vs-merge-2026.md)
- [merge-conflict-generated-files-lockfiles-schemas.md](merge-conflict-generated-files-lockfiles-schemas.md)
- [git-conflict-resolution-2026.md](git-conflict-resolution-2026.md)

## Sources
- https://git-scm.com/docs/merge-strategies
- https://git-scm.com/docs/git-merge
- https://lore.kernel.org/git/pull.941.v2.git.1629843426.gitgitgadget@gmail.com/ (ort strategy introduction)
