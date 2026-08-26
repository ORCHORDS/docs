# git reflog: recovering accidental commit loss in Cloudflare Workers projects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A `git reset --hard` to clean up a failed wrangler deploy discards 45 minutes of Worker configuration work. An interactive rebase drops the wrong commit. A `git worktree remove --force` deletes the only checkout of a branch that was never pushed. The reflog is git's local undo log—it records every time HEAD or any branch ref moved, including resets, rebases, checkouts, and amends. In a Cloudflare Workers project where deploys are coupled to commits, recovering a lost commit before the next push is critical.

## Context

The reflog is stored per-repository in `.git/logs/`. Every `git reset`, `git commit --amend`, `git rebase`, and `git checkout` appends an entry. Entries expire (default: 90 days for reachable objects, 30 days for unreachable ones, configurable via `gc.reflogExpire`). Crucially, the reflog is **local only**—it does not push, clone, or fetch. A freshly cloned repo has no reflog history. In a worktree setup, each worktree has its own `HEAD` reflog in `.git/worktrees/<name>/logs/HEAD`.

## Reading the reflog

```bash
# Show all HEAD movements with relative timestamps
git reflog

# Show with ISO timestamps and full hash
git reflog --format='%H %gd %gs %ci'

# Show reflog for a specific branch
git reflog show feature/auth-worker-d1

# Show reflog for a specific worktree's HEAD
git reflog show worktrees/staging-env/HEAD

# Limit output and filter to resets
git reflog | grep "reset:"

# Find the last time HEAD was on a specific commit hash
git reflog | grep <partial-hash>
```

## Typical recovery scenarios in Workers projects

```bash
# Scenario 1: Accidental git reset --hard before pushing
# You ran: git reset --hard HEAD~1
# Recovery:
git reflog                      # Find the entry BEFORE the reset
# HEAD@{1}  commit: feat: add D1 binding to auth-worker
git reset --hard HEAD@{1}       # Restore to that commit

# Scenario 2: Dropped commit during interactive rebase
# The rebase re-ordered commits and one "vanished"
git reflog | grep "rebase"
# HEAD@{7}  rebase (pick): fix: correct wrangler.toml env mapping
git cherry-pick HEAD@{7}        # Re-apply just that commit

# Scenario 3: Amended commit replaced the original
# You ran: git commit --amend
git reflog | grep "amend"
# HEAD@{1}  commit (amend): fix: correct wrangler.toml env mapping
# HEAD@{2}  commit: fix: correct wrangler.toml env mapping  ← the original
git show HEAD@{2}               # Inspect the original

# Scenario 4: Worktree branch deleted locally without pushing
git reflog show worktrees/feature-rate-limit/HEAD | head -5
# Find the last commit hash of the deleted branch
git branch feature-rate-limit <hash>
```

## TypeScript reflog parser for automated recovery suggestions

```typescript
// scripts/reflog-recovery-advisor.ts
// Parses the local reflog and surfaces recent destructive operations
// with recovery commands.

import { execSync } from "node:child_process";

interface ReflogEntry {
  hash: string;
  shortHash: string;
  selector: string;  // e.g. HEAD@{3}
  action: string;    // e.g. "reset: moving to HEAD~1"
  timestamp: Date;
}

type DestructiveKind = "reset" | "amend" | "rebase" | "drop";

interface RecoverySuggestion {
  entry: ReflogEntry;
  kind: DestructiveKind;
  command: string;
  description: string;
}

function parseReflog(cwd: string): ReflogEntry[] {
  const raw = execSync(
    "git reflog --format='%H %h %gd %gs %ci'",
    { cwd, encoding: "utf8" }
  );

  return raw
    .trim()
    .split("\n")
    .map((line) => {
      const [hash, shortHash, selector, ...rest] = line.split(" ");
      // Last element is the ISO timestamp; everything in between is the action
      const timestamp = new Date(rest.at(-1)!);
      const action = rest.slice(0, -1).join(" ");
      return { hash, shortHash, selector, action, timestamp };
    });
}

function buildRecoverySuggestions(
  entries: ReflogEntry[]
): RecoverySuggestion[] {
  const suggestions: RecoverySuggestion[] = [];

  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const { action, selector, hash } = entry;

    if (/^reset: moving to/.test(action)) {
      // The commit BEFORE the reset is the recovery target
      const before = entries[i + 1];
      if (before) {
        suggestions.push({
          entry,
          kind: "reset",
          command: `git reset --hard ${before.selector}`,
          description: `Undo reset; restore to ${before.shortHash} (${before.action})`,
        });
      }
    } else if (/^commit \(amend\)/.test(action)) {
      const original = entries[i + 1];
      if (original) {
        suggestions.push({
          entry,
          kind: "amend",
          command: `git show ${original.selector}  # inspect\ngit reset --soft ${original.selector}  # undo amend`,
          description: `Undo amend; original commit is ${original.shortHash}`,
        });
      }
    } else if (/^rebase \(squash\)|^rebase \(drop\)/.test(action)) {
      suggestions.push({
        entry,
        kind: "drop",
        command: `git cherry-pick ${hash}`,
        description: `Re-apply dropped/squashed commit ${entry.shortHash}`,
      });
    }
  }

  return suggestions;
}

function main(): void {
  const entries = parseReflog(process.cwd());
  const recent = entries.slice(0, 20); // Last 20 HEAD movements
  const suggestions = buildRecoverySuggestions(recent);

  if (suggestions.length === 0) {
    console.log("No recent destructive operations detected in reflog.");
    return;
  }

  console.log(
    `Found ${suggestions.length} recoverable operation(s):\n`
  );
  for (const s of suggestions) {
    console.log(`[${s.kind.toUpperCase()}] ${s.description}`);
    console.log(`  Recovery:\n    ${s.command.replace(/\n/g, "\n    ")}`);
    console.log();
  }
}

main();
```

## Recovering from a force-push that overwrote remote work

```typescript
// scripts/find-lost-remote-commits.ts
// When a force-push loses commits on the remote, the reflog may still hold them locally.

import { execSync } from "node:child_process";

interface LostCommit {
  hash: string;
  subject: string;
  author: string;
  date: string;
}

function findCommitsNotOnRemote(
  branch: string,
  remote = "origin"
): LostCommit[] {
  // Commits reachable from reflog but not from the current remote branch
  const remoteRef = `${remote}/${branch}`;

  const reflogHashes = execSync(
    `git reflog --format="%H" show ${branch}`,
    { encoding: "utf8" }
  )
    .trim()
    .split("\n")
    .filter(Boolean);

  const lost: LostCommit[] = [];
  for (const hash of reflogHashes) {
    try {
      // If this commit is an ancestor of the remote, it wasn't lost
      execSync(
        `git merge-base --is-ancestor ${hash} ${remoteRef}`,
        { stdio: "pipe" }
      );
    } catch {
      // Not an ancestor = potentially lost
      const info = execSync(
        `git log -1 --format="%H|%s|%an|%ci" ${hash}`,
        { encoding: "utf8" }
      ).trim();
      const [h, subject, author, date] = info.split("|");
      lost.push({ hash: h, subject, author, date });
    }
  }

  // Deduplicate by hash
  return [...new Map(lost.map((c) => [c.hash, c])).values()];
}

const [, , branch = "main"] = process.argv;
const lost = findCommitsNotOnRemote(branch);

if (lost.length === 0) {
  console.log(`No locally-held commits missing from origin/${branch}`);
} else {
  console.log(`Found ${lost.length} commit(s) not on origin/${branch}:`);
  for (const c of lost) {
    console.log(`  ${c.hash.slice(0, 8)} ${c.date} ${c.author}: ${c.subject}`);
  }
  console.log("\nTo recover the most recent one:");
  console.log(`  git cherry-pick ${lost[0].hash}`);
}
```

## Anti-patterns

- **Running `git gc --prune=now` immediately after a botched reset** — aggressive garbage collection permanently deletes unreachable objects before you can recover them.
- **Increasing `gc.reflogExpire` to "never" on CI runners** — CI repos clone fresh; the reflog on a runner is only valuable during that run. Inflating it wastes disk.
- **Trusting the reflog on shallow clones** — `git clone --depth 1` produces a repo with a minimal reflog; recovery options are limited.
- **Confusing `HEAD@{n}` (reflog) with `HEAD~n` (ancestry)** — `HEAD@{3}` is the fourth most-recent position of HEAD regardless of commit parentage; `HEAD~3` is three commits up the first-parent chain.

## Gotchas

- Reflog entries in worktrees live in `.git/worktrees/<name>/logs/HEAD`, not in `.git/logs/HEAD`. `git reflog` inside a worktree shows the worktree's own HEAD log automatically.
- After `git worktree remove`, the worktree's `.git/worktrees/<name>/` directory is deleted, taking its HEAD reflog with it. Always push or stash before removing a worktree.
- `git reflog expire --expire=now --all` + `git gc --prune=now` is the **only** reliable way to permanently discard reflog entries; a plain `git gc` does not prune within the default expiry windows.
- The reflog does not record the working tree state, only commit hashes and ref positions. Uncommitted changes lost to `git reset --hard` are unrecoverable from the reflog alone (use `git fsck --lost-found` for dangling blobs).

## Verification

```bash
# Simulate a recovery drill
git checkout -b recovery-test
echo "test" >> workers/api/src/index.ts
git commit -am "test: reflog recovery drill"
git reset --hard HEAD~1
# Now recover:
git reflog | head -5
git reset --hard HEAD@{1}
git log --oneline -2  # Should show the "drill" commit restored

# Confirm worktree reflog path
ls .git/worktrees/*/logs/HEAD 2>/dev/null || echo "No worktrees with logs"

# Run the recovery advisor
pnpm tsx scripts/reflog-recovery-advisor.ts
```

## Related

- `git-reflog-2026.md` — general reflog reference
- `git-worktree-remove-cleanup-automation.md` — safe worktree removal
- `git-reset-and-restore-patterns.md` — staged and unstaged undos
- `git-fsck-object-integrity-workers-repo-health.md` — recovering dangling blobs
- `rollback-strategy.md` — production rollback beyond git history

## Sources

- Git documentation: `git help reflog`, `git help gc`
- `git help worktree` — worktree-specific reflog location
- Pro Git book: Chapter 10.5 "Maintenance and Data Recovery" (git-scm.com/book)
