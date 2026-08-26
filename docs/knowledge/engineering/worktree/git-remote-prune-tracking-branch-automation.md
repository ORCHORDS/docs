# Git Remote Prune Tracking Branch Automation

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Workers monorepo with an active team accumulates hundreds of stale remote-tracking refs (e.g. `refs/remotes/origin/feature/old-auth-refactor`) long after the corresponding remote branches are merged and deleted on GitHub. `git branch -r` lists these phantom branches, `git log --remotes` includes them in graph output, and completion scripts suggest them to engineers. The repo's local `.git/packed-refs` grows unbounded.

## Context
Remote-tracking refs (`refs/remotes/<remote>/<branch>`) are local copies of what a remote reported the last time you fetched. When a branch is deleted on the remote (e.g. after a PR merge), GitHub's side of that ref disappears — but your local copy persists until you explicitly prune it. This is distinct from the *stale branch cleanup* problem addressed by the GitHub Actions / GitHub API approach: pruning is a pure local-git operation and does not require GitHub credentials. It should be automated for every developer's machine and every CI runner.

## Manual prune commands

```bash
# Prune all stale remote-tracking refs for origin
git remote prune origin

# Prune while fetching (most common daily use)
git fetch --prune origin

# Equivalent shorthand
git fetch -p origin

# Fetch + prune ALL remotes
git fetch --prune --all

# Dry-run: see what would be pruned without touching refs
git remote prune origin --dry-run
git fetch --prune --dry-run origin

# Show which remote-tracking refs currently exist
git branch -r
git for-each-ref --format='%(refname:short) %(upstream:track)' refs/remotes/origin/
```

## Making prune automatic via git config

```bash
# Per-repository: auto-prune on every fetch
git config fetch.prune true

# User-global: apply to all repositories (recommended for developer machines)
git config --global fetch.prune true

# User-global: also prune tags no longer on the remote
git config --global fetch.pruneTags true

# Verify
git config --global --get fetch.prune   # → true
```

```ini
# ~/.gitconfig (result of the global commands above)
[fetch]
    prune = true
    pruneTags = true
```

## Finding local branches that have no upstream

After pruning remote-tracking refs, local branches that were tracking now-deleted remote branches are left with a "gone" upstream status.

```bash
# List local branches whose upstream tracking branch no longer exists
git branch -vv | grep ': gone]'
# Example output:
#   feature/old-auth   a1b2c3d [origin/feature/old-auth: gone] chore: cleanup

# Extract just the branch names
git branch -vv \
  | awk '/: gone]/{print $1}' \
  | grep -v '^\*'   # skip currently checked-out branch

# Delete all gone-upstream branches (non-destructive: only gone ones)
git branch -vv \
  | awk '/: gone]/{print $1}' \
  | grep -v '^\*' \
  | xargs -r git branch -d   # -d: only merged; use -D to force
```

## Automation script: prune + clean orphaned local branches

```bash
#!/usr/bin/env bash
# scripts/git-prune-and-clean.sh
# Run weekly or on post-merge to keep the local repo tidy.
set -euo pipefail

REMOTE="${1:-origin}"

echo "==> Fetching and pruning stale remote-tracking refs for ${REMOTE}..."
git fetch --prune "${REMOTE}"

echo "==> Finding local branches with gone upstream..."
GONE_BRANCHES=$(git branch -vv \
  | awk '/: gone]/{print $1}' \
  | grep -v '^\*' || true)

if [[ -z "$GONE_BRANCHES" ]]; then
  echo "No orphaned local branches found."
  exit 0
fi

echo "Found the following orphaned branches:"
echo "$GONE_BRANCHES"

read -rp "Delete these branches? [y/N] " CONFIRM
if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "$GONE_BRANCHES" | xargs git branch -d
  echo "Deleted."
else
  echo "Skipped."
fi
```

## GitHub Actions: prune in CI to prevent stale ref accumulation

CI runners are ephemeral — pruning on the runner itself is unnecessary. However, a scheduled workflow that reports stale tracking refs helps catch misconfigured non-ephemeral self-hosted runners.

```yaml
# .github/workflows/repo-hygiene.yml
name: Repo Hygiene
on:
  schedule:
    - cron: '0 6 * * 1'   # every Monday 06:00 UTC
  workflow_dispatch:

jobs:
  prune-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - name: Prune stale remote-tracking refs
        run: git fetch --prune origin

      - name: Report gone-upstream local branches
        run: |
          GONE=$(git branch -vv | awk '/: gone]/{print $1}' | grep -v '^\*' || true)
          if [[ -n "$GONE" ]]; then
            echo "## Orphaned local branches (upstream gone):"
            echo "$GONE"
          else
            echo "No orphaned branches."
          fi

      - name: Count remote-tracking refs
        run: |
          COUNT=$(git for-each-ref --count refs/remotes/origin/ 2>/dev/null || echo 0)
          echo "Remote-tracking refs remaining after prune: ${COUNT}"
```

## TypeScript: programmatic prune check in a pre-flight script

```typescript
// scripts/check-stale-tracking.ts
import { execSync } from "node:child_process";

interface StaleBranch {
  name: string;
  lastCommit: string;
  upstream: string;
}

export function findStaleBranches(remote = "origin"): StaleBranch[] {
  // Prune first to ensure we're working with current data
  execSync(`git fetch --prune ${remote}`, { stdio: "inherit" });

  const output = execSync("git branch -vv").toString();
  const stale: StaleBranch[] = [];

  for (const line of output.split("\n")) {
    const match = line.match(/^\s*(\S+)\s+([0-9a-f]+)\s+\[(\S+): gone\]/);
    if (match) {
      stale.push({
        name: match[1],
        lastCommit: match[2],
        upstream: match[3],
      });
    }
  }
  return stale;
}

export function deleteStaleBranches(
  branches: StaleBranch[],
  force = false
): void {
  const flag = force ? "-D" : "-d";
  for (const branch of branches) {
    console.log(`Deleting orphaned branch: ${branch.name}`);
    execSync(`git branch ${flag} ${branch.name}`);
  }
}

// Main
const stale = findStaleBranches();
console.log(`Found ${stale.length} orphaned local branch(es).`);
if (stale.length > 0) {
  console.table(stale);
  deleteStaleBranches(stale);
}
```

## Git hook: post-merge prune

```bash
# .git/hooks/post-merge  (or managed via lefthook / husky)
#!/usr/bin/env bash
# Automatically prune after every merge (including PR merges via git pull)
git fetch --prune origin --quiet
echo "[git hook] Pruned stale remote-tracking refs."
```

```yaml
# lefthook.yml integration
post-merge:
  commands:
    prune-remotes:
      run: git fetch --prune origin --quiet && echo "Pruned remote-tracking refs"
```

## Packed-refs size before and after

```bash
# Before: count stale refs in packed-refs
grep -c 'refs/remotes/origin/' .git/packed-refs

# After pruning, check the file size difference
ls -lh .git/packed-refs
git remote prune origin
ls -lh .git/packed-refs

# Force repack of refs to reduce file size
git pack-refs --all
```

## Anti-patterns
- Relying on `git branch -d` to clean up without first fetching `--prune` — the local branch may delete fine but the remote-tracking ref (`refs/remotes/origin/feature/x`) stays, continuing to pollute `git log --remotes` output.
- Setting `fetch.prune = true` globally and assuming it applies to `git pull` as well — `git pull` respects `fetch.prune` for its internal fetch, so this does work, but verify with `git config pull.rebase` to ensure the full fetch happens.
- Using `-D` (force delete) in automated scripts without checking whether the branch is fully merged — this can silently discard in-progress work if the upstream tracking ref was gone for another reason.
- Running prune on a narrow shallow clone that fetched with a limited refspec — only refs included in the fetch refspec are pruned; other remote-tracking refs are left untouched.
- Conflating `git remote prune` with `git gc` — pruning removes dangling refs but does not reclaim disk space from loose objects; run `git gc --prune=now` or `git maintenance run` separately.

## Gotchas
- `git fetch --prune` only prunes refs that were fetched by the configured fetch refspec; if you added a custom namespace refspec (e.g. `+refs/pull/*/head:refs/remotes/origin/pr/*`), those refs are also subject to pruning when their remote counterpart disappears.
- On GitHub, branch deletion after a PR merge is instantaneous, but the ref may still appear for a few seconds due to cache lag — automated prune scripts run immediately after merge may see a stale ref transiently.
- `git fetch.pruneTags = true` requires Git 2.17+; it removes local tags that no longer exist on the remote, which can surprise developers who created local-only tags.
- The `gone` marker in `git branch -vv` output only appears after a `git fetch --prune` has run; if the upstream branch was deleted but no prune has occurred, the output shows `behind N` instead.
- `git remote prune origin --dry-run` and `git fetch --prune --dry-run origin` are not identical: the former reports what `remote prune` would remove based on current remote state; the latter also checks what fetch would update before pruning.

## Verification
```bash
# Confirm fetch.prune is set
git config --get fetch.prune   # → true

# Confirm prune ran (zero stale refs)
git fetch --prune origin
git branch -r | wc -l          # should decrease if stale refs existed

# Confirm no gone-upstream local branches remain
git branch -vv | grep ': gone]' || echo "No orphaned branches."

# Confirm packed-refs is compact
wc -l .git/packed-refs
```

## Related
- [stale-branch-cleanup-github-actions.md](stale-branch-cleanup-github-actions.md)
- [git-maintenance-scheduled-background-pack-optimization.md](git-maintenance-scheduled-background-pack-optimization.md)
- [git-background-maintenance-for-large-worktrees.md](git-background-maintenance-for-large-worktrees.md)
- [git-foreachref-startafter-pagination.md](git-foreachref-startafter-pagination.md)
- [git-reflog-2026.md](git-reflog-2026.md)

## Sources
- https://git-scm.com/docs/git-fetch#Documentation/git-fetch.txt---prune
- https://git-scm.com/docs/git-remote#Documentation/git-remote.txt-empruneem
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-fetchprune
- https://stackoverflow.com/questions/7726949/remove-tracking-branches-no-longer-on-remote
