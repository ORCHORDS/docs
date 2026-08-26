# git stash + Worktree Context Switching for Workers Development

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You are mid-way through a feature on `feat/rate-limiting` when a P1 lands: a production
Worker is returning 500s and you need to patch `workers/api` immediately. You have two
choices: stash your changes and switch branches in the same directory, or keep your changes
in place while doing the hotfix in a separate worktree. Most engineers reflexively reach for
`git stash` but the right choice depends on what your changes touch. This article maps the
decision and documents the TypeScript tooling to automate it cleanly in a monorepo.

## Context

`git stash` saves your working tree and index to a stack, checks out a clean HEAD, and lets
you switch branches. It is fast and stateless between sessions, but stashes are local-only,
named poorly by default, and can be lost during garbage collection if they are never
applied.

`git worktree add` creates a second checkout of the repo at a separate filesystem path. Both
the main worktree and the linked worktree track a branch independently. The linked worktree
shares the `.git` object store, so no extra disk space is used for object data — only the
working files differ.

The optimal pattern in a Cloudflare Workers monorepo: use **worktrees for parallel work**
(two features or a feature + hotfix coexisting), and **stash for ephemeral context saves**
within a single worktree (e.g., pausing to check something in another file).

## Decision Script: Stash vs. Worktree

```typescript
// scripts/context-switch.ts
import { execSync } from "node:child_process";
import path from "node:path";

interface SwitchOptions {
  targetBranch: string;
  reason?: string;
}

function hasWipChanges(): boolean {
  const status = execSync("git status --porcelain").toString().trim();
  return status.length > 0;
}

function countDirtyWorkerPackages(): number {
  const status = execSync("git status --porcelain").toString().trim();
  if (!status) return 0;
  const changedFiles = status.split("\n").map((l) => l.slice(3));
  const workerDirs = new Set(
    changedFiles
      .filter((f) => f.startsWith("workers/"))
      .map((f) => f.split("/").slice(0, 2).join("/"))
  );
  return workerDirs.size;
}

function recommendStrategy(opts: SwitchOptions): "stash" | "worktree" {
  const dirty = hasWipChanges();
  const workerCount = countDirtyWorkerPackages();

  if (!dirty) return "stash"; // nothing to save, branch switch is free
  if (workerCount >= 2) return "worktree"; // multi-package WIP — keep it isolated
  if (opts.reason === "hotfix") return "worktree"; // hotfixes deserve clean isolation
  return "stash";
}

function stashAndSwitch(branch: string, label: string): void {
  const timestamp = new Date().toISOString().slice(0, 16);
  execSync(`git stash push -u -m "wip: ${label} @ ${timestamp}"`);
  execSync(`git switch ${branch}`);
  console.log(`Stashed "${label}", switched to ${branch}`);
  console.log(`Restore with: git stash pop  (after switching back)`);
}

function worktreeAndSwitch(branch: string, label: string): void {
  const root = execSync("git rev-parse --show-toplevel").toString().trim();
  const parent = path.dirname(root);
  const name = path.basename(root);
  const dest = path.join(parent, `${name}-${branch.replace(/\//g, "-")}`);

  // Create branch if it doesn't exist
  const branches = execSync("git branch -a").toString();
  if (!branches.includes(branch)) {
    execSync(`git worktree add -b ${branch} "${dest}" origin/main`);
  } else {
    execSync(`git worktree add "${dest}" ${branch}`);
  }

  console.log(`Worktree created at: ${dest}`);
  console.log(`cd ${dest} && wrangler dev --env staging`);
}

// CLI entry: npx tsx scripts/context-switch.ts feat/hotfix hotfix
const [, , targetBranch, reason] = process.argv;
const strategy = recommendStrategy({ targetBranch, reason });
const label = targetBranch ?? "unnamed";

if (strategy === "stash") {
  stashAndSwitch(targetBranch, label);
} else {
  worktreeAndSwitch(targetBranch, label);
}
```

## Named Stash + Restore Convention for Workers

When stash is the right choice, use named stashes with a consistent format so they can be
listed and applied by label rather than position:

```typescript
// scripts/stash-manager.ts
import { execSync } from "node:child_process";

interface StashEntry {
  index: number;
  message: string;
  sha: string;
}

function listStashes(): StashEntry[] {
  const raw = execSync("git stash list --format=%gd|||%s|||%H 2>/dev/null || true")
    .toString()
    .trim();
  if (!raw) return [];

  return raw.split("\n").map((line) => {
    const [ref, msg, sha] = line.split("|||");
    const index = parseInt(ref.replace("stash@{", "").replace("}", ""), 10);
    return { index, message: msg, sha };
  });
}

function popStashByLabel(label: string): void {
  const stashes = listStashes();
  const match = stashes.find((s) => s.message.includes(label));
  if (!match) {
    throw new Error(`No stash matching "${label}". Available:\n${stashes.map((s) => s.message).join("\n")}`);
  }
  execSync(`git stash pop stash@{${match.index}}`, { stdio: "inherit" });
}

function dropOldStashes(olderThanDays = 7): void {
  const stashes = listStashes();
  const cutoff = Date.now() - olderThanDays * 86_400_000;

  for (const stash of stashes) {
    const dateStr = execSync(
      `git log -1 --format=%ci ${stash.sha} 2>/dev/null || true`
    ).toString().trim();
    if (!dateStr) continue;
    if (new Date(dateStr).getTime() < cutoff) {
      execSync(`git stash drop stash@{${stash.index}}`);
      console.log(`Dropped stale stash [${stash.index}]: ${stash.message}`);
    }
  }
}
```

## Worktree Lifecycle for Hotfixes in a Workers Monorepo

```typescript
// scripts/worktree-hotfix.ts
import { execSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

const ROOT = execSync("git rev-parse --show-toplevel").toString().trim();
const WORKTREES_DIR = path.join(path.dirname(ROOT), ".worktrees");

function createHotfixWorktree(workerName: string, ticket: string): string {
  const branch = `hotfix/${ticket}-${workerName}`;
  const dest = path.join(WORKTREES_DIR, branch.replace(/\//g, "-"));

  fs.mkdirSync(WORKTREES_DIR, { recursive: true });
  execSync(
    `git worktree add -b ${branch} "${dest}" origin/main`,
    { stdio: "inherit" }
  );

  // Copy local .dev.vars so the hotfix worktree can run wrangler dev
  const devVars = path.join(ROOT, "workers", workerName, ".dev.vars");
  const devVarsDest = path.join(dest, "workers", workerName, ".dev.vars");
  if (fs.existsSync(devVars)) {
    fs.copyFileSync(devVars, devVarsDest);
  }

  return dest;
}

function removeHotfixWorktree(ticket: string, workerName: string): void {
  const branch = `hotfix/${ticket}-${workerName}`;
  const dest = path.join(WORKTREES_DIR, branch.replace(/\//g, "-"));
  execSync(`git worktree remove --force "${dest}"`, { stdio: "inherit" });
  execSync(`git branch -d ${branch}`, { stdio: "inherit" });
  console.log(`Cleaned up hotfix worktree for ${ticket}`);
}

// Usage: npx tsx scripts/worktree-hotfix.ts create api TICKET-4321
const [, , action, workerName, ticket] = process.argv;
if (action === "create") {
  const dest = createHotfixWorktree(workerName, ticket);
  console.log(`\nHotfix worktree ready. Next steps:\n  cd ${dest}\n  pnpm install\n  wrangler dev workers/${workerName}`);
} else if (action === "remove") {
  removeHotfixWorktree(ticket, workerName);
}
```

## Anti-patterns

- **Stashing across branch boundaries with schema changes**: if the stash touches a
  `wrangler.toml` binding that does not exist on the target branch, `git stash pop` will
  conflict on a plain text file — always restore to the original branch first.
- **Long-lived stashes**: stashes older than a week are operational debt. Prefer a
  `git worktree` with a named WIP branch; it is visible in `git worktree list` and in the
  remote branch list, which stashes are not.
- **Stashing untracked files without `-u`**: new files silently stay on disk, polluting the
  worktree you just switched to. Always use `git stash push -u` in a Workers monorepo where
  new migration files and generated types appear regularly.

## Gotchas

- `git stash pop` is a destructive operation: it drops the stash entry on success. Use
  `git stash apply` + manual `git stash drop` when you are unsure the apply will be clean.
- A branch checked out in one worktree cannot be checked out in another. Attempting to do
  so returns a hard error. Use a new branch per worktree.
- `.dev.vars` files (local secrets for `wrangler dev`) are in `.gitignore` and are not
  shared between worktrees. The setup script above handles this; ad-hoc worktrees do not.

## Verification

```bash
# Confirm stash was created with the right message
git stash list | head -5

# Confirm worktrees and their branches
git worktree list

# Confirm no dirty state leaked into the new worktree
git -C /path/to/hotfix-worktree status
```

## Related

- `git-worktree-parallel-hotfix-development.md`
- `git-worktree-lockfile-isolation.md`
- `git-stash-2026.md`
- `git-worktree-specific-configuration-boundaries.md`
- `hotfix-process.md`

## Sources

- https://git-scm.com/docs/git-stash
- https://git-scm.com/docs/git-worktree
- https://developers.cloudflare.com/workers/wrangler/configuration/#local-development-settings
