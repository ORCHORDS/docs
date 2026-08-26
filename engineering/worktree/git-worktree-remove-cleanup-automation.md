# git worktree Remove Cleanup Automation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After weeks of parallel development your repository accumulates stale worktrees: feature branches whose PRs merged months ago, experiment trees that were abandoned, and hotfix trees that are locked because a process crashed. Running `git worktree list` shows a growing list of paths, some of which no longer exist on disk. Wrangler's `.wrangler/state/` directories inside those trees consume gigabytes. You want an automated, safe routine that prunes merged-branch worktrees and cleans up their Wrangler state without touching active development trees.

## Context

`git worktree` tracks each additional working tree in `.git/worktrees/<name>/`. A worktree has three states relevant to cleanup:

1. **Prunable**: the directory no longer exists on disk. `git worktree prune` removes the metadata automatically.
2. **Locked**: explicitly locked with `git worktree lock`. Prune skips these.
3. **Active**: directory exists and the branch has not merged. Must not be removed.

The safe sequence is: prune missing-directory entries first, then identify trees whose branch has merged into the integration branch, then remove those. A GitHub Actions workflow or a local cron job can automate this sequence after PR merges.

---

## Step 1 — Prune Stale Metadata for Missing Directories

```bash
# Remove .git/worktrees/<name>/ entries for paths that no longer exist on disk
git worktree prune --verbose

# Dry-run first to see what would be pruned
git worktree prune --dry-run --verbose
```

This is always safe: it only removes internal metadata, never touches any file on disk. Run it unconditionally at the start of any cleanup script.

---

## Step 2 — Identify Merged-Branch Worktrees

```bash
#!/usr/bin/env bash
# scripts/list-merged-worktrees.sh
set -euo pipefail

INTEGRATION_BRANCH="${1:-main}"
git fetch --prune origin

# Get all branches already merged into the integration branch
MERGED_BRANCHES=$(git branch --merged "origin/$INTEGRATION_BRANCH" --format "%(refname:short)")

# Walk all worktrees and find those whose branch is in the merged set
git worktree list --porcelain | awk '
  /^worktree / { path=$2 }
  /^branch /   { branch=$2; sub("refs/heads/","",branch) }
  /^$/          { print path, branch }
' | while read -r WPATH BRANCH; do
  if echo "$MERGED_BRANCHES" | grep -qx "$BRANCH"; then
    echo "MERGED: $WPATH  ($BRANCH)"
  fi
done
```

Run it to preview which trees would be removed:

```bash
bash scripts/list-merged-worktrees.sh main
# MERGED: /path/to/project  (feature/login)
# MERGED: /path/to/project       (fix/auth-token-expiry)
```

---

## Step 3 — Remove Worktrees Safely

```bash
#!/usr/bin/env bash
# scripts/cleanup-merged-worktrees.sh
set -euo pipefail

INTEGRATION_BRANCH="${1:-main}"
DRY_RUN="${DRY_RUN:-false}"

git fetch --prune origin
git worktree prune --verbose

MERGED_BRANCHES=$(git branch --merged "origin/$INTEGRATION_BRANCH" --format "%(refname:short)")

git worktree list --porcelain | awk '
  /^worktree / { path=$2 }
  /^branch /   { branch=$2; sub("refs/heads/","",branch) }
  /^$/          { print path, branch }
' | while read -r WPATH BRANCH; do
  # Never remove the main worktree (empty BRANCH or HEAD detached entries)
  [[ -z "$BRANCH" ]] && continue

  if echo "$MERGED_BRANCHES" | grep -qx "$BRANCH"; then
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[DRY RUN] Would remove: $WPATH ($BRANCH)"
    else
      echo "Removing worktree: $WPATH ($BRANCH)"
      git worktree remove --force "$WPATH"
      # Delete the now-merged local branch
      git branch -d "$BRANCH" 2>/dev/null || true
    fi
  fi
done
```

Dry-run first:

```bash
DRY_RUN=true bash scripts/cleanup-merged-worktrees.sh main
# [DRY RUN] Would remove: /path/to/project (feature/login)
```

Execute cleanup:

```bash
bash scripts/cleanup-merged-worktrees.sh main
```

---

## GitHub Actions Automation

Trigger cleanup automatically after PRs merge into `main`:

```yaml
# .github/workflows/worktree-cleanup.yml
name: Worktree Cleanup Reminder

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  notify-cleanup:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Comment merged branch name
        uses: actions/github-script@v7
        with:
          script: |
            const branch = context.payload.pull_request.head.ref;
            await github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.payload.pull_request.number,
              body: `Branch \`${branch}\` merged. Run cleanup locally:\n\`\`\`bash\nbash scripts/cleanup-merged-worktrees.sh main\n\`\`\``
            });
```

For fully automated local cleanup via a git hook, add a `post-merge` hook to the primary worktree:

```bash
#!/usr/bin/env bash
# .git/hooks/post-merge
set -euo pipefail
echo "[post-merge] Pruning stale worktrees..."
git worktree prune --verbose
bash "$(git rev-parse --show-toplevel)/scripts/cleanup-merged-worktrees.sh" main
```

```bash
chmod +x .git/hooks/post-merge
```

---

## Cleaning Up Wrangler State

Each worktree accumulates `.wrangler/state/` (local D1 databases, KV, R2 data). These are not removed by `git worktree remove` because they live inside the worktree directory and are `.gitignore`d. Before or after removal, report their size:

```bash
#!/usr/bin/env bash
# scripts/wrangler-state-audit.sh
git worktree list --porcelain | awk '/^worktree / {print $2}' | while read -r WPATH; do
  STATE_DIR="$WPATH/.wrangler/state"
  if [[ -d "$STATE_DIR" ]]; then
    SIZE=$(du -sh "$STATE_DIR" | cut -f1)
    echo "$SIZE  $STATE_DIR"
  fi
done
```

`git worktree remove --force` deletes the entire directory tree including `.wrangler/state/`, so no separate cleanup is needed as long as you use `remove` rather than a bare `rm -rf`.

---

## Anti-patterns

- **Using `rm -rf` on a worktree directory without `git worktree remove`**: this leaves orphaned metadata in `.git/worktrees/` and causes `git worktree list` to show stale entries indefinitely until `git worktree prune` runs.
- **Removing the main worktree**: `git worktree remove` refuses to remove the main (primary) worktree. Scripts must explicitly skip paths equal to the output of `git rev-parse --show-toplevel` from the primary tree.
- **Skipping `--force` on worktrees with untracked files**: `git worktree remove` without `--force` fails if the worktree has untracked or modified files. Always run a dry-run listing first and confirm the tree is safe to discard.
- **Removing locked worktrees**: a worktree locked with `git worktree lock` should not be removed without first running `git worktree unlock`. Locked trees signal that another process (or person) intends to keep them.

---

## Gotchas

- `git worktree list --porcelain` outputs one blank line between records. The awk parsing above relies on this; do not add `--no-optional-locks` which changes the format.
- `git branch --merged` compares against the local copy of the branch. Always run `git fetch --prune origin` first to update remote-tracking refs.
- A detached-HEAD worktree (from `git worktree add --detach`) has no branch line in `--porcelain` output. The script above skips those correctly with `[[ -z "$BRANCH" ]] && continue`.
- On macOS, `git worktree remove --force` may fail if any file in the directory is open in Finder or another process. Use `lsof +D <path>` to identify open file handles.

---

## Verification

```bash
# Before cleanup
git worktree list

# Run prune
git worktree prune --verbose

# Dry-run merged detection
DRY_RUN=true bash scripts/cleanup-merged-worktrees.sh main

# After cleanup
git worktree list
# Should show only the main worktree and any still-active trees

# Confirm no orphaned metadata
ls .git/worktrees/
```

---

## Related

- `git-worktree-2026.md`
- `git-worktree-lockfile-isolation.md`
- `git-worktree-porcelain-nul-safe-inventory-automation.md`
- `git-fetch-atomic-ref-update-contract.md`
- `stale-branch-cleanup-github-actions.md`

---

## Sources

- git-scm.com/docs/git-worktree
- git-scm.com/docs/git-branch
- docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request
- developers.cloudflare.com/workers/wrangler/commands/#dev
