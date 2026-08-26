# Automating Git Worktree Cleanup: Prune, Detect, and Cron

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Over weeks of parallel development, a repository accumulates stale worktree entries: deleted directories whose administrative metadata still lives in `.git/worktrees/`, merged branches that are still checked out, and CI runner leftovers that were killed mid-job. These stale entries cause `git worktree list` noise, confuse tooling, and waste inode entries. This article covers `git worktree prune`, a porcelain-based stale detector, a cleanup shell script, a cron job, and a CI post-job hook.

## Context

- Git 2.15+
- Linux/macOS developer machines and CI runners
- Shell: bash
- CI: GitHub Actions (post-job step)

---

## Section 1: Understanding Stale Worktrees

```bash
# A worktree becomes stale when:
# 1. Its directory was deleted with rm -rf instead of `git worktree remove`
# 2. A CI job was killed before teardown ran
# 3. The branch was deleted on the remote but the local worktree remains

# See all worktrees (including stale ones marked "prunable")
git worktree list --porcelain
# worktree /path/to/project
# HEAD <commit-sha>
# branch refs/heads/main
#
# worktree /path/to/project   <-- directory deleted manually
# HEAD <commit-sha>
# branch refs/heads/feature/teammate-widget
# prunable gitdir file points to non-existent location

# The "prunable" annotation tells you Git already knows it's stale
# git worktree prune will remove the .git/worktrees/<name>/ metadata
git worktree prune --dry-run
# Removing worktrees/myrepo--pr-456: gitdir file points to non-existent location

git worktree prune
# Permanently removes the stale metadata
```

---

## Section 2: Detecting Stale Worktrees via Porcelain Output

```bash
#!/usr/bin/env bash
# scripts/worktree-detect-stale.sh
# Prints stale worktrees: directories that no longer exist on disk,
# or whose branch has been deleted on origin.

set -euo pipefail

echo "=== Detecting stale worktrees ==="

STALE_COUNT=0

# Parse porcelain output into records separated by blank lines
# Fields: worktree, HEAD, branch, (optional) prunable or bare
git worktree list --porcelain | awk '
  /^worktree / { wt=$2 }
  /^HEAD /     { sha=$2 }
  /^branch /   { br=$2 }
  /^$/         { if (wt != "") print wt "|" sha "|" br; wt=""; sha=""; br="" }
  END          { if (wt != "") print wt "|" sha "|" br }
' | while IFS='|' read -r wt sha br; do
  STALE=0
  REASON=""

  # Check 1: directory no longer exists
  if [ ! -d "$wt" ]; then
    STALE=1
    REASON="directory missing"
  fi

  # Check 2: branch no longer exists on origin (skip for bare/main)
  if [ -n "$br" ] && [ "$br" != "refs/heads/main" ] && [ "$br" != "refs/heads/master" ]; then
    SHORT_BR="${br#refs/heads/}"
    if ! git ls-remote --exit-code origin "refs/heads/${SHORT_BR}" >/dev/null 2>&1; then
      STALE=1
      REASON="${REASON:+${REASON}, }branch deleted on origin"
    fi
  fi

  if [ "$STALE" -eq 1 ]; then
    echo "STALE: $wt (${REASON})"
    STALE_COUNT=$((STALE_COUNT + 1))
  else
    echo "OK:    $wt"
  fi
done

echo ""
echo "Run 'git worktree prune' to remove stale metadata."
```

---

## Section 3: Cleanup Shell Script

```bash
#!/usr/bin/env bash
# scripts/worktree-cleanup.sh
# Removes stale worktrees safely and prunes metadata
# Options:
#   --dry-run   Print what would be done without doing it
#   --force     Remove worktrees with uncommitted changes

set -euo pipefail

DRY_RUN=0
FORCE_FLAG=""

for arg in "$@"; do
  case $arg in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE_FLAG="--force" ;;
  esac
done

REPO_ROOT=$(git rev-parse --show-toplevel)
echo "=== Worktree cleanup for $REPO_ROOT ==="

# Step 1: Remove worktrees whose directory no longer exists on disk
git worktree list --porcelain | awk '
  /^worktree / { wt=$2 }
  /^$/         { if (wt != "") print wt; wt="" }
  END          { if (wt != "") print wt }
' | tail -n +2 | while read -r wt; do  # tail skips the main worktree
  if [ ! -d "$wt" ]; then
    echo "Removing stale worktree (missing dir): $wt"
    if [ "$DRY_RUN" -eq 0 ]; then
      git worktree remove $FORCE_FLAG "$wt" 2>/dev/null || true
    fi
  fi
done

# Step 2: Remove worktrees whose branch is fully merged into main
git fetch origin main --quiet
git worktree list --porcelain | awk '
  /^worktree / { wt=$2 }
  /^branch /   { br=$2 }
  /^$/         { if (wt != "" && br != "") print wt "|" br; wt=""; br="" }
  END          { if (wt != "" && br != "") print wt "|" br }
' | tail -n +2 | while IFS='|' read -r wt br; do
  SHORT_BR="${br#refs/heads/}"
  # Check if branch tip is an ancestor of origin/main (i.e., merged)
  if git merge-base --is-ancestor "$br" origin/main 2>/dev/null; then
    echo "Removing merged-branch worktree: $wt (branch: $SHORT_BR)"
    if [ "$DRY_RUN" -eq 0 ]; then
      git worktree remove $FORCE_FLAG "$wt" 2>/dev/null || true
    fi
  fi
done

# Step 3: Prune metadata
echo "Running git worktree prune..."
if [ "$DRY_RUN" -eq 1 ]; then
  git worktree prune --dry-run --verbose
else
  git worktree prune --verbose
fi

echo ""
echo "=== Remaining worktrees ==="
git worktree list
```

---

## Section 4: Cron Job Setup

```bash
# Add to crontab: runs cleanup daily at 08:00, logs to ~/logs/worktree-cleanup.log
# crontab -e

# m  h  dom mon dow  command
0    8  *   *   *    /usr/bin/bash /path/to/project \
                       >> /path/to/project 2>&1

# Create log directory
mkdir -p ~/logs

# Test the cron entry works as non-login shell (cron has a stripped PATH)
bash --norc --noprofile /path/to/project --dry-run

# To verify cron is running, check syslog
grep CRON /var/log/syslog | tail -20
# or on systemd systems:
journalctl -u cron --since "today" | grep worktree-cleanup
```

---

## Section 5: CI Post-Job Cleanup Hook (GitHub Actions)

```yaml
# .github/workflows/test.yml  (relevant excerpt)
jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup shard worktrees
        run: bash scripts/ci-worktree-setup.sh 4 ${{ github.sha }}

      - name: Run tests
        run: bash scripts/ci-run-shards.sh 4

      # Post-job cleanup — runs even if previous steps fail
      - name: Cleanup worktrees
        if: always()
        run: |
          bash scripts/worktree-cleanup.sh --force

      - name: Prune stale worktree metadata
        if: always()
        run: git worktree prune --verbose
```

---

## Section 6: TypeScript Cleanup Utility

```typescript
#!/usr/bin/env ts-node
// scripts/worktree-cleanup.ts
// Programmatic cleanup: removes missing-directory worktrees and prunes

import { execSync } from 'child_process';
import * as fs from 'fs';

const dryRun = process.argv.includes('--dry-run');
const force = process.argv.includes('--force') ? '--force' : '';

const run = (cmd: string): string => {
  return execSync(cmd).toString().trim();
};

const safeRun = (cmd: string): void => {
  if (dryRun) {
    console.log(`[dry-run] ${cmd}`);
    return;
  }
  try {
    execSync(cmd, { stdio: 'inherit' });
  } catch {
    // Non-zero exit — log but continue
    console.warn(`Command failed (continuing): ${cmd}`);
  }
};

interface Worktree {
  path: string;
  head: string;
  branch: string;
  prunable: boolean;
}

function parseWorktrees(): Worktree[] {
  const raw = run('git worktree list --porcelain');
  const worktrees: Worktree[] = [];
  let current: Partial<Worktree> = {};

  for (const line of raw.split('\n')) {
    if (line.startsWith('worktree ')) {
      current = { path: line.slice('worktree '.length), prunable: false };
    } else if (line.startsWith('HEAD ')) {
      current.head = line.slice('HEAD '.length);
    } else if (line.startsWith('branch ')) {
      current.branch = line.slice('branch '.length);
    } else if (line.includes('prunable')) {
      current.prunable = true;
    } else if (line === '') {
      if (current.path) worktrees.push(current as Worktree);
      current = {};
    }
  }
  if (current.path) worktrees.push(current as Worktree);
  return worktrees;
}

const worktrees = parseWorktrees();
const [mainWorktree, ...linkedWorktrees] = worktrees;

console.log(`Main worktree: ${mainWorktree.path}`);
console.log(`Linked worktrees: ${linkedWorktrees.length}`);

for (const wt of linkedWorktrees) {
  const missing = !fs.existsSync(wt.path);
  const prunable = wt.prunable;

  if (missing || prunable) {
    const reason = [missing && 'directory missing', prunable && 'marked prunable']
      .filter(Boolean)
      .join(', ');
    console.log(`Removing: ${wt.path} (${reason})`);
    safeRun(`git worktree remove ${force} "${wt.path}"`);
  } else {
    console.log(`Keeping: ${wt.path}`);
  }
}

console.log('Pruning metadata...');
safeRun(`git worktree prune${dryRun ? ' --dry-run' : ''} --verbose`);

console.log('\nFinal worktree list:');
console.log(run('git worktree list'));
```

---

## Anti-patterns

- Do not `rm -rf` a worktree directory without running `git worktree remove` first — the `.git/worktrees/<name>/` metadata will remain and corrupt `git worktree list` output.
- Do not run `git worktree prune` with a very short `--expire` value (e.g., `--expire=now`) in an active CI environment where ephemeral worktrees are in use — you may prune live worktrees whose directories are briefly absent during disk operations.
- Do not rely solely on `--dry-run` output without also running the real command in a test repo — prune's dry-run output occasionally lists fewer entries than the real run removes (edge case with concurrent gc).
- Do not cron-job cleanup with `--force` on a shared developer machine where colleagues may have uncommitted work in their worktrees.

## Gotchas

- **`git worktree remove` vs `git worktree prune`**: `remove` deletes the working tree directory AND the metadata. `prune` only removes metadata for worktrees whose directories are already gone. Use `remove` for live worktrees; `prune` for orphaned metadata.
- **`--expire` flag on prune**: by default, `git worktree prune` waits 3 months before removing metadata for missing directories (safety window). Override with `--expire=now` to prune immediately, or `--expire=1.week.ago` for a shorter window.
- **Locked worktrees**: `git worktree lock` marks a worktree as protected from pruning. Check with `git worktree list --porcelain | grep locked` before wondering why prune skips an entry.
- **Bare repositories**: bare repos can have worktrees too. The main "worktree" entry will have `bare` instead of `branch` in porcelain output — skip it in cleanup scripts.

## Verification

```bash
# Create a stale worktree artificially
git worktree add /tmp/stale-test origin/main
rm -rf /tmp/stale-test

# Confirm it shows as prunable
git worktree list --porcelain | grep -A4 stale-test

# Prune and verify
git worktree prune --verbose
git worktree list | grep stale-test && echo "FAIL: still listed" || echo "PASS: removed"

# Verify cleanup script dry-run
bash scripts/worktree-cleanup.sh --dry-run
```

## Related

- `documentation/categories/worktree/git-worktree-ci-parallel-test-suites.md`
- `documentation/categories/worktree/git-worktree-release-branch-hotfix-parallel.md`
- `documentation/categories/worktree/git-worktree-stash-vs-worktree-comparison.md`

## Sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-worktree#Documentation/git-worktree.txt---expirelttimegt
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstepsif
